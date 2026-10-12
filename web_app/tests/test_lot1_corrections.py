"""Non-régression des réserves du lot 1 (rapports sécurité et relecteur), sur jeu d'essai fictif."""
import pytest
from django.urls import reverse

from compte.models import Compte
from coptapp.models import Notification
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def test_notifications_membre_sans_photo_repond_200(client, jeu):
    """Une notification liée à un membre sans photo ne fait plus planter /notifications/."""
    assert not jeu['membre'].photo
    Notification.objects.create(user=jeu['compte'], membre=jeu['membre'], titre="Activité fictive")
    client.force_login(jeu['compte'])
    reponse = client.get(reverse('notifys'))
    assert reponse.status_code == 200
    assert 'Activité fictive' in reponse.content.decode()


def test_notifications_compte_sans_membre_pas_de_500(client, jeu):
    compte = Compte.objects.create_user('sans-membre', password='mot-de-passe-test-123')
    Notification.objects.create(user=compte, titre="Activité sans membre")
    client.force_login(compte)
    assert client.get(reverse('notifys')).status_code == 200


def test_notifications_membre_disparu_pas_de_500(client, jeu):
    jeu['compte'].membreId = 999999
    jeu['compte'].save()
    client.force_login(jeu['compte'])
    assert client.get(reverse('notifys')).status_code == 200
