"""F-28 : liste des membres avec recherche, filtres, pagination à 25 par page, fragment HTMX ou page complète."""
from datetime import date

import pytest
from django.urls import reverse

from compte.models import Compte
from coptapp.models import Antenne, AssociationMembre, Membre
from coptapp.services.etats import filtrer_membres_par_etat
from coptapp.services.membres import PAR_PAGE, lister_membres, membres_filtres, normaliser_filtres
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

HTMX = {'HTTP_HX_REQUEST': 'true'}


def _membre(jeu, nom, **kw):
    base = dict(province=jeu['province'], ville=jeu['ville'], antenne=jeu['antenne'], structure=jeu['association'],
                date_naissance=date(1990, 1, 1))
    base.update(kw)
    return Membre.objects.create(nom=nom, **base)


@pytest.fixture
def liste(jeu):
    autre_assoc = AssociationMembre.objects.create(nom='Autre association', sigle='AA', num_justice='F-0002')
    autre_antenne = Antenne.objects.create(nom='Antenne B', structure=autre_assoc)
    _membre(jeu, 'Kabila Jean', telephone='+243810000001', idf='MBR0000001', qualite='MOTARD', is_validate2=True)
    _membre(jeu, 'Mukendi Paul', telephone='+243820000002', idf='MBR0000002', qualite='PROPRIETAIRE',
            is_validate2=True, is_validate3=True, antenne=autre_antenne, structure=autre_assoc)
    _membre(jeu, 'Tshala Marie', qualite='MOTARD ET PROPRIETAIRE')
    _membre(jeu, None)
    _membre(jeu, '')
    _membre(jeu, 'Supprime Pierre', is_delete=True)
    return {**jeu, 'autre_assoc': autre_assoc, 'autre_antenne': autre_antenne}


def _noms(page):
    return [m.nom for m in page]


# ------------------------------------------------------------------ service

def test_F28_service_exclut_les_membres_sans_nom_et_supprimes(liste):
    noms = _noms(lister_membres(liste['compte'], {}).page_obj)
    assert None not in noms and '' not in noms and 'Supprime Pierre' not in noms
    assert sorted(noms) == ['Kabila Jean', 'Membre Fictif', 'Mukendi Paul', 'Tshala Marie']


@pytest.mark.parametrize('q, attendu', [
    ('kabila', ['Kabila Jean']), ('MBR0000002', ['Mukendi Paul']), ('820000002', ['Mukendi Paul']),
    ('+243810', ['Kabila Jean']), ('', None), ('%', []), ("o'brien", []), ('   ', None),
])
def test_F28_service_recherche_nom_identifiant_telephone(liste, q, attendu):
    noms = _noms(lister_membres(liste['compte'], {'q': q}).page_obj)
    if attendu is None:
        assert len(noms) == 4
    else:
        assert noms == attendu


def test_F28_service_filtres(liste):
    su = liste['compte']
    assert _noms(lister_membres(su, {'etat': 'actif'}).page_obj) == ['Mukendi Paul']
    assert _noms(lister_membres(su, {'etat': 'valide_antenne'}).page_obj) == ['Kabila Jean']
    assert sorted(_noms(lister_membres(su, {'etat': 'saisi'}).page_obj)) == ['Membre Fictif', 'Tshala Marie']
    assert _noms(lister_membres(su, {'qualite': 'motard'}).page_obj) == ['Kabila Jean']
    assert _noms(lister_membres(su, {'antenne': liste['autre_antenne'].id}).page_obj) == ['Mukendi Paul']
    assert _noms(lister_membres(su, {'association': liste['autre_assoc'].id}).page_obj) == ['Mukendi Paul']
    assert _noms(lister_membres(su, {'etat': 'actif', 'qualite': 'MOTARD'}).page_obj) == []


def test_F28_service_filtres_invalides_ignores(liste):
    filtres = normaliser_filtres({'etat': 'nimporte', 'qualite': 'x', 'antenne': 'abc', 'association': '-', 'q': 'a' * 500})
    assert filtres['etat'] == '' and filtres['qualite'] == '' and filtres['antenne'] == '' and filtres['association'] == ''
    assert len(filtres['q']) == 100
    assert len(lister_membres(liste['compte'], {'etat': 'nimporte', 'antenne': 'abc'}).page_obj) == 4


def test_F28_filtrer_par_etat_dans_etats_py(liste):
    base = Membre.objects.filter(is_delete=False)
    assert filtrer_membres_par_etat(base, '').count() == base.count()
    assert filtrer_membres_par_etat(base, 'renvoye').count() == 0
    assert filtrer_membres_par_etat(base, 'supprime').count() == 0


def test_F28_service_pagination_25(jeu):
    for i in range(30):
        _membre(jeu, f'Membre {i:02d}')
    su = jeu['compte']
    p1 = lister_membres(su, {}, '1').page_obj
    assert PAR_PAGE == 25 and len(p1) == 25 and p1.paginator.count == 31 and p1.has_next()
    assert len(lister_membres(su, {}, '2').page_obj) == 6
    assert lister_membres(su, {}, '999').page_obj.number == 2   # hors bornes : dernière page
    assert lister_membres(su, {}, 'abc').page_obj.number == 1   # illisible : première page
    assert lister_membres(su, {}, None).page_obj.number == 1


def test_F28_service_perimetre_respecte(liste):
    p4 = Compte.objects.create_user('visiteur', password='x', privilege4=True)
    assert _noms(lister_membres(p4, {}).page_obj) == ['Mukendi Paul']
    nu = Compte.objects.create_user('nu', password='x')
    assert _noms(lister_membres(nu, {}).page_obj) == []
    assert membres_filtres(nu, {}).count() == 0


# ------------------------------------------------------------------ vue

def test_F28_vue_page_complete_et_contexte(client, liste):
    client.force_login(liste['compte'])
    r = client.get(reverse('liste-membre'), {'q': 'kabila', 'etat': 'valide_antenne', 'page': '1'})
    assert r.status_code == 200
    assert 'app/membre-list.html' in [t.name for t in r.templates]
    assert '<html' in r.content.decode()
    c = r.context
    assert [m.nom for m in c['page_obj']] == ['Kabila Jean']
    assert c['filtres']['q'] == 'kabila' and c['filtres']['etat'] == 'valide_antenne' and c['filtres_actifs']
    assert 'membres' not in c and 'filtres_url' not in c
    assert {'antennes', 'associations', 'qualites', 'etats'} <= set(c['choix'])
    for cle in ('peut_modifier', 'peut_valider', 'peut_demander_suppression', 'peut_attribuer_privileges',
                'peut_ajouter_famille', 'peut_ajouter_engin', 'peut_voir_historique'):
        assert cle in c


def test_F28_vue_fragment_htmx(client, liste):
    client.force_login(liste['compte'])
    r = client.get(reverse('liste-membre'), {'q': 'mukendi'}, **HTMX)
    assert r.status_code == 200
    assert 'coptapp/membres/partials/_liste.html' in [t.name for t in r.templates]
    corps = r.content.decode()
    assert '<html' not in corps and 'Mukendi Paul' in corps and 'Kabila Jean' not in corps
    assert 'HX-Request' in r.headers['Vary']


def test_F28_vue_navigation_boostee_rend_la_page_complete(client, liste):
    client.force_login(liste['compte'])
    r = client.get(reverse('liste-membre'), **HTMX, HTTP_HX_BOOSTED='true')
    assert '<html' in r.content.decode()


def test_F28_vue_perimetre_visiteur_et_sans_privilege(client, liste):
    client.force_login(Compte.objects.create_user('v', password='x', privilege4=True))
    corps = client.get(reverse('liste-membre')).content.decode()
    assert 'Mukendi Paul' in corps and 'Kabila Jean' not in corps
    client.force_login(Compte.objects.create_user('n', password='x'))
    corps = client.get(reverse('liste-membre')).content.decode()
    assert 'Mukendi Paul' not in corps and 'Kabila Jean' not in corps


def test_F28_vue_anonyme_redirige(client, liste):
    assert client.get(reverse('liste-membre')).status_code == 302


def test_F28_vue_recherche_echappee(client, liste):
    _membre(liste, '<script>alert(1)</script>')
    client.force_login(liste['compte'])
    corps = client.get(reverse('liste-membre'), {'q': '<script>'}).content.decode()
    assert '<script>alert(1)' not in corps
