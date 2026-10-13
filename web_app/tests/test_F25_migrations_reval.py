"""Revalidation indépendante (testeur) : migrations (0050 à 0052 : pièce, demande de suppression, auteur de la demande).

Chaque scénario tourne dans un SOUS-PROCESSUS avec sa propre base SQLite dans un dossier temporaire (variable
DATABASE_URL) : ni `db.sqlite3` ni `db.sqlite3.avant-migration` ne sont touchés. Données fictives uniquement.
- base vide : `migrate` complet puis `makemigrations --check` ;
- base à l'état 0049 avec données : `migrate coptapp 0049`, insertion, `migrate`, vérification (aucune perte) ;
- retour arrière jusqu'à 0049 puis nouvelle montée : les lignes survivent.
"""
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

PROJET = Path(__file__).resolve().parent.parent
NOM_0049 = next((PROJET / 'coptapp' / 'migrations').glob('0049_*.py')).stem


def _env(base: Path):
    cible = base.resolve()
    assert cible != (PROJET / 'db.sqlite3').resolve()
    env = os.environ.copy()
    env.update({'DATABASE_URL': f'sqlite:///{cible.as_posix()}', 'DJANGO_SETTINGS_MODULE': 'fenamo.settings.dev',
                'DEBUG': 'True', 'MEDIA_ROOT': str(base.parent / 'media_migration')})
    return env


def _manage(base, *args, ok=True):
    r = subprocess.run([sys.executable, 'manage.py', *args], cwd=PROJET, env=_env(base), capture_output=True,
                       text=True, timeout=900)
    if ok:
        assert r.returncode == 0, f'manage.py {" ".join(args)}\n{r.stdout[-1500:]}\n{r.stderr[-2500:]}'
    return r


def _script(base, code, tmp_path):
    chemin = tmp_path / 'script_migration.py'
    chemin.write_text("import os, sys, json\nsys.path.insert(0, %r)\nimport django\ndjango.setup()\n" % str(PROJET)
                      + textwrap.dedent(code), encoding='utf-8')
    r = subprocess.run([sys.executable, str(chemin)], cwd=PROJET, env=_env(base), capture_output=True, text=True,
                       timeout=600)
    assert r.returncode == 0, r.stderr[-3000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


INSERER_A_L_ETAT_0049 = """
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    apps = MigrationExecutor(connection).loader.project_state([('coptapp', %r)]).apps
    Compte, Province = apps.get_model('compte', 'Compte'), apps.get_model('coptapp', 'Province')
    Ville, Asso = apps.get_model('coptapp', 'Ville'), apps.get_model('coptapp', 'AssociationMembre')
    Antenne, Membre = apps.get_model('coptapp', 'Antenne'), apps.get_model('coptapp', 'Membre')
    Moto, Famille = apps.get_model('coptapp', 'Moto'), apps.get_model('coptapp', 'Famille')
    Notification = apps.get_model('coptapp', 'Notification')
    compte = Compte.objects.create(username='fictif-migration', password='x')
    province = Province.objects.create(nom='Province fictive', sigle='PF', user=compte)
    ville = Ville.objects.create(nom='Ville fictive', province=province)
    asso = Asso.objects.create(nom='Association fictive', sigle='AF', num_justice='F-MIG-1', province=province, ville=ville)
    asso.users.add(compte)
    antenne = Antenne.objects.create(nom='Antenne fictive', structure=asso)
    m1 = Membre.objects.create(nom='Membre Un', telephone='+243000000001', structure=asso, antenne=antenne,
                               is_validate2=True, user=compte)
    m2 = Membre.objects.create(nom='Membre Deux', is_delete=True, structure=asso)
    m3 = Membre.objects.create(nom='Membre Trois', is_validate2=True, is_validate3=True, fiche_id='fiche_id/ancien.pdf')
    Moto.objects.create(proprietaire=m1, structure=asso, abonnement='2026-01-01', numero='001PF')
    Famille.objects.create(membre=m1, beneficiere='Proche fictif')
    Notification.objects.create(user=compte, membre=m1, titre='Titre fictif')
    print(json.dumps({'ok': True}))
""" % NOM_0049

VERIFIER = """
    from django.apps import apps
    from coptapp.models import Membre, Moto, Famille, Notification, AssociationMembre, Antenne, Province, Ville
    from compte.models import Compte
    m = {x.nom: x for x in Membre.objects.all()}
    resultat = {
        'comptes': Compte.objects.filter(username='fictif-migration').count(),
        'membres': Membre.objects.count(), 'motos': Moto.objects.count(), 'familles': Famille.objects.count(),
        'notifications': Notification.objects.count(), 'associations': AssociationMembre.objects.count(),
        'antennes': Antenne.objects.count(), 'provinces': Province.objects.count(), 'villes': Ville.objects.count(),
        'telephone_un': m['Membre Un'].telephone, 'supprime_deux': m['Membre Deux'].is_delete,
        'valides_trois': [m['Membre Trois'].is_validate2, m['Membre Trois'].is_validate3],
        'fiche_trois': m['Membre Trois'].fiche_id.name,
        'demandes': Membre.objects.filter(suppression_demandee=True).count(),
        'motifs_non_vides': Membre.objects.exclude(motif_suppression='').count(),
        'auteurs_demande': Membre.objects.exclude(suppression_demandee_par=None).count(),
        'asso_users': AssociationMembre.objects.get().users.count(),
    }
    print(json.dumps(resultat))
"""

ATTENDU = {
    'comptes': 1, 'membres': 3, 'motos': 1, 'familles': 1, 'notifications': 1, 'associations': 1, 'antennes': 1,
    'provinces': 1, 'villes': 1, 'telephone_un': '+243000000001', 'supprime_deux': True,
    'valides_trois': [True, True], 'fiche_trois': 'fiche_id/ancien.pdf', 'demandes': 0, 'motifs_non_vides': 0,
    'auteurs_demande': 0, 'asso_users': 1,
}


@pytest.fixture
def base(tmp_path):
    return tmp_path / 'migration.sqlite3'


def test_F25_migrate_depuis_une_base_vide_puis_makemigrations_check(base):
    _manage(base, 'migrate', '--noinput')
    _manage(base, 'migrate', '--check')  # plus rien à appliquer
    verification = _manage(base, 'makemigrations', '--check', '--dry-run')
    assert 'No changes detected' in verification.stdout
    plan = _manage(base, 'showmigrations', 'coptapp').stdout
    assert '[X] 0052' in plan and '[ ]' not in plan


def test_F25_migrate_depuis_0049_avec_donnees_sans_perte(base, tmp_path):
    _manage(base, 'migrate', 'coptapp', '0049', '--noinput')
    assert '[ ] 0050' in _manage(base, 'showmigrations', 'coptapp').stdout
    _script(base, INSERER_A_L_ETAT_0049, tmp_path)
    _manage(base, 'migrate', '--noinput')
    assert _script(base, VERIFIER, tmp_path) == ATTENDU
    assert 'No changes detected' in _manage(base, 'makemigrations', '--check', '--dry-run').stdout


def test_F25_retour_arriere_jusqu_a_0049_puis_remontee_gardent_les_lignes(base, tmp_path):
    _manage(base, 'migrate', 'coptapp', '0049', '--noinput')
    _script(base, INSERER_A_L_ETAT_0049, tmp_path)
    _manage(base, 'migrate', '--noinput')
    _manage(base, 'migrate', 'coptapp', '0049', '--noinput')  # retour arrière : colonnes 0051 / 0052 retirées
    assert '[ ] 0050' in _manage(base, 'showmigrations', 'coptapp').stdout
    _manage(base, 'migrate', '--noinput')
    assert _script(base, VERIFIER, tmp_path) == ATTENDU


def test_F25_la_base_de_l_utilisateur_n_est_pas_celle_des_scenarios(base):
    reelle = (PROJET / 'db.sqlite3').resolve()
    assert Path(_env(base)['DATABASE_URL'].removeprefix('sqlite:///')).resolve() != reelle
