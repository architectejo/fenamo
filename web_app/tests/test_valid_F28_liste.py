"""Validation indépendante de la liste /membres/ (F-28) : recherche, filtres, pagination, injection, XSS, requêtes."""
from datetime import date

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from compte.models import Compte
from coptapp.models import Antenne, AssociationMembre, Membre
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

HTMX = {'HTTP_HX_REQUEST': 'true'}
BOOSTE = {'HTTP_HX_REQUEST': 'true', 'HTTP_HX_BOOSTED': 'true'}
URL = '/membres/'


def _m(jeu, nom, **kw):
    base = dict(province=jeu['province'], antenne=jeu['antenne'], structure=jeu['association'],
                date_naissance=date(1990, 1, 1))
    base.update(kw)
    return Membre.objects.create(nom=nom, **base)


@pytest.fixture
def su(client, jeu):
    client.force_login(jeu['compte'])
    return jeu['compte']


@pytest.fixture
def base(jeu):
    autre = AssociationMembre.objects.create(nom='Seconde asso', sigle='SA', num_justice='F-9')
    ant2 = Antenne.objects.create(nom='Antenne Z', structure=autre)
    _m(jeu, 'Alpha Kasongo', idf='MBR1111111', numero_carte_de_membre='CARTE-777', telephone='+243811111111',
       qualite='MOTARD', is_validate2=True)
    _m(jeu, 'Bravo Ilunga', idf='MBR2222222', numero_carte_de_membre='CARTE-888', telephone='+243822222222',
       qualite='PROPRIETAIRE', is_validate2=True, is_validate3=True, antenne=ant2, structure=autre)
    _m(jeu, 'Charlie 100% Sûr', qualite='MOTARD ET PROPRIETAIRE')
    return {**jeu, 'autre': autre, 'ant2': ant2}


def _noms(r):
    return [m.nom for m in r.context['page_obj']]


# ---------------------------------------------------------------- recherche

@pytest.mark.parametrize('q, attendu', [
    ('kasongo', 'Alpha Kasongo'), ('MBR2222', 'Bravo Ilunga'), ('CARTE-777', 'Alpha Kasongo'),
    ('82222', 'Bravo Ilunga'), ('  ilunga  ', 'Bravo Ilunga'),
])
def test_F28_recherche_sur_nom_idf_carte_telephone(client, su, base, q, attendu):
    r = client.get(URL, {'q': q})
    assert r.status_code == 200 and _noms(r) == [attendu]


def test_F28_recherche_sans_resultat_message_vide(client, su, base):
    r = client.get(URL, {'q': 'zzzzintrouvable'})
    assert r.status_code == 200 and _noms(r) == [] and r.context['filtres_actifs']
    assert 'Aucun membre ne correspond' in r.content.decode()


@pytest.mark.parametrize('q', ["' OR 1=1 --", "'; DROP TABLE coptapp_membre; --", '" OR ""="', '_', '%%', '_%_',
                               '\\', "a' UNION SELECT * FROM compte_compte --"])
def test_F28_injection_sql_et_jokers_like_sont_litteraux(client, su, base, q):
    avant = Membre.objects.count()
    r = client.get(URL, {'q': q})
    assert r.status_code == 200
    assert _noms(r) == []  # aucun nom ne contient ces caractères : pas de « tout renvoyer »
    assert Membre.objects.count() == avant


def test_F28_joker_pourcent_ne_trouve_que_le_pourcent_litteral(client, su, base):
    assert _noms(client.get(URL, {'q': '100%'})) == ['Charlie 100% Sûr']


def test_F28_tres_longue_chaine_ne_plante_pas(client, su, base):
    r = client.get(URL, {'q': 'a' * 100000})
    assert r.status_code == 200 and len(r.context['filtres']['q']) <= 100


@pytest.mark.parametrize('q', ['Sûr', 'É', 'ß', '日本語', '\U0001F600', 'é', '‮', '\x00', 'a\x00b'])
def test_F28_caracteres_unicode_jamais_500(client, su, base, q):
    assert client.get(URL, {'q': q}).status_code == 200


def test_F28_recherche_unicode_accentuee(client, su, base):
    assert _noms(client.get(URL, {'q': 'Sûr'})) == ['Charlie 100% Sûr']


# ---------------------------------------------------------------- filtres

def test_F28_filtre_etat(client, su, base):
    assert _noms(client.get(URL, {'etat': 'actif'})) == ['Bravo Ilunga']
    assert _noms(client.get(URL, {'etat': 'valide_antenne'})) == ['Alpha Kasongo']
    assert sorted(_noms(client.get(URL, {'etat': 'saisi'}))) == ['Charlie 100% Sûr', 'Membre Fictif']
    assert _noms(client.get(URL, {'etat': 'valide-antenne'})) == ['Alpha Kasongo']  # tiret toléré


def test_F28_filtre_qualite_insensible_a_la_casse(client, su, base):
    assert _noms(client.get(URL, {'qualite': 'motard'})) == ['Alpha Kasongo']
    assert _noms(client.get(URL, {'qualite': 'MOTARD ET PROPRIETAIRE'})) == ['Charlie 100% Sûr']


def test_F28_filtre_antenne_et_association(client, su, base):
    assert _noms(client.get(URL, {'antenne': base['ant2'].id})) == ['Bravo Ilunga']
    assert _noms(client.get(URL, {'association': base['autre'].id})) == ['Bravo Ilunga']
    assert _noms(client.get(URL, {'association': base['autre'].id, 'q': 'alpha'})) == []


def test_F28_filtres_combines(client, su, base):
    r = client.get(URL, {'etat': 'actif', 'qualite': 'PROPRIETAIRE', 'antenne': base['ant2'].id, 'q': 'bravo'})
    assert _noms(r) == ['Bravo Ilunga']


@pytest.mark.parametrize('params', [
    {'etat': 'inconnu'}, {'etat': "x' OR 1=1"}, {'qualite': 'ROBOT'}, {'antenne': 'abc'}, {'antenne': '-1'},
    {'antenne': '0'}, {'antenne': '9' * 40}, {'association': '1e9'}, {'association': '<b>'}, {'antenne': ['1', '2']},
    {'etat': ['actif', 'saisi']},
])
def test_F28_filtres_invalides_jamais_500(client, su, base, params):
    assert client.get(URL, params).status_code == 200


def test_F28_filtres_invalides_ne_filtrent_pas(client, su, base):
    r = client.get(URL, {'etat': 'inconnu', 'qualite': 'ROBOT', 'antenne': 'abc'})
    assert r.context['page_obj'].paginator.count == 4 and not r.context['filtres_actifs']


def test_F28_membres_sans_nom_et_supprimes_exclus(client, su, base, jeu):
    _m(jeu, None)
    _m(jeu, '')
    _m(jeu, 'Supprimé', is_delete=True)
    noms = _noms(client.get(URL))
    assert 'Supprimé' not in noms and None not in noms and '' not in noms


# ---------------------------------------------------------------- pagination

@pytest.fixture
def soixante(jeu):
    Membre.objects.bulk_create([
        Membre(nom=f'Membre{i:03d}', province=jeu['province'], antenne=jeu['antenne'], structure=jeu['association'])
        for i in range(60)
    ])


def test_F28_pagination_25_par_page(client, su, soixante):
    # 60 + le membre du jeu d'essai = 61
    assert len(_noms(client.get(URL))) == 25
    assert len(_noms(client.get(URL, {'page': 2}))) == 25
    r = client.get(URL, {'page': 3})
    assert len(_noms(r)) == 11 and r.context['page_obj'].paginator.num_pages == 3


@pytest.mark.parametrize('page, attendue', [('999', 3), ('abc', 1), ('-1', 3), ('0', 3), ('', 1), ('1.5', 1),
                                            ('<script>', 1), ('9' * 50, 3), ('2', 2)])
def test_F28_page_hors_bornes_ou_illisible(client, su, soixante, page, attendue):
    """Hors bornes -> dernière page ; illisible -> première (docstring de lister_membres)."""
    r = client.get(URL, {'page': page})
    assert r.status_code == 200 and r.context['page_obj'].number == attendue


def test_F28_liens_de_pagination_gardent_les_filtres(client, su, soixante):
    corps = client.get(URL, {'q': 'Membre', 'qualite': ''}).content.decode()
    assert 'page=2' in corps and 'q=Membre' in corps


# ---------------------------------------------------------------- XSS reflété

PIRATE = '"><script>alert(1)</script><img src=x onerror=alert(2)>'


@pytest.mark.parametrize('entete', [{}, HTMX, BOOSTE], ids=['complet', 'fragment', 'boost'])
@pytest.mark.parametrize('param', ['q', 'etat', 'qualite', 'antenne', 'association', 'page'])
def test_F28_xss_reflechi_dans_les_filtres(client, su, base, param, entete):
    r = client.get(URL, {param: PIRATE}, **entete)
    corps = r.content.decode()
    assert r.status_code == 200
    assert '<script>alert(1)' not in corps
    assert '<img src=x' not in corps


def test_F28_xss_q_est_echappe_dans_le_champ(client, su, base):
    corps = client.get(URL, {'q': '"><script>alert(1)</script>'}).content.decode()
    assert 'value="&quot;&gt;&lt;script&gt;alert(1)' in corps


def test_F28_xss_q_dans_les_liens_de_pagination(client, su, soixante):
    corps = client.get(URL, {'q': 'Membre"><script>alert(1)</script>'}).content.decode()
    assert '<script>alert(1)' not in corps


# ---------------------------------------------------------------- fragment / page complète

def test_F28_fragment_htmx_sans_coque_page_complete_avec(client, su, base):
    frag = client.get(URL, **HTMX).content.decode()
    page = client.get(URL).content.decode()
    assert '<html' not in frag.lower() and 'Alpha Kasongo' in frag
    assert '<html' in page.lower() and 'id="liste-zone"' in page and 'Alpha Kasongo' in page


def test_F28_navigation_boostee_recoit_la_page_complete(client, su, base):
    assert '<html' in client.get(URL, **BOOSTE).content.decode().lower()


def test_F28_reponse_varie_sur_hx_request(client, su, base):
    assert 'HX-Request' in client.get(URL, **HTMX).headers.get('Vary', '')


def test_F28_fragment_sans_requete_de_coque(client, su, base):
    client.get(URL)  # chauffe session / contenttypes
    with CaptureQueriesContext(connection) as frag:
        client.get(URL, **HTMX)
    with CaptureQueriesContext(connection) as page:
        client.get(URL)
    sql_frag = ' '.join(q['sql'].lower() for q in frag)
    assert 'coptapp_notification' not in sql_frag
    assert 'coptapp_notification' in ' '.join(q['sql'].lower() for q in page)  # la page complète a bien la coque
    assert len(frag) < len(page)


def test_F28_get_ne_modifie_aucune_donnee(client, su, base):
    avant = list(Membre.objects.order_by('id').values())
    client.get(URL, {'q': 'a', 'etat': 'actif', 'page': 2})
    client.get(URL, **HTMX)
    assert list(Membre.objects.order_by('id').values()) == avant


def test_F28_anonyme_redirige_vers_connexion(client, base):
    r = client.get(URL)
    assert r.status_code == 302 and 'connexion' in r['Location']


def test_F28_session_expiree_htmx_hx_redirect(client, base):
    r = client.get(URL, **HTMX)
    assert r.status_code == 200 and 'HX-Redirect' in r.headers


# ---------------------------------------------------------------- N+1

def _requetes(client, params=None):
    client.get(URL)  # session
    with CaptureQueriesContext(connection) as c:
        r = client.get(URL, params or {})
    assert r.status_code == 200
    return len(c)


def test_F28_pas_de_n_plus_un_sur_la_liste(client, su, jeu):
    for i in range(3):
        _m(jeu, f'Petit{i}')
    petit = _requetes(client)
    Membre.objects.bulk_create([
        Membre(nom=f'Grand{i}', province=jeu['province'], antenne=jeu['antenne'], structure=jeu['association'],
               is_validate2=i % 2 == 0)
        for i in range(60)
    ])
    grand = _requetes(client)
    assert grand <= petit + 1, (petit, grand)


def test_F28_pas_de_n_plus_un_avec_photos_et_comptes(client, su, jeu):
    agent = Compte.objects.create_user('ag', password='x', privilege1=True)
    for i in range(30):
        _m(jeu, f'Avec compte {i}', user=agent, photo='x.jpg')
    assert _requetes(client) <= 25
    assert _requetes(client, {'page': 2}) <= 25
