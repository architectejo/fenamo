"""Matrice privilège x route (F-21, F-23, F-25, F-26, F-35 + référentiel et site) : 404 hors périmètre, 403 sans droit.

Jeu : un membre « validé antenne » saisi par l'agent (p1), dans l'association A où p1, p2 et p3 sont rattachés.
Profils : nu (aucun privilège), p1 (agent), p2, p3, p4 (visiteur), p5, su, ed (éditeur du site).
"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from compte.models import Compte
from coptapp.models import AssociationMembre, Antenne, Membre
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

PROFILS = ('nu', 'p1', 'p2', 'p3', 'p4', 'p5', 'su', 'ed')


@pytest.fixture
def acteurs(jeu):
    comptes = {
        'nu': Compte.objects.create_user('nu', password='x'),
        'p1': Compte.objects.create_user('p1', password='x', privilege1=True),
        'p2': Compte.objects.create_user('p2', password='x', privilege2=True),
        'p3': Compte.objects.create_user('p3', password='x', privilege3=True),
        'p4': Compte.objects.create_user('p4', password='x', privilege4=True),
        'p5': Compte.objects.create_user('p5', password='x', privilege5=True),
        'su': jeu['compte'],
        'ed': Compte.objects.create_user('ed', password='x', editor=True),
    }
    for nom in ('p1', 'p2', 'p3'):
        jeu['association'].users.add(comptes[nom])
    Membre.objects.filter(pk=jeu['membre'].pk).update(is_validate2=True, user=comptes['p1'])
    jeu['membre'].refresh_from_db()
    autre = AssociationMembre.objects.create(nom='Autre association', sigle='AB', num_justice='F-0002')
    return {**jeu, 'comptes': comptes, 'autre': autre,
            'autre_antenne': Antenne.objects.create(nom='Antenne B', structure=autre)}


def _reponse(client, acteurs, profil, methode, route, args, donnees=None):
    client.force_login(acteurs['comptes'][profil])
    url = reverse(route, kwargs=args(acteurs)) if callable(args) else reverse(route, kwargs=args)
    return getattr(client, methode)(url, donnees or {})


def S(defaut=None, **kw):
    """Attendus par profil : S(403, p1=200)."""
    return {p: kw.get(p, defaut) for p in PROFILS}


M = lambda a: {'id': a['membre'].id}                                        # noqa: E731
FAMILLE = {'nom': 'Proche', 'qualite': 'ENFANT', 'genre': 'F', 'annee': '2010'}
ENGIN = {k: 'x' for k in ('plaque', 'chassie', 'moteur', 'marque', 'couleur')}

# ecriture = p1, p2, p3, p5, su ; lecteurs du membre (visible) = p1, p2, p3, p5, su ; p4 et ed ne le voient pas
VISIBLES = dict(nu=404, p4=404, ed=404)
ROUTES = [
    # (route, méthode, arguments, données, attendus)
    ('membre-view', 'get', M, None, S(200, **VISIBLES)),
    ('validate', 'post', M, None, S(302, nu=404, p4=404, ed=404, p1=403)),
    ('structure-attribution', 'post', lambda a: {'idM': a['membre'].id, 'id': a['association'].id}, None,
     S(302, p1=403, p2=403, **VISIBLES)),
    ('antenne-attribution', 'post', lambda a: {'idM': a['membre'].id, 'id': a['antenne'].id}, None,
     S(302, p1=403, p2=403, **VISIBLES)),
    ('ville-attribution', 'post', lambda a: {'idM': a['membre'].id, 'id': a['ville'].id}, None,
     S(302, p1=403, p2=403, **VISIBLES)),
    # cibles que le compte ne gère pas : seuls SU et privilege5 rattachent ailleurs
    ('structure-attribution', 'post', lambda a: {'idM': a['membre'].id, 'id': a['autre'].id}, None,
     S(403, p5=302, su=302, **VISIBLES)),
    ('antenne-attribution', 'post', lambda a: {'idM': a['membre'].id, 'id': a['autre_antenne'].id}, None,
     S(403, p5=302, su=302, **VISIBLES)),
    ('add-family', 'get', M, None, S(200, **VISIBLES)),
    ('add-family', 'post', M, FAMILLE, S(200, **VISIBLES)),
    ('edit-family', 'post', lambda a: {'id': a['famille'].id}, FAMILLE, S(200, p1=403, **VISIBLES)),
    ('delete-family', 'post', lambda a: {'id': a['famille'].id}, None, S(302, p1=403, **VISIBLES)),
    ('add-moto', 'get', M, None, S(200, **VISIBLES)),
    ('view-moto', 'get', lambda a: {'id': a['moto'].id}, None, S(200, **VISIBLES)),
    ('edit-moto', 'get', lambda a: {'id': a['moto'].id}, None, S(200, p1=403, **VISIBLES)),
    ('edit-moto', 'post', lambda a: {'id': a['moto'].id}, ENGIN, S(200, p1=403, **VISIBLES)),
    ('delete-moto', 'post', lambda a: {'id': a['moto'].id}, None, S(302, p1=403, **VISIBLES)),
    ('moto-attribution', 'post', M, {'numero': '001PF'}, S(302, **VISIBLES)),
    ('add-membre', 'get', lambda a: {'id': a['association'].id}, None, S(200, nu=404, p4=404, ed=404)),
    ('add-membre', 'get', lambda a: {'id': a['autre'].id}, None, S(404, p5=200, su=200)),
    ('add-fenamo-membre', 'get', {}, None, S(403, p5=200, su=200)),
    # associations
    ('str-list', 'get', {}, None, S(200)),
    ('structure-admin', 'get', lambda a: {'id': a['association'].id}, None, S(200, nu=404, p4=404, ed=404)),
    ('structure-admin', 'get', lambda a: {'id': a['autre'].id}, None, S(404, p5=200, su=200)),
    ('edit-structure', 'get', lambda a: {'id': a['association'].id}, None, S(403, p5=200, su=200)),
    ('edit-structure', 'post', lambda a: {'id': a['association'].id}, {}, S(403, p5=200, su=200)),
    ('add-structure', 'get', {}, None, S(403, p5=200, su=200)),
    ('ville-select', 'get', lambda a: {'id': a['association'].id}, None, S(403, p5=302, su=302)),
    ('ville-attr', 'post', lambda a: {'id': a['ville'].id, 'sid': a['association'].id}, None, S(403, p5=302, su=302)),
    # géographie
    ('antenne-view', 'get', lambda a: {'id': a['antenne'].id}, None, S(200, nu=404, p4=404, ed=404)),
    ('antenne-view', 'get', lambda a: {'id': a['autre_antenne'].id}, None, S(404, p5=200, su=200)),
    ('add-antenne', 'get', lambda a: {'id': a['association'].id}, None, S(403, p5=200, su=200)),
    ('edit-antenne', 'get', lambda a: {'id': a['antenne'].id}, None, S(403, p5=200, su=200)),
    ('edit-antenne', 'post', lambda a: {'id': a['antenne'].id}, {'nom': 'Renommée'}, S(403, p5=200, su=200)),
    ('province-view', 'get', lambda a: {'id': a['province'].id}, None, S(200, nu=404, p4=404, ed=404)),
    ('add-province', 'get', {}, None, S(403, p5=200, su=200)),
    ('add-province', 'post', {}, {'nom': 'Nouvelle', 'sigle': 'NV'}, S(403, p5=200, su=200)),
    ('add-ville', 'get', lambda a: {'id': a['province'].id}, None, S(403, p5=200, su=200)),
    ('ville-view', 'get', lambda a: {'id': a['ville'].id}, None, S(200, nu=404, p4=404, ed=404)),
    # communiqués : publication par SU et éditeur, lecture pour tous
    ('message', 'get', {}, None, S(403, su=200, ed=200)),
    ('message', 'post', {}, {'message': 'Annonce'}, S(403, su=200, ed=200)),
    ('list-message', 'get', {}, None, S(200)),
    ('communique', 'get', lambda a: {'id': a['communique'].id}, None, S(200)),
    # contenu du site : SU et éditeur
    ('contact', 'get', {}, None, S(403, su=200, ed=200)),
    ('contact-view', 'get', lambda a: {'id': a['contact'].id}, None, S(403, su=200, ed=200)),
    ('contact-view', 'post', lambda a: {'id': a['contact'].id}, {}, S(403, su=200, ed=200)),
    ('site', 'get', {}, None, S(403, su=200, ed=200)),
    ('article', 'get', lambda a: {'id': a['article'].id}, None, S(403, su=200, ed=200)),
    ('article', 'post', lambda a: {'id': a['article'].id}, {'titre': 'Nouveau', 'description': 'd'}, S(403, su=200, ed=200)),
    ('delete-article', 'post', lambda a: {'id': a['article'].id}, None, S(403, su=302, ed=302)),
    ('config', 'get', {}, None, S(403, su=200, ed=200)),
]


def _id(r):
    return f"{r[0]}-{r[1]}"


@pytest.mark.parametrize('profil', PROFILS)
@pytest.mark.parametrize('route', ROUTES, ids=_id)
def test_F21_matrice_privilege_par_route(client, acteurs, route, profil):
    nom, methode, args, donnees, attendus = route
    r = _reponse(client, acteurs, profil, methode, nom, args, donnees)
    assert r.status_code == attendus[profil], f'{profil} {methode.upper()} {nom}'


@pytest.mark.parametrize('route', [r for r in ROUTES if r[1] == 'get'], ids=_id)
def test_F21_matrice_anonyme_redirige_vers_la_connexion(client, acteurs, route):
    nom, methode, args, _donnees, _att = route
    url = reverse(nom, kwargs=args(acteurs) if callable(args) else args)
    r = client.get(url)
    assert r.status_code == 302 and '/connexion/' in r['Location']


# ---------------------------------------------------------------- lecture seule (privilege4) même cumulée

@pytest.fixture
def visiteur_cumule(acteurs):
    """Un compte qui cumule tous les privilèges ET la lecture seule, devant un membre actif qu'il voit."""
    Membre.objects.filter(pk=acteurs['membre'].pk).update(is_validate3=True)
    compte = Compte.objects.create_user('tout4', password='x', privilege1=True, privilege2=True, privilege3=True,
                                        privilege4=True, privilege5=True, editor=True)
    acteurs['association'].users.add(compte)
    return compte


def test_F21_privilege4_cumule_est_en_lecture_seule_sur_toutes_les_ecritures(client, acteurs, visiteur_cumule):
    client.force_login(visiteur_cumule)
    m, a = acteurs['membre'].id, acteurs['association'].id
    assert client.get(reverse('membre-view', kwargs={'id': m})).status_code == 200  # il lit
    ecritures = [
        ('post', reverse('membre-view', kwargs={'id': m}), {'modifier': '1'}),
        ('post', reverse('membre-view', kwargs={'id': m}), {'privilege': '1'}),
        ('post', reverse('validate', kwargs={'id': m}), {}),
        ('post', reverse('delete-membre', kwargs={'id': m}), {}),
        ('post', reverse('structure-attribution', kwargs={'idM': m, 'id': a}), {}),
        ('post', reverse('antenne-attribution', kwargs={'idM': m, 'id': acteurs['antenne'].id}), {}),
        ('post', reverse('ville-attribution', kwargs={'idM': m, 'id': acteurs['ville'].id}), {}),
        ('post', reverse('add-family', kwargs={'id': m}), FAMILLE),
        ('post', reverse('edit-family', kwargs={'id': acteurs['famille'].id}), FAMILLE),
        ('post', reverse('delete-family', kwargs={'id': acteurs['famille'].id}), {}),
        ('post', reverse('add-moto', kwargs={'id': m}), ENGIN),
        ('post', reverse('edit-moto', kwargs={'id': acteurs['moto'].id}), ENGIN),
        ('post', reverse('delete-moto', kwargs={'id': acteurs['moto'].id}), {}),
        ('post', reverse('moto-attribution', kwargs={'id': m}), {'numero': '001PF'}),
        ('post', reverse('add-membre', kwargs={'id': a}), {}),
        ('post', reverse('add-fenamo-membre'), {}),
        ('post', reverse('edit-structure', kwargs={'id': a}), {}),
        ('post', reverse('add-structure'), {}),
        ('post', reverse('add-province'), {'nom': 'X', 'sigle': 'X'}),
        ('post', reverse('add-antenne', kwargs={'id': a}), {'nom': 'X'}),
        ('post', reverse('message'), {'message': 'x'}),
        ('post', reverse('delete-article', kwargs={'id': acteurs['article'].id}), {}),
        ('post', reverse('article', kwargs={'id': acteurs['article'].id}), {'titre': 'x'}),
    ]
    for methode, url, donnees in ecritures:
        assert getattr(client, methode)(url, donnees).status_code == 403, url
    acteurs['membre'].refresh_from_db()
    assert acteurs['membre'].nom == 'Membre Fictif' and not acteurs['membre'].is_delete


def test_F21_agent_ne_gere_que_les_engins_et_familles_de_ses_saisies(client, acteurs):
    autre = Membre.objects.create(nom='Autre saisie', is_validate1=True, structure=acteurs['association'])
    client.force_login(acteurs['comptes']['p1'])
    assert client.get(reverse('add-family', kwargs={'id': autre.id})).status_code == 404  # pas sa saisie : invisible
    assert client.get(reverse('add-family', kwargs={'id': acteurs['membre'].id})).status_code == 200


def test_F21_rattachement_ferme_l_escalade_du_privilege3(client, acteurs):
    """Un privilege3 ne rattache ni un membre d'une autre association, ni à une association qui n'est pas la sienne."""
    p3 = acteurs['comptes']['p3']
    etranger = Membre.objects.create(nom='Étranger', is_validate1=True, is_validate2=True, structure=acteurs['autre'])
    sans_structure = Membre.objects.create(nom='Orphelin', is_validate1=True, is_validate2=True)
    client.force_login(p3)
    for membre in (etranger, sans_structure):
        r = client.post(reverse('structure-attribution', kwargs={'idM': membre.id, 'id': acteurs['association'].id}))
        assert r.status_code == 403
        membre.refresh_from_db()
        assert membre.structure_id != acteurs['association'].id
    r = client.post(reverse('structure-attribution', kwargs={'idM': acteurs['membre'].id, 'id': acteurs['autre'].id}))
    assert r.status_code == 403
    acteurs['membre'].refresh_from_db()
    assert acteurs['membre'].structure_id == acteurs['association'].id


def test_F35_engin_d_un_membre_d_une_autre_association(client, acteurs):
    from coptapp.models import Moto
    etranger = Membre.objects.create(nom='Étranger', is_validate1=True, is_validate2=True, structure=acteurs['autre'])
    moto = Moto.objects.create(proprietaire=etranger, abonnement=acteurs['moto'].abonnement, numero='999XX')
    client.force_login(acteurs['comptes']['p3'])
    assert client.get(reverse('view-moto', kwargs={'id': moto.id})).status_code == 200  # visible : lecture
    assert client.get(reverse('edit-moto', kwargs={'id': moto.id})).status_code == 403  # pas son association
    assert client.post(reverse('delete-moto', kwargs={'id': moto.id})).status_code == 403
    moto.refresh_from_db()
    assert not moto.is_delete
    # attribution d'un motard : le numéro d'un engin hors périmètre n'est pas trouvé
    client.force_login(acteurs['comptes']['p1'])
    client.post(reverse('moto-attribution', kwargs={'id': acteurs['membre'].id}), {'numero': '999XX'})
    moto.refresh_from_db()
    assert not moto.motard_id


def test_F23_jeton_csrf_et_get_interdit_sur_les_ecritures(client, acteurs):
    client.force_login(acteurs['comptes']['su'])
    for nom, args in (('validate', M(acteurs)), ('delete-membre', M(acteurs)), ('delete-moto', {'id': acteurs['moto'].id}),
                      ('delete-family', {'id': acteurs['famille'].id}), ('moto-attribution', M(acteurs))):
        assert client.get(reverse(nom, kwargs=args)).status_code == 405, nom
