import socket

import pytest


@pytest.fixture(autouse=True)
def aucun_reseau(monkeypatch):
    """Les tests n'appellent jamais la vraie API : toute connexion sortante échoue."""
    tentatives = []

    def interdit(self, *args, **kwargs):
        tentatives.append(args)
        raise AssertionError("Appel réseau réel interdit en test")

    monkeypatch.setattr(socket.socket, "connect", interdit)
    monkeypatch.setattr(socket.socket, "connect_ex", interdit)
    yield tentatives


@pytest.fixture(autouse=True)
def cache_isole(settings, tmp_path):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "tests",
        }
    }
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()
