"""Lot 2a : chaque page de contenu répond avec l'API simulée (S-01, S-09, S-10, S-11), contenus et états vides."""
import pytest

PAGES = [
    "/", "/a-propos/", "/organisation/comite/", "/organisation/coordinations/", "/documents/", "/application/",
    "/actualites/", "/actualites/assemblee-generale-annuelle/", "/galerie/", "/contact/", "/adhesion/",
    "/mentions-legales/", "/confidentialite/",
]


@pytest.mark.parametrize("chemin", PAGES)
def test_S01_chaque_page_repond_avec_l_api_simulee(client, chemin):
    rep = client.get(chemin)
    assert rep.status_code == 200
    html = rep.content.decode()
    assert '<main id="contenu"' in html and "<h1" in html
    assert "bandeau-degrade" not in html


@pytest.mark.parametrize("chemin", PAGES)
def test_S12_api_coupee_sans_copie_la_page_ne_plante_pas(client, api, chemin):
    api.coupee()
    rep = client.get(chemin)
    # Un article inconnu de toute copie répond 503 sobre ; les autres pages s'affichent avec un état vide
    assert rep.status_code == (503 if "assemblee" in chemin else 200)
    assert "<h1" in rep.content.decode()
