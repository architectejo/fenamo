"""Non-régression des réserves du lot 1 (rapports sécurité et relecteur), sur jeu d'essai fictif."""
import pytest
from django.urls import reverse

from compte.models import Compte
from coptapp.models import Notification
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def test_notifications_membre_sans_photo_repond_200(client, jeu):
    """Une notification liée à un membre sans photo ne fait plus planter /notifications/."""
    assert not jeu['membre'].photo
    Notification.objects.create(user=jeu['compte'], membre=jeu['membre'], titre="Activité fictive")
    client.force_login(jeu['compte'])
    reponse = client.get(reverse('notifys'))
    assert reponse.status_code == 200
    assert 'Activité fictive' in reponse.content.decode()


def test_notifications_compte_sans_membre_pas_de_500(client, jeu):
    compte = Compte.objects.create_user('sans-membre', password='mot-de-passe-test-123')
    Notification.objects.create(user=compte, titre="Activité sans membre")
    client.force_login(compte)
    assert client.get(reverse('notifys')).status_code == 200


def test_notifications_membre_disparu_pas_de_500(client, jeu):
    jeu['compte'].membreId = 999999
    jeu['compte'].save()
    client.force_login(jeu['compte'])
    assert client.get(reverse('notifys')).status_code == 200


def test_racine_est_le_tableau_de_bord(client, jeu):
    assert reverse('tableau-bord') == '/'
    client.force_login(jeu['compte'])
    reponse = client.get('/')
    assert reponse.status_code == 200
    assert 'coptapp/tableau_bord/tableau_bord.html' in [t.name for t in reponse.templates]
    assert client.get('/tableau-de-bord/').status_code == 404


def test_racine_anonyme_redirige_vers_la_connexion(client, db):
    reponse = client.get('/')
    assert reponse.status_code == 302
    assert reponse['Location'].startswith(reverse('application'))


def test_connexion_redirige_vers_la_racine(client, jeu):
    client.force_login(jeu['compte'])
    assert client.get(reverse('application'))['Location'] == '/'


# ------------------------------------------------------------------ réglages

from tests.test_lot1_socle import ENV_PROD, base_vide, manage  # noqa: E402,F401


@pytest.fixture
def env_prod(base_vide):
    return {**ENV_PROD, **base_vide}


def test_dev_accepte_secret_key_vide(base_vide):
    r = manage('check', '--settings=fenamo.settings.dev', env_extra={**base_vide, 'SECRET_KEY': ''})
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize('cle', ['trop-courte', 'x' * 49, 'changer-cette-valeur-' + 'x' * 60,
                                 'dev-' + 'x' * 60, 'django-insecure-' + 'x' * 60])
def test_prod_refuse_secret_key_faible(env_prod, cle):
    r = manage('check', '--settings=fenamo.settings.prod', env_extra={**env_prod, 'SECRET_KEY': cle})
    assert r.returncode != 0
    assert 'SECRET_KEY' in r.stderr


def test_prod_sans_preload_et_reglages_lus_dans_env(env_prod, tmp_path):
    code = ("from django.conf import settings as s;"
            "print(hasattr(s, 'SECURE_HSTS_PRELOAD') and s.SECURE_HSTS_PRELOAD, s.STATIC_ROOT, s.MEDIA_ROOT,"
            " s.EMAIL_HOST, s.EMAIL_PORT, s.EMAIL_HOST_USER, s.EMAIL_USE_TLS)")
    extra = {**env_prod, 'STATIC_ROOT': str(tmp_path / 's'), 'MEDIA_ROOT': str(tmp_path / 'm'),
             'EMAIL_HOST': 'smtp.example.invalid', 'EMAIL_PORT': '2525', 'EMAIL_HOST_USER': 'u'}
    r = manage('shell', '-c', code, '--settings=fenamo.settings.prod', env_extra=extra)
    sortie = r.stdout.strip().splitlines()[-1]
    assert sortie == f"False {tmp_path / 's'} {tmp_path / 'm'} smtp.example.invalid 2525 u True", r.stdout + r.stderr


def test_dev_media_et_static_par_defaut_si_env_vide(base_vide):
    code = "from django.conf import settings as s; print(s.STATIC_ROOT.name, s.MEDIA_ROOT.name)"
    r = manage('shell', '-c', code, '--settings=fenamo.settings.dev',
               env_extra={**base_vide, 'STATIC_ROOT': '', 'MEDIA_ROOT': ''})
    assert r.stdout.strip().splitlines()[-1] == 'staticfiles media', r.stdout + r.stderr


# ------------------------------------------------------------- config HTMX

def test_htmx_eval_desactive_et_textes_en_json_script(client, jeu):
    import json
    import re
    client.force_login(jeu['compte'])
    html = client.get('/').content.decode()
    config = json.loads(re.search(r"name=\"htmx-config\" content='([^']+)'", html).group(1))
    assert config['allowEval'] is False
    brut = re.search(r'<script id="fenamo-textes" type="application/json">(.*?)</script>', html, re.S).group(1)
    assert set(json.loads(brut)) == {'connexionPerdue', 'erreurServeur', 'refuse', 'introuvable'}
    assert 'FENAMO_TEXTES' not in html


def test_fenamo_js_sans_acces_interne_alpine():
    from pathlib import Path
    from django.conf import settings
    js = (Path(settings.BASE_DIR) / 'static' / 'js' / 'fenamo.js').read_text(encoding='utf-8')
    assert '_x_dataStack' not in js
    assert 'Alpine.$data' in js


# ------------------------------------------------------------------ libellés

def test_mot_ville_absent_du_texte_visible(client, jeu):
    import re
    from tests.test_lot1_socle import get_isole, texte_visible
    client.force_login(jeu['compte'])
    noms = ('liste-membre', 'membre-view', 'province-view', 'structure-admin', 'str-list', 'ville-view',
            'ville-select', 'add-ville', 'view-moto', 'tableau-bord', 'edit-structure')
    from tests.test_plan_url import table
    fautifs = []
    for nom, _, cible in table(jeu):
        if nom not in noms:
            continue
        reponse = get_isole(client, cible)
        if reponse.status_code == 200 and re.search(r'(?i)\bvilles?\b', texte_visible(re.sub(r'(?s)<!--.*?-->', '', reponse.contenu))):
            fautifs.append(cible)
    assert fautifs == [], f"« ville » visible sur : {fautifs}"


# Lien connu mort, signalé au rapport : le fichier APK n'est pas dans le dépôt (site transitoire virtrine/).
FICHIERS_STATIQUES_ABSENTS_CONNUS = {'app/fenamo-app.apk'}


def test_images_et_fichiers_statiques_des_gabarits_existent():
    import re
    from pathlib import Path
    from django.conf import settings
    from django.contrib.staticfiles import finders
    absents = []
    for gabarit in Path(settings.BASE_DIR).rglob('*.html'):
        if {'vendor', '__pycache__'} & set(gabarit.parts):
            continue
        texte = gabarit.read_text(encoding='utf-8', errors='ignore')
        texte = re.sub(r'(?s)<!--.*?-->', '', texte)
        for chemin in re.findall(r"""\{%\s*static\s+['"]([^'"]+)['"]\s*%\}""", texte):
            if chemin not in FICHIERS_STATIQUES_ABSENTS_CONNUS and not finders.find(chemin):
                absents.append(f"{gabarit.relative_to(settings.BASE_DIR)} : {chemin}")
    assert absents == [], absents
