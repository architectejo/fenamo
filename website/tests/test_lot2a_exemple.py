"""Mode « données d'exemple » : jeu statique sans donnée réelle, bascule, API coupée, bandeau, purge."""
import html as _html
import json
import re

import pytest
from django.core.cache import cache

from services import api_client
from tests.test_lot2a_pages import PAGES

def lire(client, chemin):
    return _html.unescape(client.get(chemin).content.decode())


def appels_de_donnees(api):
    return [a for a in api.appels_donnees() if a[1] != "config/"]


@pytest.mark.parametrize("chemin", PAGES)
def test_exemple_chaque_page_sans_appel_aux_points_de_donnees(client, api, chemin):
    api.inactive()
    if "assemblee" in chemin:
        chemin = "/actualites/communique-d-exemple/"
    rep = client.get(chemin)
    html = rep.content.decode()
    assert rep.status_code == 200 and "Données d'exemple." in html and "noindex" in html
    assert appels_de_donnees(api) == []


def test_exemple_contenus_du_jeu_statique(client, api):
    api.inactive()
    assert "Communiqué d'exemple" in lire(client, "/actualites/")
    assert "Prénom Nom 1 (exemple)" in lire(client, "/organisation/comite/")
    coord = lire(client, "/organisation/coordinations/")
    assert coord.count('class="coord"') == 27 and "Antenne d'exemple 1" in coord
    assert lire(client, "/galerie/").count("data-visionneuse data-legende") == 6
    assert "exemple.svg" in lire(client, "/galerie/")
    assert "Document d'exemple" in lire(client, "/documents/")
    assert api.config_corps["nom"] and "Assemblée générale annuelle" not in lire(client, "/actualites/")


def test_exemple_mode_reel_pas_de_bandeau_exemple(client):
    html = lire(client, "/")
    assert "Données d'exemple" not in html and "Assemblée générale annuelle" in html


def test_exemple_bascule_par_403_inactif_sur_un_point_de_donnees(client, api):
    client.get("/")  # config réelle en cache : mode réel
    api.repondre("articles/", 403, {"statut": "inactif", "detail": "Données réelles désactivées."})
    html = lire(client, "/actualites/")
    assert "Données d'exemple." in html and "Communiqué d'exemple" in html and "Assemblée générale" not in html
    assert api_client.dernier_mode() == "statique" and api_client.statique_force()


def test_exemple_retour_au_reel_apres_purge(client, api):
    api.inactive()
    assert "Données d'exemple." in lire(client, "/")
    api.rallumee()
    api_client.purger_cache()
    html = lire(client, "/")
    assert "Données d'exemple" not in html and "Assemblée générale annuelle" in html


def test_exemple_api_coupee_apres_mode_statique_reste_statique(client, api):
    api.inactive()
    client.get("/")
    api.coupee()
    api_client.purger_cache()
    cache.delete("api:panne")
    html = lire(client, "/actualites/")
    assert "Données d'exemple." in html and "Communiqué d'exemple" in html


def test_exemple_copie_reelle_jamais_servie_si_dernier_etat_statique(client, api):
    client.get("/actualites/")  # copies réelles en secours
    api.inactive()
    client.get("/")  # config → statique
    api.coupee()
    api_client.purger_cache()
    cache.delete("api:panne")
    html = lire(client, "/actualites/")
    assert "Assemblée générale annuelle" not in html and "Communiqué d'exemple" in html


def test_exemple_api_coupee_en_mode_reel_garde_la_copie(client, api):
    client.get("/actualites/")
    api.coupee()
    api_client.purger_cache()
    cache.delete("api:panne")
    html = lire(client, "/actualites/")
    assert "Assemblée générale annuelle" in html and "bandeau-degrade" in html and "Données d'exemple" not in html


def test_exemple_langues_actives_viennent_de_l_api_minimale(client, api):
    api.inactive()
    assert "data-langue" not in lire(client, "/")  # langues_actives = ["fr"]


def test_exemple_robots_interdit_tout(client, api):
    api.inactive()
    assert "Disallow: /\n" in lire(client, "/robots.txt")


def test_exemple_article_inconnu_et_page_hors_limite_404(client, api):
    api.inactive()
    assert client.get("/actualites/inconnu/").status_code == 404
    assert client.get("/actualites/?page=9").status_code == 404


def test_exemple_purge_signee_relit_le_mode(client, api, settings):
    import hashlib
    import hmac
    import time

    settings.PURGE_SECRET = "s"
    client.get("/")
    api.inactive()
    t = str(int(time.time()))
    sig = hmac.new(b"s", t.encode(), hashlib.sha256).hexdigest()
    assert client.post("/_purge/", HTTP_X_PURGE_HORODATAGE=t, HTTP_X_PURGE_SIGNATURE=sig).status_code == 204
    assert "Données d'exemple." in lire(client, "/")


def test_exemple_fixture_inactif_conforme_au_contrat():
    from tests.conftest import charger

    f = charger("api_site_inactif.json")
    assert f["config"]["body"]["donnees_reelles"] is False
    assert set(f["config"]["body"]) == {"nom", "devise", "langues_actives", "donnees_reelles"}
    assert f["autres"]["status"] == 403 and f["autres"]["body"]["statut"] == "inactif"


def test_exemple_le_jeu_ne_contient_aucune_donnee_reelle():
    """Échoue si une chaîne ressemble à un numéro MBR, un téléphone +243/0xx ou une adresse e-mail réelle."""
    from services import donnees_statiques

    chemins = ["config/", "articles/", "articles/communique-d-exemple/", "galerie/", "comite/", "coordinations/", "statistiques/"]
    texte = json.dumps([donnees_statiques.repondre(c, {}) for c in chemins], ensure_ascii=False)
    assert not re.search(r"MBR\s?\d", texte, re.I)
    assert not re.search(r"\+?243[\s\d]{6,}", texte) and not re.search(r"\b0[89]\d[\s\d]{6,}", texte)
    for courriel in re.findall(r"[\w.+-]+@[\w.-]+", texte):
        assert courriel.endswith(".invalid"), courriel
    for url in re.findall(r"https?://[^\"\s]+", texte):
        assert ".invalid" in url, url
    assert all("(exemple)" in m["nom"] for m in donnees_statiques.repondre("comite/", {})["membres"])
    assert len(donnees_statiques.repondre("coordinations/", {})) == 27


def test_exemple_copies_de_secours_videes_des_que_le_mode_exemple_est_connu(client, api):
    client.get("/actualites/")
    brute = api_client._cle("articles/", {"page": 1, "taille": 12}, "fr")
    assert cache.get(api_client.cle_secours(brute)) is not None
    api.inactive()
    api_client.purger_cache()
    client.get("/")  # config : donnees_reelles=false
    assert cache.get(api_client.cle_secours(brute)) is None
    api.coupee()
    api_client.purger_cache()
    cache.delete("api:panne")
    assert "Assemblée générale annuelle" not in lire(client, "/actualites/")


def test_exemple_403_inactif_vide_les_copies_de_secours(client, api):
    client.get("/actualites/")
    brute = api_client._cle("articles/", {"page": 1, "taille": 12}, "fr")
    api_client.purger_cache()  # copies fraîches expirées : l'appel repart vers l'API
    api.repondre("articles/", 403, {"statut": "inactif", "detail": "Données réelles désactivées."})
    client.get("/actualites/")
    assert cache.get(api_client.cle_secours(brute)) is None


def test_exemple_purge_en_mode_exemple_vide_aussi_les_copies_de_secours(client, api):
    client.get("/actualites/")
    api_client.retenir_mode("statique")
    api_client.purger_cache()
    cle = api_client.cle_secours(api_client._cle("config/", None, None))
    assert cache.get(cle) is None


def test_exemple_parametres_de_pagination_invalides_ne_plantent_pas():
    from services import donnees_statiques

    assert donnees_statiques.repondre("articles/", {"page": "abc", "taille": "x"})["page"] == 1
