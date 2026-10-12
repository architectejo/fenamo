"""Revalidation indépendante du sous-lot 2a après la passe de corrections (données fictives)."""
import pytest
from django.test import Client
from django.urls import reverse

from compte.models import Compte
from coptapp.models import Membre, Moto
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

MDP = 'Bon-mot-de-passe-1x'
PRIVS = [f'privilege{i}' for i in range(1, 6)]


def _privs(c):
    c.refresh_from_db()
    return [getattr(c, p) for p in PRIVS]


@pytest.fixture
def simple(jeu):
    Compte.objects.filter(pk=jeu['compte'].pk).update(membreId=None)
    return Compte.objects.create_user('simple', password=MDP, membreId=jeu['membre'].id)


@pytest.fixture
def autre(jeu):
    return Compte.objects.create_user('autre', password=MDP)


# (1) C1 : privilèges réservés aux SU
@pytest.mark.parametrize('champs', [
    {'privilege': '1', 'privilege5': 'on'},
    {'privilege': '1', 'privilege5': 'on', 'privilege1': 'on', 'privilege2': 'on'},
    {'privilege5': 'on'},
])
def test_F02_C1_simple_ne_modifie_pas_ses_privileges(client, jeu, simple, champs):
    client.force_login(simple)
    r = client.post(reverse('membre-view', kwargs={'id': jeu['membre'].id}), champs)
    if 'privilege' in champs:
        assert r.status_code == 403
    assert _privs(simple) == [False] * 5  # sans le marqueur « privilege » : ignoré, aucune modification


def test_F02_C1_simple_ne_modifie_pas_ceux_d_un_autre(client, jeu, simple, autre):
    m2 = Membre.objects.create(nom='Autre Fictif', date_naissance=jeu['membre'].date_naissance,
                               province=jeu['province'], ville=jeu['ville'],
                               antenne=jeu['antenne'], structure=jeu['association'])
    Compte.objects.filter(pk=autre.pk).update(membreId=m2.id)
    client.force_login(simple)
    r = client.post(reverse('membre-view', kwargs={'id': m2.id}), {'privilege': '1', 'privilege5': 'on'})
    assert r.status_code in (403, 404)
    assert _privs(autre) == [False] * 5 and _privs(simple) == [False] * 5


# (2) mot de passe temporaire d'adminer
def test_F02_adminer_mot_de_passe_unique_et_non_cache(client, jeu):
    Compte.objects.filter(pk=jeu['compte'].pk).update(membreId=None)
    client.force_login(jeu['compte'])
    r = client.post(reverse('adminer', kwargs={'id': jeu['membre'].id}))
    assert r.status_code == 200
    assert 'no-store' in r['Cache-Control']
    mdp = r.content.decode().split('<strong class="secret">')[1].split('</strong>')[0]
    assert Compte.objects.get(membreId=jeu['membre'].id).check_password(mdp)
    assert 'messages' not in r.cookies
    assert all(mdp not in m.value for m in r.cookies.values())
    for adresse in ('/membres/', reverse('membre-view', kwargs={'id': jeu['membre'].id}), '/'):
        assert mdp not in client.get(adresse).content.decode()


# (3) verrouillage (axes)
def test_F01_axes_casse_differente_meme_verrou(client, db):
    Compte.objects.create_user('Cible', password=MDP)
    for v in ('cible', 'CIBLE', 'Cible', ' cible', 'cIbLe'):
        client.post('/connexion/', {'username': v, 'password': 'faux'})
    assert client.post('/connexion/', {'username': 'CIBLE', 'password': MDP}).status_code == 429


def test_F01_axes_quatre_echecs_ne_verrouillent_pas(client, db):
    Compte.objects.create_user('tiede', password=MDP)
    for _ in range(4):
        client.post('/connexion/', {'username': 'tiede', 'password': 'faux'})
    assert client.post('/connexion/', {'username': 'tiede', 'password': MDP}).status_code == 302


def test_F01_axes_cinq_echecs_429(client, db):
    Compte.objects.create_user('cinq', password=MDP)
    for _ in range(5):
        client.post('/connexion/', {'username': 'cinq', 'password': 'faux'})
    assert client.post('/connexion/', {'username': 'cinq', 'password': 'faux'}).status_code == 429


def test_F01_axes_verrou_ip_atteint_bloque(client, db, settings):
    settings.IP_ECHECS_MAX = 6
    Compte.objects.create_user('sain', password=MDP)
    for i in range(6):
        client.post('/connexion/', {'username': f'x{i}', 'password': 'faux'})
    assert client.post('/connexion/', {'username': 'sain', 'password': MDP}).status_code == 429


def test_F01_axes_ip_sous_le_seuil_ne_bloque_pas_un_autre_utilisateur(client, db, settings):
    settings.IP_ECHECS_MAX = 10
    Compte.objects.create_user('sain', password=MDP)
    for i in range(6):
        client.post('/connexion/', {'username': f'y{i}', 'password': 'faux'})
    assert client.post('/connexion/', {'username': 'sain', 'password': MDP}).status_code == 302


# (4) changement de mot de passe
def test_F04_identique_a_l_ancien_refuse_et_rien_ne_change(client, db):
    c = Compte.objects.create_user('chg', password=MDP, doit_changer_mot_de_passe=True)
    client.force_login(c)
    r = client.post(reverse('securite'), {'old_password': MDP, 'new_password1': MDP, 'new_password2': MDP})
    assert r.status_code == 200
    c.refresh_from_db()
    assert c.doit_changer_mot_de_passe and c.check_password(MDP)


def test_F04_changement_valide_remet_le_drapeau_a_zero(client, db):
    c = Compte.objects.create_user('chg2', password=MDP, doit_changer_mot_de_passe=True)
    client.force_login(c)
    nouveau = 'Tout-autre-secret-84Q'
    r = client.post(reverse('securite'), {'old_password': MDP, 'new_password1': nouveau, 'new_password2': nouveau})
    assert r.status_code in (200, 302)
    c.refresh_from_db()
    assert c.check_password(nouveau) and c.doit_changer_mot_de_passe is False


def test_F04_compte_cree_via_admin_django_doit_changer(client, jeu):
    client.force_login(jeu['compte'])
    mdp = 'Mdp-admin-test-7391'
    r = client.post('/gestion-technique/compte/compte/add/',
                    {'username': 'cree-admin', 'password1': mdp, 'password2': mdp})
    assert r.status_code == 302
    assert Compte.objects.get(username='cree-admin').doit_changer_mot_de_passe is True


# (5) attributMoto
def _post(jeu, **d):
    c = Client(raise_request_exception=False)
    c.force_login(jeu['compte'])
    return c.post(reverse('moto-attribution', kwargs={'id': jeu['membre'].id}), d)


@pytest.mark.parametrize('donnees', [{}, {'numero': ''}, {'numero': 'INCONNU-999'}])
def test_F01_attributMoto_absent_ou_inconnu_pas_de_500(jeu, donnees):
    assert _post(jeu, **donnees).status_code < 500
    jeu['moto'].refresh_from_db()
    assert not jeu['moto'].motard_id


def test_F01_attributMoto_double_pas_de_500(jeu):
    Moto.objects.create(proprietaire=jeu['membre'], structure=jeu['association'], ville=jeu['ville'],
                        province=jeu['province'], abonnement=jeu['moto'].abonnement, numero=jeu['moto'].numero)
    assert _post(jeu, numero=jeu['moto'].numero).status_code < 500


# (6) santé
def test_F06_sante_et_racine_api_repondent(client, db):
    for adresse in ('/api/v1/sante/', '/api/v1/'):
        assert client.get(adresse).status_code == 200
