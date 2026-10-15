"""Migrations coptapp 0063 (schéma) et 0064 (données) des communiqués : aller-retour sur base temporaire, données existantes conservées."""
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

PROJET = Path(__file__).resolve().parent.parent


def _env(base: Path):
    cible = base.resolve()
    assert cible != (PROJET / 'db.sqlite3').resolve()
    env = os.environ.copy()
    env.update({'DATABASE_URL': f'sqlite:///{cible.as_posix()}', 'DJANGO_SETTINGS_MODULE': 'fenamo.settings.dev', 'DEBUG': 'True',
                'MEDIA_ROOT': str(base.parent / 'media_migration')})
    return env


def _manage(base, *args):
    r = subprocess.run([sys.executable, 'manage.py', *args], cwd=PROJET, env=_env(base), capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, f'manage.py {" ".join(args)}\n{r.stdout[-1500:]}\n{r.stderr[-2500:]}'
    return r


def _script(base, code, tmp_path):
    chemin = tmp_path / 'script_migration.py'
    chemin.write_text("import os, sys, json\nsys.path.insert(0, %r)\nimport django\ndjango.setup()\n" % str(PROJET) + textwrap.dedent(code),
                      encoding='utf-8')
    r = subprocess.run([sys.executable, str(chemin)], cwd=PROJET, env=_env(base), capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-3000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


@pytest.fixture
def base(tmp_path):
    return tmp_path / 'migration.sqlite3'


def test_F40_0063_0064_donnees_existantes_titre_date_et_national_aller_retour(base, tmp_path):
    _manage(base, 'migrate', 'coptapp', '0062', '--noinput')
    _script(base, """
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        apps = MigrationExecutor(connection).loader.project_state([('coptapp', '0062_membre_etat_donnees')]).apps
        Communique = apps.get_model('coptapp', 'Communique')
        Communique.objects.create(message='Assemblée générale ce jeudi.\\nSeconde ligne détaillée.')
        Communique.objects.create(message='x' * 300)
        Communique.objects.create(message='')
        Communique.objects.create(message=None)
        print(json.dumps(1))
    """, tmp_path)
    _manage(base, 'migrate', 'coptapp', '0064', '--noinput')
    r = _script(base, """
        from coptapp.models import Communique
        lignes = list(Communique.objects.order_by('pk').values_list('titre', 'publie_le', 'province', 'antenne'))
        lignes = [[l[0], l[1] is None, l[2], l[3]] for l in lignes]
        print(json.dumps({'lignes': lignes, 'longueurs': [len(c.titre) for c in Communique.objects.all()]}))
    """, tmp_path)
    assert r['lignes'][0] == ['Assemblée générale ce jeudi.', False, None, None]  # titre = début du message ; sans ciblage = national
    assert all(ligne[1] is False and ligne[2] is None and ligne[3] is None for ligne in r['lignes']) and max(r['longueurs']) <= 120
    assert r['lignes'][2][0] == 'Communiqué' and r['lignes'][3][0] == 'Communiqué'
    _manage(base, 'migrate', 'coptapp', '0062', '--noinput')  # retour arrière : les communiqués restent
    r2 = _script(base, """
        from django.db import connection
        with connection.cursor() as c:
            c.execute('SELECT COUNT(*) FROM coptapp_communique')
            nombre = c.fetchone()[0]
            colonnes = [x.name for x in connection.introspection.get_table_description(c, 'coptapp_communique')]
        print(json.dumps({'nombre': nombre, 'colonnes': colonnes, 'lectures': 'coptapp_lecturecommunique' in connection.introspection.table_names()}))
    """, tmp_path)
    assert r2['nombre'] == 4 and 'titre' not in r2['colonnes'] and 'publie_le' not in r2['colonnes'] and r2['lectures'] is False
    _manage(base, 'migrate', 'coptapp', '--noinput')
    assert 'No changes detected' in _manage(base, 'makemigrations', '--check', '--dry-run').stdout
