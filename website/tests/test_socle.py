import socket

import pytest
import requests
from django.core.management import call_command
from django.urls import reverse
from django.utils import translation

from services import api_client


def test_lot1_le_projet_demarre():
    call_command("check")


def test_lot1_accueil_francais_sans_prefixe(client):
    rep = client.get("/")
    assert rep.status_code == 200
    assert "Unité, Discipline et Progrès" in rep.content.decode()
    assert '<html lang="fr">' in rep.content.decode()


@pytest.mark.parametrize("code", ["ln", "sw", "lua", "kg"])
def test_lot1_prefixe_langue_repond_avec_repli_francais(client, code, api, langues_completes):
    api.config(langues_actives=["fr", code])
    rep = client.get(f"/{code}/")
    assert rep.status_code == 200
    html = rep.content.decode()
    assert f'<html lang="{code}">' in html
    # aucune traduction fournie : le texte source français s'affiche
    assert "Unité, Discipline et Progrès" in html


def test_lot1_francais_n_a_pas_de_prefixe():
    with translation.override("fr"):
        assert reverse("pages:accueil") == "/"
    with translation.override("ln"):
        assert reverse("pages:accueil") == "/ln/"


def test_lot1_hreflang_et_pas_de_noindex_par_defaut(client, api, langues_completes):
    api.config(langues_actives=["fr", "ln", "sw", "lua", "kg"])
    html = client.get("/").content.decode()
    for code in ("fr", "ln", "sw", "lua", "kg", "x-default"):
        assert f'hreflang="{code}"' in html
    assert "noindex" not in html


def test_lot1_noindex_parametrable(client, settings):
    settings.SITE_NOINDEX = True
    assert 'content="noindex, nofollow"' in client.get("/").content.decode()


def test_lot1_selecteur_visible_seulement_si_plusieurs_langues(client, api, langues_completes):
    """Le sélecteur de langue (data-langue) n'apparaît qu'avec au moins deux langues ; le menu principal reste."""
    api.config(langues_actives=["fr"])
    html = client.get("/").content.decode()
    assert "data-langue" not in html and 'class="langue' not in html and '<nav class="site-nav"' in html
    api.config(langues_actives=["fr", "ln"])
    from django.core.cache import cache

    cache.clear()
    html = client.get("/").content.decode()
    assert "data-langue" in html and 'href="/ln/"' in html


def test_lot1_bibliotheques_locales_sans_cdn(client):
    import re

    html = client.get("/").content.decode()
    assert "http://" not in html.replace("http://localhost", "")
    for src in re.findall(r'<script[^>]+src="([^"]+)"', html):
        assert src.startswith("/static/"), src
    assert "googleapis" not in html and "cdn" not in html.lower()
    assert "vendor/htmx.min.js" in client.get("/actualites/").content.decode()


def test_lot1_aucun_appel_reseau_reel(client, aucun_reseau):
    client.get("/")
    client.get("/ln/")
    assert aucun_reseau == []
    with pytest.raises(AssertionError):
        socket.socket().connect(("127.0.0.1", 9))


def test_lot1_api_client_mode_degrade(monkeypatch, settings):
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

    cache.delete(api_client._cle_fraiche(api_client._cle("config/", None, None), api_client._version()))
    rep = api_client.get("config/", ttl="config")
    assert rep.degrade and rep.donnees == {"ok": 1}
    with pytest.raises(api_client.ApiIndisponible):
        api_client.get("articles/", ttl="articles")


def test_lot1_purge_garde_les_copies_de_secours(monkeypatch):
    """Purge puis API en panne : le mode dégradé sert encore la copie de secours."""
    from django.core.cache import cache

    class Faux:
        status_code = 200

        def json(self):
            return {"ok": 2}

    appels = {"n": 0}

    def ok(*a, **k):
        appels["n"] += 1
        return Faux()

    monkeypatch.setattr(requests, "request", ok)
    cache.set("compteur:ip:1", 7, 3600)
    api_client.get("config/", ttl="config")
    api_client.purger_cache()
    assert cache.get("compteur:ip:1") == 7
    api_client.get("config/", ttl="config")
    assert appels["n"] == 2  # la copie fraîche a été invalidée

    api_client.purger_cache()

    def coupee(*a, **k):
        raise requests.ConnectionError("coupée")

    monkeypatch.setattr(requests, "request", coupee)
    rep = api_client.get("config/", ttl="config")
    assert rep.degrade and rep.donnees == {"ok": 2}


def test_lot1_api_client_refuse_les_redirections(monkeypatch):
    vus = {}

    class Redir:
        status_code = 302

        def json(self):
            return {}

    def fake(*a, **k):
        vus.update(k)
        return Redir()

    monkeypatch.setattr(requests, "request", fake)
    with pytest.raises(api_client.ApiIndisponible):
        api_client.get("config/")
    assert vus["allow_redirects"] is False


def test_lot1_hreflang_limite_aux_langues_actives(client, api, langues_completes):
    api.config(langues_actives=["fr", "ln"])
    html = client.get("/").content.decode()
    assert 'hreflang="fr"' in html and 'hreflang="ln"' in html and 'hreflang="x-default"' in html
    for code in ("sw", "lua", "kg"):
        assert f'hreflang="{code}"' not in html


@pytest.mark.parametrize("code", ["ln", "sw", "lua", "kg"])
def test_lot1_langue_inactive_redirige_vers_le_francais(client, code, api, langues_completes):
    api.config(langues_actives=["fr"])
    rep = client.get(f"/{code}/")
    assert rep.status_code == 302 and rep["Location"] == "/"
    from django.core.cache import cache

    cache.clear()
    api.config(langues_actives=["fr", code])
    assert client.get(f"/{code}/").status_code == 200


def test_S11_langue_non_complete_jamais_active(client, api):
    """Une langue active dans l'API mais dont le .po n'est pas complet n'est pas proposée (repli sur le français)."""
    api.config(langues_actives=["fr", "ln"])
    assert "data-langue" not in client.get("/").content.decode()
    assert client.get("/ln/").status_code == 302


def test_S11_repli_env_quand_l_api_est_absente(client, api, settings):
    api.coupee()
    settings.ACTIVE_LANGUAGES = ["fr", "sw"]
    assert client.get("/sw/").status_code == 200
