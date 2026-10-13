"""Navigation HTMX : fragment ou page selon la requête, en-têtes de cache sur les pages connectées (données personnelles)."""
from django.urls import reverse

from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def test_F28_liste_fragment_page_complete_et_restauration(client, jeu):
    client.force_login(jeu['compte'])
    url = reverse('liste-membre')
    fragment = client.get(url, HTTP_HX_REQUEST='true').content.decode()
    assert '<html' not in fragment and 'id="liste-resume"' in fragment and 'hx-swap-oob' in fragment
    boosted = client.get(url, HTTP_HX_REQUEST='true', HTTP_HX_BOOSTED='true').content.decode()
    assert '<html' in boosted
    retour = client.get(url, HTTP_HX_REQUEST='true', HTTP_HX_HISTORY_RESTORE_REQUEST='true').content.decode()
    assert '<html' in retour  # retour arrière : jamais le fragment seul
    complete = client.get(url).content.decode()
    assert complete.count('id="liste-resume"') == 1 and 'hx-swap-oob' not in complete


def test_F28_en_tetes_cache_et_vary_sur_pages_connectees(client, jeu):
    client.force_login(jeu['compte'])
    for nom in ('liste-membre', 'tableau-bord'):
        r = client.get(reverse(nom))
        cc = r['Cache-Control']
        assert 'no-store' in cc and 'private' in cc
        vary = r['Vary']
        assert 'HX-Request' in vary and 'HX-Boosted' in vary


def test_F28_historique_htmx_desactive_sur_liste_et_fiche(client, jeu):
    client.force_login(jeu['compte'])
    assert 'hx-history="false"' in client.get(reverse('liste-membre')).content.decode()
    assert 'hx-history="false"' in client.get(reverse('membre-view', kwargs={'id': jeu['membre'].id})).content.decode()
