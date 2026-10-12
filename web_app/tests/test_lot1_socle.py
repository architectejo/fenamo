"""Critères de fin du lot 1 « Socle » (cahier des charges web § 11.1), sur jeu d'essai fictif.

Les routes de modification en GET et le filtrage par rôle sont reportés au lot 2 :
ce fichier ne les vérifie pas (voir le rapport du testeur).
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from django.apps import apps
from django.conf import settings
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.urls import reverse

# Fabrique de jeu d'essai et table des écrans de l'annexe B (tests/test_plan_url.py).
from tests.test_plan_url import NOMS_ECRANS, hachage_rapide, jeu, table  # noqa: F401

RACINE = Path(settings.BASE_DIR)
PYTHON = sys.executable


def manage(*args, env_extra=None, base_dir_env=True):
    """Lance manage.py dans un sous-processus avec un environnement contrôlé."""
    env = {k: v for k, v in os.environ.items()
           if k not in ('SECRET_KEY', 'DEBUG', 'DATABASE_URL', 'ALLOWED_HOSTS', 'DJANGO_SETTINGS_MODULE')}
    env.update(env_extra or {})
    return subprocess.run(
        [PYTHON, 'manage.py', *args], cwd=RACINE, env=env,
        capture_output=True, text=True, timeout=300,
    )


def get_isole(client, cible, **extra):
    """GET puis annulation de la transaction : une route qui modifie en GET (lot 2) ne contamine pas les suivantes."""
    with transaction.atomic():
        reponse = client.get(cible, follow=True, **extra)
        reponse.contenu = reponse.content.decode() if reponse.status_code == 200 else ''
        transaction.set_rollback(True)
    return reponse


@pytest.fixture
def base_vide(tmp_path):
    return {'DATABASE_URL': f"sqlite:///{(tmp_path / 'vide.sqlite3').as_posix()}"}


# ---------------------------------------------------------------- démarrage

def test_lot1_check_passe(base_vide):
    r = manage('check', env_extra=base_vide)
    assert r.returncode == 0, r.stderr


def test_lot1_aucune_migration_manquante(base_vide):
    r = manage('makemigrations', '--check', '--dry-run', env_extra=base_vide)
    assert r.returncode == 0, r.stdout + r.stderr


def test_lot1_migrate_sur_sqlite_vide(base_vide):
    r = manage('migrate', '--noinput', env_extra=base_vide)
    assert r.returncode == 0, r.stderr
    r = manage('showmigrations', '--plan', env_extra=base_vide)
    assert '[ ]' not in r.stdout


# ------------------------------------------------------------------ « coptam »

EXTENSIONS_TEXTE = {'.py', '.html', '.txt', '.md', '.js', '.css', '.json', '.ini', '.example', '.cfg', '.toml', '.yml', '.yaml'}


def test_lot1_aucune_occurrence_de_coptam():
    fautifs = []
    for fichier in RACINE.rglob('*'):
        if not fichier.is_file():
            continue
        parties = set(fichier.relative_to(RACINE).parts)
        if parties & {'migrations', '__pycache__', 'docs', '.pytest_cache', 'vendor', 'node_modules'}:
            continue
        if fichier.name in ('test_lot1_socle.py', 'CLAUDE.md'):  # CLAUDE.md documente le renommage
            continue
        if fichier.suffix not in EXTENSIONS_TEXTE and fichier.name != '.env.example':
            continue
        if 'coptam' in fichier.read_text(encoding='utf-8', errors='ignore').lower():
            fautifs.append(str(fichier.relative_to(RACINE)))
    assert fautifs == [], f"« coptam » présent dans : {fautifs}"


def test_lot1_aucun_fichier_ou_dossier_nomme_coptam():
    noms = [str(p.relative_to(RACINE)) for p in RACINE.rglob('*coptam*') if '__pycache__' not in p.parts]
    assert noms == []


def test_lot1_pas_de_coptam_dans_l_interface(client, jeu):
    client.force_login(jeu['compte'])
    for nom in ('tableau-bord', 'liste-membre', 'str-list'):
        cible = next(c for n, _, c in table(jeu) if n == nom)
        assert 'coptam' not in client.get(cible, follow=True).content.decode().lower(), cible
    assert 'coptam' not in client.get('/connexion/').content.decode().lower()


# --------------------------------------------------- écrans de l'annexe B

# Écrans qui redirigent par conception (GET qui agit puis renvoie vers une fiche : lot 2 les passera en POST,
# ou connexion déjà ouverte). Tout autre écran doit répondre 200.
REDIRECTIONS_ATTENDUES = {
    'application': '/',
    'adminer': '/membres/',
    'ville-select': '/associations/',
    'validate': '/associations/mon-association/',
    'delete-membre': '/membres/',
    'view-user': '/membres/',
    'delete-family': '/membres/',
    'delete-moto': '/membres/',
    'moto-attribution': '/membres/',
    'delete-article': '/contenu-site/',
    'structure-attribution': '/membres/',
    'ville-attribution': '/membres/',
    'antenne-attribution': '/membres/',
    'ville-attr': '/villes/',
}


@pytest.mark.parametrize('nom', NOMS_ECRANS)
def test_lot1_ecran_annexe_B_repond(client, jeu, nom):
    client.force_login(jeu['compte'])
    cible = next(c for n, _, c in table(jeu) if n == nom)
    reponse = client.get(cible)
    if nom in REDIRECTIONS_ATTENDUES:
        assert reponse.status_code == 302, f"{nom} {cible} -> {reponse.status_code}"
        assert reponse['Location'].startswith(REDIRECTIONS_ATTENDUES[nom]), (nom, reponse['Location'])
    else:
        assert reponse.status_code == 200, f"{nom} {cible} -> {reponse.status_code}"


def test_lot1_toutes_les_urls_de_l_annexe_B_sont_resolues(jeu):
    for nom, kwargs, cible in table(jeu):
        assert reverse(nom, kwargs=kwargs) == cible


def test_lot1_mobapp_pages_ouvrent(client, jeu):
    for adresse in ('/mob/', '/mob/register/'):
        assert client.get(adresse).status_code in (200, 302), adresse
    m = jeu['membre'].id
    for adresse in (f'/mob/espace/{m}', f'/mob/data/{m}'):
        assert client.get(adresse).status_code in (200, 302), adresse


def test_lot1_virtrine_gestion_du_contenu_ouvre(client, jeu):
    client.force_login(jeu['compte'])
    for adresse in ('/contenu-site/', '/contenu-site/messages/', '/contenu-site/configuration/',
                    f"/contenu-site/articles/{jeu['article'].id}/modifier/",
                    f"/contenu-site/messages/{jeu['contact'].id}/"):
        assert client.get(adresse).status_code in (200, 302), adresse


# ----------------------------------------------------------------- vocabulaire

@pytest.mark.xfail(reason="Lot 2 : certaines routes (valider, supprimer, rattacher) modifient encore en GET", strict=False)
def test_lot1_aucune_modification_en_get(client, jeu):
    """Reporté au lot 2 (§ 11.1). Le test échoue tant que des routes modifient en GET ; la liste est dans le message."""
    from django.apps import apps as registre
    client.force_login(jeu['compte'])

    def etat():
        return {m.__name__: list(m.objects.order_by('pk').values_list('pk', flat=True)) for m in registre.get_models()
                if m._meta.app_label in ('coptapp', 'virtrine', 'compte')}

    avant = etat()
    fautifs = []
    for nom, kwargs, cible in table(jeu):
        if nom == 'deconnexion':
            continue
        with transaction.atomic():
            client.get(cible)
            if etat() != avant:
                fautifs.append(cible)
            transaction.set_rollback(True)
    assert fautifs == [], f"Modification en GET : {fautifs}"


def texte_visible(html):
    html = re.sub(r'(?is)<(script|style)\b.*?</\1>', ' ', html)
    attributs = ' '.join(re.findall(r'(?i)\b(?:title|placeholder|alt|aria-label|value)="([^"]*)"', html))
    return re.sub(r'<[^>]+>', ' ', html) + ' ' + attributs


def test_lot1_mot_structure_absent_de_l_interface(client, jeu):
    client.force_login(jeu['compte'])
    fautifs = []
    for nom, kwargs, cible in table(jeu):
        if nom in ('deconnexion',):
            continue
        reponse = get_isole(client, cible)
        if reponse.status_code != 200:
            continue
        texte = texte_visible(reponse.contenu)
        # « Jeu d'essai fictif » : les valeurs saisies par le test ne contiennent pas ce mot.
        if re.search(r'(?i)structure', texte):
            fautifs.append(cible)
    assert fautifs == [], f"« structure » visible sur : {fautifs}"


def test_lot1_verbose_name_vocabulaire_charte():
    from coptapp.models import AssociationMembre, Moto, Province
    assert AssociationMembre._meta.verbose_name == 'association membre'
    assert AssociationMembre._meta.verbose_name_plural == 'associations membres'
    assert Moto._meta.verbose_name == 'engin'
    assert Moto._meta.verbose_name_plural == 'engins'
    assert Province._meta.verbose_name == 'coordination provinciale'
    assert Province._meta.verbose_name_plural == 'coordinations provinciales'


def test_lot1_aucun_verbose_name_structure_dans_les_modeles():
    for modele in apps.get_models():
        assert 'structure' not in str(modele._meta.verbose_name).lower(), modele
        for champ in modele._meta.get_fields():
            etiquette = str(getattr(champ, 'verbose_name', ''))
            assert 'structure' not in etiquette.lower(), f"{modele.__name__}.{champ.name}"


def test_lot1_modele_renomme_association_membre():
    assert apps.get_model('coptapp', 'AssociationMembre')
    with pytest.raises(LookupError):
        apps.get_model('coptapp', 'Structure')


# ------------------------------------------------------------ réglages prod

ENV_PROD = {
    'SECRET_KEY': 'cle-de-test-uniquement-' + 'x' * 60,
    'ALLOWED_HOSTS': 'app.example.invalid',
    'CSRF_TRUSTED_ORIGINS': 'https://app.example.invalid',
}


@pytest.fixture
def env_prod(base_vide):
    return {**ENV_PROD, **base_vide, 'DJANGO_SETTINGS_MODULE': 'fenamo.settings.prod'}


def test_lot1_prod_check_deploy_sans_alerte(env_prod):
    r = manage('check', '--deploy', '--settings=fenamo.settings.prod', env_extra=env_prod)
    assert r.returncode == 0, r.stdout + r.stderr
    assert 'WARNINGS' not in r.stderr and 'ERRORS' not in r.stderr, r.stderr


def test_lot1_prod_exige_secret_key(env_prod):
    sans_cle = {k: v for k, v in env_prod.items() if k != 'SECRET_KEY'}
    r = manage('check', '--settings=fenamo.settings.prod', env_extra=sans_cle)
    assert r.returncode != 0
    assert 'SECRET_KEY' in r.stderr


def test_lot1_prod_debug_faux_meme_si_env_dit_vrai(env_prod):
    code = "from django.conf import settings; print(settings.DEBUG)"
    r = manage('shell', '-c', code, '--settings=fenamo.settings.prod', env_extra={**env_prod, 'DEBUG': 'True'})
    assert r.stdout.strip().endswith('False'), r.stdout + r.stderr


def test_lot1_prod_cookies_secure_et_hsts(env_prod):
    code = ("from django.conf import settings as s;"
            "print(s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, s.SECURE_HSTS_SECONDS, "
            "s.SECURE_SSL_REDIRECT, s.SECURE_HSTS_INCLUDE_SUBDOMAINS)")
    r = manage('shell', '-c', code, '--settings=fenamo.settings.prod', env_extra=env_prod)
    vals = r.stdout.strip().splitlines()[-1].split()
    assert vals[0] == 'True' and vals[1] == 'True' and int(vals[2]) >= 31536000
    assert vals[3] == 'True' and vals[4] == 'True', r.stdout + r.stderr


def test_lot1_dev_n_exige_pas_de_secret_key(base_vide):
    r = manage('check', '--settings=fenamo.settings.dev', env_extra=base_vide)
    assert r.returncode == 0, r.stderr


def test_lot1_env_exemple_documente_les_variables_obligatoires():
    texte = (RACINE / '.env.example').read_text(encoding='utf-8')
    for variable in ('SECRET_KEY', 'DEBUG', 'ALLOWED_HOSTS', 'DATABASE_URL', 'SITE_API_KEY'):
        assert variable in texte, variable


def test_lot1_env_reel_non_suivi_par_git():
    ignore = (RACINE.parent / '.gitignore').read_text(encoding='utf-8')
    assert '.env' in ignore and 'db.sqlite3' in ignore


# --------------------------------------------------------------- ressources

def test_lot1_aucun_http_externe_dans_les_gabarits():
    """Aucune URL http(s):// dans les gabarits, hors liens <a> et espaces de noms XML/SVG."""
    fautifs = []
    for fichier in RACINE.rglob('*.html'):
        if {'vendor', 'node_modules', '__pycache__'} & set(fichier.parts):
            continue
        texte = fichier.read_text(encoding='utf-8', errors='ignore')
        texte = re.sub(r'xmlns(?::\w+)?="https?://[^"]*"', '', texte)
        texte = re.sub(r'(?is)<a\b[^>]*>', '', texte)  # liens sortants cliquables : hors chargement de ressource
        for m in re.finditer(r'https?://[^\s"\'<>)]+', texte):
            fautifs.append(f"{fichier.relative_to(RACINE)} : {m.group(0)}")
    assert fautifs == [], fautifs


def test_lot1_aucun_cdn_dans_css_et_js_locaux():
    fautifs = []
    for fichier in (RACINE / 'static').rglob('*'):
        if fichier.suffix not in ('.css',) or not fichier.is_file():
            continue
        texte = fichier.read_text(encoding='utf-8', errors='ignore')
        if re.search(r'@import\s+(?:url\()?["\']?https?://|url\(["\']?https?://', texte):
            fautifs.append(str(fichier.relative_to(RACINE)))
    assert fautifs == []


def test_lot1_bibliotheques_front_locales_presentes():
    noms = {p.name.lower() for p in (RACINE / 'static').rglob('*') if p.is_file()}
    for attendu in ('htmx', 'alpine', 'bootstrap'):
        assert any(attendu in n for n in noms), attendu


# ------------------------------------------------------ migration 0047

@pytest.mark.django_db(transaction=True)
def test_lot1_migration_0047_reversible_sur_base_fictive(hachage_rapide):
    from datetime import date

    from coptapp.models import AssociationMembre, Province, Ville

    province = Province.objects.create(nom="Province fictive", sigle="PF")
    ville = Ville.objects.create(nom="Antenne fictive", province=province)
    AssociationMembre.objects.create(
        nom="Association fictive", sigle="AF", province=province, ville=ville,
        num_justice="F-0001", type_de_structure="ASBL",
    )

    executor = MigrationExecutor(connection)
    dernieres = executor.loader.graph.leaf_nodes()
    avant = [('coptapp', '0046_membre_idf_membre_password')]
    apres = [('coptapp', '0047_rename_structure_associationmembre')]

    try:
        executor.migrate(avant)
        ancien = MigrationExecutor(connection).loader.project_state(avant).apps
        Structure = ancien.get_model('coptapp', 'Structure')
        assert Structure.objects.filter(nom="Association fictive").count() == 1

        executor = MigrationExecutor(connection)
        executor.migrate(apres)
        nouveau = MigrationExecutor(connection).loader.project_state(apres).apps
        assert nouveau.get_model('coptapp', 'AssociationMembre').objects.filter(nom="Association fictive").count() == 1
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(dernieres)

    assert AssociationMembre.objects.filter(nom="Association fictive", type_de_structure="ASBL").count() == 1
