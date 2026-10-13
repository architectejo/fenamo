"""F-35 : engin : champ manquant ou trop long = erreur 400 propre (plaque 10, marque 20, couleur 20 caractères)."""
import pytest
from django.test import Client
from django.urls import reverse

from tests.test_F21_matrice_routes import acteurs  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

ENGIN = {k: 'x' for k in ('plaque', 'chassie', 'moteur', 'marque', 'couleur')}


@pytest.mark.parametrize('route, args', [('add-moto', 'membre'), ('edit-moto', 'moto')])
def test_F35_engin_incomplet_ou_trop_long_400(acteurs, route, args):
    c = Client(raise_request_exception=False)
    c.force_login(acteurs['comptes']['su'])
    url = reverse(route, kwargs={'id': acteurs[args].id})
    for manquant in ENGIN:
        assert c.post(url, {k: v for k, v in ENGIN.items() if k != manquant}).status_code == 400, manquant
    assert c.post(url, {}).status_code == 400
    for champ, longueur in (('plaque', 11), ('marque', 21), ('couleur', 21), ('chassie', 51), ('moteur', 51)):
        assert c.post(url, {**ENGIN, champ: 'x' * longueur}).status_code == 400, champ
    assert c.post(url, ENGIN).status_code == 200
