"""Réglages de développement local (SQLite, DEBUG actif)."""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = env.bool('DEBUG', default=True)

# Valeur de développement uniquement : ne sert jamais en production (prod.py exige SECRET_KEY).
SECRET_KEY = env('SECRET_KEY', default='dev-uniquement-ne-pas-utiliser-en-production')

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1', '[::1]'])

# Courriels affichés dans la console.
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
