"""F-26 : proche d'un membre : champ manquant, invalide ou trop long = erreur 400 propre (jamais 500 ni DataError)."""
import pytest
from django.test import Client
from django.urls import reverse

from tests.test_F21_matrice_routes import acteurs  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

FAMILLE = {'nom': 'Proche', 'qualite': 'ENFANT', 'genre': 'F', 'annee': '2010'}


@pytest.mark.parametrize('route, args', [('add-family', 'membre'), ('edit-family', 'famille')])
def test_F26_famille_incomplete_invalide_ou_trop_longue_400(acteurs, route, args):
    c = Client(raise_request_exception=False)
    c.force_login(acteurs['comptes']['su'])
    url = reverse(route, kwargs={'id': acteurs[args].id})
    for donnees in ({}, {k: v for k, v in FAMILLE.items() if k != 'annee'}, {**FAMILLE, 'annee': 'dix'},
                    {**FAMILLE, 'nom': '  '}, {**FAMILLE, 'nom': 'x' * 51}, {**FAMILLE, 'qualite': 'x' * 11},
                    {**FAMILLE, 'genre': 'x' * 21}):
        assert c.post(url, donnees).status_code == 400, donnees
    assert c.post(url, FAMILLE).status_code == 200
