"""Limite de débit par clé : fenêtre fixe d'une minute dans le cache ``limites`` (DatabaseCache, partagé entre les processus)."""
import logging
import time

from django.conf import settings
from django.core.cache import caches
from django.db import DatabaseError

logger = logging.getLogger('api.limites')
FENETRE = 60


def limite_pour(methode):
    return settings.SITE_API_LIMITE_GET if methode == 'GET' else settings.SITE_API_LIMITE_POST


def controler(identite, methode):
    """None si la requête passe ; sinon le nombre de secondes à attendre (en-tête Retry-After)."""
    seau = 'GET' if methode == 'GET' else 'POST'
    maintenant = time.time()
    fenetre = int(maintenant // FENETRE)
    cle = f'site-api:{identite}:{seau}:{fenetre}'
    cache = caches['limites']
    try:
        cache.add(cle, 0, FENETRE + 5)
        compte = cache.incr(cle)
    except (DatabaseError, ValueError) as erreur:
        logger.error("Limite de débit indisponible (%s) : requête acceptée. La table cache_limites existe-t-elle (createcachetable) ?", erreur)
        return None
    if compte > limite_pour(methode):
        return max(1, int(FENETRE - maintenant % FENETRE) + 1)
    return None
