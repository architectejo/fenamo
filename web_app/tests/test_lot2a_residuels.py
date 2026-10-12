"""Résiduels du sous-lot 2a : verrou IP sur l'admin, paramètres sensibles, mot de passe changé via l'admin."""
from compte.models import Compte
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

MDP = 'Bon-mot-de-passe-1x'


def test_F01_verrou_ip_applique_a_la_connexion_de_l_admin(client, db, settings):
    settings.IP_ECHECS_MAX = 3
    for i in range(3):
        client.post('/connexion/', {'username': f'x{i}', 'password': 'faux'})
    r = client.post('/gestion-technique/login/', {'username': 'x9', 'password': 'faux'})
    assert r.status_code == 429
    assert client.get('/gestion-technique/login/').status_code == 200  # la page elle-même reste lisible


def test_F01_admin_login_normal_sans_verrou(client, db):
    Compte.objects.create_superuser('root', 'r@example.invalid', MDP)
    r = client.post('/gestion-technique/login/', {'username': 'root', 'password': MDP, 'next': '/gestion-technique/'})
    assert r.status_code == 302


def test_F01_parametres_sensibles_masques(client, db):
    c = Compte.objects.create_user('u', password=MDP)
    r = client.post('/connexion/', {'username': 'u', 'password': 'faux'})
    assert list(r.wsgi_request.sensitive_post_parameters) == ['password']
    client.force_login(c)
    r = client.post('/mon-compte/securite/', {'old_password': 'x'})
    assert set(r.wsgi_request.sensitive_post_parameters) == {'old_password', 'new_password1', 'new_password2'}


def test_F04_mot_de_passe_change_par_un_su_dans_l_admin_doit_etre_change(client, jeu):
    cible = Compte.objects.create_user('cible', password=MDP)
    assert not cible.doit_changer_mot_de_passe
    client.force_login(jeu['compte'])
    r = client.post(f'/gestion-technique/compte/compte/{cible.pk}/password/',
                    {'password1': 'Nouveau-mdp-admin-5521', 'password2': 'Nouveau-mdp-admin-5521'})
    assert r.status_code == 302
    cible.refresh_from_db()
    assert cible.doit_changer_mot_de_passe and cible.check_password('Nouveau-mdp-admin-5521')


def test_F04_admin_sans_changement_de_mot_de_passe_ne_force_rien(client, jeu):
    cible = Compte.objects.create_user('cible2', password=MDP)
    client.force_login(jeu['compte'])
    client.post(f'/gestion-technique/compte/compte/{cible.pk}/password/', {'password1': 'a', 'password2': 'b'})
    cible.refresh_from_db()
    assert not cible.doit_changer_mot_de_passe


def test_F01_commande_debloquer_ip(client, db, settings):
    from django.core.management import call_command
    settings.IP_ECHECS_MAX = 3
    for i in range(3):
        client.post('/connexion/', {'username': f'x{i}', 'password': 'faux'})
    assert client.post('/connexion/', {'username': 'bon', 'password': 'faux'}).status_code == 429
    call_command('debloquer_ip', '127.0.0.1')
    assert client.post('/connexion/', {'username': 'bon', 'password': 'faux'}).status_code == 200
