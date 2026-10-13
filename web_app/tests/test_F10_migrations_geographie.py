"""Sous-lot 2d : migrations 0057 (préchargement des 27 coordinations) et 0058 (villes vers antennes).

Chaque scénario tourne dans un SOUS-PROCESSUS avec sa propre base SQLite temporaire (DATABASE_URL) : ``db.sqlite3`` n'est
jamais touché. Données fictives uniquement.
"""
import importlib
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

PROJET = Path(__file__).resolve().parent.parent
M0057 = importlib.import_module('coptapp.migrations.0057_precharger_coordinations')


def _env(base: Path):
    cible = base.resolve()
    assert cible != (PROJET / 'db.sqlite3').resolve()
    env = os.environ.copy()
    env.update({'DATABASE_URL': f'sqlite:///{cible.as_posix()}', 'DJANGO_SETTINGS_MODULE': 'fenamo.settings.dev',
                'DEBUG': 'True', 'MEDIA_ROOT': str(base.parent / 'media_migration')})
    return env


def _manage(base, *args):
    r = subprocess.run([sys.executable, 'manage.py', *args], cwd=PROJET, env=_env(base), capture_output=True,
                       text=True, timeout=900)
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


def _etat_0056(base, tmp_path):
    """Base à l'état 0056 avec des données fictives : géographie, rattachements vides ou déjà posés."""
    _manage(base, 'migrate', 'coptapp', '0056', '--noinput')
    return _script(base, """
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        apps = MigrationExecutor(connection).loader.project_state([('coptapp', '0056_geographie_champs')]).apps
        Province, Ville, Asso = (apps.get_model('coptapp', n) for n in ('Province', 'Ville', 'AssociationMembre'))
        Antenne, Membre, Moto = (apps.get_model('coptapp', n) for n in ('Antenne', 'Membre', 'Moto'))
        kin = Province.objects.create(nom='Kinshasa fictive', sigle='KF')
        bu = Province.objects.create(nom='Nom local fictif', code='BU')
        v1 = Ville.objects.create(nom='Ville A', province=bu)
        v2 = Ville.objects.create(nom='Ville Kin', province=kin)
        v3 = Ville.objects.create(nom='Ville orpheline', province=None)
        v4 = Ville.objects.create(nom='Ville B', province=bu)
        deja = Antenne.objects.create(nom='Antenne existante')
        Antenne.objects.create(nom='Ville B', ville_origine=v4, coordination=bu)
        Asso.objects.create(nom='Asso fictive', num_justice='F-2D-1', ville=v1)
        Asso.objects.create(nom='Asso rattachee', num_justice='F-2D-2', ville=v1, antenne=deja)
        m1 = Membre.objects.create(nom='Membre Un', ville=v1)
        m2 = Membre.objects.create(nom='Membre Deux', ville=v1, antenne=deja)
        Membre.objects.create(nom='Membre Trois', ville=None)
        Membre.objects.create(nom='Membre Quatre', ville=v2)
        Moto.objects.create(proprietaire=m1, ville=v1, numero='001', abonnement='2026-01-01')
        Moto.objects.create(proprietaire=m2, ville=v1, antenne=deja, numero='002', abonnement='2026-01-01')
        print(json.dumps({'ok': True}))
    """, tmp_path)


VERIFIER_0058 = """
    from coptapp.models import Province, Ville, Antenne, Membre, Moto, AssociationMembre
    nom = lambda o: o.antenne.nom if o.antenne_id else None
    issues = Antenne.objects.exclude(ville_origine=None)
    print(json.dumps({
        'antennes': Antenne.objects.count(), 'issues': issues.count(),
        'villes_sans_antenne': Ville.objects.filter(antenne_issue=None).count(),
        'coord_kin': issues.get(nom='Ville Kin').coordination.nom,
        'coord_orpheline': issues.get(nom='Ville orpheline').coordination_id,
        'types_remplis': issues.exclude(type='').count(), 'codes_remplis': issues.exclude(code=None).count(),
        'membres': {m.nom: nom(m) for m in Membre.objects.all()},
        'motos': {m.numero: nom(m) for m in Moto.objects.all()},
        'assos': {a.nom: nom(a) for a in AssociationMembre.objects.all()},
    }))
"""

LISTER_PROVINCES = """
    from coptapp.models import Province
    print(json.dumps(sorted(Province.objects.values_list('nom', 'code', 'ordre'), key=lambda t: t[0])))
"""


@pytest.fixture
def base(tmp_path):
    return tmp_path / 'migration.sqlite3'


def test_F10_constantes_27_codes_uniques_et_ordre():
    assert len(M0057.COORDINATIONS) == 27
    assert len({code for _, _, code in M0057.COORDINATIONS}) == 27
    assert len({nom for _, nom, _ in M0057.COORDINATIONS}) == 27
    assert [o for o, _, _ in M0057.COORDINATIONS] == list(range(1, 28))
    assert {'KN-E', 'KN-O', 'LW', 'MD'} <= {code for _, _, code in M0057.COORDINATIONS}


def test_F10_base_vide_27_coordinations_et_makemigrations_check(base, tmp_path):
    _manage(base, 'migrate', '--noinput')
    assert 'No changes detected' in _manage(base, 'makemigrations', '--check', '--dry-run').stdout
    lignes = _script(base, LISTER_PROVINCES, tmp_path)
    assert len(lignes) == 27 and len({code for _, code, _ in lignes}) == 27


def test_F10_0057_ne_touche_pas_l_existant_rejeu_et_retour(base, tmp_path):
    _etat_0056(base, tmp_path)
    _manage(base, 'migrate', 'coptapp', '0057', '--noinput')
    lignes = _script(base, LISTER_PROVINCES, tmp_path)
    assert len(lignes) == 28   # 26 créées + BU existante (code déjà présent) + Kinshasa fictive sans code
    assert ['Nom local fictif', 'BU', None] in lignes and ['Kinshasa fictive', None, None] in lignes
    assert not any(nom == 'Bas-Uele' for nom, _, _ in lignes)   # pas de doublon ni de fusion automatique
    rejeu = _script(base, """
        from django.apps import apps
        from coptapp.models import Province
        import importlib
        m = importlib.import_module('coptapp.migrations.0057_precharger_coordinations')
        avant = Province.objects.count()
        m.precharger(apps, None)
        print(json.dumps({'avant': avant, 'apres': Province.objects.count()}))
    """, tmp_path)
    assert rejeu['avant'] == rejeu['apres'] == 28
    _manage(base, 'migrate', 'coptapp', '0056', '--noinput')
    assert [n for n, _, _ in _script(base, LISTER_PROVINCES, tmp_path)] == ['Kinshasa fictive', 'Nom local fictif']


def test_F10_0057_retour_arriere_garde_une_coordination_referencee(base, tmp_path):
    _manage(base, 'migrate', 'coptapp', '0057', '--noinput')
    _script(base, """
        from coptapp.models import Province, Ville
        Ville.objects.create(nom='Ville liee', province=Province.objects.get(code='HK'))
        print(json.dumps(1))
    """, tmp_path)
    _manage(base, 'migrate', 'coptapp', '0056', '--noinput')
    assert _script(base, LISTER_PROVINCES, tmp_path) == [['Haut-Katanga', 'HK', 3]]


def test_F11_0058_conversion_non_ecrasement_aller_retour_et_rejeu(base, tmp_path):
    _etat_0056(base, tmp_path)
    _manage(base, 'migrate', 'coptapp', '0058', '--noinput')
    r = _script(base, VERIFIER_0058, tmp_path)
    assert r['issues'] == 4 and r['villes_sans_antenne'] == 0 and r['antennes'] == 5
    assert r['coord_kin'] == 'Kinshasa fictive' and r['coord_orpheline'] is None
    assert r['types_remplis'] == 0 and r['codes_remplis'] == 0
    assert r['membres'] == {'Membre Un': 'Ville A', 'Membre Deux': 'Antenne existante', 'Membre Trois': None,
                            'Membre Quatre': 'Ville Kin'}
    assert r['motos'] == {'001': 'Ville A', '002': 'Antenne existante'}
    assert r['assos'] == {'Asso fictive': 'Ville A', 'Asso rattachee': 'Antenne existante'}
    rejeu = _script(base, """
        from django.apps import apps
        from coptapp.models import Antenne
        import importlib
        m = importlib.import_module('coptapp.migrations.0058_villes_vers_antennes')
        avant = Antenne.objects.count()
        m.villes_vers_antennes(apps, None)
        print(json.dumps({'avant': avant, 'apres': Antenne.objects.count()}))
    """, tmp_path)
    assert rejeu['avant'] == rejeu['apres']
    _manage(base, 'migrate', 'coptapp', '0056', '--noinput')
    r3 = _script(base, """
        from coptapp.models import Antenne, Membre, Moto, AssociationMembre
        print(json.dumps({'antennes': sorted(Antenne.objects.values_list('nom', flat=True)),
                          'membres': {m.nom: (m.antenne.nom if m.antenne_id else None) for m in Membre.objects.all()},
                          'motos': Moto.objects.exclude(antenne=None).count(),
                          'assos': {a.nom: (a.antenne.nom if a.antenne_id else None) for a in AssociationMembre.objects.all()}}))
    """, tmp_path)
    assert r3['antennes'] == ['Antenne existante']
    assert r3['membres']['Membre Un'] is None and r3['membres']['Membre Deux'] == 'Antenne existante'
    assert r3['motos'] == 1
    assert r3['assos'] == {'Asso fictive': None, 'Asso rattachee': 'Antenne existante'}
    _manage(base, 'migrate', '--noinput')
    assert _script(base, VERIFIER_0058, tmp_path) == r
