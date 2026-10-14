"""F-11 / § 9.1 (audit sécurité 2d) : rattachements mobiles, coordination de l'antenne, ville d'une association, migration 0056."""
import pytest
from django.contrib.auth.hashers import make_password
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.urls import reverse

from compte.models import JournalAction
from compte.services.mobile import empreinte_session
from coptapp.forms import AntenneForm
from coptapp.models import Antenne, AssociationMembre, Membre, Province, Ville
from coptapp.services.geographie import antenne_depuis_ville, rattacher_association
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def _mobile(client, membre):
    s = client.session
    s['mob_membre_id'] = membre.id
    s['mob_empreinte'] = empreinte_session(membre)
    s.save()


@pytest.fixture
def libre(jeu):
    """Un membre mobile sans rattachement, non validé (is_validate1 vaut True dès la création : ce n'est pas « validé »)."""
    m = Membre.objects.create(nom='Libre', idf='MBR0000080', password=make_password('x'), province=jeu['province'])
    return m


def _etat(m):
    return Membre.objects.values('structure_id', 'ville_id', 'antenne_id').get(pk=m.pk)


# ---------------------------------------------------------------- M1 : garde des rattachements mobiles

@pytest.mark.parametrize('validation', [{'is_validate2': True}, {'is_validate3': True}])
def test_M1_membre_valide_ne_change_plus_seul_ses_rattachements(client, jeu, libre, validation):
    Membre.objects.filter(pk=libre.pk).update(**validation)
    _mobile(client, Membre.objects.get(pk=libre.pk))
    avant = _etat(libre)
    journal = JournalAction.objects.count()
    assert client.post(reverse('attribut-str', kwargs={'id': libre.id, 'id_str': jeu['association'].id})).status_code == 403
    assert client.post(reverse('attribut-ville', kwargs={'id': libre.id, 'id_ville': jeu['ville'].id})).status_code == 403
    assert client.get(reverse('data', kwargs={'id': libre.id})).status_code == 302  # data renvoie à l'espace
    assert client.post(reverse('data', kwargs={'id': libre.id}), {'structure': jeu['association'].id}).status_code == 302
    assert _etat(libre) == avant and JournalAction.objects.count() == journal


def test_M1_membre_deja_rattache_refuse(client, jeu, libre):
    _mobile(client, libre)
    assert client.post(reverse('attribut-str', kwargs={'id': libre.id, 'id_str': jeu['association'].id})).status_code == 302
    avant = _etat(libre)
    autre = AssociationMembre.objects.create(nom='Autre', province=jeu['province'], num_justice='F-AUTRE', ville=jeu['ville'])
    assert client.post(reverse('attribut-str', kwargs={'id': libre.id, 'id_str': autre.id})).status_code == 403  # déjà une association
    assert _etat(libre) == avant
    ville2 = Ville.objects.create(nom='Deux', province=jeu['province'])
    assert client.post(reverse('attribut-ville', kwargs={'id': libre.id, 'id_ville': ville2.id})).status_code == 403  # déjà une antenne
    assert _etat(libre) == avant


def test_M1_attribut_str_journalise_et_met_ville_et_antenne_en_coherence(client, jeu, libre):
    _mobile(client, libre)
    avant = JournalAction.objects.filter(action=JournalAction.Action.RATTACHEMENT).count()
    assert client.post(reverse('attribut-str', kwargs={'id': libre.id, 'id_str': jeu['association'].id})).status_code == 302
    libre.refresh_from_db()
    ville_assoc = jeu['association'].ville
    assert libre.structure_id == jeu['association'].id and libre.ville_id == ville_assoc.id
    assert libre.antenne_id == ville_assoc.antenne_issue.id
    ligne = JournalAction.objects.filter(action=JournalAction.Action.RATTACHEMENT, objet_id=libre.id).latest('id')
    assert JournalAction.objects.filter(action=JournalAction.Action.RATTACHEMENT).count() == avant + 1
    assert {k: v for k, v in ligne.avant.items() if k != 'province'} == {'structure': None, 'ville': None, 'antenne': None}
    assert {k: v for k, v in ligne.apres.items() if k != 'province'} == {
        'structure': jeu['association'].id, 'ville': ville_assoc.id, 'antenne': libre.antenne_id}


def test_M1_rattacher_association_avec_antenne_seule_et_sans_rien(jeu, libre):
    neuve = Province.objects.create(nom='Neuve', code='NEU')
    antenne = Antenne.objects.create(nom='Sans ville', coordination=neuve)
    seule = AssociationMembre.objects.create(nom='Antenne seule', num_justice='F-S', antenne=antenne)
    rattacher_association(None, libre, seule)
    libre.refresh_from_db()
    assert libre.structure_id == seule.id and libre.antenne_id == antenne.id and libre.ville_id is None
    vide = AssociationMembre.objects.create(nom='Vide', num_justice='F-V')
    autre = Membre.objects.create(nom='Autre')
    rattacher_association(None, autre, vide)
    autre.refresh_from_db()
    assert autre.structure_id == vide.id and autre.ville_id is None and autre.antenne_id is None


def test_M1_rattacher_association_ne_mele_pas_deux_anciennes_donnees(jeu, libre):
    ville = Ville.objects.create(nom='Origine', province=jeu['province'])
    issue = antenne_depuis_ville(ville, creer=True)
    association = AssociationMembre.objects.create(nom='Avec ville', num_justice='F-AV', ville=ville)  # antenne non renseignée
    rattacher_association(None, libre, association)
    libre.refresh_from_db()
    assert libre.ville_id == ville.id and libre.antenne_id == issue.id


# ---------------------------------------------------------------- F1 : coordination de l'antenne issue d'une ville

def test_F1_antenne_issue_d_une_ville_garde_la_coordination_de_la_ville(jeu):
    issue = antenne_depuis_ville(jeu['ville'], creer=True)
    autre = Province.objects.create(nom='Autre', code='AU')
    formulaire = AntenneForm({'nom': 'N', 'coordination': autre.id}, instance=issue)
    assert not formulaire.is_valid() and 'coordination' in formulaire.errors
    ok = AntenneForm({'nom': 'N', 'coordination': jeu['province'].id}, instance=issue)
    assert ok.is_valid()
    sans = AntenneForm({'nom': 'N'}, instance=issue)
    assert sans.is_valid()
    libre = Antenne.objects.create(nom='Libre')  # sans ville d'origine : aucune contrainte
    assert AntenneForm({'nom': 'N', 'coordination': autre.id}, instance=libre).is_valid()


def test_F1_la_vue_de_modification_refuse_aussi(client, jeu):
    issue = antenne_depuis_ville(jeu['ville'], creer=True)
    autre = Province.objects.create(nom='Autre', code='AU')
    client.force_login(jeu['compte'])
    client.post(reverse('edit-antenne', kwargs={'id': issue.id}), {'nom': 'N', 'coordination': autre.id})
    issue.refresh_from_db()
    assert issue.coordination_id == jeu['province'].id


# ---------------------------------------------------------------- F2 : ville d'une association sans coordination

def test_F2_ville_attr_association_sans_coordination_404(client, jeu):
    sans = AssociationMembre.objects.create(nom='Sans coordination', num_justice='F-SC')
    client.force_login(jeu['compte'])
    assert client.post(reverse('ville-attr', kwargs={'id': jeu['ville'].id, 'sid': sans.id})).status_code == 404
    sans.refresh_from_db()
    assert sans.ville_id is None and sans.antenne_id is None


# ---------------------------------------------------------------- F3 : liens de la page d'une ville

def test_F3_ville_view_les_liens_visent_l_association_pas_la_ville(client, jeu):
    client.force_login(jeu['compte'])
    html = client.get(reverse('ville-view', kwargs={'id': jeu['ville'].id})).content.decode()
    assert reverse('add-antenne', kwargs={'id': jeu['association'].id}) in html
    assert reverse('add-membre', kwargs={'id': jeu['association'].id}) in html
    if jeu['ville'].id != jeu['association'].id:
        assert reverse('add-antenne', kwargs={'id': jeu['ville'].id}) not in html


def test_F3_ville_view_sans_association_ne_plante_pas(client, jeu):
    seule = Ville.objects.create(nom='Seule', province=jeu['province'])
    client.force_login(jeu['compte'])
    r = client.get(reverse('ville-view', kwargs={'id': seule.id}))
    assert r.status_code == 200 and 'Ajout antenne' not in r.content.decode()


# ---------------------------------------------------------------- F4 : migration 0056, unicité vérifiée

@pytest.mark.django_db(transaction=True)
def test_F4_migration_0056_le_code_renomme_est_verifie_libre(capsys):
    MigrationExecutor(connection).migrate([('coptapp', '0055_hacher_mots_de_passe_des_membres')])
    ancien = MigrationExecutor(connection).loader.project_state([('coptapp', '0055_hacher_mots_de_passe_des_membres')]).apps
    Antenne_ = ancien.get_model('coptapp', 'Antenne')
    a = Antenne_.objects.create(nom='A', code='DUP')
    b = Antenne_.objects.create(nom='B', code='DUP')
    c = Antenne_.objects.create(nom='C', code=f'DUP-{b.pk}')  # le suffixe « naturel » de B est déjà pris
    d = Antenne_.objects.create(nom='D', code='DUP')
    long = Antenne_.objects.create(nom='L1', code='X' * 20)
    long2 = Antenne_.objects.create(nom='L2', code='X' * 20)
    MigrationExecutor(connection).migrate([('coptapp', '0056_geographie_champs')])
    nouveau = MigrationExecutor(connection).loader.project_state([('coptapp', '0056_geographie_champs')]).apps
    codes = {x.nom: x.code for x in nouveau.get_model('coptapp', 'Antenne').objects.all()}
    assert codes['A'] == 'DUP' and codes['C'] == f'DUP-{b.pk}'
    assert codes['B'] == f'DUP-{b.pk}-2'  # collision évitée par la boucle de suffixe
    assert codes['D'] == f'DUP-{d.pk}'
    assert codes['L1'] == 'X' * 20 and codes['L2'].endswith(f'-{long2.pk}') and len(codes['L2']) == 20  # début raccourci, suffixe intact
    assert len(set(codes.values())) == len(codes)  # tous uniques
    assert 'AVERTISSEMENT 0056' in capsys.readouterr().out
    MigrationExecutor(connection).migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())
