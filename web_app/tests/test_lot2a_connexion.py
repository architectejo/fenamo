"""Sous-lot 2a : connexion obligatoire par défaut (a1)."""
import pytest
from django.urls import reverse

from tests.test_plan_url import hachage_rapide, jeu, table  # noqa: F401

EXEMPTEES = {'application', 'sante'}


def test_F01_anonyme_redirige_vers_la_connexion_partout(client, jeu):
    fautifs = []
    for nom, kwargs, cible in table(jeu):
        r = client.get(cible)
        if r.status_code != 302 or not r['Location'].startswith('/connexion/'):
            if nom not in EXEMPTEES:
                fautifs.append((nom, r.status_code))
    assert fautifs == []


def test_F01_exemptions_acceptees(client, db):
    assert client.get('/connexion/').status_code == 200
    assert client.get('/api/v1/').status_code == 200
    assert client.get('/mob/').status_code == 200
    assert client.get('/ancien-site/').status_code == 404  # retiré : le site public passe par l'API


def test_F01_anonyme_htmx_recoit_hx_redirect(client, jeu):
    r = client.get('/membres/', HTTP_HX_REQUEST='true')
    assert r.status_code == 200
    assert r['HX-Redirect'].startswith('/connexion/')


def test_F01_anonyme_ne_lit_pas_les_medias(client, db):
    assert client.get('/media/x.jpg').status_code in (302, 404)


# ------------------------------------------------------------ a2 : POST seulement

def test_F01_get_membre_view_ne_cree_pas_de_notification(client, jeu):
    from coptapp.models import Notification
    client.force_login(jeu['compte'])
    client.get(reverse('membre-view', kwargs={'id': jeu['membre'].id}))
    assert Notification.objects.count() == 0


def test_F01_get_contact_view_ne_marque_pas_traite(client, jeu):
    client.force_login(jeu['compte'])
    client.get(reverse('contact-view', kwargs={'id': jeu['contact'].id}))
    jeu['contact'].refresh_from_db()
    assert not jeu['contact'].traiter
    client.post(reverse('contact-view', kwargs={'id': jeu['contact'].id}))
    jeu['contact'].refresh_from_db()
    assert jeu['contact'].traiter


def test_F01_post_sans_csrf_refuse(jeu):
    from django.test import Client
    c = Client(enforce_csrf_checks=True)
    c.force_login(jeu['compte'])
    assert c.post(reverse('delete-family', kwargs={'id': jeu['famille'].id})).status_code == 403


def test_F01_post_supprime_la_famille(client, jeu):
    from coptapp.models import Famille
    client.force_login(jeu['compte'])
    assert client.post(reverse('delete-family', kwargs={'id': jeu['famille'].id})).status_code == 302
    assert not Famille.objects.filter(id=jeu['famille'].id).exists()


def test_F01_ancienne_accueil_supprimee(client, jeu):
    client.force_login(jeu['compte'])
    assert client.get('/accueil-ancien/').status_code == 404
