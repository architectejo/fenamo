"""Validation indépendante 2e (testeur) : matrice rôle x route de l'écran Utilisateurs (F-02, F-03, F-05, F-06).

Profils : su, pr, vn, vp (coordination P), va (antenne A de P), at, vi, ed, nu (sans nomination ni privilège), hors (validateur
provincial d'une AUTRE coordination Q), anonyme. Cible des actions : un agent de terrain (AT) de l'antenne A, nommé par le SU.
Attendus : 302 anonyme ; 403 pour qui ne peut nommer aucun rôle (at, vi, ed, nu) ; 404 hors périmètre (hors) ; 200 ou 204 pour qui gère.
"""
from datetime import date

import pytest
from django.test import Client
from django.urls import reverse

from compte import roles
from compte.models import Compte, JournalAction, Nomination
from compte.services.nominations import creer_nomination
from coptapp.models import Antenne, Membre, Province
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

PROFILS = ('su', 'pr', 'vn', 'vp', 'va', 'at', 'vi', 'ed', 'nu', 'hors')
GERANTS = ('su', 'pr', 'vn', 'vp', 'va')  # peuvent nommer au moins un rôle ET gérer l'AT de l'antenne A


@pytest.fixture
def monde(jeu):
    P = jeu['province']
    Q = Province.objects.create(nom='Quest', sigle='QU', code='QU')
    Antenne.objects.filter(pk=jeu['antenne'].pk).update(coordination=P)
    A = Antenne.objects.get(pk=jeu['antenne'].pk)
    AQ = Antenne.objects.create(nom='Antenne Q', coordination=Q)
    su = jeu['compte']
    comptes = {'su': su}

    def nommer(nom, role, **perimetre):
        c = Compte.objects.create_user(nom, password='x')
        creer_nomination(su, c, role, **perimetre)
        return Compte.objects.get(pk=c.pk)

    comptes.update(pr=nommer('pr', roles.PR), vn=nommer('vn', roles.VN), vp=nommer('vp', roles.VP, coordination=P),
                   va=nommer('va', roles.VA, antenne=A), at=nommer('at', roles.AT, antenne=A), vi=nommer('vi', roles.VI),
                   ed=nommer('ed', roles.ED), hors=nommer('hors', roles.VP, coordination=Q))
    comptes['nu'] = Compte.objects.create_user('nu', password='x')
    cible = nommer('cible-at', roles.AT, antenne=A)
    actif = Membre.objects.create(nom='Actif Nommable', date_naissance=date(1990, 1, 1), province=P, antenne=A,
                                  structure=jeu['association'], etat='actif')
    return {**jeu, 'comptes': comptes, 'cible': cible, 'P': P, 'Q': Q, 'A': A, 'AQ': AQ, 'membre_actif': actif}


def _url(nom, cible=None):
    return reverse(nom, kwargs={'id': cible.id}) if cible is not None else reverse(nom)


# (route, avec_cible, données POST valides ou None si GET seulement, attendu POST des gérants)
def _donnees(monde):
    return {
        'utilisateurs-nommer': {'membre': monde['membre_actif'].id, 'role': 'AT', 'antenne': monde['A'].id},
        'utilisateurs-externe': {'username': 'ext-visiteur', 'type': 'VI', 'portee': 'national'},
        'utilisateurs-reinitialiser': {},
        'utilisateurs-desactiver': {'motif': 'Départ de la fédération'},
        'utilisateurs-reactiver': {},
        'utilisateurs-role': {'role': 'AT', 'antenne': monde['A'].id, 'motif': 'test'},
        'utilisateurs-renouveler': {'motif': 'test'},
    }


ROUTES_CIBLE = ('utilisateurs-reinitialiser', 'utilisateurs-desactiver', 'utilisateurs-reactiver', 'utilisateurs-role',
                'utilisateurs-renouveler')
ROUTES_SANS_CIBLE = ('utilisateurs-nommer', 'utilisateurs-externe')
TOUTES_LES_ROUTES = ('utilisateurs', 'utilisateurs-membres-nommables', *ROUTES_SANS_CIBLE, *ROUTES_CIBLE)


def test_F21_roles_les_9_routes_utilisateurs_sont_dans_la_matrice():
    from tests.test_F21_trous_matrice_reval import TOUTES
    declarees = {nom for nom, _m, _v in TOUTES if nom.startswith('utilisateurs')}
    assert declarees == set(TOUTES_LES_ROUTES) and len(declarees) == 9


# ---------------------------------------------------------------- GET : liste, recherche, modales

@pytest.mark.parametrize('profil', PROFILS)
@pytest.mark.parametrize('route', ['utilisateurs', 'utilisateurs-membres-nommables', 'utilisateurs-nommer', 'utilisateurs-externe'])
def test_F21_roles_get_sans_cible(client, monde, route, profil):
    client.force_login(monde['comptes'][profil])
    attendu = 200 if profil in ('su', 'pr', 'vn', 'vp', 'va', 'hors') else 403
    if route == 'utilisateurs-externe':
        attendu = 200 if profil in ('su', 'pr') else 403  # compte externe : SU et PR seulement
    assert client.get(_url(route)).status_code == attendu, (profil, route)


@pytest.mark.parametrize('profil', PROFILS)
@pytest.mark.parametrize('route', ROUTES_CIBLE)
def test_F21_roles_get_modale_sur_un_compte(client, monde, route, profil):
    client.force_login(monde['comptes'][profil])
    attendu = 200 if profil in GERANTS else (404 if profil == 'hors' else 403)
    r = client.get(_url(route, monde['cible']))
    assert r.status_code == attendu, (profil, route)
    assert attendu != 200 or b'<html' not in r.content  # une modale est toujours un fragment


@pytest.mark.parametrize('route', TOUTES_LES_ROUTES)
def test_F21_roles_anonyme_redirige_vers_la_connexion(client, monde, route):
    url = _url(route, monde['cible'] if route in ROUTES_CIBLE else None)
    for methode in ('get', 'post'):
        r = getattr(client, methode)(url)
        assert r.status_code == 302 and '/connexion/' in r['Location'], (route, methode)


@pytest.mark.parametrize('profil', ['su', 'pr', 'va'])
def test_F21_roles_personne_n_agit_sur_son_propre_compte(client, monde, profil):
    client.force_login(monde['comptes'][profil])
    moi = monde['comptes'][profil]
    for route in ROUTES_CIBLE:
        assert client.get(_url(route, moi)).status_code == 403, route
        assert client.post(_url(route, moi), _donnees(monde)[route]).status_code == 403, route
    moi.refresh_from_db()
    assert moi.is_active


@pytest.mark.parametrize('profil', ['pr', 'vn', 'vp', 'va'])
def test_F21_roles_un_compte_su_est_invisible_pour_les_autres_roles(client, monde, profil):
    client.force_login(monde['comptes'][profil])
    for route in ROUTES_CIBLE:
        assert client.get(_url(route, monde['comptes']['su'])).status_code == 404, route
        assert client.post(_url(route, monde['comptes']['su']), _donnees(monde)[route]).status_code == 404, route


def test_F21_roles_compte_inconnu_404(client, monde):
    client.force_login(monde['comptes']['su'])
    for route in ROUTES_CIBLE:
        assert client.get(reverse(route, kwargs={'id': 999999})).status_code == 404


# ---------------------------------------------------------------- POST : effet réel selon le profil

@pytest.mark.parametrize('profil', PROFILS)
@pytest.mark.parametrize('route', ROUTES_CIBLE)
def test_F21_roles_post_sur_un_compte(client, monde, route, profil):
    cible = monde['cible']
    if route == 'utilisateurs-reactiver':
        Compte.objects.filter(pk=cible.pk).update(is_active=False)
    client.force_login(monde['comptes'][profil])
    avant = Compte.objects.get(pk=cible.pk).password
    r = client.post(_url(route, cible), _donnees(monde)[route])
    gere = profil in GERANTS
    attendu = (200, 204) if gere else ((404,) if profil == 'hors' else (403,))
    assert r.status_code in attendu, (profil, route, r.status_code)
    apres = Compte.objects.get(pk=cible.pk)
    if not gere:  # refus : rien n'a bougé, aucune ligne de journal
        assert apres.password == avant and apres.is_active == (route != 'utilisateurs-reactiver')
        assert Nomination.objects.filter(compte=cible).count() == 1
        assert not JournalAction.objects.filter(auteur=monde['comptes'][profil]).exclude(
            action__in=(JournalAction.Action.CONNEXION,)).exists()
    elif route == 'utilisateurs-reinitialiser':
        assert apres.password != avant and apres.doit_changer_mot_de_passe
    elif route == 'utilisateurs-desactiver':
        assert not apres.is_active
    elif route == 'utilisateurs-reactiver':
        assert apres.is_active
    else:  # changement de rôle ou renouvellement : l'ancienne nomination est conservée, une nouvelle est active
        assert Nomination.objects.filter(compte=cible).count() == 2 and Nomination.objects.filter(compte=cible, active=True).count() == 1


@pytest.mark.parametrize('profil', PROFILS)
def test_F21_roles_post_nommer(client, monde, profil):
    client.force_login(monde['comptes'][profil])
    avant = Compte.objects.count()
    r = client.post(_url('utilisateurs-nommer'), _donnees(monde)['utilisateurs-nommer'])
    if profil in GERANTS:
        assert r.status_code == 200 and Compte.objects.count() == avant + 1  # compte créé : le mot de passe est affiché
        assert Nomination.objects.filter(membre=monde['membre_actif'], role='AT', active=True).exists()
    else:
        assert r.status_code == (404 if profil == 'hors' else 403) and Compte.objects.count() == avant
        assert not Nomination.objects.filter(membre=monde['membre_actif']).exists()


@pytest.mark.parametrize('profil', PROFILS)
def test_F21_roles_post_compte_externe(client, monde, profil):
    client.force_login(monde['comptes'][profil])
    avant = Compte.objects.count()
    r = client.post(_url('utilisateurs-externe'), _donnees(monde)['utilisateurs-externe'])
    if profil in ('su', 'pr'):
        assert r.status_code == 200 and Compte.objects.filter(username='ext-visiteur').exists()
    else:
        assert r.status_code == 403 and Compte.objects.count() == avant


def test_F21_roles_editeur_externe_reserve_au_su(client, monde):
    client.force_login(monde['comptes']['pr'])
    r = client.post(_url('utilisateurs-externe'), {'username': 'ext-ed', 'type': 'ED', 'portee': 'national'})
    assert r.status_code == 403 and not Compte.objects.filter(username='ext-ed').exists()
    client.force_login(monde['comptes']['su'])
    assert client.post(_url('utilisateurs-externe'), {'username': 'ext-ed', 'type': 'ED'}).status_code == 200


# ---------------------------------------------------------------- GET ne modifie rien ; CSRF exigé

def _instantane():
    return (list(Compte.objects.order_by('pk').values_list('pk', 'password', 'is_active', 'doit_changer_mot_de_passe')),
            list(Nomination.objects.order_by('pk').values_list('pk', 'role', 'active', 'fin')),
            JournalAction.objects.count())


@pytest.mark.parametrize('profil', PROFILS)
def test_F21_roles_get_ne_modifie_aucune_donnee(client, monde, profil):
    """Les routes d'action répondent à GET par la modale (200) et ne modifient rien : pas de 405 attendu, pas d'effet."""
    client.force_login(monde['comptes'][profil])
    avant = _instantane()
    for route in TOUTES_LES_ROUTES:
        client.get(_url(route, monde['cible'] if route in ROUTES_CIBLE else None), {'membre': monde['membre_actif'].id})
    assert _instantane() == avant


@pytest.mark.parametrize('route', [r for r in TOUTES_LES_ROUTES if r not in ('utilisateurs', 'utilisateurs-membres-nommables')])
def test_F21_roles_post_sans_jeton_csrf_refuse(monde, route):
    c = Client(enforce_csrf_checks=True)
    c.force_login(monde['comptes']['su'])
    avant = _instantane()
    r = c.post(_url(route, monde['cible'] if route in ROUTES_CIBLE else None), _donnees(monde)[route])
    assert r.status_code == 403
    assert _instantane() == avant


@pytest.mark.parametrize('route', ['utilisateurs', 'utilisateurs-membres-nommables'])
def test_F21_roles_liste_et_recherche_n_acceptent_pas_post(client, monde, route):
    client.force_login(monde['comptes']['su'])
    assert client.post(_url(route)).status_code == 405


@pytest.mark.parametrize('route', [r for r in ROUTES_CIBLE + ROUTES_SANS_CIBLE])
def test_F21_roles_put_delete_refuses(client, monde, route):
    client.force_login(monde['comptes']['su'])
    url = _url(route, monde['cible'] if route in ROUTES_CIBLE else None)
    assert client.put(url).status_code == 405 and client.delete(url).status_code == 405


# ---------------------------------------------------------------- périmètre des listes

def test_F21_roles_liste_limitee_au_perimetre(client, monde):
    """Le VP de P ne voit pas les comptes de la coordination Q ; le VP de Q ne voit pas ceux de P."""
    autre = Compte.objects.create_user('agent-de-q', password='x')
    creer_nomination(monde['comptes']['su'], autre, roles.AT, antenne=monde['AQ'])
    client.force_login(monde['comptes']['vp'])
    page = client.get(_url('utilisateurs')).content.decode()
    assert 'cible-at' in page and 'agent-de-q' not in page
    client.force_login(monde['comptes']['hors'])
    page = client.get(_url('utilisateurs')).content.decode()
    assert 'agent-de-q' in page and 'cible-at' not in page
    assert client.get(_url('utilisateurs-desactiver', autre)).status_code == 200
    assert client.get(_url('utilisateurs-desactiver', monde['cible'])).status_code == 404


def test_F21_roles_recherche_de_membre_hors_perimetre_vide(client, monde):
    autre = Membre.objects.create(nom='Zoulou Hors Perimetre', province=monde['Q'], antenne=monde['AQ'], etat='actif')
    client.force_login(monde['comptes']['vp'])
    corps = client.get(_url('utilisateurs-membres-nommables'), {'q': 'Zoulou'}).content.decode()
    assert 'Zoulou' not in corps
    client.force_login(monde['comptes']['pr'])
    assert 'Zoulou' in client.get(_url('utilisateurs-membres-nommables'), {'q': 'Zoulou'}).content.decode()
    assert autre.pk
