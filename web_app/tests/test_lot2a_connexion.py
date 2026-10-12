"""Sous-lot 2a : connexion obligatoire par défaut (a1)."""
import pytest
from django.urls import reverse

from tests.test_plan_url import hachage_rapide, jeu, table  # noqa: F401

EXEMPTEES = {'application', 'sante'}


def test_anonyme_redirige_vers_la_connexion_partout(client, jeu):
    fautifs = []
    for nom, kwargs, cible in table(jeu):
        r = client.get(cible)
        if r.status_code != 302 or not r['Location'].startswith('/connexion/'):
            if nom not in EXEMPTEES:
                fautifs.append((nom, r.status_code))
    assert fautifs == []


def test_exemptions_acceptees(client, db):
    assert client.get('/connexion/').status_code == 200
    assert client.get('/api/v1/').status_code == 200
    assert client.get('/mob/').status_code == 200
    assert client.get('/ancien-site/').status_code == 200


def test_anonyme_htmx_recoit_hx_redirect(client, jeu):
    r = client.get('/membres/', HTTP_HX_REQUEST='true')
    assert r.status_code == 200
    assert r['HX-Redirect'].startswith('/connexion/')


def test_anonyme_ne_lit_pas_les_medias(client, db):
    assert client.get('/media/x.jpg').status_code in (302, 404)
