"""Clés du site public : création, vérification, révocation. La clé complète n'est jamais stockée ni journalisée.

Format : ``fsk_<prefixe>_<jeton>`` (préfixe = 8 caractères hexadécimaux, jeton = ``secrets.token_urlsafe(32)``)."""
import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from api.models import CleSite

logger = logging.getLogger('api.cles')
CLES_ACTIVES_MAX = 2  # une clé en service + une clé de rotation
INTERVALLE_UTILISATION = timedelta(hours=1)
_EMPREINTE_FACTICE = hashlib.sha256(b'cle-inexistante').hexdigest()


class CleSiteErreur(ValueError):
    """Création ou révocation impossible (message en français)."""


def empreinte(cle):
    return hashlib.sha256(cle.encode('utf-8')).hexdigest()


def extraire_prefixe(cle):
    """Préfixe d'une clé au bon format, sinon None."""
    morceaux = (cle or '').split('_', 2)
    if len(morceaux) == 3 and morceaux[0] == 'fsk' and len(morceaux[1]) == 8 and morceaux[2]:
        return morceaux[1]
    return None


@transaction.atomic
def creer_cle(nom):
    """(CleSite, clé en clair). Refuse une troisième clé active : révoquer d'abord l'ancienne après la bascule du site."""
    nom = (nom or '').strip()
    if not nom:
        raise CleSiteErreur("Le nom de la clé est obligatoire.")
    if CleSite.objects.select_for_update().filter(active=True).count() >= CLES_ACTIVES_MAX:
        raise CleSiteErreur(f"{CLES_ACTIVES_MAX} clés sont déjà actives : révoquez l'ancienne (revoquer_cle_site) avant d'en créer une.")
    while True:
        prefixe = secrets.token_hex(4)
        if not CleSite.objects.filter(prefixe=prefixe).exists():
            break
    cle = f'fsk_{prefixe}_{secrets.token_urlsafe(32)}'
    objet = CleSite.objects.create(nom=nom[:100], prefixe=prefixe, empreinte=empreinte(cle))
    logger.info("Clé du site créée : %s (préfixe %s).", objet.nom, prefixe)
    return objet, cle


@transaction.atomic
def revoquer_cle(prefixe):
    objet = CleSite.objects.select_for_update().filter(prefixe=prefixe).first()
    if objet is None:
        raise CleSiteErreur(f"Aucune clé avec le préfixe « {prefixe} ».")
    if objet.active:
        objet.active = False
        objet.revoquee_le = timezone.now()
        objet.save(update_fields=['active', 'revoquee_le'])
        logger.info("Clé du site révoquée : %s (préfixe %s).", objet.nom, prefixe)
    return objet


def verifier(cle):
    """Identité de l'appelant : ``('cle', CleSite)``, ``('dev', None)`` (repli DEBUG avec SITE_API_KEY) ou None si la clé est refusée."""
    cle = cle or ''
    prefixe = extraire_prefixe(cle)
    objet = CleSite.objects.filter(prefixe=prefixe, active=True).first() if prefixe else None
    attendue = objet.empreinte if objet else _EMPREINTE_FACTICE  # même travail que la clé existe ou non
    correspond = hmac.compare_digest(empreinte(cle), attendue)
    if objet and correspond:
        _noter_utilisation(objet)
        return 'cle', objet
    reglee = getattr(settings, 'SITE_API_KEY', '')
    if settings.DEBUG and reglee and hmac.compare_digest(cle.encode('utf-8'), reglee.encode('utf-8')):
        return 'dev', None
    return None


def _noter_utilisation(objet):
    """Écrit la dernière utilisation au plus une fois par heure (pas d'écriture à chaque requête)."""
    limite = timezone.now() - INTERVALLE_UTILISATION
    if objet.derniere_utilisation is None or objet.derniere_utilisation < limite:
        CleSite.objects.filter(pk=objet.pk).filter(
            Q(derniere_utilisation__isnull=True) | Q(derniere_utilisation__lt=limite)).update(derniere_utilisation=timezone.now())
