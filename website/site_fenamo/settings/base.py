"""Configuration commune. Les valeurs sensibles viennent du .env (django-environ)."""
from pathlib import Path

import environ
from django.conf.locale import LANG_INFO
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
SITE_URL = env("SITE_URL", default="http://localhost:8001").rstrip("/")
SITE_NOINDEX = env.bool("SITE_NOINDEX", default=False)
# Espace des utilisateurs (application web de gestion) : lien du pied de page et du menu
APP_URL = env("APP_URL", default="https://app.fenamordc.cd/")

INSTALLED_APPS = [
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "pages",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "pages.middleware.SuiviApiMiddleware",
    "pages.middleware.LangueInactiveMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "site_fenamo.urls"
# Les anciennes adresses (annexe B) et /_purge/ sont hors préfixe de langue : pas de redirection automatique
APPEND_SLASH = True
WSGI_APPLICATION = "site_fenamo.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "pages.context_processors.site",
            ],
        },
    }
]

# --- Base locale : sessions et compteurs seulement, aucune donnée métier ---
# var/ n'est pas versionné : on le crée au démarrage (dépôt neuf, déploiement).
VAR_DIR = BASE_DIR / "var"
(VAR_DIR / "cache").mkdir(parents=True, exist_ok=True)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": VAR_DIR / "site.sqlite3",
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SESSION_ENGINE = "django.contrib.sessions.backends.db"

# --- Cache Django sur fichiers (pas de Redis sur mutualisé) ---
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": str(VAR_DIR / "cache"),
    }
}

# --- API de l'application web (§ 6) ---
API_BASE_URL = env("API_BASE_URL", default="http://localhost:8000/api/v1/site/")
SITE_API_KEY = env("SITE_API_KEY", default="")
API_TIMEOUT = env.float("API_TIMEOUT", default=5)
# Sonde du verrou F-07 : vide = dérivée de API_BASE_URL (…/api/v1/site/ -> …/api/v1/sante/)
API_SANTE_URL = env("API_SANTE_URL", default="")
API_SANTE_INTERVALLE = env.int("API_SANTE_INTERVALLE", default=30)  # secondes entre deux sondes
PURGE_SECRET = env("PURGE_SECRET", default="")
PURGE_TOLERANCE = 300  # secondes d'écart admis entre l'horodatage signé et l'heure du site
PURGE_LIMITE_PAR_MINUTE = 10
GOOGLE_MAPS_KEY = env("GOOGLE_MAPS_KEY", default="")

# Durées de cache par point d'accès, en secondes (§ 6.1)
CACHE_TTL = {
    "config": env.int("CACHE_TTL_CONFIG", default=15 * 60),
    "articles": env.int("CACHE_TTL_ARTICLES", default=5 * 60),
    "galerie": env.int("CACHE_TTL_GALERIE", default=15 * 60),
    "comite": env.int("CACHE_TTL_COMITE", default=60 * 60),
    "coordinations": env.int("CACHE_TTL_COORDINATIONS", default=24 * 60 * 60),
    "associations": env.int("CACHE_TTL_ASSOCIATIONS", default=60 * 60),
    "statistiques": env.int("CACHE_TTL_STATISTIQUES", default=60 * 60),
}
# Copie de secours conservée plus longtemps pour le mode dégradé (S-12)
CACHE_STALE_TTL = env.int("CACHE_STALE_TTL", default=30 * 24 * 60 * 60)

# --- Langues (§ 7) ---
LANGUAGE_CODE = "fr"
LANGUAGES = [
    ("fr", _("Français")),
    ("ln", _("Lingala")),
    ("sw", _("Kiswahili")),
    ("lua", _("Tshiluba")),
    ("kg", _("Kikongo")),
]
# Repli seulement : les langues actives viennent de la configuration de l'API (config.langues_actives) et ne
# sont proposées que si leur fichier .po est complet (services/langues.py). Ce réglage sert quand l'API ne
# répond pas et qu'aucune copie de la configuration n'existe ; le français est toujours actif.
ACTIVE_LANGUAGES = list(dict.fromkeys(["fr", *env.list("ACTIVE_LANGUAGES", default=["fr"])]))
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True
USE_TZ = True
TIME_ZONE = "Africa/Kinshasa"

# Django ne connaît pas ln, lua ni kg : sans cette déclaration, get_supported_language_variant()
# les rejette et LocaleMiddleware ne les active pas. update() modifie le dictionnaire global
# de Django au chargement des réglages : acceptable ici, le projet n'en dépend que pour ces trois codes
# (fr et sw existent déjà).
LANG_INFO.update(
    {
        "ln": {"bidi": False, "code": "ln", "name": "Lingala", "name_local": "Lingála"},
        "lua": {"bidi": False, "code": "lua", "name": "Luba-Lulua", "name_local": "Tshiluba"},
        "kg": {"bidi": False, "code": "kg", "name": "Kongo", "name_local": "Kikongo"},
    }
)

# --- Fichiers statiques (HTMX et Alpine servis en local, aucun CDN) ---
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# --- Formulaire de contact (S-07) : limite par adresse IP, à la charge du site (l'API ne voit que le serveur du site) ---
CONTACT_LIMITE_IP = env.int("CONTACT_LIMITE_IP", default=5)  # envois par fenêtre et par adresse IP
CONTACT_LIMITE_FENETRE = env.int("CONTACT_LIMITE_FENETRE", default=3600)  # secondes
