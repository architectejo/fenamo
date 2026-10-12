"""Lot 1 : réglages par environnement du site (SECRET_KEY, cookies, HSTS), en sous-processus."""
import os
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def lancer(module, env_extra, *args):
    env = {k: v for k, v in os.environ.items() if k not in ("SECRET_KEY", "DEBUG", "DJANGO_SETTINGS_MODULE")}
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, "manage.py", *args, f"--settings=site_fenamo.settings.{module}"],
        cwd=RACINE, env=env, capture_output=True, text=True, timeout=120,
    )


def test_lot1_prod_exige_secret_key():
    r = lancer("prod", {"ALLOWED_HOSTS": "site.example.invalid"}, "check")
    assert r.returncode != 0
    assert "SECRET_KEY" in r.stderr


def test_lot1_dev_demarre_sans_secret_key():
    r = lancer("dev", {}, "check")
    assert r.returncode == 0, r.stderr


def test_lot1_prod_cookies_secure_hsts_debug_faux():
    code = ("from django.conf import settings as s;"
            "print(s.DEBUG, s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, s.SECURE_HSTS_SECONDS)")
    r = lancer("prod", {"SECRET_KEY": "cle-de-test-" + "x" * 60, "DEBUG": "True",
                        "ALLOWED_HOSTS": "site.example.invalid"}, "shell", "-c", code)
    derniere = r.stdout.strip().splitlines()[-1].split()
    assert derniere[:3] == ["False", "True", "True"], r.stdout + r.stderr
    assert int(derniere[3]) >= 31536000
