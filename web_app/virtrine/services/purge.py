"""Purge du cache du site public après une publication (F-60 à F-63, cahier § 2.4).

``demander_purge()`` planifie l'appel APRÈS la validation de la transaction (``transaction.on_commit`` : jamais de purge pour une
modification annulée). L'appel est un POST sans corps vers ``SITE_PURGE_URL``, signé par HMAC-SHA256 de l'horodatage avec
``SITE_PURGE_SECRET`` (en-têtes ``X-Purge-Horodatage`` et ``X-Purge-Signature``), délai de 3 secondes. Un échec est journalisé (logger
``virtrine.purge``) et ne bloque jamais l'éditeur. Pas de purge sans réglage, ni pendant le verrouillage de l'application (F-07)."""
import hashlib
import hmac
import logging
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction

logger = logging.getLogger('virtrine.purge')
DELAI_SECONDES = 3


def signer(horodatage, secret):
    """Signature hexadécimale HMAC-SHA256 de l'horodatage (texte) avec le secret partagé."""
    return hmac.new(secret.encode('utf-8'), str(horodatage).encode('utf-8'), hashlib.sha256).hexdigest()


def demander_purge():
    """Planifie la purge du cache du site après le commit de la transaction en cours (immédiatement hors transaction)."""
    transaction.on_commit(envoyer_purge)


def envoyer_purge():
    """Envoie la demande de purge ; retourne True si le site a répondu 2xx, False sinon (rien n'est jamais levé)."""
    adresse = getattr(settings, 'SITE_PURGE_URL', '')
    secret = getattr(settings, 'SITE_PURGE_SECRET', '')
    if not adresse or not secret:
        logger.debug("Purge du site non configurée (SITE_PURGE_URL / SITE_PURGE_SECRET) : ignorée.")
        return False
    from compte.services.verrou_application import est_verrouillee
    if est_verrouillee():
        logger.info("Application verrouillée : purge du site non envoyée.")
        return False
    if urlsplit(adresse).scheme not in ('http', 'https'):
        logger.warning("SITE_PURGE_URL doit être une adresse http ou https : purge ignorée.")
        return False
    horodatage = str(int(time.time()))
    requete = urllib.request.Request(adresse, data=b'', method='POST', headers={
        'X-Purge-Horodatage': horodatage, 'X-Purge-Signature': signer(horodatage, secret)})
    try:
        with urllib.request.urlopen(requete, timeout=DELAI_SECONDES) as reponse:  # noqa: S310 (schéma contrôlé ci-dessus)
            return 200 <= reponse.status < 300
    except (urllib.error.URLError, OSError, ValueError) as erreur:
        logger.warning("Purge du site échouée (%s) : le contenu apparaîtra à l'expiration du cache.", erreur)
        return False
