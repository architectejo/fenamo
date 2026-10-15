"""F-40 : communiqué sans titre ou sans message = erreur 422 propre (modale conservée) ; publication ; textes traduisibles."""
from django.test import Client
from django.urls import reverse

from coptapp.models import Communique
from tests.test_F21_matrice_routes import acteurs  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def test_F40_communique_sans_message_422_puis_publication(acteurs):
    c = Client(raise_request_exception=False)
    c.force_login(acteurs['comptes']['su'])
    assert c.post(reverse('message'), {}).status_code == 422
    assert c.post(reverse('message'), {'titre': 'Titre', 'message': '  '}).status_code == 422
    assert c.post(reverse('message'), {'titre': '', 'message': 'Annonce'}).status_code == 422
    avant = Communique.objects.count()  # le jeu d'essai en contient déjà un
    r = c.post(reverse('message'), {'titre': 'Annonce', 'message': 'Annonce détaillée'})
    assert r.status_code == 302 and Communique.objects.count() == avant + 1 and Communique.objects.filter(titre='Annonce').count() == 1
    # nouvelle publication identique : un nouveau communiqué (plus de blocage « déjà envoyé » : chacun est horodaté et notifie)
    assert c.post(reverse('message'), {'titre': 'Annonce', 'message': 'Annonce détaillée'}).status_code == 302
    assert Communique.objects.count() == avant + 2
