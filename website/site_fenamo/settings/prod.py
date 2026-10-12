"""Réglages de production (cPanel mutualisé, Passenger).

Variables obligatoires dans `.env` : SECRET_KEY (50 caractères au moins),
ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, API_BASE_URL (https), SITE_API_KEY.
Fichiers statiques : servis par WhiteNoise (comme web_app), après
`python manage.py collectstatic --noinput`.
"""
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import API_BASE_URL, MIDDLEWARE, SECRET_KEY, env

DEBUG = False

# Obligatoires : aucune valeur par défaut en production (ImproperlyConfigured si absentes).
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS")

if len(SECRET_KEY) < 50 or SECRET_KEY.lower().startswith(("changer", "dev", "django-insecure")):
    raise ImproperlyConfigured(
        "SECRET_KEY invalide : au moins 50 caractères, ne commençant pas par changer/dev/django-insecure."
    )
if not API_BASE_URL.startswith("https://"):
    raise ImproperlyConfigured("API_BASE_URL doit commencer par https:// en production.")

# WhiteNoise sert les fichiers statiques depuis Passenger, juste après SecurityMiddleware.
MIDDLEWARE = [
    MIDDLEWARE[0],
    "whitenoise.middleware.WhiteNoiseMiddleware",
    *MIDDLEWARE[1:],
]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Compression sans manifeste : un fichier statique absent ne bloque pas une page.
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_REFERRER_POLICY = "same-origin"
