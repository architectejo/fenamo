"""F-40 : communiqué sans texte = erreur 400 propre ; textes traduisibles."""
from django.test import Client
from django.urls import reverse

from tests.test_F21_matrice_routes import acteurs  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def test_F40_communique_sans_message_400_puis_envoi(acteurs):
    c = Client(raise_request_exception=False)
    c.force_login(acteurs['comptes']['su'])
    assert c.post(reverse('message'), {}).status_code == 400
    assert c.post(reverse('message'), {'message': '  '}).status_code == 400
    r = c.post(reverse('message'), {'message': 'Annonce'})
    assert r.status_code == 200 and 'Envoyé' in r.content.decode()
    assert 'déjà envoyé' in c.post(reverse('message'), {'message': 'Annonce'}).content.decode()
