"""F-11 : antennes (commune ou territoire) issues des villes héritées ; service de géographie ; périmètres ; migration 0056."""
import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.urls import reverse

from compte.models import Compte, JournalAction
from coptapp.models import Antenne, AssociationMembre, Membre, Province, Ville
from coptapp.services import geographie
from coptapp.services.droits_provisoires import (
    antennes_du_perimetre, cible_rattachable, provinces_du_perimetre, villes_du_perimetre,
)
from coptapp.services.geographie import (
    antenne_depuis_ville, completer_antenne, coordination_par_code, rattacher_antenne, rattacher_ville, ville_depuis_antenne,
)
from tests.test_F21_matrice_routes import acteurs  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


# ---------------------------------------------------------------- modèle

def test_F11_champs_de_l_antenne(jeu):
    a = Antenne.objects.create(nom='Lemba', coordination=jeu['province'], type=Antenne.Type.COMMUNE, ville_origine=jeu['ville'],
                               code='LEM')
    assert jeu['province'].antennes.get() == a and jeu['ville'].antenne_issue == a
    assert a.type == 'commune' and a.coordination_id == jeu['province'].id


def test_F11_code_d_antenne_unique_mais_plusieurs_sans_code(db):
    Antenne.objects.create(nom='A', code='X1')
    Antenne.objects.create(nom='B')
    Antenne.objects.create(nom='C', code=None)
    Antenne.objects.create(nom='D', code='  ')  # vide : devient NULL
    assert Antenne.objects.filter(code__isnull=True).count() == 3
    with pytest.raises(IntegrityError), transaction.atomic():
        Antenne.objects.create(nom='E', code='X1')


def test_F11_une_ville_n_a_qu_une_antenne_d_origine(jeu):
    Antenne.objects.create(nom='A', ville_origine=jeu['ville'])
    with pytest.raises(IntegrityError), transaction.atomic():
        Antenne.objects.create(nom='B', ville_origine=jeu['ville'])


def test_F11_suppression_de_la_ville_ou_de_l_antenne_ne_supprime_pas_les_membres(jeu):
    a = Antenne.objects.create(nom='A', ville_origine=jeu['ville'])
    AssociationMembre.objects.filter(pk=jeu['association'].pk).update(antenne=a)
    a.delete()
    jeu['association'].refresh_from_db()
    assert jeu['association'].antenne_id is None


# ---------------------------------------------------------------- service

def test_F11_coordination_par_code(db):
    p = Province.objects.create(nom='Fictive', code='ZZ1')
    assert coordination_par_code(' zz1 ') == p
    assert coordination_par_code('ZZ9') is None and coordination_par_code('') is None and coordination_par_code(None) is None


def test_F11_antenne_depuis_ville_lecture_et_creation(jeu):
    ville = Ville.objects.create(nom='Matete', province=jeu['province'])
    assert antenne_depuis_ville(None) is None and antenne_depuis_ville(ville) is None
    assert Antenne.objects.filter(ville_origine=ville).count() == 0  # la lecture ne crée rien
    a = antenne_depuis_ville(ville, creer=True)
    assert a.nom == 'Matete' and a.coordination_id == jeu['province'].id and a.ville_origine_id == ville.id
    assert antenne_depuis_ville(ville, creer=True) == a and antenne_depuis_ville(ville) == a  # idempotent
    assert ville_depuis_antenne(a) == ville and ville_depuis_antenne(None) is None
    assert ville_depuis_antenne(Antenne.objects.create(nom='Nouvelle')) is None


def test_F11_rattacher_ville_ecrit_ville_et_antenne_et_journalise(jeu):
    ville = Ville.objects.create(nom='Ngaba', province=jeu['province'])
    membre = jeu['membre']
    rattacher_ville(jeu['compte'], membre, ville)
    membre.refresh_from_db()
    assert membre.ville_id == ville.id and membre.antenne_id == ville.antenne_issue.id
    ligne = JournalAction.objects.filter(action=JournalAction.Action.RATTACHEMENT, objet_id=membre.id).latest('id')
    assert ligne.apres == {'ville': ville.id, 'antenne': ville.antenne_issue.id} and ligne.avant['ville'] == jeu['ville'].id
    rattacher_ville(jeu['compte'], membre, None)  # détacher les deux
    membre.refresh_from_db()
    assert membre.ville_id is None and membre.antenne_id is None


def test_F11_rattacher_ville_association_et_auteur_absent(jeu):
    ville = Ville.objects.create(nom='Kintambo', province=jeu['province'])
    rattacher_ville(None, jeu['association'], ville)  # espace mobile : pas de compte
    jeu['association'].refresh_from_db()
    assert jeu['association'].ville_id == ville.id and jeu['association'].antenne_id == ville.antenne_issue.id


def test_F11_rattacher_ville_est_atomique(jeu, monkeypatch):
    ville = Ville.objects.create(nom='Bandal', province=jeu['province'])

    def echec(*a, **k):
        raise RuntimeError('journal indisponible')

    monkeypatch.setattr(geographie, 'journaliser', echec)
    avant = (jeu['membre'].ville_id, jeu['membre'].antenne_id)
    with pytest.raises(RuntimeError):
        rattacher_ville(jeu['compte'], jeu['membre'], ville)
    jeu['membre'].refresh_from_db()
    assert (jeu['membre'].ville_id, jeu['membre'].antenne_id) == avant  # ni ville ni antenne : tout ou rien
    assert not Antenne.objects.filter(ville_origine=ville).exists()


def test_F11_rattacher_ville_n_ecrase_pas_une_autre_modification(jeu):
    ville = Ville.objects.create(nom='Limete', province=jeu['province'])
    ancien = Membre.objects.get(pk=jeu['membre'].pk)
    Membre.objects.filter(pk=ancien.pk).update(village='Concurrent')
    rattacher_ville(jeu['compte'], ancien, ville)
    assert Membre.objects.get(pk=ancien.pk).village == 'Concurrent'


def test_F11_rattacher_antenne_suit_la_ville_d_origine(jeu):
    issue = antenne_depuis_ville(Ville.objects.create(nom='Selembao', province=jeu['province']), creer=True)
    nouvelle = Antenne.objects.create(nom='Nouvelle', coordination=jeu['province'])
    rattacher_antenne(jeu['compte'], jeu['membre'], issue)
    jeu['membre'].refresh_from_db()
    assert jeu['membre'].antenne_id == issue.id and jeu['membre'].ville_id == issue.ville_origine_id
    rattacher_antenne(jeu['compte'], jeu['membre'], nouvelle)  # sans ville d'origine : la ville reste
    jeu['membre'].refresh_from_db()
    assert jeu['membre'].antenne_id == nouvelle.id and jeu['membre'].ville_id == issue.ville_origine_id


def test_F11_completer_antenne_apres_un_formulaire(jeu):
    sans = Membre.objects.create(nom='Sans antenne', ville=jeu['ville'])
    assert sans.antenne_id is None
    completer_antenne(sans)
    sans.refresh_from_db()
    assert sans.antenne_id == jeu['ville'].antenne_issue.id and sans.ville_id == jeu['ville'].id
    avec = Membre.objects.create(nom='Déjà', ville=jeu['ville'], antenne=jeu['antenne'])
    completer_antenne(avec)
    avec.refresh_from_db()
    assert avec.antenne_id == jeu['antenne'].id  # une antenne déjà choisie n'est pas écrasée


# ---------------------------------------------------------------- vues et mobapp

def test_F11_vue_attribution_de_ville_ecrit_aussi_l_antenne(client, acteurs):
    ville = Ville.objects.create(nom='Kalamu', province=acteurs['province'])
    client.force_login(acteurs['comptes']['su'])
    r = client.post(reverse('ville-attribution', kwargs={'idM': acteurs['membre'].id, 'id': ville.id}))
    assert r.status_code == 302
    acteurs['membre'].refresh_from_db()
    assert acteurs['membre'].ville_id == ville.id and acteurs['membre'].antenne.ville_origine_id == ville.id


def test_F11_vue_attribution_d_antenne_ecrit_aussi_la_ville(client, acteurs):
    issue = antenne_depuis_ville(Ville.objects.create(nom='Masina', province=acteurs['province']), creer=True)
    client.force_login(acteurs['comptes']['su'])
    client.post(reverse('antenne-attribution', kwargs={'idM': acteurs['membre'].id, 'id': issue.id}))
    acteurs['membre'].refresh_from_db()
    assert acteurs['membre'].antenne_id == issue.id and acteurs['membre'].ville_id == issue.ville_origine_id


def test_F11_vue_ajout_de_ville_cree_son_antenne(client, acteurs):
    client.force_login(acteurs['comptes']['su'])
    client.post(reverse('add-ville', kwargs={'id': acteurs['province'].id}), {'nom': 'Kimbanseke'})
    ville = Ville.objects.get(nom='Kimbanseke')
    assert ville.antenne_issue.coordination_id == acteurs['province'].id


def test_F11_vue_ville_d_une_association(client, acteurs):
    ville = Ville.objects.create(nom='Ndjili', province=acteurs['province'])
    client.force_login(acteurs['comptes']['su'])
    client.post(reverse('ville-attr', kwargs={'id': ville.id, 'sid': acteurs['association'].id}))
    acteurs['association'].refresh_from_db()
    assert acteurs['association'].ville_id == ville.id and acteurs['association'].antenne_id == ville.antenne_issue.id


def test_F11_vue_ajout_d_antenne_porte_la_coordination(client, acteurs):
    client.force_login(acteurs['comptes']['su'])
    client.post(reverse('add-antenne', kwargs={'id': acteurs['association'].id}), {'nom': 'Neuve', 'zone': 'Z', 'code': 'NEU'})
    assert Antenne.objects.get(code='NEU').coordination_id == acteurs['province'].id


def test_F11_mob_rattachement_ecrit_ville_et_antenne(client, jeu):
    from django.contrib.auth.hashers import make_password

    from compte.services.mobile import empreinte_session
    m = Membre.objects.create(nom='Mob', idf='MBR0000090', password=make_password('x'), province=jeu['province'])
    s = client.session
    s['mob_membre_id'] = m.id
    s['mob_empreinte'] = empreinte_session(m)
    s.save()
    r = client.post(reverse('attribut-ville', kwargs={'id': m.id, 'id_ville': jeu['ville'].id}))
    assert r.status_code == 302
    m.refresh_from_db()
    assert m.ville_id == jeu['ville'].id and m.antenne_id == jeu['ville'].antenne_issue.id
    m2 = Membre.objects.create(nom='Mob2', idf='MBR0000091', password=make_password('x'), province=jeu['province'])
    s = client.session
    s['mob_membre_id'] = m2.id
    s['mob_empreinte'] = empreinte_session(m2)
    s.save()
    client.post(reverse('data', kwargs={'id': m2.id}), {'structure': jeu['association'].id})
    m2.refresh_from_db()
    assert m2.structure_id == jeu['association'].id and m2.ville_id == jeu['association'].ville_id and m2.antenne_id


# ---------------------------------------------------------------- périmètres (T5)

def test_F11_perimetre_antennes_issues_des_villes_et_antenne_de_l_association(jeu):
    compte = Compte.objects.create_user('p3', password='x', privilege3=True)
    jeu['association'].users.add(compte)
    issue = antenne_depuis_ville(jeu['ville'], creer=True)  # antenne de la ville de l'association
    choisie = Antenne.objects.create(nom='Choisie', coordination=jeu['province'])
    autre_ville = Ville.objects.create(nom='Ailleurs', province=Province.objects.create(nom='Autre province', sigle='AP'))
    ailleurs = antenne_depuis_ville(autre_ville, creer=True)
    AssociationMembre.objects.filter(pk=jeu['association'].pk).update(antenne=choisie)
    ids = set(antennes_du_perimetre(compte).values_list('pk', flat=True))
    assert {issue.id, choisie.id, jeu['antenne'].id} <= ids and ailleurs.id not in ids  # aucune régression sur l'ancienne antenne
    assert jeu['province'] in provinces_du_perimetre(compte)
    assert autre_ville not in villes_du_perimetre(compte)


def test_F11_perimetre_via_la_fiche_du_membre_avec_ville_sans_antenne(jeu):
    compte = Compte.objects.create_user('simple', password='x', membreId=jeu['membre'].id)
    Membre.objects.filter(pk=jeu['membre'].pk).update(antenne=None)
    issue = antenne_depuis_ville(jeu['ville'], creer=True)
    assert issue.id in set(antennes_du_perimetre(compte).values_list('pk', flat=True))


def test_F11_perimetre_une_antenne_donne_sa_ville_et_sa_coordination(jeu):
    compte = Compte.objects.create_user('p2', password='x', privilege2=True)
    autre_province = Province.objects.create(nom='Nord', sigle='NO')
    ville = Ville.objects.create(nom='Nordville', province=autre_province)
    antenne = antenne_depuis_ville(ville, creer=True)
    association = AssociationMembre.objects.create(nom='Nord assoc', num_justice='F-NORD', antenne=antenne)
    association.users.add(compte)
    assert ville in villes_du_perimetre(compte) and autre_province in provinces_du_perimetre(compte)
    assert antenne in antennes_du_perimetre(compte)


def test_F11_cible_rattachable_avec_antennes_issues(jeu):
    p3 = Compte.objects.create_user('p3', password='x', privilege3=True)
    jeu['association'].users.add(p3)
    issue = antenne_depuis_ville(jeu['ville'], creer=True)
    assert cible_rattachable(p3, 'antenne', issue)  # antenne issue de la ville de l'association
    assert cible_rattachable(p3, 'antenne', jeu['antenne'])  # ancienne antenne de l'association : pas de régression
    choisie = Antenne.objects.create(nom='Choisie')
    AssociationMembre.objects.filter(pk=jeu['association'].pk).update(antenne=choisie)
    assert cible_rattachable(p3, 'antenne', choisie)
    etrangere = antenne_depuis_ville(Ville.objects.create(nom='Etrangere'), creer=True)
    assert not cible_rattachable(p3, 'antenne', etrangere)
    # ville : celle de l'association, ou celle d'origine de son antenne
    assert cible_rattachable(p3, 'ville', jeu['ville'])
    AssociationMembre.objects.filter(pk=jeu['association'].pk).update(ville=None, antenne=issue)
    assert cible_rattachable(p3, 'ville', jeu['ville']) and not cible_rattachable(p3, 'ville', etrangere.ville_origine)


# ---------------------------------------------------------------- migration 0056

@pytest.mark.django_db(transaction=True)
def test_F11_migration_0056_aller_retour_et_codes_d_antenne_normalises():
    executeur = MigrationExecutor(connection)
    executeur.migrate([('coptapp', '0055_hacher_mots_de_passe_des_membres')])
    ancien = MigrationExecutor(connection).loader.project_state([('coptapp', '0055_hacher_mots_de_passe_des_membres')]).apps
    Ant = ancien.get_model('coptapp', 'Antenne')
    ids = [Ant.objects.create(nom=n, code=c).pk for n, c in (('A', 'DUP'), ('B', 'DUP'), ('C', ''), ('D', ''), ('E', None), ('F', 'UNIQ'))]
    Province_ = ancien.get_model('coptapp', 'Province')
    Province_.objects.create(nom='Avant', sigle='AV')
    executeur = MigrationExecutor(connection)
    executeur.migrate([('coptapp', '0056_geographie_champs')])
    nouveau = MigrationExecutor(connection).loader.project_state([('coptapp', '0056_geographie_champs')]).apps
    codes = dict(nouveau.get_model('coptapp', 'Antenne').objects.values_list('nom', 'code'))
    assert codes['A'] == 'DUP' and codes['B'] == f'DUP-{ids[1]}' and codes['C'] is None and codes['D'] is None
    assert codes['E'] is None and codes['F'] == 'UNIQ'
    p = nouveau.get_model('coptapp', 'Province').objects.get(nom='Avant')
    assert p.code is None and p.ordre is None and p.sigle == 'AV'  # l'ancien sigle est intact
    executeur = MigrationExecutor(connection)
    executeur.migrate([('coptapp', '0055_hacher_mots_de_passe_des_membres')])  # retour arrière
    assert ancien.get_model('coptapp', 'Province').objects.get(nom='Avant').sigle == 'AV'
    executeur = MigrationExecutor(connection)
    executeur.migrate(executeur.loader.graph.leaf_nodes())
