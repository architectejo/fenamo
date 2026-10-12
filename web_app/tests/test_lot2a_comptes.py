"""Sous-lot 2a, tâche a3 : création de comptes et mot de passe."""
import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from compte.models import Compte
from compte.services.comptes import generer_mot_de_passe
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def test_F02_mot_de_passe_genere_aleatoire():
    mdps = {generer_mot_de_passe() for _ in range(50)}
    assert len(mdps) == 50
    assert all(len(m) == 12 and any(c.isdigit() for c in m) for m in mdps)


@pytest.fixture
def simple(jeu):
    return Compte.objects.create_user('simple', password='mot-de-passe-test-123')


def test_F02_adminer_reserve_aux_superutilisateurs(client, jeu, simple):
    url = reverse('adminer', kwargs={'id': jeu['membre'].id})
    client.force_login(simple)
    assert client.post(url).status_code == 403
    assert client.get(url).status_code == 403  # le contrôle du rôle précède celui de la méthode


def test_F02_adminer_cree_compte_mot_de_passe_aleatoire(client, jeu):
    client.force_login(jeu['compte'])
    membre = jeu['membre']
    Compte.objects.filter(membreId=membre.id).update(membreId=None)  # le jeu lie le SU au membre
    r = client.post(reverse('adminer', kwargs={'id': membre.id}))
    compte = Compte.objects.get(membreId=membre.id)
    assert compte.doit_changer_mot_de_passe
    assert not compte.is_superuser
    assert compte.username != (compte.email or 'x')
    corps = r.content.decode()
    mdp = corps.split('Mot de passe temporaire :')[1].split('<strong class="user-select-all">')[1].split('</strong>')[0]
    assert compte.check_password(mdp)
    assert mdp != compte.username and 'fenamo.cd' not in compte.email


def test_F02_add_user_superutilisateur_seulement(client, jeu, simple):
    client.force_login(simple)
    assert client.get(reverse('add-user')).status_code == 403
    client.force_login(jeu['compte'])
    r = client.post(reverse('add-user'), {'username': 'nouveau', 'email': 'n@example.invalid'})
    assert r.status_code == 200
    c = Compte.objects.get(username='nouveau')
    assert c.doit_changer_mot_de_passe and c.has_usable_password() and not c.privilege5


def test_F06_delete_user_retire(client, jeu):
    client.force_login(jeu['compte'])
    assert client.post('/comptes/desactiver/').status_code == 404


def test_F02_changement_impose_a_la_premiere_connexion(client, jeu):
    Compte.objects.create_user('premier', password='Temporaire-123x', doit_changer_mot_de_passe=True)
    client.force_login(Compte.objects.get(username='premier'))
    r = client.get('/membres/')
    assert r.status_code == 302 and r['Location'] == reverse('securite')
    r = client.get('/membres/', HTTP_HX_REQUEST='true')
    assert r['HX-Redirect'] == reverse('securite')
    assert client.get(reverse('securite')).status_code == 200


def test_F04_securite_exige_ancien_mot_de_passe_et_validation(client, db):
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


# ------------------------------------------------------------------ a4 : admin

def test_F02_admin_reserve_aux_superutilisateurs(client, jeu, simple):
    assert client.get('/gestion-technique/').status_code == 302
    staff = Compte.objects.create_user('staff', password='mot-de-passe-test-123', is_staff=True)
    client.force_login(staff)
    r = client.get('/gestion-technique/')
    assert r.status_code == 302 and '/gestion-technique/login/' in r['Location']
    client.force_login(jeu['compte'])
    assert client.get('/gestion-technique/').status_code == 200


def test_F02_admin_compte_mot_de_passe_hache_et_membre_sans_password(client, jeu):
    client.force_login(jeu['compte'])
    r = client.post('/gestion-technique/compte/compte/add/', {
        'username': 'cree-admin', 'password1': 'Mdp-admin-test-7391', 'password2': 'Mdp-admin-test-7391'})
    assert r.status_code == 302
    c = Compte.objects.get(username='cree-admin')
    assert c.password.startswith(('pbkdf2_', 'md5$')) and 'Mdp-admin' not in c.password
    html = client.get(f"/gestion-technique/coptapp/membre/{jeu['membre'].id}/change/").content.decode()
    assert 'name="password"' not in html


def test_F01_page_connexion_admin_accessible_a_l_anonyme(client, db):
    assert client.get('/gestion-technique/login/').status_code == 200


# ------------------------------------------------------------------ a5 : axes, sessions, CSP

def test_F01_verrou_apres_cinq_echecs(client, db, settings):
    Compte.objects.create_user('cible', password='Bon-mot-de-passe-1x')
    for _ in range(4):
        assert client.post('/connexion/', {'username': 'cible', 'password': 'faux'}).status_code == 200
    # le 5e échec déclenche le verrou
    assert client.post('/connexion/', {'username': 'cible', 'password': 'faux'}).status_code == 429
    r = client.post('/connexion/', {'username': 'cible', 'password': 'Bon-mot-de-passe-1x'})
    assert r.status_code == 429
    # un autre nom d'utilisateur (même IP) n'est pas bloqué
    Compte.objects.create_user('autre', password='Bon-mot-de-passe-1x')
    assert client.post('/connexion/', {'username': 'autre', 'password': 'Bon-mot-de-passe-1x'}).status_code == 302


def test_F01_connexion_normale_et_reglages(client, db, settings):
    Compte.objects.create_user('ok', password='Bon-mot-de-passe-1x')
    assert client.post('/connexion/', {'username': 'ok', 'password': 'Bon-mot-de-passe-1x'}).status_code == 302
    assert settings.SESSION_COOKIE_AGE == 1800 and settings.SESSION_SAVE_EVERY_REQUEST is True
    assert settings.AXES_FAILURE_LIMIT == 5 and settings.AXES_COOLOFF_TIME.total_seconds() == 1800


def test_F01_csp_en_rapport_seulement(client, db):
    r = client.get('/connexion/')
    assert 'Content-Security-Policy-Report-Only' in r.headers
    assert 'Content-Security-Policy' not in r.headers


# ------------------------------------------------------------------ refus

def test_F02_add_user_post_refuse_aux_non_superutilisateurs(client, jeu, simple):
    client.force_login(simple)
    avant = Compte.objects.count()
    r = client.post(reverse('add-user'), {'username': 'intrus', 'email': 'i@example.invalid'})
    assert r.status_code == 403 and Compte.objects.count() == avant


def test_F02_adminer_membre_ayant_deja_un_compte(client, jeu):
    # le jeu lie déjà le SU au membre : pas de nouveau compte, pas de mot de passe affiché
    client.force_login(jeu['compte'])
    avant = Compte.objects.count()
    r = client.post(reverse('adminer', kwargs={'id': jeu['membre'].id}))
    assert r.status_code == 302 and Compte.objects.count() == avant
    assert 'temporaire' not in ' '.join(str(m) for m in get_messages(r.wsgi_request)).lower()


def test_F02_middleware_repond_403_json_sur_l_api(client, db):
    c = Compte.objects.create_user('force', password='Temporaire-123x', doit_changer_mot_de_passe=True)
    client.force_login(c)
    r = client.get('/api/v1/sante/')
    assert r.status_code == 403 and r['Content-Type'].startswith('application/json')
    assert 'detail' in r.json()


def test_F04_securite_anonyme_redirige_vers_la_connexion(client, db):
    r = client.get('/mon-compte/securite/')
    assert r.status_code == 302 and r['Location'].startswith('/connexion/')
    assert client.post('/mon-compte/securite/').status_code == 302
