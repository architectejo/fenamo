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


def test_racine_est_le_tableau_de_bord(client, jeu):
    assert reverse('tableau-bord') == '/'
    client.force_login(jeu['compte'])
    reponse = client.get('/')
    assert reponse.status_code == 200
    assert 'coptapp/tableau_bord/tableau_bord.html' in [t.name for t in reponse.templates]
    assert client.get('/tableau-de-bord/').status_code == 404


def test_racine_anonyme_redirige_vers_la_connexion(client, db):
    reponse = client.get('/')
    assert reponse.status_code == 302
    assert reponse['Location'].startswith(reverse('application'))


def test_connexion_redirige_vers_la_racine(client, jeu):
    client.force_login(jeu['compte'])
    assert client.get(reverse('application'))['Location'] == '/'
