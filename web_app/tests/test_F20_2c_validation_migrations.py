"""Validation indépendante 2c : migrations coptapp 0053 à 0055 et compte 0012 depuis l'état 0052 / 0011, aller-retour."""
import pytest
from django.contrib.auth.hashers import check_password, identify_hasher, make_password
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

ETAT_AVANT = [('coptapp', '0052_membre_suppression_demandee_par'), ('compte', '0011_alter_journalaction_action')]
ETAT_APRES = [('coptapp', '0055_hacher_mots_de_passe_des_membres'), ('compte', '0012_alter_journalaction_action')]


def _migrer(cibles):
    executeur = MigrationExecutor(connection)
    executeur.migrate(cibles)
    return MigrationExecutor(connection).loader.project_state(cibles).apps


@pytest.fixture
def retour_au_sommet(db):
    yield
    executeur = MigrationExecutor(connection)
    executeur.migrate(executeur.loader.graph.leaf_nodes())


@pytest.mark.django_db(transaction=True)
def test_F20_2c_migrations_0053_a_0055_depuis_0052_resultat_exact_et_rejouable(retour_au_sommet):
    apps = _migrer(ETAT_AVANT)
    Membre = apps.get_model('coptapp', 'Membre')
    deja = make_password('deja-hache-9')
    trente_deux = 'a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6'  # 32 caractères : ressemble à un MD5 sans sel
    clairs = {
        'Clair simple': 'motdepasse',
        'Clair special': 'p@$$w0rd"<é>\' $x$',
        'Clair 32': trente_deux,
        'Clair espace': '  avec espaces  ',
        'Clair long': 'x' * 60,
    }
    for nom, mdp in clairs.items():
        Membre.objects.create(nom=nom, password=mdp)
    Membre.objects.create(nom='Hache', password=deja)
    Membre.objects.create(nom='Vide', password='')
    Membre.objects.create(nom='Nul', password=None)
    avant = {m.nom: m.password for m in Membre.objects.all()}

    apres_apps = _migrer(ETAT_APRES)
    M = apres_apps.get_model('coptapp', 'Membre')
    apres = {m.nom: m.password for m in M.objects.all()}
    for nom, mdp in clairs.items():
        assert apres[nom] != mdp, nom
        identify_hasher(apres[nom])
        assert check_password(mdp, apres[nom]), nom
    assert apres['Hache'] == deja and apres['Vide'] == '' and apres['Nul'] is None
    assert M._meta.get_field('password').max_length == 128

    # rejouable : arrière (les hachages restent) puis avant : aucun double hachage
    _migrer(ETAT_AVANT)
    assert {m.nom: m.password for m in _migrer(ETAT_AVANT).get_model('coptapp', 'Membre').objects.all()} == apres
    apres2 = {m.nom: m.password for m in _migrer(ETAT_APRES).get_model('coptapp', 'Membre').objects.all()}
    assert apres2 == apres
    assert avant['Hache'] == apres2['Hache']


@pytest.mark.django_db(transaction=True)
def test_F20_2c_migration_compte_0012_ajoute_et_retire_l_action_consultation_de_piece_sans_perte(retour_au_sommet):
    apps = _migrer(ETAT_APRES)
    Journal = apps.get_model('compte', 'JournalAction')
    champ = Journal._meta.get_field('action')
    assert 'consultation_piece' in dict(champ.choices)
    # aller-retour complet : l'action n'existe pas avant 0012
    avant = _migrer(ETAT_AVANT).get_model('compte', 'JournalAction')._meta.get_field('action')
    assert 'consultation_piece' not in dict(avant.choices)
    apps = _migrer(ETAT_APRES)
    assert apps.get_model('compte', 'JournalAction')._meta.get_field('action').max_length == 40


@pytest.mark.django_db(transaction=True)
def test_F20_2c_etat_final_sans_migration_manquante():
    from django.core.management import call_command
    call_command('makemigrations', '--check', '--dry-run')
