"""Sous-lot 2a, tâche a3 : création de comptes et mot de passe."""
import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from compte.models import Compte
from compte.services.comptes import generer_mot_de_passe
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def test_mot_de_passe_genere_aleatoire():
    mdps = {generer_mot_de_passe() for _ in range(50)}
    assert len(mdps) == 50
    assert all(len(m) == 12 and any(c.isdigit() for c in m) for m in mdps)


@pytest.fixture
def simple(jeu):
    return Compte.objects.create_user('simple', password='mot-de-passe-test-123')


def test_adminer_reserve_aux_superutilisateurs(client, jeu, simple):
    url = reverse('adminer', kwargs={'id': jeu['membre'].id})
    client.force_login(simple)
    assert client.post(url).status_code == 403
    assert client.get(url).status_code == 403 or client.get(url).status_code == 405


def test_adminer_cree_compte_mot_de_passe_aleatoire(client, jeu):
    client.force_login(jeu['compte'])
    membre = jeu['membre']
    Compte.objects.filter(membreId=membre.id).update(membreId=None)  # le jeu lie le SU au membre
    r = client.post(reverse('adminer', kwargs={'id': membre.id}))
    compte = Compte.objects.get(membreId=membre.id)
    assert compte.doit_changer_mot_de_passe
    assert not compte.is_superuser
    assert compte.username != (compte.email or 'x')
    texte = ' '.join(str(m) for m in get_messages(r.wsgi_request))
    mdp = texte.split('mot de passe temporaire : ')[1].split(' ')[0]
    assert compte.check_password(mdp)
    assert mdp != compte.username and 'fenamo.cd' not in compte.email


def test_add_user_superutilisateur_seulement(client, jeu, simple):
    client.force_login(simple)
    assert client.get(reverse('add-user')).status_code == 403
    client.force_login(jeu['compte'])
    r = client.post(reverse('add-user'), {'username': 'nouveau', 'email': 'n@example.invalid'})
    assert r.status_code == 200
    c = Compte.objects.get(username='nouveau')
    assert c.doit_changer_mot_de_passe and c.has_usable_password() and not c.privilege5


def test_delete_user_retire(client, jeu):
    client.force_login(jeu['compte'])
    assert client.post('/comptes/desactiver/').status_code == 404


def test_changement_impose_a_la_premiere_connexion(client, jeu):
    Compte.objects.create_user('premier', password='Temporaire-123x', doit_changer_mot_de_passe=True)
    assert client.login(username='premier', password='Temporaire-123x')
    r = client.get('/membres/')
    assert r.status_code == 302 and r['Location'] == reverse('securite')
    r = client.get('/membres/', HTTP_HX_REQUEST='true')
    assert r['HX-Redirect'] == reverse('securite')
    assert client.get(reverse('securite')).status_code == 200


def test_securite_exige_ancien_mot_de_passe_et_validation(client, db):
    c = Compte.objects.create_user('u', password='Temporaire-123x', doit_changer_mot_de_passe=True)
    client.force_login(c)
    url = reverse('securite')
    r = client.post(url, {'old_password': 'faux', 'new_password1': 'Nouveau-mdp-9876', 'new_password2': 'Nouveau-mdp-9876'})
    assert r.status_code == 200
    r = client.post(url, {'old_password': 'Temporaire-123x', 'new_password1': '12345678', 'new_password2': '12345678'})
    assert r.status_code == 200
    c.refresh_from_db()
    assert c.doit_changer_mot_de_passe
    r = client.post(url, {'old_password': 'Temporaire-123x', 'new_password1': 'Nouveau-mdp-9876', 'new_password2': 'Nouveau-mdp-9876'})
    assert r.status_code == 302
    c.refresh_from_db()
    assert not c.doit_changer_mot_de_passe and c.check_password('Nouveau-mdp-9876')
    assert client.get('/membres/').status_code == 200  # session conservée, plus de blocage
