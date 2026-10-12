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

INSTALLED_APPS = [
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "pages",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "site_fenamo.urls"
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
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "var" / "site.sqlite3",
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SESSION_ENGINE = "django.contrib.sessions.backends.db"

# --- Cache Django sur fichiers (pas de Redis sur mutualisé) ---
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": str(BASE_DIR / "var" / "cache"),
    }
}

# --- API de l'application web (§ 6) ---
API_BASE_URL = env("API_BASE_URL", default="http://localhost:8000/api/v1/site/")
SITE_API_KEY = env("SITE_API_KEY", default="")
API_TIMEOUT = env.float("API_TIMEOUT", default=5)
PURGE_SECRET = env("PURGE_SECRET", default="")
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
# Langues proposées dans le sélecteur (le français est toujours actif).
ACTIVE_LANGUAGES = list(dict.fromkeys(["fr", *env.list("ACTIVE_LANGUAGES", default=["fr"])]))
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True
USE_TZ = True
TIME_ZONE = "Africa/Kinshasa"

# Django ne connaît pas ln, lua ni kg : on les déclare (fr et sw existent déjà).
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
