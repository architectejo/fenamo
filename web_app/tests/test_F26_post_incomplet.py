"""F-26 / F-35 : un champ de POST manquant ou invalide donne une erreur 400 propre, jamais un KeyError (500)."""
import pytest
from django.test import Client
from django.urls import reverse

from tests.test_F21_matrice_routes import acteurs  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

FAMILLE = {'nom': 'Proche', 'qualite': 'ENFANT', 'genre': 'F', 'annee': '2010'}
ENGIN = {k: 'x' for k in ('plaque', 'chassie', 'moteur', 'marque', 'couleur')}


def _su(acteurs):
    c = Client(raise_request_exception=False)
    c.force_login(acteurs['comptes']['su'])
    return c


@pytest.mark.parametrize('route, args', [('add-family', 'membre'), ('edit-family', 'famille')])
def test_F26_famille_incomplete_ou_invalide_400(acteurs, route, args):
    c = _su(acteurs)
    url = reverse(route, kwargs={'id': acteurs[args].id})
    for donnees in ({}, {k: v for k, v in FAMILLE.items() if k != 'annee'}, {**FAMILLE, 'annee': 'dix'},
                    {**FAMILLE, 'nom': '  '}):
        assert c.post(url, donnees).status_code == 400, donnees
    assert c.post(url, FAMILLE).status_code == 200


@pytest.mark.parametrize('route, args', [('add-moto', 'membre'), ('edit-moto', 'moto')])
def test_F35_engin_incomplet_400(acteurs, route, args):
    c = _su(acteurs)
    url = reverse(route, kwargs={'id': acteurs[args].id})
    for manquant in ENGIN:
        assert c.post(url, {k: v for k, v in ENGIN.items() if k != manquant}).status_code == 400, manquant
    assert c.post(url, {}).status_code == 400


def test_F21_ville_province_communique_sans_champ_400(acteurs):
    c = _su(acteurs)
    assert c.post(reverse('add-ville', kwargs={'id': acteurs['province'].id}), {}).status_code == 400
    assert c.post(reverse('add-ville', kwargs={'id': acteurs['province'].id}), {'nom': '  '}).status_code == 400
    assert c.post(reverse('add-province'), {}).status_code == 400
    assert c.post(reverse('message'), {}).status_code == 400
    assert c.post(reverse('add-ville', kwargs={'id': acteurs['province'].id}), {'nom': 'Nouvelle'}).status_code == 200


def test_F21_contact_public_de_l_ancien_site_sans_champ_400(db):
    c = Client(raise_request_exception=False)
    assert c.post(reverse('home'), {}).status_code == 400
