"""Point d'entrée Passenger (cPanel) : expose l'application WSGI."""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "site_fenamo.settings.prod")

from site_fenamo.wsgi import application  # noqa: E402,F401
