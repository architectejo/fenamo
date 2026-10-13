"""Validation du sous-lot 2a : connexion obligatoire, POST seulement, comptes, admin, gabarits, déploiement."""
import os
import re
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from django.apps import apps
from django.contrib.sessions.models import Session
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from compte.models import Compte
from tests.test_plan_url import ROUTES_POST_SEULEMENT, hachage_rapide, jeu, table  # noqa: F401

RACINE = Path(__file__).resolve().parent.parent
MDP = 'Bon-mot-de-passe-1x'
POST_SEUL = sorted(ROUTES_POST_SEULEMENT)  # contient 'deconnexion'


def _cible(jeu, nom):
    return next(c for n, _, c in table(jeu) if n == nom)


def _urls_ecrans(jeu):
    """Annexe B hors exemptions : connexion, santé de l'API, /mob/, /ancien-site/."""
    return [(n, c) for n, _, c in table(jeu) if n != 'application']


# ----------------------------------------------------------- (1) connexion obligatoire

@pytest.mark.parametrize('methode', ['get', 'post'])
def test_F01_anonyme_302_vers_connexion_sur_toute_l_annexe_B(jeu, methode):
    c = Client()
    fautifs = []
    for nom, cible in _urls_ecrans(jeu):
        r = getattr(c, methode)(cible)
        if r.status_code != 302 or not r['Location'].startswith('/connexion/'):
            fautifs.append((nom, r.status_code))
    assert fautifs == []


def test_F01_anonyme_htmx_hx_redirect_sur_toute_l_annexe_B(jeu):
    c = Client()
    fautifs = []
    for nom, cible in _urls_ecrans(jeu):
        r = c.get(cible, HTTP_HX_REQUEST='true')
        if not r.headers.get('HX-Redirect', '').startswith('/connexion/'):
            fautifs.append((nom, r.status_code))
    assert fautifs == []


def test_F01_anonyme_admin_et_configuration_site(jeu):
    c = Client()
    r = c.get('/gestion-technique/')
    assert r.status_code == 302 and '/gestion-technique/login/' in r['Location']
    assert c.get('/contenu-site/configuration/').status_code == 302


def test_F01_exemptions_acceptees(client, db):
    assert client.get('/connexion/').status_code == 200
    assert client.get('/api/v1/').status_code == 200
    assert client.get('/mob/').status_code == 200
    assert client.get('/ancien-site/').status_code == 200


# ----------------------------------------------------------- (2) routes POST seulement

@pytest.mark.parametrize('nom', POST_SEUL)
def test_F01_route_post_seulement_405_en_get(jeu, nom):
    c = Client(enforce_csrf_checks=True)
    c.force_login(jeu['compte'])
    assert c.get(_cible(jeu, nom)).status_code == 405


@pytest.mark.parametrize('nom', POST_SEUL)
def test_F01_route_post_seulement_refuse_sans_jeton_csrf(jeu, nom):
    c = Client(enforce_csrf_checks=True)
    c.force_login(jeu['compte'])
    assert c.post(_cible(jeu, nom)).status_code == 403


@pytest.mark.parametrize('nom', POST_SEUL)
def test_F01_route_post_seulement_fonctionne_avec_csrf(jeu, nom):
    c = Client(enforce_csrf_checks=True)
    c.force_login(jeu['compte'])
    c.get('/')  # dépose le cookie CSRF
    jeton = c.cookies['csrftoken'].value
    donnees = {'csrfmiddlewaretoken': jeton}
    if nom == 'moto-attribution':
        donnees['numero'] = jeu['moto'].numero
    if nom == 'delete-membre':
        donnees.update({'action': 'executer', 'motif': 'Test CSRF'})
    r = c.post(_cible(jeu, nom), donnees)
    assert r.status_code in (200, 302), (nom, r.status_code)


def test_F01_moto_attribution_sans_numero_ne_plante_pas(jeu):
    c = Client(raise_request_exception=False)
    c.force_login(jeu['compte'])
    r = c.post(_cible(jeu, 'moto-attribution'))
    assert r.status_code < 500


def test_F01_contact_view_get_sans_effet_post_avec_csrf_marque_traite(jeu):
    c = Client(enforce_csrf_checks=True)
    c.force_login(jeu['compte'])
    url = _cible(jeu, 'contact-view')
    assert c.get(url).status_code == 200
    jeu['contact'].refresh_from_db()
    assert not jeu['contact'].traiter
    assert c.post(url).status_code == 403
    c.get('/')
    c.post(url, {'csrfmiddlewaretoken': c.cookies['csrftoken'].value})
    jeu['contact'].refresh_from_db()
    assert jeu['contact'].traiter


def test_F01_aucun_get_ne_modifie_les_donnees(jeu):
    c = Client()
    c.force_login(jeu['compte'])
    modeles = [m for m in apps.get_models() if m._meta.app_label in ('coptapp', 'compte', 'virtrine')]
    avant = {m: m.objects.count() for m in modeles}
    etat_contact = jeu['contact'].traiter
    for nom, _, cible in table(jeu):
        if nom in ROUTES_POST_SEULEMENT:
            continue
        c.get(cible)
        c.get(cible, HTTP_HX_REQUEST='true')
    assert {m: m.objects.count() for m in modeles} == avant
    jeu['contact'].refresh_from_db()
    assert jeu['contact'].traiter == etat_contact


# ----------------------------------------------------------- (3) F-01 verrou et session

def test_F01_blocage_apres_5_echecs_avec_message(db):
    Compte.objects.create_user('cible', password=MDP)
    c = Client()
    for _ in range(4):
        r = c.post('/connexion/', {'username': 'cible', 'password': 'faux'})
        assert r.status_code == 200 and 'incorrect' in r.content.decode()
    r = c.post('/connexion/', {'username': 'cible', 'password': 'faux'})
    assert r.status_code == 429
    corps = r.content.decode()
    assert 'bloquée' in corps and 'Trop de tentatives' in corps
    assert c.post('/connexion/', {'username': 'cible', 'password': MDP}).status_code == 429


def test_F01_reussite_remet_le_compteur_a_zero(db):
    Compte.objects.create_user('cible', password=MDP)
    c = Client()
    for _ in range(3):
        c.post('/connexion/', {'username': 'cible', 'password': 'faux'})
    assert c.post('/connexion/', {'username': 'cible', 'password': MDP}).status_code == 302
    c.post('/deconnexion/')
    for _ in range(3):
        assert c.post('/connexion/', {'username': 'cible', 'password': 'faux'}).status_code == 200


def test_F01_session_expiree_redirige_vers_connexion(jeu):
    c = Client()
    c.force_login(jeu['compte'])
    assert c.get('/membres/').status_code == 200
    Session.objects.all().delete()
    r = c.get('/membres/')
    assert r.status_code == 302 and r['Location'].startswith('/connexion/')
    assert c.get('/membres/', HTTP_HX_REQUEST='true').headers['HX-Redirect'].startswith('/connexion/')


def test_F01_session_dont_la_date_est_depassee(jeu):
    c = Client()
    c.force_login(jeu['compte'])
    Session.objects.update(expire_date=timezone.now() - timedelta(seconds=1))
    assert c.get('/membres/').status_code == 302


def test_F01_session_30_minutes_glissante(settings):
    assert settings.SESSION_COOKIE_AGE == 1800
    assert settings.SESSION_SAVE_EVERY_REQUEST is True and settings.SESSION_COOKIE_HTTPONLY is True


# ----------------------------------------------------------- (4) F-04 mot de passe

def test_F04_ancien_mot_de_passe_exige(db):
    c = Client()
    u = Compte.objects.create_user('u', password=MDP)
    c.force_login(u)
    nouveau = {'new_password1': 'Nouveau-mdp-9876', 'new_password2': 'Nouveau-mdp-9876'}
    assert c.post(reverse('securite'), nouveau).status_code == 200
    assert c.post(reverse('securite'), {**nouveau, 'old_password': 'faux'}).status_code == 200
    u.refresh_from_db()
    assert u.check_password(MDP)


@pytest.mark.parametrize('mdp', ['12345678', 'court1A', 'password', 'u'])
def test_F04_nouveau_mot_de_passe_valide_par_validate_password(db, mdp):
    c = Client()
    u = Compte.objects.create_user('u', password=MDP)
    c.force_login(u)
    r = c.post(reverse('securite'), {'old_password': MDP, 'new_password1': mdp, 'new_password2': mdp})
    assert r.status_code == 200
    u.refresh_from_db()
    assert u.check_password(MDP)


def test_F04_confirmation_differente_refusee(db):
    c = Client()
    u = Compte.objects.create_user('u', password=MDP)
    c.force_login(u)
    r = c.post(reverse('securite'), {
        'old_password': MDP, 'new_password1': 'Nouveau-mdp-9876', 'new_password2': 'Autre-mdp-98765'})
    assert r.status_code == 200
    u.refresh_from_db()
    assert u.check_password(MDP)


def test_F04_securite_exige_la_connexion_et_le_csrf(db):
    assert Client().post(reverse('securite')).status_code == 302
    c = Client(enforce_csrf_checks=True)
    c.force_login(Compte.objects.create_user('u', password=MDP))
    assert c.post(reverse('securite'), {'old_password': MDP}).status_code == 403


def test_F04_securite_d_un_autre_membre_ne_change_pas_son_mot_de_passe(jeu):
    simple = Compte.objects.create_user('simple', password=MDP)
    c = Client()
    c.force_login(simple)
    url = f"/mon-compte/securite/{jeu['membre'].id}/"  # ancienne adresse retirée
    assert c.post(url).status_code == 404
    c.post(url, {'old_password': MDP, 'new_password1': 'Nouveau-mdp-9876', 'new_password2': 'Nouveau-mdp-9876'})
    jeu['compte'].refresh_from_db()
    assert jeu['compte'].check_password('mot-de-passe-test-123')


# ----------------------------------------------------------- (5) création de comptes

def test_F04_add_user_refuse_aux_non_superutilisateurs(jeu):
    simple = Compte.objects.create_user('simple', password=MDP)
    c = Client()
    c.force_login(simple)
    avant = Compte.objects.count()
    assert c.get(reverse('add-user')).status_code == 403
    assert c.post(reverse('add-user'), {'username': 'intrus', 'email': 'i@example.invalid'}).status_code == 403
    assert c.post(reverse('adminer', kwargs={'id': jeu['membre'].id})).status_code == 403
    assert Compte.objects.count() == avant


def test_F04_add_user_mot_de_passe_aleatoire_et_unique(jeu):
    c = Client()
    c.force_login(jeu['compte'])
    mots = set()
    for i in range(3):
        r = c.post(reverse('add-user'), {'username': f'nouv{i}', 'email': f'n{i}@example.invalid'})
        assert r.status_code == 200
        corps = r.content.decode()
        assert 'mot de passe temporaire : ' in corps
        mots.add(corps.split('mot de passe temporaire : ')[1].split(' ')[0])
        compte = Compte.objects.get(username=f'nouv{i}')
        assert compte.doit_changer_mot_de_passe and not compte.is_superuser and not compte.is_staff
    assert len(mots) == 3


def test_F04_add_user_refuse_pseudo_en_double(jeu):
    c = Client()
    c.force_login(jeu['compte'])
    r = c.post(reverse('add-user'), {'username': 'admin-test', 'email': 'x@example.invalid'})
    assert r.status_code == 200
    assert Compte.objects.filter(username='admin-test').count() == 1


def test_F04_premiere_connexion_force_la_redirection_mais_laisse_la_deconnexion(db):
    Compte.objects.create_user('premier', password=MDP, doit_changer_mot_de_passe=True)
    c = Client()
    assert c.post('/connexion/', {'username': 'premier', 'password': MDP}).status_code == 302
    for url in ('/', '/membres/', '/notifications/'):
        r = c.get(url)
        assert r.status_code == 302 and r['Location'] == reverse('securite'), url
        assert c.get(url, HTTP_HX_REQUEST='true')['HX-Redirect'] == reverse('securite')
    assert c.post('/deconnexion/').status_code == 302


# ----------------------------------------------------------- (6) admin

def test_F04_gestion_technique_interdite_aux_non_superusers(jeu):
    simple = Compte.objects.create_user('simple', password=MDP)
    staff = Compte.objects.create_user('staff', password=MDP, is_staff=True)
    for compte in (simple, staff):
        c = Client()
        c.force_login(compte)
        for url in ('/gestion-technique/', '/gestion-technique/compte/compte/',
                    '/gestion-technique/compte/compte/add/', '/gestion-technique/coptapp/membre/'):
            r = c.get(url)
            assert r.status_code in (302, 403, 404), (compte.username, url, r.status_code)


def test_F04_admin_accessible_au_superuser(jeu):
    c = Client()
    c.force_login(jeu['compte'])
    assert c.get('/gestion-technique/compte/compte/').status_code == 200


def test_F04_membre_password_absent_de_l_admin(jeu):
    c = Client()
    c.force_login(jeu['compte'])
    html = c.get(f"/gestion-technique/coptapp/membre/{jeu['membre'].id}/change/").content.decode()
    assert 'name="password"' not in html and 'id_password' not in html
    assert 'column-password' not in c.get('/gestion-technique/coptapp/membre/').content.decode()


def test_F04_admin_hache_le_mot_de_passe_et_valide_sa_force(jeu):
    c = Client()
    c.force_login(jeu['compte'])
    c.post('/gestion-technique/compte/compte/add/', {
        'username': 'cree-admin', 'password1': 'Mdp-admin-test-7391', 'password2': 'Mdp-admin-test-7391'})
    assert 'Mdp-admin' not in Compte.objects.get(username='cree-admin').password
    r = c.post('/gestion-technique/compte/compte/add/', {
        'username': 'faible', 'password1': '12345678', 'password2': '12345678'})
    assert r.status_code == 200 and not Compte.objects.filter(username='faible').exists()


# ----------------------------------------------------------- (7) gabarits

def _gabarits():
    dossiers = [RACINE / 'templates', *RACINE.glob('*/templates')]
    return sorted({p for d in dossiers if d.exists() for p in d.rglob('*.html')})


def test_F01_aucun_lien_a_href_vers_une_route_post_seulement(jeu):
    fautifs = []
    for p in _gabarits():
        texte = p.read_text(encoding='utf-8')
        for balise in re.findall(r'<a\b[^>]*>', texte, flags=re.S):
            m = re.search(r'href\s*=\s*"([^"]*)"', balise)
            if not m:
                continue
            for nom in POST_SEUL:
                if re.search(r"\{%\s*url\s+['\"]" + re.escape(nom) + r"['\"]", m.group(1)):
                    fautifs.append((p.name, nom))
    assert fautifs == []


def test_F01_aucun_hx_get_vers_une_route_post_seulement():
    fautifs = []
    for p in _gabarits():
        texte = p.read_text(encoding='utf-8')
        for nom in POST_SEUL:
            if re.search(r"hx-get\s*=\s*\"[^\"]*\{%\s*url\s+['\"]" + re.escape(nom) + r"['\"]", texte):
                fautifs.append((p.name, nom))
    assert fautifs == []


def test_F01_formulaires_post_ont_un_jeton_csrf():
    fautifs = []
    for p in _gabarits():
        texte = p.read_text(encoding='utf-8')
        for m in re.finditer(r'<form\b[^>]*method\s*=\s*"post"[^>]*>(.*?)</form>', texte, flags=re.S | re.I):
            if 'csrf_token' not in m.group(0):
                fautifs.append(p.name)
    assert fautifs == []


def test_F01_aucun_filtre_safe_dans_virtrine_et_site():
    fautifs = []
    for p in (RACINE / 'virtrine' / 'templates').rglob('*.html'):
        if re.search(r'\|\s*safe\b|\{%\s*autoescape\s+off|integration_code', p.read_text(encoding='utf-8')):
            fautifs.append(str(p.relative_to(RACINE)))
    for p in (RACINE / 'templates').rglob('*.html'):
        if 'site' in p.parts and re.search(r'\|\s*safe\b', p.read_text(encoding='utf-8')):
            fautifs.append(str(p.relative_to(RACINE)))
    assert fautifs == []


def test_F01_aucun_cdn_dans_les_gabarits():
    motif = re.compile(r'cdn\.|cdnjs|jsdelivr|unpkg|googleapis|gstatic|bootstrapcdn')
    ressource = re.compile(r'(?:src|href)\s*=\s*["\']\s*(?:https?:)?//', re.I)
    fautifs = []
    for p in _gabarits():
        for ligne in p.read_text(encoding='utf-8').splitlines():
            if motif.search(ligne) or (ressource.search(ligne) and not re.search(r'<a\b', ligne)):
                fautifs.append((p.name, ligne.strip()[:100]))
    assert fautifs == []


# ----------------------------------------------------------- (8) déploiement

def _manage(*args, env=None):
    return subprocess.run(
        [sys.executable, 'manage.py', *args], cwd=RACINE, capture_output=True, text=True,
        env={**os.environ, **(env or {})}, timeout=300)


def test_F01_pas_de_migration_manquante():
    r = _manage('makemigrations', '--check', '--dry-run')
    assert r.returncode == 0, r.stdout + r.stderr


def test_F01_check_deploy_production():
    r = _manage('check', '--deploy', '--fail-level', 'WARNING', env={
        'DJANGO_SETTINGS_MODULE': 'fenamo.settings.prod',
        'SECRET_KEY': 'x' * 60 + '!aZ9' * 5,
        'ALLOWED_HOSTS': 'app.fenamordc.cd',
        'CSRF_TRUSTED_ORIGINS': 'https://app.fenamordc.cd',
    })
    assert r.returncode == 0, r.stdout + r.stderr
