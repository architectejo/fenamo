"""Validation indépendante du lot « état unique » (testeur), partie données : formulaires sans champ d'état, mobapp, migrations 0061 et
0062 (aller-retour, cas ambigus), commande verifier_etats_membres, tableau de bord et filtres par état, charger_donnees_demo."""
import inspect
import io
from datetime import date

import pytest
from django import forms
from django.contrib.auth.hashers import make_password
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.urls import reverse

from compte import roles
from compte.models import Compte
from compte.services.nominations import creer_nomination
from coptapp.models import Antenne, Membre, Province, miroirs_de
from tests.conftest import forcer_etat
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

CHAMPS_ETAT = {'etat', 'etat_precedent', 'motif_renvoi', 'renvoye', 'is_delete', 'is_validate1', 'is_validate2', 'is_validate3',
               'suppression_demandee', 'motif_suppression', 'suppression_demandee_par'}
ETATS = ('saisi', 'valide_antenne', 'valide_province', 'actif', 'renvoye', 'a_renouveler', 'supprime')


# ================================================================ formulaires sans champ d'état

def _formulaires_de_membre():
    import coptapp.forms
    import mobapp.forms
    trouves = []
    for module in (coptapp.forms, mobapp.forms):
        for _nom, classe in inspect.getmembers(module, inspect.isclass):
            meta = getattr(classe, 'Meta', None)
            if issubclass(classe, forms.ModelForm) and getattr(meta, 'model', None) is Membre:
                trouves.append(classe)
    return trouves


def test_F23_2f_aucun_formulaire_de_membre_n_expose_etat_ni_miroirs():
    formulaires = _formulaires_de_membre()
    assert len(formulaires) >= 3
    for f in formulaires:
        assert f._meta.fields is not None and f._meta.exclude is None, f.__name__  # liste blanche, jamais d'exclude
        exposes = set(f.base_fields) & CHAMPS_ETAT
        # MembreModificationForm peut exposer des champs de saisie, jamais d'état
        assert not exposes, (f.__name__, exposes)


def test_F23_2f_post_forge_d_un_champ_etat_ignore_a_la_creation_web(client, jeu):
    client.force_login(jeu['compte'])
    forge = {'etat': 'actif', 'etat_precedent': 'actif', 'motif_renvoi': 'x', 'renvoye': 'on', 'is_validate2': 'on', 'is_validate3': 'on',
             'is_delete': 'on', 'is_validate1': 'on'}
    donnees = {'nom': 'Forgé Web', 'genre': 'HOMME', 'qualite': 'PROPRIETAIRE', 'titre': 'MR', 'fonction': 'Membre simple',
               'comite': 'ANTENNE', 'etat_civil': 'Celibataire', 'categorie': 'H', 'date_naissance': '1992-05-06', **forge}
    client.post(reverse('add-membre', kwargs={'id': jeu['association'].id}), donnees)
    client.post(reverse('add-fenamo-membre'), {**donnees, 'nom': 'Forgé Fenamo', 'province': jeu['province'].id})
    crees = Membre.objects.filter(nom__startswith='Forgé')
    assert crees.count() >= 1
    for m in crees:
        assert m.etat == 'saisi' and not m.is_validate2 and not m.is_validate3 and not m.is_delete and not m.renvoye and m.motif_renvoi == ''


def test_F23_2f_post_forge_d_un_champ_etat_ignore_a_la_modification(client, jeu):
    client.force_login(jeu['compte'])
    m = jeu['membre']
    forcer_etat(m, 'valide_antenne')
    client.post(reverse('membre-view', kwargs={'id': m.id}),
                {'nom': 'Nom modifié', 'etat': 'actif', 'etat_precedent': 'x', 'is_validate3': 'on', 'renvoye': 'on', 'is_delete': 'on',
                 'motif_renvoi': 'forgé'})
    m.refresh_from_db()
    assert m.etat == 'valide_antenne' and not m.is_validate3 and not m.renvoye and not m.is_delete and m.motif_renvoi == ''


def test_F23_2f_post_forge_d_un_champ_etat_ignore_a_l_inscription_mobile(client, jeu):
    donnees = {'nom': 'Forgé Mob', 'genre': 'HOMME', 'qualite': 'PROPRIETAIRE', 'province': jeu['province'].id, 'date_naissance': '1992-05-06',
               'lieux_naissance': 'Kinshasa', 'password1': 'Mot-de-passe-9x', 'password2': 'Mot-de-passe-9x', 'etat': 'actif',
               'etat_precedent': 'actif', 'renvoye': 'on', 'is_validate2': 'on', 'is_validate3': 'on', 'motif_renvoi': 'x'}
    assert client.post(reverse('register'), donnees).status_code == 302
    m = Membre.objects.get(nom='Forgé Mob')
    assert m.etat == 'saisi' and not m.is_validate2 and not m.is_validate3 and not m.renvoye and m.motif_renvoi == ''


# ================================================================ mobapp : rattachements seulement à l'état saisi

MDP = 'Secret-fictif-91x'


@pytest.fixture
def mob(jeu):
    Antenne.objects.filter(pk=jeu['antenne'].pk).update(coordination=jeu['province'])
    m = Membre.objects.create(nom='Membre Mob', idf='MBR0000071', password=make_password(MDP), province=jeu['province'])
    return {**jeu, 'm': m}


def _connecter(client, m):
    assert client.post(reverse('home-mob'), {'idf': m.idf, 'pass': MDP}).status_code == 302


def test_F23_2f_inscription_mobile_cree_a_saisi_et_pose_le_miroir(client, jeu):
    client.post(reverse('register'), {'nom': 'Nouveau Mob', 'genre': 'HOMME', 'qualite': 'PROPRIETAIRE', 'province': jeu['province'].id,
                                      'date_naissance': '1992-05-06', 'lieux_naissance': 'K', 'password1': MDP, 'password2': MDP})
    m = Membre.objects.get(nom='Nouveau Mob')
    assert m.etat == 'saisi' and (m.is_delete, m.is_validate2, m.is_validate3, m.renvoye) == (False, False, False, False)


@pytest.mark.parametrize('etat', ETATS)
def test_F23_2f_mob_rattachement_seulement_a_l_etat_saisi(client, mob, etat):
    m = mob['m']
    if etat != 'saisi':
        forcer_etat(m, etat)
    if etat == 'supprime':  # un membre supprimé ne se connecte plus du tout
        client.post(reverse('home-mob'), {'idf': m.idf, 'pass': MDP})
        assert 'mob_membre_id' not in client.session
        return
    _connecter(client, m)
    r_str = client.post(reverse('attribut-str', kwargs={'id': m.id, 'id_str': mob['association'].id}))
    r_ville = client.post(reverse('attribut-ville', kwargs={'id': m.id, 'id_ville': mob['ville'].id}))
    r_data = client.post(reverse('data', kwargs={'id': m.id}), {'structure': mob['association'].id, 'ville': mob['ville'].id})
    m.refresh_from_db()
    if etat == 'saisi':
        assert r_str.status_code == 302 and m.structure_id == mob['association'].id
    else:
        assert r_str.status_code == 403 and r_ville.status_code == 403
        assert r_data.status_code == 302 and r_data['Location'].endswith(f'/espace/{m.id}')  # renvoyé à l'espace, rien écrit
        assert m.structure_id is None and m.ville_id is None and m.antenne_id is None and m.etat == etat


def test_F23_2f_mob_un_rattachement_ne_change_pas_l_etat(client, mob):
    m = mob['m']
    _connecter(client, m)
    client.post(reverse('attribut-str', kwargs={'id': m.id, 'id_str': mob['association'].id}))
    m.refresh_from_db()
    assert m.etat == 'saisi' and not m.is_validate2


# ================================================================ migrations 0061 / 0062

ANTE = [('coptapp', '0060_membre_renvoi')]
V61 = [('coptapp', '0061_membre_etat_unique')]
V62 = [('coptapp', '0062_membre_etat_donnees')]


def _migrer(cibles):
    MigrationExecutor(connection).migrate(cibles)
    return MigrationExecutor(connection).loader.project_state(cibles).apps


@pytest.fixture
def retour_au_sommet(db):
    yield
    e = MigrationExecutor(connection)
    e.migrate(e.loader.graph.leaf_nodes())


def _attendu_vers_etat(delete, v2, v3, renvoye):
    """Règle de la migration, écrite d'après sa documentation (indépendante de son code)."""
    etat = 'valide_antenne' if v2 else 'saisi'
    if v3:
        etat = 'actif'
    precedent = ''
    if renvoye:
        precedent, etat = etat, 'renvoye'
    if delete:
        precedent, etat = etat, 'supprime'
    return etat, precedent


COMBINAISONS = [(d, a, b, r) for d in (False, True) for a in (False, True) for b in (False, True) for r in (False, True)]


@pytest.mark.django_db(transaction=True)
def test_F23_2f_migration_0062_seize_combinaisons_resultat_exact_rejouable_et_inverse(retour_au_sommet):
    apps = _migrer(ANTE)
    M = apps.get_model('coptapp', 'Membre')
    ids = {}
    for d, a, b, r in COMBINAISONS:
        ids[(d, a, b, r)] = M.objects.create(nom=f'C{int(d)}{int(a)}{int(b)}{int(r)}', is_delete=d, is_validate2=a, is_validate3=b,
                                             renvoye=r, motif_renvoi='Motif' if r else '').pk
    avant = {k: (M.objects.get(pk=pk).nom, M.objects.get(pk=pk).motif_renvoi) for k, pk in ids.items()}

    M = _migrer(V62).get_model('coptapp', 'Membre')
    for k, pk in ids.items():
        m = M.objects.get(pk=pk)
        assert (m.etat, m.etat_precedent) == _attendu_vers_etat(*k), k
        assert (m.nom, m.motif_renvoi) == avant[k]
        # les booléens ne sont jamais modifiés dans le sens direct
        assert (m.is_delete, m.is_validate2, m.is_validate3, m.renvoye) == k
    instantane = {pk: (M.objects.get(pk=pk).etat, M.objects.get(pk=pk).etat_precedent) for pk in ids.values()}

    # inverse : miroirs recalculés selon la règle du modèle
    M = _migrer(V61).get_model('coptapp', 'Membre')
    for k, pk in ids.items():
        etat, precedent = instantane[pk]
        m = M.objects.get(pk=pk)
        attendu = miroirs_de(etat, precedent)
        assert (m.is_delete, m.is_validate2, m.is_validate3, m.renvoye) == (
            attendu['is_delete'], attendu['is_validate2'], attendu['is_validate3'], attendu['renvoye']), k
        assert m.nom.startswith('C')  # aucune perte de ligne
    assert M.objects.count() == 16

    # rejouable : de nouveau en avant, puis une deuxième fois (déjà converti) : états identiques
    M = _migrer(V62).get_model('coptapp', 'Membre')
    deuxieme = {pk: (M.objects.get(pk=pk).etat, M.objects.get(pk=pk).etat_precedent) for pk in ids.values()}
    from coptapp.migrations import __path__ as _  # noqa: F401
    import importlib
    mig = importlib.import_module('coptapp.migrations.0062_membre_etat_donnees')
    mig.vers_etat_unique(MigrationExecutor(connection).loader.project_state(V62).apps, None)
    troisieme = {pk: (M.objects.get(pk=pk).etat, M.objects.get(pk=pk).etat_precedent) for pk in ids.values()}
    assert deuxieme == troisieme
    # quel que soit le passage, un état déjà posé n'est pas dégradé : seul le cas « supprimé + renvoyé » est stable aussi
    assert all(etat in ETATS for etat, _p in troisieme.values())


@pytest.mark.django_db(transaction=True)
def test_F23_2f_migration_0062_les_cas_ambigus_sont_listes_par_la_commande(retour_au_sommet):
    apps = _migrer(ANTE)
    M = apps.get_model('coptapp', 'Membre')
    M.objects.create(nom='Ambigu V3 sans V2', idf='AMB1', is_validate3=True)
    M.objects.create(nom='Ambigu renvoyé supprimé', idf='AMB2', renvoye=True, is_delete=True)
    M.objects.create(nom='Net', idf='NET1', is_validate2=True)
    _migrer(V62)
    from coptapp.services.verification_etats import verifier
    r = verifier()
    ambigus = {idf for _pk, idf, _raisons in r['ambigus']}
    assert 'AMB1' in ambigus and 'NET1' not in ambigus
    assert r['ecarts'] == [] or all(idf != 'NET1' for _pk, idf, _c in r['ecarts'])  # AMB1 : is_validate2 miroir diffère de la lecture grossière


@pytest.mark.django_db(transaction=True)
def test_F23_2f_migration_0062_par_lots_et_sans_membre(retour_au_sommet):
    _migrer(ANTE)
    _migrer(V62)  # table vide : sans erreur
    _migrer(ANTE)
    M = _migrer(ANTE).get_model('coptapp', 'Membre')
    M.objects.bulk_create([M(nom=f'L{i}', is_validate2=True) for i in range(1100)])  # plus de deux lots de 500
    M = _migrer(V62).get_model('coptapp', 'Membre')
    assert M.objects.filter(etat='valide_antenne').count() == 1100


@pytest.mark.django_db
def test_F23_2f_makemigrations_a_jour():
    call_command('makemigrations', '--check', '--dry-run', verbosity=0)


# ================================================================ commande verifier_etats_membres

def _sortie(*args):
    s = io.StringIO()
    call_command('verifier_etats_membres', *args, stdout=s)
    return s.getvalue()


@pytest.fixture
def desaccords(db):
    ok = Membre.objects.create(nom='Cohérent', idf='OK1', etat='actif')
    ecart = Membre.objects.create(nom='Écart Secret Nom', idf='ECA1', etat='actif')
    from django.db.models import QuerySet
    QuerySet(model=Membre).filter(pk=ecart.pk).update(is_validate3=False, is_validate2=False)  # miroirs désynchronisés, sans traduction
    ambigu = Membre.objects.create(nom='Ambigu', idf='AMB1', etat='renvoye')
    QuerySet(model=Membre).filter(pk=ambigu.pk).update(is_validate2=True)  # renvoyé avec une validation conservée
    return ok, ecart, ambigu


def test_F23_2f_verifier_etats_compte_ecarts_ambigus_sans_donnees_personnelles(desaccords):
    sortie = _sortie()
    assert 'Membres lus : 3' in sortie and 'actif : 2' in sortie and 'renvoye : 1' in sortie
    assert 'Écarts état/miroirs : 2' in sortie and 'ECA1' in sortie and 'OK1' not in sortie
    assert 'Cas ambigus' in sortie and 'AMB1' in sortie
    assert 'Secret Nom' not in sortie  # id et idf seulement


def test_F23_2f_verifier_etats_sans_option_n_ecrit_rien(desaccords):
    avant = list(Membre.objects.order_by('pk').values_list('pk', 'etat', 'is_validate2', 'is_validate3', 'renvoye', 'is_delete'))
    _sortie()
    _sortie('--dry-run')
    assert list(Membre.objects.order_by('pk').values_list('pk', 'etat', 'is_validate2', 'is_validate3', 'renvoye', 'is_delete')) == avant


def test_F23_2f_verifier_etats_corriger_dry_run_n_ecrit_rien_et_corriger_ne_touche_que_les_miroirs(desaccords):
    ok, ecart, ambigu = desaccords
    avant = list(Membre.objects.order_by('pk').values_list('pk', 'etat', 'is_validate2', 'is_validate3', 'renvoye', 'is_delete'))
    assert 'Simulation : 2 membre(s)' in _sortie('--corriger', '--dry-run')
    assert list(Membre.objects.order_by('pk').values_list('pk', 'etat', 'is_validate2', 'is_validate3', 'renvoye', 'is_delete')) == avant
    sortie = _sortie('--corriger')
    assert '2 membre(s) resynchronisé(s)' in sortie
    for m in (ok, ecart, ambigu):
        m.refresh_from_db()
    assert (ecart.etat, ecart.is_validate2, ecart.is_validate3) == ('actif', True, True)  # miroirs recalculés DEPUIS l'état
    assert ambigu.etat == 'renvoye' and not ambigu.is_validate2  # l'état n'est jamais modifié
    assert 'Écarts état/miroirs : 0' in _sortie() and 'Cas ambigus' in _sortie()
    assert '0 membre(s) resynchronisé(s)' in _sortie('--corriger')  # idempotent


# ================================================================ tableau de bord et filtres par état

@pytest.fixture
def peuple(jeu):
    forcer_etat(jeu['membre'], 'actif')
    ant = jeu['antenne']
    Antenne.objects.filter(pk=ant.pk).update(coordination=jeu['province'])
    ant = Antenne.objects.get(pk=ant.pk)
    noms = {}
    for e, n in (('saisi', 2), ('valide_antenne', 3), ('valide_province', 1), ('actif', 2), ('renvoye', 2), ('a_renouveler', 1), ('supprime', 1)):
        for i in range(n):
            m = Membre.objects.create(nom=f'{e} numero {i}', antenne=ant, province=jeu['province'], user=jeu['compte'])
            forcer_etat(m, e)
            noms.setdefault(e, []).append(m.nom)
    return {**jeu, 'noms': noms, 'ant': ant}


def test_F23_2f_tableau_de_bord_compte_chaque_etat(client, peuple):
    from coptapp.services.tableau_bord import indicateurs_tableau_bord
    i = indicateurs_tableau_bord(peuple['compte'])
    assert (i['saisis'], i['valides_antenne'], i['valides_province'], i['actifs'], i['renvoyes']) == (2, 3, 1, 3, 2)  # 3 actifs : le membre du jeu en plus
    assert i['graphique']['etats'] == ['saisi', 'valide_antenne', 'valide_province', 'actif', 'renvoye'] and sum(i['graphique']['valeurs']) == 11
    client.force_login(peuple['compte'])
    r = client.get(reverse('tableau-bord'))
    assert r.status_code == 200 and b'<html' in r.content


@pytest.mark.parametrize('etat', ['saisi', 'valide_antenne', 'valide_province', 'actif', 'renvoye', 'a_renouveler'])
def test_F23_2f_liste_filtre_par_etat(client, peuple, etat):
    client.force_login(peuple['compte'])
    corps = client.get(reverse('liste-membre'), {'etat': etat}).content.decode()
    for e, noms in peuple['noms'].items():
        for nom in noms:
            assert (nom in corps) == (e == etat), (etat, nom)
    frag = client.get(reverse('liste-membre'), {'etat': etat}, HTTP_HX_REQUEST='true').content.decode()
    assert '<html' not in frag and all((n in frag) == (e == etat) for e, ns in peuple['noms'].items() for n in ns)


def test_F23_2f_liste_filtre_supprime_ou_inconnu_ne_montre_jamais_les_supprimes(client, peuple):
    client.force_login(peuple['compte'])
    for valeur in ('supprime', 'inconnu', "'; --"):
        corps = client.get(reverse('liste-membre'), {'etat': valeur}).content.decode()
        assert 'supprime numero 0' not in corps, valeur
    assert 'supprime numero 0' not in client.get(reverse('liste-membre')).content.decode()


def test_F23_2f_liste_perimetre_du_visiteur_et_du_va_par_etat(client, peuple):
    c = Compte.objects.create_user('vi', password='x')
    creer_nomination(peuple['compte'], c, roles.VI)
    client.force_login(c)
    corps = client.get(reverse('liste-membre')).content.decode()
    assert 'actif numero 0' in corps and 'saisi numero 0' not in corps and 'valide_province numero 0' not in corps
    assert 'a_renouveler numero 0' not in corps  # « à renouveler » n'est pas « actif » : le visiteur ne le voit plus
    va = Compte.objects.create_user('va', password='x')
    creer_nomination(peuple['compte'], va, roles.VA, antenne=peuple['ant'])
    client.force_login(va)
    corps = client.get(reverse('liste-membre')).content.decode()
    assert 'saisi numero 0' in corps and 'supprime numero 0' not in corps


# ================================================================ charger_donnees_demo

def _demo():
    call_command('charger_donnees_demo', verbosity=0)


def test_F23_2f_demo_etats_varies_et_coherents_avec_les_miroirs(settings, db):
    settings.DEBUG = True
    _demo()
    membres = Membre.objects.filter(idf__startswith='DEMO')
    etats = set(membres.values_list('etat', flat=True))
    assert {'saisi', 'valide_antenne', 'valide_province', 'actif', 'renvoye', 'supprime'} <= etats, etats
    for m in membres:
        attendu = miroirs_de(m.etat, m.etat_precedent)
        assert (m.is_delete, m.is_validate2, m.is_validate3, m.renvoye) == (
            attendu['is_delete'], attendu['is_validate2'], attendu['is_validate3'], attendu['renvoye']), (m.idf, m.etat)
        assert m.etat in ETATS
        if m.etat == 'renvoye':
            assert m.motif_renvoi
        if m.etat == 'supprime':
            assert m.etat_precedent in ETATS and m.etat_precedent != 'supprime'
    assert 'Écarts état/miroirs : 0' in _sortie()


def test_F23_2f_demo_idempotente_sur_les_etats(settings, db):
    settings.DEBUG = True
    _demo()
    avant = sorted(Membre.objects.filter(idf__startswith='DEMO').values_list('idf', 'etat', 'etat_precedent', 'motif_renvoi'))
    from compte.models import JournalAction
    journal = JournalAction.objects.count()
    _demo()
    _demo()
    assert sorted(Membre.objects.filter(idf__startswith='DEMO').values_list('idf', 'etat', 'etat_precedent', 'motif_renvoi')) == avant
    assert JournalAction.objects.count() == journal
    call_command('charger_donnees_demo', '--reinitialiser', verbosity=0)
    assert sorted(Membre.objects.filter(idf__startswith='DEMO').values_list('idf', 'etat', 'etat_precedent', 'motif_renvoi')) == avant
