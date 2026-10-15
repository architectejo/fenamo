"""Migrations virtrine 0020 (schéma) et 0021 (données) : aller-retour, slugs uniques, copie des téléphones et des partenaires, articles en brouillon.

Chaque scénario tourne dans un SOUS-PROCESSUS avec sa propre base SQLite temporaire : ``db.sqlite3`` n'est jamais touché. Données fictives.
"""
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


def _etat_0019(base, tmp_path):
    _manage(base, 'migrate', 'virtrine', '0019', '--noinput')
    return _script(base, """
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        apps = MigrationExecutor(connection).loader.project_state([('virtrine', '0019_alter_article_image_alter_config_image_background_and_more')]).apps
        Article, Config = apps.get_model('virtrine', 'Article'), apps.get_model('virtrine', 'Config')
        Article.objects.create(titre='Assemblée générale', description='<p>Texte</p>', integration_code='<iframe src=x></iframe>')
        Article.objects.create(titre='Assemblée générale', description='doublon de titre')
        Article.objects.create(titre='')
        Article.objects.create(titre=None)
        Config.objects.create(nom='FENAMO', phone1='+243810000001', phone2=' ', phone3='+243810000003', phone7='+243810000007',
                              partenaire1='Ministère des Transports', link1='https://transports.example', partenaire4='Partenaire sans lien')
        print(json.dumps(1))
    """, tmp_path)


def test_F60_0020_0021_donnees_copiees_slugs_uniques_et_brouillons(base, tmp_path):
    _etat_0019(base, tmp_path)
    _manage(base, 'migrate', 'virtrine', '0021', '--noinput')
    r = _script(base, """
        from virtrine.models import Article, Config, Partenaire, TelephoneSite
        print(json.dumps({
            'slugs': list(Article.objects.order_by('pk').values_list('slug', flat=True)),
            'statuts': sorted(set(Article.objects.values_list('statut', flat=True))),
            'integration': Article.objects.order_by('pk').first().integration_code,
            'telephones': list(TelephoneSite.objects.values_list('numero', 'ordre')),
            'partenaires': list(Partenaire.objects.values_list('nom', 'lien', 'ordre')),
            'config': Config.objects.count(), 'langues': Config.instance().langues_actives, 'paiement': Config.instance().paiement_en_ligne_actif,
            'anciennes_colonnes': [Config.objects.get().phone1, Config.objects.get().partenaire1, Config.objects.get().link1],
        }))
    """, tmp_path)
    assert r['slugs'] == ['assemblee-generale', 'assemblee-generale-2', 'article', 'article-2']
    assert len(set(r['slugs'])) == 4 and r['statuts'] == ['brouillon']  # rien n'est publié automatiquement
    assert r['integration'] == '<iframe src=x></iframe>'  # gardé en base, jamais exposé
    assert r['telephones'] == [['+243810000001', 1], ['+243810000003', 3], ['+243810000007', 7]]
    assert r['partenaires'] == [['Ministère des Transports', 'https://transports.example', 1], ['Partenaire sans lien', '', 4]]
    assert r['config'] == 1 and r['langues'] == 'fr' and r['paiement'] is False
    assert r['anciennes_colonnes'] == ['+243810000001', 'Ministère des Transports', 'https://transports.example']  # anciennes colonnes gardées


def test_F60_0021_idempotente_et_retour_arriere_garde_les_anciennes_colonnes(base, tmp_path):
    _etat_0019(base, tmp_path)
    _manage(base, 'migrate', 'virtrine', '0021', '--noinput')
    rejeu = _script(base, """
        import importlib
        from django.apps import apps
        from virtrine.models import Article, Partenaire, TelephoneSite
        m = importlib.import_module('virtrine.migrations.0021_site_public_donnees')
        avant = (Article.objects.count(), TelephoneSite.objects.count(), Partenaire.objects.count(), list(Article.objects.values_list('slug', flat=True)))
        m.remplir(apps, None)
        apres = (Article.objects.count(), TelephoneSite.objects.count(), Partenaire.objects.count(), list(Article.objects.values_list('slug', flat=True)))
        print(json.dumps([avant == apres]))
    """, tmp_path)
    assert rejeu == [True]
    _manage(base, 'migrate', 'virtrine', '0019', '--noinput')
    r = _script(base, """
        from django.db import connection
        with connection.cursor() as c:
            c.execute('SELECT phone1, phone3, phone7, partenaire1, link1 FROM virtrine_config')
            config = list(c.fetchone())
            c.execute('SELECT titre, integration_code FROM virtrine_article ORDER BY id')
            articles = c.fetchall()
            tables = connection.introspection.table_names()
        print(json.dumps({'config': config, 'articles': articles, 'tables': [t for t in tables if t.startswith('virtrine_')]}))
    """, tmp_path)
    assert r['config'] == ['+243810000001', '+243810000003', '+243810000007', 'Ministère des Transports', 'https://transports.example']
    assert r['articles'][0] == ['Assemblée générale', '<iframe src=x></iframe>'] and len(r['articles']) == 4
    assert 'virtrine_telephonesite' not in r['tables'] and 'virtrine_partenaire' not in r['tables'] and 'virtrine_articletraduction' not in r['tables']
    _manage(base, 'migrate', 'virtrine', '--noinput')  # remontée complète
    assert 'No changes detected' in _manage(base, 'makemigrations', '--check', '--dry-run').stdout


def test_F60_base_vide_migre_et_makemigrations_propre(base):
    _manage(base, 'migrate', '--noinput')
    assert 'No changes detected' in _manage(base, 'makemigrations', '--check', '--dry-run').stdout
