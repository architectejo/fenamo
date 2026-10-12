import socket

import pytest
import requests
from django.core.management import call_command
from django.urls import reverse
from django.utils import translation

from services import api_client


def test_W1_le_projet_demarre():
    call_command("check")


def test_W1_accueil_francais_sans_prefixe(client):
    rep = client.get("/")
    assert rep.status_code == 200
    assert "Unité, Discipline et Progrès" in rep.content.decode()
    assert '<html lang="fr">' in rep.content.decode()


@pytest.mark.parametrize("code", ["ln", "sw", "lua", "kg"])
def test_W2_prefixe_langue_repond_avec_repli_francais(client, code):
    rep = client.get(f"/{code}/")
    assert rep.status_code == 200
    html = rep.content.decode()
    assert f'<html lang="{code}">' in html
    # aucune traduction fournie : le texte source français s'affiche
    assert "Unité, Discipline et Progrès" in html


def test_W2_francais_n_a_pas_de_prefixe():
    with translation.override("fr"):
        assert reverse("pages:accueil") == "/"
    with translation.override("ln"):
        assert reverse("pages:accueil") == "/ln/"


def test_W2_hreflang_et_pas_de_noindex_par_defaut(client):
    html = client.get("/").content.decode()
    for code in ("fr", "ln", "sw", "lua", "kg", "x-default"):
        assert f'hreflang="{code}"' in html
    assert "noindex" not in html


def test_W2_noindex_parametrable(client, settings):
    settings.SITE_NOINDEX = True
    assert 'content="noindex, nofollow"' in client.get("/").content.decode()


def test_W2_selecteur_visible_seulement_si_plusieurs_langues(client, settings):
    settings.ACTIVE_LANGUAGES = ["fr"]
    assert "<nav" not in client.get("/").content.decode()
    settings.ACTIVE_LANGUAGES = ["fr", "ln"]
    html = client.get("/").content.decode()
    assert "<nav" in html and 'href="/ln/"' in html


def test_W2_bibliotheques_locales_sans_cdn(client):
    html = client.get("/").content.decode()
    assert "vendor/htmx.min.js" in html and "vendor/alpine.min.js" in html
    assert "http://" not in html.replace("http://localhost", "")
    assert "https://" not in html


def test_W1_aucun_appel_reseau_reel(client, aucun_reseau):
    client.get("/")
    client.get("/ln/")
    assert aucun_reseau == []
    with pytest.raises(AssertionError):
        socket.socket().connect(("127.0.0.1", 9))


def test_W1_api_client_mode_degrade(monkeypatch, settings):
    """L'API coupée : copie en cache servie en mode dégradé, sinon ApiIndisponible."""
    appels = {"n": 0}

    class Faux:
        status_code = 200

        def json(self):
            return {"ok": 1}

    def ok(*a, **k):
        appels["n"] += 1
        return Faux()

    monkeypatch.setattr(requests, "request", ok)
    rep = api_client.get("config/", ttl="config")
    assert rep.donnees == {"ok": 1} and not rep.degrade
    api_client.get("config/", ttl="config")
    assert appels["n"] == 1  # deuxième lecture servie par le cache

    def coupee(*a, **k):
        raise requests.ConnectionError("coupée")

    monkeypatch.setattr(requests, "request", coupee)
    from django.core.cache import cache

    cache.delete_many([k for k in ("api:fresh:" + api_client._cle("config/", None, None),)])
    rep = api_client.get("config/", ttl="config")
    assert rep.degrade and rep.donnees == {"ok": 1}
    with pytest.raises(api_client.ApiIndisponible):
        api_client.get("articles/", ttl="articles")
