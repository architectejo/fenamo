"""Revalidation indépendante (testeur) : routes restées HORS de test_F21_matrice_routes.py.

1. On énumère toutes les routes déclarées (`urls.py` de coptapp, compte, virtrine, api, mobapp) et on les compare à la
   matrice existante : toute route absente est listée dans TROUS_CONNUS et couverte ci-dessous par une matrice
   complémentaire (profils nu, p1, p2, p3, p4, p5, su, ed). Une NOUVELLE route non couverte fait échouer le test.
2. Toute route protégée renvoie l'anonyme vers /connexion/ (GET et POST) ; la liste des routes publiques est figée.
3. Aucune route ne modifie de données en GET (instantané de toute la base avant / après).
"""
import re

import pytest
from django.apps import apps
from django.urls import URLResolver, get_resolver, reverse

from tests.test_F21_matrice_routes import FAMILLE, ENGIN, M, PROFILS, ROUTES, S, _reponse, acteurs  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


# ---------------------------------------------------------------- énumération des routes

def routes_declarees():
    """[(nom, adresse avec paramètres, vue)] pour toutes les routes sauf l'administration technique et /media/."""
    trouvees = []

    def parcourir(motifs, prefixe=''):
        for motif in motifs:
            if isinstance(motif, URLResolver):
                parcourir(motif.url_patterns, prefixe + str(motif.pattern))
            elif motif.name:
                trouvees.append((motif.name, prefixe + str(motif.pattern), motif.callback))

    parcourir(get_resolver().url_patterns)
    return [r for r in trouvees if not r[1].startswith('gestion-technique/')]


def adresse_factice(modele):
    return '/' + re.sub(r'<int:\w+>', '1', modele)


NOMS_MATRICE_EXISTANTE = {r[0] for r in ROUTES}
TOUTES = routes_declarees()
# Routes déclarées mais absentes de test_F21_matrice_routes.py (constat au 2026-10-13) : couvertes plus bas.
TROUS_CONNUS = {
    # application web
    'application', 'deconnexion', 'adminer', 'add-user', 'securite', 'tableau-bord', 'home-session', 'liste-membre',
    'delete-membre', 'view-user', 'recherche', 'notifys',
    # hors périmètre de cette matrice (test dédié) : API, mob, ancien site
    'sante', 'racine', 'home-mob', 'session', 'register', 'data', 'attribut-str', 'attribut-ville',
    'home', 'vue-article', 'about', 'news', 'portail', 'politique',
}


def test_F21_trous_de_matrice_listes_et_couverts():
    """Chaque route absente de la matrice d'origine est connue (TROUS_CONNUS) : une nouvelle route non testée échoue."""
    absentes = {nom for nom, _m, _v in TOUTES} - NOMS_MATRICE_EXISTANTE
    assert absentes == TROUS_CONNUS, (
        f'nouveaux trous : {sorted(absentes - TROUS_CONNUS)} ; trous comblés : {sorted(TROUS_CONNUS - absentes)}')


ROUTES_PUBLIQUES_ATTENDUES = {
    'application', 'sante', 'racine', 'home-mob', 'session', 'register', 'data', 'attribut-str', 'attribut-ville',
    'home', 'vue-article', 'about', 'news', 'portail', 'politique',
}


def test_F21_liste_figee_des_routes_publiques():
    """Une route sans connexion obligatoire est une décision : toute nouvelle route publique doit être validée."""
    publiques = {nom for nom, _m, vue in TOUTES if getattr(vue, 'login_required', True) is False}
    assert publiques == ROUTES_PUBLIQUES_ATTENDUES, sorted(publiques ^ ROUTES_PUBLIQUES_ATTENDUES)


PROTEGEES = [(n, m) for n, m, v in TOUTES if getattr(v, 'login_required', True) is not False]


@pytest.mark.parametrize('methode', ['get', 'post'])
@pytest.mark.parametrize('nom, modele', PROTEGEES, ids=[p[0] for p in PROTEGEES])
def test_F21_anonyme_redirige_vers_la_connexion_sur_toute_route_protegee(client, db, nom, modele, methode):
    r = getattr(client, methode)(adresse_factice(modele))
    assert r.status_code == 302 and '/connexion/' in r['Location'], (nom, r.status_code)


# ---------------------------------------------------------------- aucune modification en GET

def _instantane():
    resultat = {}
    for app in ('coptapp', 'compte', 'virtrine'):
        for modele in apps.get_app_config(app).get_models():
            resultat[modele.__name__] = list(modele.objects.order_by('pk').values())
    return resultat


ROUTES_GET_A_PARCOURIR = [
    (nom, modele) for nom, modele, _v in TOUTES
    if nom not in ROUTES_PUBLIQUES_ATTENDUES and nom not in ('deconnexion',)
]


@pytest.mark.parametrize('profil', ['su', 'p5', 'p2', 'p1'])
def test_F21_aucune_route_ne_modifie_de_donnees_en_get(client, acteurs, profil):
    """Parcourt TOUTES les routes protégées en GET (identifiants réels) : l'instantané de la base ne bouge pas."""
    client.raise_request_exception = False
    client.force_login(acteurs['comptes'][profil])
    ids = {'id': 0, 'idM': acteurs['membre'].id, 'sid': acteurs['association'].id}
    avant = _instantane()
    for nom, _modele in ROUTES_GET_A_PARCOURIR:
        # identifiant plausible selon la route, sinon 1
        cible = {
            'membre-view': acteurs['membre'].id, 'delete-membre': acteurs['membre'].id, 'validate': acteurs['membre'].id,
            'view-moto': acteurs['moto'].id, 'edit-moto': acteurs['moto'].id, 'delete-moto': acteurs['moto'].id,
            'adminer': acteurs['membre'].id, 'view-user': acteurs['membre'].id,
        }.get(nom, 1)
        modele = dict((n, m) for n, m, _v in TOUTES)[nom]
        url = '/' + re.sub(r'<int:\w+>', str(cible), modele)
        client.get(url)
    assert _instantane() == avant


# ---------------------------------------------------------------- matrice complémentaire (profil x route)

PROVINCE = lambda a: {'id': a['province'].id}                               # noqa: E731
ASSO = lambda a: {'id': a['association'].id}                                # noqa: E731
VISIBLES = dict(nu=404, p4=404, ed=404)

COMPLEMENT = [
    # (route, méthode, arguments, données, attendus par profil)
    ('tableau-bord', 'get', {}, None, S(200)),
    ('home-session', 'get', {}, None, S(200)),
    ('liste-membre', 'get', {}, None, S(200)),
    ('recherche', 'get', {}, None, S(200)),
    ('recherche', 'post', {}, {'search': '1', 'champ': 'Membre'}, S(200)),
    ('notifys', 'get', {}, None, S(200)),
    ('securite', 'get', {}, None, S(200)),
    ('view-user', 'get', M, None, S(302)),
    # comptes : super-utilisateur seulement
    ('add-user', 'get', {}, None, S(403, su=200)),
    ('add-user', 'post', {}, {}, S(403, su=200)),
    ('adminer', 'get', M, None, S(403, su=405)),
    ('adminer', 'post', M, None, S(403, su=302)),  # le membre du SU a déjà un compte : renvoi vers la fiche
    # suppression : demande (agent, validateurs) ou exécution (p5, su), avec motif
    ('delete-membre', 'get', M, None, S(405)),
    ('delete-membre', 'post', M, {'action': 'demander', 'motif': 'Doublon'}, S(302, **VISIBLES)),
    # sans action ni motif : 302 avec message (variante historique) ou 400 (variante à action explicite)
    ('delete-membre', 'post', M, {}, {p: ((404, 400) if p in ('nu', 'p4', 'ed') else (302, 400)) for p in PROFILS}),
    # écritures dont seule la lecture (GET) était couverte
    ('edit-family', 'get', lambda a: {'id': a['famille'].id}, None, S(200, p1=403, **VISIBLES)),
    ('add-moto', 'post', M, ENGIN, S(200, **VISIBLES)),
    ('add-membre', 'post', ASSO, {}, S(200, nu=404, p4=404, ed=404)),
    ('add-fenamo-membre', 'post', {}, {}, S(403, p5=200, su=200)),
    ('add-structure', 'post', {}, {}, S(403, p5=200, su=200)),
    ('add-antenne', 'post', ASSO, {'nom': 'Nouvelle antenne'}, S(403, p5=302, su=302)),
    ('add-ville', 'post', PROVINCE, {'nom': 'Ville nouvelle'}, S(403, p5=200, su=200)),
    ('ville-select', 'post', ASSO, {'ville': 'KINSHASA'}, S(403, p5=302, su=302)),
    ('config', 'post', {}, {}, S(403, su=200, ed=200)),
    ('site', 'post', {}, {}, S(403, su=200, ed=200)),
    # déconnexion en dernier de la liste logique : POST seulement
    ('deconnexion', 'get', {}, None, S(405)),
    ('deconnexion', 'post', {}, None, S(302)),
    ('application', 'get', {}, None, S(302)),  # déjà connecté : renvoi vers le tableau de bord
]


def _identifiant(r):
    return f'{r[0]}-{r[1]}'


def test_F21_complement_couvre_chaque_trou_de_l_application_web():
    couverts = {r[0] for r in COMPLEMENT}
    a_couvrir = TROUS_CONNUS - {'sante', 'racine', 'home-mob', 'session', 'register', 'data', 'attribut-str',
                                'attribut-ville', 'home', 'vue-article', 'about', 'news', 'portail', 'politique'}
    assert a_couvrir <= couverts, sorted(a_couvrir - couverts)


@pytest.mark.parametrize('profil', PROFILS)
@pytest.mark.parametrize('route', COMPLEMENT, ids=_identifiant)
def test_F21_matrice_complementaire_profil_par_route(client, acteurs, route, profil):
    client.raise_request_exception = False
    nom, methode, args, donnees, attendus = route
    r = _reponse(client, acteurs, profil, methode, nom, args, donnees)
    attendu = attendus[profil]
    assert r.status_code in (attendu if isinstance(attendu, tuple) else (attendu,)),         f'{profil} {methode.upper()} {nom} -> {r.status_code}'


@pytest.mark.parametrize('route', [r for r in COMPLEMENT if r[1] == 'get' and r[0] != 'application'], ids=_identifiant)
def test_F21_matrice_complementaire_page_complete_et_fragment_htmx(client, acteurs, route):
    """Pour le super-utilisateur : la page complète contient la coque, le fragment HTMX n'en contient pas."""
    nom, _m, args, _d, attendus = route
    if attendus['su'] != 200:
        pytest.skip('route sans page pour le SU')
    client.force_login(acteurs['comptes']['su'])
    url = reverse(nom, kwargs=args(acteurs) if callable(args) else args)
    complete = client.get(url)
    fragment = client.get(url, HTTP_HX_REQUEST='true')
    assert complete.status_code == fragment.status_code == 200
    assert b'<html' in complete.content
    assert 'HX-Request' in complete['Vary']


# ---------------------------------------------------------------- données invalides : jamais de 500

@pytest.mark.xfail(reason='BUG a corriger (backend-django) : KeyError -> 500 quand un champ du POST manque (addFamily).', strict=False)
def test_F21_ajout_famille_sans_champs_ne_donne_pas_500(client, acteurs):
    client.raise_request_exception = False
    client.force_login(acteurs['comptes']['su'])
    r = client.post(reverse('add-family', kwargs=M(acteurs)), {})
    assert r.status_code < 500


@pytest.mark.xfail(reason='BUG a corriger (backend-django) : Province.DoesNotExist -> 500 sur identifiant inconnu (addVille).', strict=False)
def test_F21_ajout_ville_province_inconnue_donne_404(client, acteurs):
    client.raise_request_exception = False
    client.force_login(acteurs['comptes']['su'])
    r = client.get(reverse('add-ville', kwargs={'id': 999999}))
    assert r.status_code == 404


@pytest.mark.xfail(reason='BUG a corriger (backend-django) : Antenne.DoesNotExist -> 500 sur identifiant inconnu (editAntenne).', strict=False)
def test_F21_modifier_antenne_inconnue_donne_404(client, acteurs):
    client.raise_request_exception = False
    client.force_login(acteurs['comptes']['su'])
    r = client.get(reverse('edit-antenne', kwargs={'id': 999999}))
    assert r.status_code == 404


@pytest.mark.xfail(reason='BUG a corriger (backend-django) : KeyError sur request.POST["nom"] -> 500 (addVille).', strict=False)
def test_F21_ajout_ville_sans_nom_ne_donne_pas_500(client, acteurs):
    client.raise_request_exception = False
    client.force_login(acteurs['comptes']['su'])
    r = client.post(reverse('add-ville', kwargs=PROVINCE(acteurs)), {})
    assert r.status_code < 500
