"""Réglages communs à tous les environnements (FENAMO-RDC, application web).

Les valeurs sensibles ou propres à un environnement viennent du fichier `.env`
(voir `.env.example`) ou de variables d'environnement, lues avec django-environ.
Les réglages `dev.py` et `prod.py` complètent ce module.
"""

from datetime import timedelta
from pathlib import Path

import environ

# web_app/ : fenamo/settings/base.py -> fenamo/settings -> fenamo -> web_app
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / '.env')

# SECRET_KEY est définie dans dev.py (valeur de développement) et prod.py (obligatoire).

DEBUG = env.bool('DEBUG', default=False)

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])


# Applications

INSTALLED_APPS = [
    'fenamo.apps.FenamoAdminConfig',  # remplace django.contrib.admin : accès réservé aux SU
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_htmx',
    'axes',
    'mobapp',
    'compte',
    'coptapp',
    'virtrine',
    'api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
    'fenamo.htmx.HtmxSessionMessagesMiddleware',
    # Après HtmxSessionMessagesMiddleware : sa redirection vers /connexion/ devient un HX-Redirect en HTMX.
    # Toute vue exige la connexion, sauf celles marquées @login_not_required (connexion, santé, /mob/, /ancien-site/).
    'django.contrib.auth.middleware.LoginRequiredMiddleware',
    'compte.middleware.ChangementMotDePasseMiddleware',
    'fenamo.csp.CspReportOnlyMiddleware',
    'axes.middleware.AxesMiddleware',  # en dernier (documentation django-axes)
]

# Messages en session (jamais dans un cookie : un message peut contenir une information sensible).
MESSAGE_STORAGE = 'django.contrib.messages.storage.session.SessionStorage'

ROOT_URLCONF = 'fenamo.urls'
WSGI_APPLICATION = 'fenamo.wsgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'fenamo.contexte.textes_interface',
                'fenamo.contexte.coque',
            ],
            'libraries': {'design': 'fenamo.balises'},
        },
    },
]


# Base de données : SQLite en développement, MySQL en production.
# Exemple MySQL : DATABASE_URL=mysql://utilisateur:motdepasse@127.0.0.1:3306/base

DATABASES = {
    'default': env.db('DATABASE_URL', default=f'sqlite:///{BASE_DIR / "db.sqlite3"}'),
}
if DATABASES['default']['ENGINE'] == 'django.db.backends.mysql':
    DATABASES['default'].setdefault('OPTIONS', {})['charset'] = 'utf8mb4'


# Mots de passe

# Verrou anti force brute (django-axes) : 5 échecs consécutifs sur le couple nom d'utilisateur + adresse IP.
AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]
AXES_FAILURE_LIMIT = env.int('AXES_FAILURE_LIMIT', default=5)
AXES_LOCKOUT_PARAMETERS = [['username', 'ip_address']]
# Nom normalisé (strip + minuscules) : « Admin » et « admin  » comptent pour le même verrou.
AXES_USERNAME_CALLABLE = 'compte.services.verrou.nom_utilisateur_normalise'
# Journal des échecs, base du seuil par adresse IP seule (compte/services/verrou.py).
AXES_ENABLE_ACCESS_FAILURE_LOG = True
# Verrou par adresse IP seule (rotation de pseudos) : seuil plus haut, car plusieurs agents peuvent partager
# une même adresse (cybercafé, antenne de téléphonie).
IP_ECHECS_MAX = env.int('IP_ECHECS_MAX', default=30)
AXES_COOLOFF_TIME = timedelta(minutes=env.int('AXES_COOLOFF_MINUTES', default=30))
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = 'compte/verrou.html'

# Sessions : expiration après inactivité (secondes), prolongée à chaque requête.
SESSION_COOKIE_AGE = env.int('SESSION_COOKIE_AGE', default=1800)
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# Politique de sécurité du contenu, en mode rapport seulement (aucun blocage) le temps de la mettre au point.
# Alpine.js (version standard) exige 'unsafe-eval' ; les styles en ligne sont encore présents dans les gabarits hérités.
CSP_REPORT_ONLY_POLICY = env('CSP_REPORT_ONLY_POLICY', default=(
    "default-src 'self'; script-src 'self' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
    "base-uri 'self'; form-action 'self'"
))

AUTH_USER_MODEL = 'compte.Compte'
LOGIN_URL = 'application'
LOGIN_REDIRECT_URL = 'tableau-bord'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# Internationalisation

LANGUAGE_CODE = 'fr'
TIME_ZONE = 'Africa/Kinshasa'
USE_I18N = True
USE_TZ = True


# Fichiers statiques et médias (bibliothèques front servies en local, sans CDN)

STATIC_URL = 'static/'
# STATIC_ROOT et MEDIA_ROOT : chemins absolus lus dans .env (§ 7.2) ; en production, mettre les médias
# hors du dossier de l'application pour qu'un déploiement ne les écrase pas.
STATIC_ROOT = Path(env('STATIC_ROOT', default='') or BASE_DIR / 'staticfiles')
STATICFILES_DIRS = [d for d in (BASE_DIR / 'static',) if d.is_dir()]

MEDIA_URL = '/media/'
MEDIA_ROOT = Path(env('MEDIA_ROOT', default='') or BASE_DIR / 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Liaison avec le site public (website/) : clé d'accès à l'API et purge du cache.
# Laisser vide tant que le site n'est pas branché.

SITE_API_KEY = env('SITE_API_KEY', default='')
SITE_PURGE_URL = env('SITE_PURGE_URL', default='')
SITE_PURGE_SECRET = env('SITE_PURGE_SECRET', default='')


# Journalisation : sortie standard (récupérée par Passenger dans les journaux cPanel)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {'format': '{asctime} {levelname} {name} {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'simple'},
    },
    'root': {'handlers': ['console'], 'level': env('LOG_LEVEL', default='INFO')},
}
