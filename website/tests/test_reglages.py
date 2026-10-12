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


CLE = "cle-de-test-" + "x" * 60
PROD_OK = {
    "SECRET_KEY": CLE,
    "ALLOWED_HOSTS": "site.example.invalid",
    "CSRF_TRUSTED_ORIGINS": "https://site.example.invalid",
    "API_BASE_URL": "https://app.example.invalid/api/v1/site/",
}


def prod(**modif):
    env = {**PROD_OK, **modif}
    return lancer("prod", {k: v for k, v in env.items() if v is not None}, "check")


def test_lot1_prod_valide_demarre():
    r = prod()
    assert r.returncode == 0, r.stderr


def test_lot1_prod_exige_secret_key():
    r = prod(SECRET_KEY=None)
    assert r.returncode != 0 and "SECRET_KEY" in r.stderr


def test_lot1_prod_refuse_cles_faibles():
    for cle in ("courte", "changer-moi-" + "x" * 60, "dev-" + "x" * 60, "django-insecure-" + "x" * 60):
        r = prod(SECRET_KEY=cle)
        assert r.returncode != 0 and "SECRET_KEY" in r.stderr, cle


def test_lot1_prod_exige_hosts_et_origines_csrf():
    assert prod(ALLOWED_HOSTS=None).returncode != 0
    assert prod(CSRF_TRUSTED_ORIGINS=None).returncode != 0


def test_lot1_prod_exige_api_en_https():
    r = prod(API_BASE_URL="http://app.example.invalid/api/v1/site/")
    assert r.returncode != 0 and "API_BASE_URL" in r.stderr


def test_lot1_dev_demarre_sans_secret_key():
    r = lancer("dev", {}, "check")
    assert r.returncode == 0, r.stderr


def test_lot1_prod_cookies_secure_hsts_whitenoise():
    code = ("from django.conf import settings as s;"
            "print(s.DEBUG, s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, s.SECURE_HSTS_SECONDS,"
            " 'whitenoise.middleware.WhiteNoiseMiddleware' in s.MIDDLEWARE)")
    r = lancer("prod", {**PROD_OK, "DEBUG": "True"}, "shell", "-c", code)
    derniere = r.stdout.strip().splitlines()[-1].split()
    assert derniere[:3] == ["False", "True", "True"], r.stdout + r.stderr
    assert int(derniere[3]) >= 31536000 and derniere[4] == "True"
