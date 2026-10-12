"""Passe de corrections du sous-lot 2a (rapports sécurité et relecteur)."""
import pytest
from django.urls import reverse

from compte.models import Compte
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

MDP = 'Bon-mot-de-passe-1x'


# ------------------------------------------------------------- C1 : privilèges réservés aux SU

@pytest.fixture
def pirate(jeu):
    Compte.objects.filter(pk=jeu['compte'].pk).update(membreId=None)
    return Compte.objects.create_user('pirate', password=MDP, membreId=jeu['membre'].id)


def test_F02_non_su_ne_peut_pas_s_attribuer_privilege5(client, jeu, pirate):
    client.force_login(pirate)
    url = reverse('membre-view', kwargs={'id': jeu['membre'].id})
    r = client.post(url, {'privilege': '1', 'privilege5': 'on', 'privilege1': 'on'})
    assert r.status_code == 403
    pirate.refresh_from_db()
    assert not any(getattr(pirate, f'privilege{i}') for i in range(1, 6))


def test_F02_su_attribue_les_privileges_et_journalise(client, jeu, pirate):
    from coptapp.models import Notification
    client.force_login(jeu['compte'])
    url = reverse('membre-view', kwargs={'id': jeu['membre'].id})
    assert client.post(url, {'privilege': '1', 'privilege3': 'on'}).status_code == 200
    pirate.refresh_from_db()
    assert pirate.privilege3 and not pirate.privilege5
    assert Notification.objects.filter(titre="Attribution des privilèges").exists()


# ------------------------------------------------------------- M1 : mot de passe jamais en cookie

def test_F04_adminer_mot_de_passe_dans_le_corps_pas_dans_les_cookies(client, jeu):
    Compte.objects.filter(pk=jeu['compte'].pk).update(membreId=None)
    client.force_login(jeu['compte'])
    r = client.post(reverse('adminer', kwargs={'id': jeu['membre'].id}))
    assert r.status_code == 200
    assert 'no-store' in r['Cache-Control']
    compte = Compte.objects.get(membreId=jeu['membre'].id)
    corps = r.content.decode()
    mdp = corps.split('<strong class="user-select-all">')[1].split('</strong>')[0]
    assert compte.check_password(mdp)
    cookies = ' '.join(m.value for m in r.cookies.values())
    assert mdp not in cookies and 'messages' not in r.cookies
    assert mdp not in client.get('/membres/').content.decode()  # affiché une seule fois


def test_F04_adminer_htmx_renvoie_le_fragment(client, jeu):
    Compte.objects.filter(pk=jeu['compte'].pk).update(membreId=None)
    client.force_login(jeu['compte'])
    r = client.post(reverse('adminer', kwargs={'id': jeu['membre'].id}), HTTP_HX_REQUEST='true')
    assert r.status_code == 200 and '<html' not in r.content.decode()


def test_F04_add_user_no_store(client, jeu):
    client.force_login(jeu['compte'])
    r = client.post(reverse('add-user'), {'username': 'nstore', 'email': 'n@example.invalid'})
    assert 'no-store' in r['Cache-Control']


def test_messages_stockes_en_session(settings):
    assert settings.MESSAGE_STORAGE.endswith('session.SessionStorage')


# ------------------------------------------------------------- M2 : verrou normalisé et par IP

def test_F04_verrou_insensible_a_la_casse_et_aux_espaces(client, db):
    Compte.objects.create_user('cible', password=MDP)
    for variante in ('cible', 'CIBLE', ' Cible ', 'cible', 'CiBle'):
        client.post('/connexion/', {'username': variante, 'password': 'faux'})
    assert client.post('/connexion/', {'username': 'cible', 'password': MDP}).status_code == 429


def test_F04_verrou_par_adresse_ip_seule(client, db, settings):
    settings.IP_ECHECS_MAX = 8
    Compte.objects.create_user('bon', password=MDP)
    for i in range(8):
        assert client.post('/connexion/', {'username': f'inconnu{i}', 'password': 'faux'}).status_code == 200
    # tous pseudos confondus : l'adresse est bloquée, même avec un pseudo sain et le bon mot de passe
    assert client.post('/connexion/', {'username': 'bon', 'password': MDP}).status_code == 429


# ------------------------------------------------------------- mot de passe : identique, admin

def test_F04_nouveau_mot_de_passe_identique_refuse(client, db):
    c = Compte.objects.create_user('u', password=MDP)
    client.force_login(c)
    r = client.post(reverse('securite'), {'old_password': MDP, 'new_password1': MDP, 'new_password2': MDP})
    assert r.status_code == 200 and 'différent de l' in r.content.decode()


def test_F04_compte_cree_par_l_admin_doit_changer_son_mot_de_passe(client, jeu):
    client.force_login(jeu['compte'])
    r = client.post('/gestion-technique/compte/compte/add/', {
        'username': 'par-admin', 'password1': 'Mdp-admin-test-7391', 'password2': 'Mdp-admin-test-7391'})
    assert r.status_code == 302
    assert Compte.objects.get(username='par-admin').doit_changer_mot_de_passe


# ------------------------------------------------------------- bouton « Créer le compte »

def test_F04_bouton_creer_le_compte_pour_les_su_seulement(client, jeu):
    Compte.objects.filter(pk=jeu['compte'].pk).update(membreId=None)
    url = reverse('membre-view', kwargs={'id': jeu['membre'].id})
    client.force_login(jeu['compte'])
    html = client.get(url).content.decode()
    assert 'Créer le compte' in html and 'Attribuer un rôle' not in html
    p5 = Compte.objects.create_user('p5', password=MDP, privilege5=True, privilege3=True)
    client.force_login(p5)
    assert 'Créer le compte' not in client.get(url).content.decode()
