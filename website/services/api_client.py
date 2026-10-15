"""Unique point d'appel à l'API de l'application web (/api/v1/site/).

Aucun autre module du site ne doit importer `requests` ni appeler l'API.
Ce module gère : la clé du site, le délai maximal (5 s), le cache par point
d'accès, la copie de secours du mode dégradé (S-12) et les erreurs.

Les fonctions par point d'accès (config, articles, comité…) sont dans
`services/site_api.py`, au-dessus de `get` ; la vérification et les dépôts
(lot 3) passeront par `get` sans cache et `post`.

Verrou F-07 : un 503 dont le corps JSON porte `statut == "suspendu"` n'est pas
une panne. Il lève `ApiSuspendu`, n'est pas journalisé comme une erreur, ne
renouvelle aucune copie de secours, et l'état est retenu quelques minutes :
pendant ce temps, les appels ne partent plus (une seule sonde de
`/api/v1/sante/` par intervalle, pour détecter la fin du verrou).
"""
from __future__ import annotations

import contextvars
import hashlib
import logging
import time
from typing import Any
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

_FRESH = "api:fresh:"
_STALE = "api:stale:"
_VERSION = "api:version"
_ETAT = "api:etat"  # verrou F-07 connu : {"message", "sonde"}
_DUREE_ETAT = 10 * 60  # le message du super-utilisateur est ré-appris au plus tard après ce délai
_PANNE = "api:panne"  # panne constatée : les lectures suivantes n'attendent pas 5 s de plus chacune
_DUREE_PANNE = 15

# Suivi de la requête en cours (rempli par le middleware, lu par le contexte des gabarits)
_suivi: contextvars.ContextVar = contextvars.ContextVar("api_suivi", default=None)


def demarrer_suivi() -> None:
    """Appelé au début de chaque requête HTTP : réinitialise ce que la page doit signaler."""
    _suivi.set({"degrade": False, "copie_le": None, "suspendu": False, "panne": False})


def suivi() -> dict:
    """État de la requête : contenu venant d'une copie (degrade, copie_le), verrou (suspendu), panne sans copie."""
    return _suivi.get() or {"degrade": False, "copie_le": None, "suspendu": False, "panne": False}


def _noter(**infos) -> None:
    etat = _suivi.get()
    if etat is None:
        return
    if infos.get("copie_le"):
        ancienne = etat["copie_le"]
        etat["copie_le"] = infos["copie_le"] if ancienne is None else min(ancienne, infos["copie_le"])
    for cle in ("degrade", "suspendu", "panne"):
        if infos.get(cle):
            etat[cle] = True


def _version() -> int:
    """Numéro de version des copies fraîches ; purger_cache() l'incrémente."""
    return cache.get(_VERSION, 0)


class ApiIndisponible(Exception):
    """L'API ne répond pas (réseau, délai dépassé, erreur serveur) et aucune copie en cache."""


class ApiSuspendu(Exception):
    """L'application web est verrouillée (F-07) ; `message` est le texte du super-utilisateur (brut, à échapper)."""

    def __init__(self, message: str = ""):
        super().__init__("Application suspendue (F-07)")
        self.message = message


class ApiErreur(Exception):
    """L'API a répondu par une erreur applicative (4xx) ; `champs` porte les erreurs de validation."""

    def __init__(self, status: int, champs: dict | None = None, detail: str = ""):
        super().__init__(detail or f"Erreur API {status}")
        self.status = status
        self.champs = champs or {}


class Reponse:
    """Résultat d'une lecture : `donnees`, et `degrade=True` si c'est une copie périmée (S-12).

    `copie_le` : instant (secondes Unix) où la copie servie avait été lue ; `suspendu` : la copie est servie
    parce que l'application est verrouillée (et non en panne).
    """

    def __init__(self, donnees: Any, degrade: bool = False, copie_le: float | None = None, suspendu: bool = False):
        self.donnees = donnees
        self.degrade = degrade
        self.copie_le = copie_le
        self.suspendu = suspendu


def _url(chemin: str) -> str:
    return settings.API_BASE_URL.rstrip("/") + "/" + chemin.lstrip("/")


def url_sante() -> str:
    """Adresse de la sonde : API_SANTE_URL, sinon `sante/` voisin de `site/` dans API_BASE_URL."""
    if getattr(settings, "API_SANTE_URL", ""):
        return settings.API_SANTE_URL
    base = settings.API_BASE_URL.rstrip("/") + "/"
    return urljoin(base, "../sante/")


def _headers() -> dict:
    return {"X-Site-Key": settings.SITE_API_KEY, "Accept": "application/json"}


def _lire_sante() -> str:
    """'ok', 'suspendu' ou 'panne' d'après /api/v1/sante/ (200 même verrouillée, voir erreurs.md)."""
    try:
        rep = requests.get(
            url_sante(), headers={"Accept": "application/json"}, timeout=settings.API_TIMEOUT, allow_redirects=False
        )
        corps = rep.json() if rep.status_code == 200 else {}
    except (requests.RequestException, ValueError) as exc:
        logger.info("Sonde de santé sans réponse : %s", exc)
        return "panne"
    statut = corps.get("statut") if isinstance(corps, dict) else None
    return statut if statut in ("ok", "suspendu") else "panne"


def _marquer_suspendu(message: str) -> None:
    cache.set(_ETAT, {"message": message, "sonde": time.time()}, _DUREE_ETAT)


def verrou_connu() -> dict | None:
    """Verrou F-07 retenu, sinon None. Au plus une sonde de santé par API_SANTE_INTERVALLE ; fin du verrou : état effacé."""
    etat = cache.get(_ETAT)
    if not etat:
        return None
    if time.time() - etat["sonde"] >= settings.API_SANTE_INTERVALLE:
        etat["sonde"] = time.time()  # posé avant l'appel : les requêtes suivantes ne sondent pas en même temps
        cache.set(_ETAT, etat, _DUREE_ETAT)
        if _lire_sante() == "ok":
            cache.delete(_ETAT)
            return None
    return etat


def etat_service() -> str:
    """'suspendu' si le verrou F-07 est connu, sinon 'ok' (une panne ne se retient pas : chaque appel retente)."""
    return "suspendu" if verrou_connu() else "ok"


def message_verrou() -> str:
    etat = cache.get(_ETAT)
    return etat["message"] if etat else ""


def _cle(chemin: str, params: dict | None, langue: str | None) -> str:
    """Clé de cache stable et sans caractère interdit (la requête de recherche est libre) : empreinte courte."""
    items = sorted((params or {}).items())
    return hashlib.sha1(f"{chemin}|{items}|{langue or ''}".encode("utf-8")).hexdigest()


def _cle_fraiche(cle: str, version: int) -> str:
    return f"{_FRESH}v{version}:{cle}"


def _requete(methode: str, chemin: str, lecture: bool = False, **kw) -> requests.Response:
    etat = verrou_connu()
    if etat:
        # Verrou connu : aucun appel de données, seulement la sonde de santé à intervalle limité.
        _noter(suspendu=True)
        raise ApiSuspendu(etat["message"])
    if lecture and cache.get(_PANNE):
        raise ApiIndisponible("Panne constatée il y a moins de quelques secondes")
    try:
        rep = requests.request(
            methode,
            _url(chemin),
            headers=_headers(),
            timeout=settings.API_TIMEOUT,
            allow_redirects=False,
            **kw,
        )
    except requests.RequestException as exc:
        logger.warning("API injoignable (%s %s) : %s", methode, chemin, exc)
        cache.set(_PANNE, 1, _DUREE_PANNE)
        raise ApiIndisponible(str(exc)) from exc
    if 300 <= rep.status_code < 400:
        # Redirections refusées : l'adresse de l'API est mal configurée.
        logger.warning("API : redirection %s refusée (%s %s)", rep.status_code, methode, chemin)
        raise ApiIndisponible(f"Redirection HTTP {rep.status_code}")
    if rep.status_code == 503:
        try:
            corps = rep.json()
        except ValueError:
            corps = None
        if isinstance(corps, dict) and corps.get("statut") == "suspendu":
            message = corps.get("message")
            message = message if isinstance(message, str) else ""
            logger.info("API verrouillée (F-07) : %s %s", methode, chemin)  # un verrou n'est pas une erreur
            _marquer_suspendu(message)
            _noter(suspendu=True)
            raise ApiSuspendu(message)
    if rep.status_code >= 500:
        logger.warning("API en erreur %s (%s %s)", rep.status_code, methode, chemin)
        cache.set(_PANNE, 1, _DUREE_PANNE)
        raise ApiIndisponible(f"HTTP {rep.status_code}")
    if lecture and rep.status_code in (401, 403, 429):
        # Clé refusée ou limite de débit : pour une lecture, c'est une indisponibilité (copie de secours, pas de page cassée).
        logger.warning("API : lecture refusée %s (%s %s)", rep.status_code, methode, chemin)
        raise ApiIndisponible(f"HTTP {rep.status_code}")
    if rep.status_code >= 400:
        try:
            corps = rep.json()
        except ValueError:
            corps = {}
        raise ApiErreur(rep.status_code, corps if isinstance(corps, dict) else {})
    return rep


def get(
    chemin: str,
    params: dict | None = None,
    ttl: str | int | None = None,
    langue: str | None = None,
) -> Reponse:
    """Lecture. `ttl` : clé de settings.CACHE_TTL, ou secondes ; None = aucun cache.

    Avec cache : copie fraîche si présente ; sinon appel ; si l'appel échoue (panne ou verrou F-07),
    dernière copie connue (`degrade=True`), servie sans être renouvelée ; sinon ApiIndisponible ou ApiSuspendu.
    """
    duree = settings.CACHE_TTL[ttl] if isinstance(ttl, str) else ttl
    cle = _cle(chemin, params, langue)
    version = _version()
    if duree:
        frais = cache.get(_cle_fraiche(cle, version))
        if frais is not None:
            return Reponse(frais)
    try:
        params_url = dict(params or {})
        if langue:
            params_url["lang"] = langue
        donnees = _requete("GET", chemin, lecture=True, params=params_url).json()
    except (ApiIndisponible, ApiSuspendu, ValueError) as exc:
        if duree:
            ancien = cache.get(_STALE + cle)
            if ancien is not None:
                suspendu = isinstance(exc, ApiSuspendu)
                _noter(degrade=True, copie_le=ancien["t"], suspendu=suspendu)
                return Reponse(ancien["d"], degrade=True, copie_le=ancien["t"], suspendu=suspendu)
        if isinstance(exc, ApiSuspendu):
            raise
        _noter(panne=True)
        if isinstance(exc, ApiIndisponible):
            raise
        raise ApiIndisponible("Réponse illisible") from exc
    if duree:
        cache.set(_cle_fraiche(cle, version), donnees, duree)
        cache.set(_STALE + cle, {"d": donnees, "t": time.time()}, settings.CACHE_STALE_TTL)
    return Reponse(donnees)


def post(chemin: str, donnees: dict | None = None, fichiers: dict | None = None) -> Any:
    """Dépôt (contact, adhésion, paiement) : jamais de cache, jamais de repli."""
    rep = _requete("POST", chemin, data=donnees or {}, files=fichiers)
    try:
        return rep.json()
    except ValueError as exc:
        raise ApiIndisponible("Réponse illisible") from exc


def purger_cache() -> None:
    """Invalide les copies fraîches (adresse de purge sécurisée : `pages.views.purge`).

    Les copies de secours (_STALE) et les compteurs ne sont pas touchés : le
    mode dégradé (S-12) reste disponible si l'API tombe juste après la purge.
    """
    # Horodatage (jamais d'expiration) : cache.incr() réappliquerait un délai par défaut.
    cache.set(_VERSION, max(time.time_ns(), _version() + 1), None)
    cache.delete(_PANNE)
