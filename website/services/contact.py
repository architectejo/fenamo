"""Formulaire de contact (S-07) : un service testable, appelé par la vue `pages.views.contact`.

Rôles :
- poser l'horodatage d'ouverture dans un jeton signé (le visiteur ne peut pas le modifier ; ni session ni compte :
  seul le cookie technique de sécurité `csrftoken` de Django est posé avec le formulaire, voir /confidentialite/) ;
- appliquer la limite par adresse IP (cache local, compteur atomique). L'adresse lue est `request.META[CONTACT_IP_HEADER]`
  (`REMOTE_ADDR` par défaut) : derrière un proxy ou un CDN, REMOTE_ADDR est l'adresse du proxy et la limite frapperait
  tous les visiteurs ensemble ; il faut alors que l'hébergeur transmette l'IP réelle dans REMOTE_ADDR, ou régler
  CONTACT_IP_HEADER (ex. HTTP_X_FORWARDED_FOR, seulement si le proxy écrase cet en-tête : sinon il est falsifiable) ;
- n'appeler l'API que par `api_client.post` (en-tête X-Site-Key), jamais en mode exemple ;
- traduire chaque réponse de l'API (201, 400, 413, 429, 503, panne) en un état d'affichage ; le formulaire est
  toujours conservé (valeurs saisies) sauf après un envoi réussi.

Aucun texte saisi n'est journalisé. Le texte brut est envoyé tel quel à l'API (c'est elle qui retire tout HTML) et
le gabarit échappe à l'affichage.
"""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from . import api_client, site_api
from .api_client import ApiErreur, ApiInactif, ApiIndisponible, ApiSuspendu

logger = logging.getLogger(__name__)

SEL_JETON = "fenamo.contact.ouverture"
VALIDITE_JETON = 23 * 3600  # l'API refuse un formulaire ouvert depuis plus de 24 h
CHAMPS = ("nom", "mail", "telephone", "objet", "message")
# Longueurs maximales du contrat (web_app/docs/api/site.md) : un envoi plus long n'atteint pas l'API
MAXIMA = {"nom": 100, "mail": 254, "telephone": 20, "objet": 100, "message": 3000}

# Valeur envoyée (français, lue par les éditeurs) et libellé affiché (traduit)
SUJETS = (
    ("Question générale", gettext_lazy("Question générale")),
    ("Adhésion d'une association membre", gettext_lazy("Adhésion d'une association membre")),
    ("Identification d'un membre ou d'un engin", gettext_lazy("Identification d'un membre ou d'un engin")),
    ("Presse et partenariats", gettext_lazy("Presse et partenariats")),
    ("Autre", gettext_lazy("Autre")),
)


@dataclass
class Etat:
    """Ce que le gabarit affiche. `cas` : formulaire | envoye | exemple | suspendu."""

    cas: str = "formulaire"
    status: int = 200
    valeurs: dict = field(default_factory=dict)
    erreurs: dict = field(default_factory=dict)  # champ -> [messages]
    globales: list = field(default_factory=list)  # messages hors champ
    alerte: str = ""  # titre d'une alerte (indisponible, limite, expiré…)
    detail: str = ""  # texte de l'alerte
    jeton: str = ""
    attente: int | None = None  # Retry-After, en secondes
    message_verrou: str = ""
    sujets: tuple = SUJETS


# ---------- Horodatage d'ouverture (ouvert_le) ----------

def jeton_ouverture() -> str:
    return signing.TimestampSigner(salt=SEL_JETON).sign(str(int(time.time())))


def lire_jeton(jeton: str) -> int | None:
    """Horodatage Unix signé à l'affichage, ou None (absent, falsifié, trop ancien)."""
    try:
        valeur = signing.TimestampSigner(salt=SEL_JETON).unsign(jeton or "", max_age=VALIDITE_JETON)
        return int(valeur)
    except (signing.BadSignature, ValueError):
        return None


def _jeton_a_conserver(jeton: str) -> str:
    """Conserve l'ouverture d'origine d'un formulaire renvoyé avec erreurs (sinon l'API verrait un envoi « trop rapide »)."""
    return jeton if lire_jeton(jeton) is not None else jeton_ouverture()


# ---------- Limite par adresse IP ----------

def _cle_ip(ip: str) -> str:
    return "contact:ip:" + hashlib.sha256(f"{ip}|{settings.SECRET_KEY}".encode()).hexdigest()[:32]


def attente_ip(ip: str) -> int | None:
    """Secondes à attendre si l'adresse a atteint la limite ; sinon None. Chaque appel compte un envoi.

    Compteur atomique : `cache.add` crée le compteur (et l'instant de début) avec la durée de la fenêtre, `cache.incr`
    l'augmente sans lecture puis écriture séparées.
    """
    cle = _cle_ip(ip)
    fenetre = settings.CONTACT_LIMITE_FENETRE
    cache.add(cle + ":debut", time.time(), fenetre)
    cache.add(cle, 0, fenetre)
    try:
        n = cache.incr(cle)
    except ValueError:  # expiré entre add et incr
        cache.set(cle, 1, fenetre)
        n = 1
    if n > settings.CONTACT_LIMITE_IP:
        debut = cache.get(cle + ":debut") or time.time()
        return max(1, int(debut + fenetre - time.time()))
    return None


# ---------- Affichage et traitement ----------

def afficher() -> Etat:
    """GET : formulaire neuf, ou page sans formulaire (mode exemple, application verrouillée)."""
    if site_api.config()["statique"]:
        return _exemple(status=200)
    if api_client.etat_service() == "suspendu":
        return _suspendu(Etat(cas="suspendu"), status=200)
    return Etat(jeton=jeton_ouverture())


def _exemple(status: int = 503) -> Etat:
    return Etat(
        cas="exemple",
        status=status,
        alerte=_("Formulaire indisponible pour le moment"),
        detail=_("Le formulaire n'est pas encore ouvert. Joignez la FENAMO-RDC par téléphone ou par e-mail, ou rendez-vous au siège national."),
    )


def _suspendu(etat: Etat, status: int = 503) -> Etat:
    etat.status = status
    etat.alerte = _("Service momentanément indisponible")
    etat.detail = _("Le service est suspendu pour le moment. Votre message n'a pas été envoyé.")
    etat.message_verrou = api_client.message_verrou()
    return etat


def _nettoyer(brut) -> dict:
    """Valeurs saisies : du texte seulement, sans espace superflu aux extrémités."""
    valeurs = {}
    for nom in CHAMPS:
        v = brut.get(nom, "")
        valeurs[nom] = v.strip() if isinstance(v, str) else ""
    return valeurs


def _erreurs_locales(valeurs: dict) -> dict:
    erreurs = {}
    for nom, maxi in MAXIMA.items():
        if len(valeurs[nom]) > maxi:
            erreurs[nom] = [_("Ce champ est trop long (%(maxi)s caractères au plus).") % {"maxi": maxi}]
    return erreurs


def traiter(brut, ip: str) -> Etat:
    """POST : renvoie l'état à afficher. `brut` est le dictionnaire POST (QueryDict)."""
    if site_api.config()["statique"]:
        return _exemple()  # mode exemple : l'API n'est jamais appelée
    valeurs = _nettoyer(brut)
    jeton = brut.get("ouverture", "")
    jeton = jeton if isinstance(jeton, str) else ""
    etat = Etat(valeurs=valeurs, jeton=_jeton_a_conserver(jeton))

    attente = attente_ip(ip)
    if attente is not None:
        etat.status = 429
        etat.attente = attente
        etat.alerte = _("Trop d'envois depuis votre connexion")
        etat.detail = _("Vous avez envoyé plusieurs messages en peu de temps. Vos saisies sont conservées : réessayez dans %(minutes)s minutes.") % {"minutes": -(-attente // 60)}
        return etat

    if brut.get("site_web"):
        # Champ piège rempli : réponse identique à un succès, rien n'est transmis (le robot ne sait pas qu'il est détecté).
        logger.info("Contact : champ piège rempli, message écarté")
        return Etat(cas="envoye")

    ouvert_le = lire_jeton(jeton)
    if ouvert_le is None:
        etat.status = 400
        etat.alerte = _("Le formulaire est resté ouvert trop longtemps")
        etat.detail = _("Vos saisies sont conservées. Patientez un instant puis envoyez de nouveau le message.")
        return etat

    etat.erreurs = _erreurs_locales(valeurs)
    if etat.erreurs:
        etat.status = 400
        return etat

    donnees = {**valeurs, "ouvert_le": ouvert_le, "site_web": ""}
    try:
        reponse = api_client.post("contact/", donnees)
    except ApiInactif:
        site_api.signaler_inactif()
        return _exemple()
    except ApiSuspendu:
        return _suspendu(etat)
    except ApiIndisponible:
        return _indisponible(etat)
    except ApiErreur as exc:
        return _erreur_api(etat, exc)

    if isinstance(reponse, dict) and reponse.get("statut") == "recu":
        return Etat(cas="envoye")
    logger.warning("Contact : réponse inattendue de l'API")
    return _indisponible(etat)


def _indisponible(etat: Etat) -> Etat:
    etat.status = 503
    etat.alerte = _("Service momentanément indisponible")
    etat.detail = _("Votre message n'a pas été envoyé. Vos saisies sont conservées : réessayez dans quelques minutes, ou écrivez-nous par e-mail.")
    return etat


def _messages(valeur) -> list[str]:
    liste = valeur if isinstance(valeur, list) else [valeur]
    return [m.strip()[:300] for m in liste if isinstance(m, str) and m.strip()]


def _erreur_api(etat: Etat, exc: ApiErreur) -> Etat:
    if exc.status == 400:
        etat.status = 400
        for nom, valeur in exc.champs.items():
            textes = _messages(valeur)
            if not textes:
                continue
            if nom in CHAMPS:
                etat.erreurs[nom] = textes
            else:  # non_field_errors, ouvert_le, champ inconnu : message hors champ
                etat.globales += textes
        if not etat.erreurs and not etat.globales:
            etat.globales = [_("Le message n'a pas pu être validé. Vérifiez les champs et réessayez.")]
        return etat
    if exc.status == 413:
        etat.status = 413
        etat.alerte = _("Message trop volumineux")
        etat.detail = _("Raccourcissez votre message puis envoyez-le de nouveau.")
        return etat
    if exc.status == 429:
        etat.status = 429
        etat.attente = exc.retry_after
        etat.alerte = _("Trop de messages envoyés")
        if exc.retry_after:
            etat.detail = _("Réessayez dans %(minutes)s minutes. Vos saisies sont conservées.") % {"minutes": -(-exc.retry_after // 60)}
        else:
            etat.detail = _("Réessayez un peu plus tard. Vos saisies sont conservées.")
        return etat
    logger.warning("Contact : refus inattendu de l'API (%s)", exc.status)  # 401 (clé), 405…
    return _indisponible(etat)
