"""Réglages de production (cPanel mutualisé, Passenger, MySQL).

Variables obligatoires dans `.env` : SECRET_KEY, ALLOWED_HOSTS, DATABASE_URL.
Facultatives mais attendues : EMAIL_* (envoi des courriels), STATIC_ROOT, MEDIA_ROOT.
"""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import MIDDLEWARE, env

DEBUG = False

SECRET_KEY = env('SECRET_KEY')
if len(SECRET_KEY) < 50 or SECRET_KEY.lower().startswith(('changer', 'dev', 'django-insecure')):
    raise ImproperlyConfigured(
        "SECRET_KEY de production invalide : au moins 50 caractères et jamais une valeur "
        "d'exemple (changer…, dev…, django-insecure…). Voir .env.example pour la générer."
    )
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS')

# Droits hérités (privilege1 à privilege5) : COUPÉS par défaut en production (un compte sans nomination ne voit que sa propre fiche).
# Les réactiver est une décision explicite de transition (FENAMO_DROITS_HERITES=True dans .env) ; `check --deploy` avertit alors.
FENAMO_DROITS_HERITES = env.bool('FENAMO_DROITS_HERITES', default=False)

# WhiteNoise sert les fichiers statiques depuis Passenger, juste après SecurityMiddleware.
MIDDLEWARE = [
    MIDDLEWARE[0],
    'whitenoise.middleware.WhiteNoiseMiddleware',
    *MIDDLEWARE[1:],
]

STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    # Compression sans manifeste : un fichier statique absent ne bloque pas l'affichage d'une page.
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}

# HTTPS obligatoire
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int('SECURE_HSTS_SECONDS', default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'

# Courriels (SMTP du compte cPanel), lus dans .env
EMAIL_HOST = env('EMAIL_HOST', default='localhost')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_USE_SSL = env.bool('EMAIL_USE_SSL', default=False)
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='FENAMO-RDC <noreply@fenamordc.cd>')
SERVER_EMAIL = env('SERVER_EMAIL', default=DEFAULT_FROM_EMAIL)

# Pas de HSTS « preload » : engagement difficile à annuler, à décider explicitement par la FENAMO-RDC.
SILENCED_SYSTEM_CHECKS = ['security.W021']
