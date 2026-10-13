"""F-21 : identifiant absent = 404 propre (jamais 500) ; rattachement : le membre est contrôlé avant la cible."""
import pytest
from django.test import Client
from django.urls import reverse

from compte.models import Compte
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


@pytest.mark.parametrize('nom, methode', [
    ('communique', 'get'), ('contact-view', 'get'), ('contact-view', 'post'), ('article', 'get'), ('article', 'post'),
    ('delete-article', 'post'), ('edit-antenne', 'get'), ('add-ville', 'get'), ('add-ville', 'post'),
])
def test_F21_identifiant_absent_donne_404(jeu, nom, methode):
    c = Client(raise_request_exception=False)
    c.force_login(jeu['compte'])
    assert getattr(c, methode)(reverse(nom, kwargs={'id': 987654})).status_code == 404


def test_F21_rattachement_controle_le_membre_avant_la_cible(jeu):
    """Un compte sans accès au membre reçoit 404 quelle que soit la cible : il ne peut pas deviner les cibles existantes."""
    c = Client()
    c.force_login(Compte.objects.create_user('curieux', password='x', privilege3=True))
    membre = jeu['membre'].id
    existante = c.post(reverse('structure-attribution', kwargs={'idM': membre, 'id': jeu['association'].id}))
    absente = c.post(reverse('structure-attribution', kwargs={'idM': membre, 'id': 987654}))
    assert existante.status_code == absente.status_code == 404
    for nom in ('antenne-attribution', 'ville-attribution'):
        assert c.post(reverse(nom, kwargs={'idM': membre, 'id': 987654})).status_code == 404
