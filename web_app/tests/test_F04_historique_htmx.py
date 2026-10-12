"""F-04 : le mot de passe temporaire ne doit jamais entrer dans l'historique HTMX (localStorage)."""
from django.urls import reverse

from compte.models import Compte
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def test_F04_adminer_exclut_la_page_de_l_historique_htmx(client, jeu):
    client.force_login(jeu['compte'])
    membre = jeu['membre']
    Compte.objects.filter(membreId=membre.id).update(membreId=None)
    url = reverse('adminer', kwargs={'id': membre.id})
    complet = client.post(url).content.decode()
    assert 'Mot de passe temporaire' in complet and 'hx-history="false"' in complet
    Compte.objects.filter(membreId=membre.id).delete()
    fragment = client.post(url, HTTP_HX_REQUEST='true').content.decode()
    assert 'Mot de passe temporaire' in fragment and 'hx-history="false"' in fragment


def test_F04_add_user_exclut_la_page_de_l_historique_htmx(client, jeu):
    client.force_login(jeu['compte'])
    r = client.post(reverse('add-user'), {'username': 'hist', 'email': 'h@example.invalid'})
    corps = r.content.decode()
    assert 'mot de passe temporaire' in corps and 'hx-history="false"' in corps
