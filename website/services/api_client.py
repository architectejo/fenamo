"""Unique point d'appel à l'API de l'application web (/api/v1/site/).

Aucun autre module du site ne doit importer `requests` ni appeler l'API.
Ce module gère : la clé du site, le délai maximal (5 s), le cache par point
d'accès, la copie de secours du mode dégradé (S-12) et les erreurs.

Interface posée au lot 1 : les fonctions par page (articles, comité, etc.)
et la vérification s'ajouteront par-dessus `get` et `post` aux lots suivants.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

_FRESH = "api:fresh:"
_STALE = "api:stale:"
_VERSION = "api:version"


def _version() -> int:
    """Numéro de version des copies fraîches ; purger_cache() l'incrémente."""
    return cache.get(_VERSION, 0)


class ApiIndisponible(Exception):
    """L'API ne répond pas (réseau, délai dépassé, erreur serveur) et aucune copie en cache."""


class ApiErreur(Exception):
    """L'API a répondu par une erreur applicative (4xx) ; `champs` porte les erreurs de validation."""

    def __init__(self, status: int, champs: dict | None = None, detail: str = ""):
        super().__init__(detail or f"Erreur API {status}")
        self.status = status
        self.champs = champs or {}


class Reponse:
    """Résultat d'une lecture : `donnees`, et `degrade=True` si c'est une copie périmée (S-12)."""

    def __init__(self, donnees: Any, degrade: bool = False):
        self.donnees = donnees
        self.degrade = degrade


def _url(chemin: str) -> str:
    return settings.API_BASE_URL.rstrip("/") + "/" + chemin.lstrip("/")


def _headers() -> dict:
    return {"X-Site-Key": settings.SITE_API_KEY, "Accept": "application/json"}


def _cle(chemin: str, params: dict | None, langue: str | None) -> str:
    items = sorted((params or {}).items())
    return f"{chemin}|{items}|{langue or ''}"


def _cle_fraiche(cle: str, version: int) -> str:
    return f"{_FRESH}v{version}:{cle}"


def _requete(methode: str, chemin: str, **kw) -> requests.Response:
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
        raise ApiIndisponible(str(exc)) from exc
    if 300 <= rep.status_code < 400:
        # Redirections refusées : l'adresse de l'API est mal configurée.
        logger.warning("API : redirection %s refusée (%s %s)", rep.status_code, methode, chemin)
        raise ApiIndisponible(f"Redirection HTTP {rep.status_code}")
    if rep.status_code >= 500:
        logger.warning("API en erreur %s (%s %s)", rep.status_code, methode, chemin)
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

    Avec cache : copie fraîche si présente ; sinon appel ; si l'appel échoue,
    dernière copie connue (`degrade=True`) ; sinon ApiIndisponible.
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
        donnees = _requete("GET", chemin, params=params_url).json()
    except (ApiIndisponible, ValueError) as exc:
        if duree:
            ancien = cache.get(_STALE + cle)
            if ancien is not None:
                return Reponse(ancien, degrade=True)
        if isinstance(exc, ApiIndisponible):
            raise
        raise ApiIndisponible("Réponse illisible") from exc
    if duree:
        cache.set(_cle_fraiche(cle, version), donnees, duree)
        cache.set(_STALE + cle, donnees, settings.CACHE_STALE_TTL)
    return Reponse(donnees)


def post(chemin: str, donnees: dict | None = None, fichiers: dict | None = None) -> Any:
    """Dépôt (contact, adhésion, paiement) : jamais de cache, jamais de repli."""
    rep = _requete("POST", chemin, data=donnees or {}, files=fichiers)
    try:
        return rep.json()
    except ValueError as exc:
        raise ApiIndisponible("Réponse illisible") from exc


def purger_cache() -> None:
    """Invalide les copies fraîches (adresse de purge sécurisée, lot ultérieur).

    Les copies de secours (_STALE) et les compteurs ne sont pas touchés : le
    mode dégradé (S-12) reste disponible si l'API tombe juste après la purge.
    """
    # Horodatage (jamais d'expiration) : cache.incr() réappliquerait un délai par défaut.
    cache.set(_VERSION, max(time.time_ns(), _version() + 1), None)
