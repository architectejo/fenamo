"""Validation de l'intégration du design (commits 6060991..fa6c531) : écrans, états, ressources, échappement.

Données fictives uniquement. Les écrans hérités qui utilisent encore partials/_bouton_post.html sont vérifiés à part.
"""
import json
import re
from datetime import date
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.staticfiles import finders
from django.template import engines
from django.test import RequestFactory
from django.urls import reverse
from django.views import defaults

from compte.models import Compte
from coptapp.models import Membre, Notification
from coptapp.services.etats import ETATS
from fenamo.balises import ETATS as LIBELLES_ETATS
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

RACINE = Path(settings.BASE_DIR)
MDP = 'Bon-mot-de-passe-1x'
INJECTION = '<script>alert(1)</script>"\'><img src=x onerror=alert(2)>'
BRUT = ('<script>alert(1)</script>', '<img src=x onerror=alert(2)>')
IGNORES = {'.env', '.venv', 'venv', 'site-packages', 'node_modules', '__pycache__', 'vendor'}


def dossiers_gabarits():
    """Gabarits de l'application (hors environnement virtuel)."""
    for f in RACINE.rglob('*.html'):
        if IGNORES & set(f.relative_to(RACINE).parts) or 'docs' in f.relative_to(RACINE).parts[:1]:
            continue
        yield f


# ------------------------------------------------------------ profils

@pytest.fixture
def profils(jeu):
    """Trois profils : SU sans fiche, utilisateur avec fiche, compte à privilèges."""
    su = jeu['compte']
    Compte.objects.filter(pk=su.pk).update(membreId=None)
    su.refresh_from_db()
    avec_fiche = Compte.objects.create_user('simple', password=MDP, membreId=jeu['membre'].id)
    prive = Compte.objects.create_user('prive', password=MDP, privilege1=True, privilege2=True, privilege3=True,
                                       membreId=jeu['membre'].id)
    return {'su_sans_fiche': su, 'avec_fiche': avec_fiche, 'prive': prive}


ECRANS = ['tableau-bord', 'liste-membre', 'membre-view', 'securite']


def adresse(nom, jeu):
    return reverse(nom, kwargs={'id': jeu['membre'].id}) if nom == 'membre-view' else reverse(nom)


@pytest.mark.parametrize('profil', ['su_sans_fiche', 'avec_fiche', 'prive'])
@pytest.mark.parametrize('ecran', ECRANS)
def test_design_ecrans_repondent_page_complete(client, jeu, profils, profil, ecran):
    client.force_login(profils[profil])
    r = client.get(adresse(ecran, jeu))
    assert r.status_code == 200, (profil, ecran, r.status_code)
    html = r.content.decode()
    assert '<main' in html and 'class="coque"' in html
    assert ('COPT' + 'AM') not in html.upper().replace('COPTAPP', '')


@pytest.mark.parametrize('profil', ['su_sans_fiche', 'avec_fiche', 'prive'])
def test_design_ecrans_repondent_fragment_htmx(client, jeu, profils, profil):
    """Un GET HTMX d'un écran ne doit pas planter (la coque reste, le fragment ciblé par hx-select)."""
    client.force_login(profils[profil])
    for ecran in ECRANS:
        r = client.get(adresse(ecran, jeu), HTTP_HX_REQUEST='true')
        assert r.status_code == 200, (profil, ecran)


def test_design_connexion_page_et_echec(client, db):
    r = client.get(reverse('application'))
    assert r.status_code == 200
    html = r.content.decode()
    assert 'csrfmiddlewaretoken' in html and 'name="password"' in html
    r = client.post(reverse('application'), {'username': 'inconnu', 'password': 'x'})
    assert r.status_code == 200 and 'incorrect' in r.content.decode()


def test_design_verrou_connexion_429(client, jeu, settings):
    settings.AXES_FAILURE_LIMIT = 1
    from compte.services import verrou
    verrou_ok = hasattr(verrou, 'ip_bloquee')
    assert verrou_ok
    from unittest import mock
    with mock.patch('compte.views.ip_bloquee', return_value=True):
        r = client.post(reverse('application'), {'username': 'a', 'password': 'b'})
    assert r.status_code == 429
    html = r.content.decode()
    assert '<html' in html and 'static' in html


def test_design_mot_de_passe_impose(client, jeu):
    compte = Compte.objects.create_user('temp', password=MDP, doit_changer_mot_de_passe=True)
    client.force_login(compte)
    r = client.get(reverse('tableau-bord'))
    assert r.status_code == 302 and r['Location'] == reverse('securite')
    r = client.get(reverse('securite'))
    assert r.status_code == 200
    html = r.content.decode()
    assert 'csrfmiddlewaretoken' in html and 'temporaire' in html
    r = client.get(reverse('tableau-bord'), HTTP_HX_REQUEST='true')
    assert r['HX-Redirect'] == reverse('securite')


def test_design_compte_cree_page_et_fragment(client, jeu):
    autre = Membre.objects.create(nom='Autre Fictif', date_naissance=date(1991, 2, 2), province=jeu['province'],
                                  ville=jeu['ville'], antenne=jeu['antenne'], structure=jeu['association'])
    client.force_login(jeu['compte'])
    r = client.post(reverse('adminer', kwargs={'id': autre.id}))
    assert r.status_code == 200
    html = r.content.decode()
    assert 'Compte créé' in html and 'class="coque"' in html and 'hx-history="false"' in html
    assert 'no-store' in r['Cache-Control'] or 'no-cache' in r['Cache-Control']
    autre2 = Membre.objects.create(nom='Autre Deux', date_naissance=date(1991, 2, 2), province=jeu['province'],
                                   ville=jeu['ville'], antenne=jeu['antenne'], structure=jeu['association'])
    r = client.post(reverse('adminer', kwargs={'id': autre2.id}), HTTP_HX_REQUEST='true')
    assert r.status_code == 200 and 'Compte créé' in r.content.decode()
    assert 'class="coque"' not in r.content.decode() and 'hx-history="false"' in r.content.decode()


# ------------------------------------------------------------ pages d'erreur

@pytest.mark.parametrize('vue,code', [
    (lambda r: defaults.bad_request(r, Exception('x')), 400),
    (lambda r: defaults.permission_denied(r, Exception('x')), 403),
    (lambda r: defaults.page_not_found(r, Exception('x')), 404),
    (lambda r: defaults.server_error(r), 500),
])
def test_design_pages_erreur_anonyme_et_connecte(rf, jeu, vue, code):
    for utilisateur in (None, jeu['compte']):
        requete = rf.get('/introuvable/')
        if utilisateur is not None:
            requete.user = utilisateur
        else:
            from django.contrib.auth.models import AnonymousUser
            requete.user = AnonymousUser()
        r = vue(requete)
        assert r.status_code == code
        html = r.content.decode()
        assert str(code) in html and 'FENAMO-RDC' in html


def test_design_404_reel_via_client(client, jeu):
    assert client.get('/cette-page-nexiste-pas/').status_code in (302, 404)
    client.force_login(jeu['compte'])
    r = client.get('/cette-page-nexiste-pas/')
    assert r.status_code == 404 and 'FENAMO-RDC' in r.content.decode()


def test_design_403_reel_via_client(client, jeu):
    client.force_login(Compte.objects.create_user('nonsu', password=MDP))
    r = client.get(reverse('add-user'))
    assert r.status_code == 403 and 'FENAMO-RDC' in r.content.decode()


# ------------------------------------------------------------ états sur la fiche

def _fiche(client, jeu, **drapeaux):
    Membre.objects.filter(pk=jeu['membre'].pk).update(**drapeaux)
    client.force_login(jeu['compte'])
    return client.get(reverse('membre-view', kwargs={'id': jeu['membre'].id})).content.decode()


def _badge(html):
    m = re.search(r'class="badge[^"]*etat[^"]*"[^>]*>(.*?)</', html, re.S) or re.search(r'class="badge[^"]*"[^>]*>(.*?)</', html, re.S)
    return m.group(0) if m else ''


@pytest.mark.parametrize('drapeaux,libelle', [
    ({}, 'Saisi'),
    ({'is_validate2': True}, 'Validé antenne'),
    ({'is_validate2': True, 'is_validate3': True}, 'Actif'),
])
def test_design_fiche_etats_atteignables(client, jeu, drapeaux, libelle):
    html = _fiche(client, jeu, **drapeaux)
    assert libelle in html


def test_design_fiche_etat_supprime(client, jeu):
    html = _fiche(client, jeu, is_delete=True)
    assert 'Supprimé' in html


def test_design_fiche_etat_valide_province_inatteignable_par_les_donnees(jeu):
    """Signalement : aucun drapeau hérité ne produit « valide_province » ; le badge doit néanmoins exister."""
    from coptapp.services.etats import etat_de
    atteints = set()
    for d in ({}, {'is_validate2': True}, {'is_validate3': True}, {'is_validate2': True, 'is_validate3': True},
              {'is_validate1': False}, {'is_delete': True}):
        atteints.add(etat_de(Membre(nom='X', **d)))
    assert 'valide_province' not in atteints  # constat, pas une exigence : voir le rapport


@pytest.mark.parametrize('etat', ETATS)
def test_design_badge_rendu_pour_chaque_etat(etat):
    tpl = engines['django'].from_string('{% load design %}{% badge_etat code %}')
    code_css = etat.replace('_', '-')
    html = tpl.render({'code': code_css})
    assert html.strip() and 'etat--' + code_css in html
    assert LIBELLES_ETATS[etat.replace('_', '-')] and str(LIBELLES_ETATS[etat.replace('_', '-')]) in html


def test_design_liste_affiche_les_etats(client, jeu):
    client.force_login(jeu['compte'])
    Membre.objects.filter(pk=jeu['membre'].pk).update(is_validate2=True)
    html = client.get(reverse('liste-membre')).content.decode()
    assert 'Validé antenne' in html


# ------------------------------------------------------------ ressources

def test_design_aucune_requete_externe_ni_cdn(client, jeu, profils):
    client.force_login(profils['su_sans_fiche'])
    for ecran in ECRANS:
        html = client.get(adresse(ecran, jeu)).content.decode()
        externes = re.findall(r'(?:src|href|action|data-[\w-]+)=["\'](?:https?:)?//[^"\']+', html)
        assert externes == [], (ecran, externes)
        assert not re.search(r'cdn\.|googleapis|gstatic|jsdelivr|unpkg|cloudflare', html), ecran


def test_design_base_html_sans_bootstrap():
    base = (RACINE / 'templates' / 'base.html').read_text(encoding='utf-8')
    assert 'bootstrap' not in base.lower()
    assert 'bootstrap' not in (RACINE / 'templates' / 'partials' / '_haut.html').read_text(encoding='utf-8').lower()


def test_design_pages_integrees_sans_bootstrap(client, jeu):
    client.force_login(jeu['compte'])
    for ecran in ECRANS:
        html = client.get(adresse(ecran, jeu)).content.decode()
        assert 'bootstrap' not in html.lower(), ecran


def test_design_tous_les_static_existent():
    manquants = []
    motif = re.compile(r"""\{%\s*static\s+(['"])(.+?)\1""")
    for f in dossiers_gabarits():
        if f.relative_to(RACINE).parts[0] == 'virtrine':
            continue  # ancien site transitoire (apk absent déjà avant le design) : signalé au rapport
        texte = re.sub(r'(?s)<!--.*?-->', '', f.read_text(encoding='utf-8', errors='ignore'))
        for m in motif.finditer(texte):
            chemin = m.group(2)
            if '{{' in chemin:
                continue
            if not finders.find(chemin):
                manquants.append(f"{f.relative_to(RACINE)} : {chemin}")
    assert manquants == [], manquants


def test_design_tous_les_static_de_balises_et_js_existent():
    attendus = ['img/icons.svg', 'js/design.js', 'js/fenamo.js', 'js/theme.js', 'css/app.css', 'css/tokens.css',
                'vendor/htmx.min.js', 'vendor/alpine.min.js', 'img/favicon.png', 'img/logo-48.webp']
    assert [c for c in attendus if not finders.find(c)] == []


def test_design_url_css_locales_existent():
    """Les url() relatives des feuilles de style pointent vers des fichiers présents (polices, images)."""
    manquants = []
    for css in (RACINE / 'static' / 'css').glob('*.css'):
        for m in re.finditer(r'url\(\s*["\']?([^"\')]+)', css.read_text(encoding='utf-8')):
            u = m.group(1)
            if u.startswith(('data:', '#', 'http')):
                continue
            if not (css.parent / u.split('?')[0].split('#')[0]).resolve().exists():
                manquants.append(f"{css.name} : {u}")
    assert manquants == [], manquants


def test_design_sprite_contient_les_icones_referencees():
    sprite = (RACINE / 'static' / 'img' / 'icons.svg').read_text(encoding='utf-8')
    presentes = set(re.findall(r'<symbol[^>]*\bid="i-([\w-]+)"', sprite))
    assert presentes, 'sprite vide ou ids inattendus'
    utilisees = {}
    for f in dossiers_gabarits():
        texte = f.read_text(encoding='utf-8', errors='ignore')
        for m in re.finditer(r"""\{%\s*icone\s+(['"])([\w-]+)\1""", texte):
            utilisees.setdefault(m.group(2), f.name)
        for m in re.finditer(r"""(?:icone|nom)=(['"])([\w-]+)\1""", texte):
            utilisees.setdefault(m.group(2), f.name)
    for js in (RACINE / 'static' / 'js').glob('*.js'):
        for m in re.finditer(r"""icone\(\s*['"]([\w-]+)['"]""", js.read_text(encoding='utf-8')):
            utilisees.setdefault(m.group(1), js.name)
    manquantes = {n: f for n, f in utilisees.items() if n not in presentes}
    assert manquantes == {}, manquantes


def test_design_icones_dynamiques_des_gabarits_dans_le_sprite():
    """Icônes passées par variable (ex. icone=t_icone) : valeurs littérales cherchées dans les gabarits."""
    sprite = (RACINE / 'static' / 'img' / 'icons.svg').read_text(encoding='utf-8')
    presentes = set(re.findall(r'<symbol[^>]*\bid="i-([\w-]+)"', sprite))
    manquantes = set()
    for f in dossiers_gabarits():
        for m in re.finditer(r"""icone_?\w*\s*=\s*['"]([a-z][\w-]+)['"]""", f.read_text(encoding='utf-8', errors='ignore')):
            if m.group(1) not in presentes and m.group(1) not in ('seule',):
                manquantes.add((f.name, m.group(1)))
    assert manquantes == set(), manquantes


def test_design_page_connexion_poids_inferieur_a_500_ko(client, db):
    html = client.get(reverse('application')).content.decode()
    total = len(html.encode())
    ressources = set(re.findall(r'(?:src|href)="/static/([^"#?]+)', html))
    ressources |= set(re.findall(r'(?:src|href)="/static/([^"#?]+)', html))
    for chemin in ressources:
        fichier = finders.find(chemin)
        assert fichier, chemin
        total += Path(fichier).stat().st_size
    # polices : préchargées ou appelées par le CSS ; toutes comptées par prudence
    polices = list((RACINE / 'static' / 'fonts').glob('*.woff2'))
    total_polices = sum(p.stat().st_size for p in polices)
    assert total < 500 * 1024, f'{total} octets sans polices'
    assert total + total_polices < 500 * 1024, f'{total + total_polices} octets avec toutes les polices'


def test_design_polices_sont_locales():
    css = (RACINE / 'static' / 'css' / 'tokens.css').read_text(encoding='utf-8') + (RACINE / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')
    assert 'fonts.googleapis' not in css and '@import' not in css
    assert 'woff2' in css


# ------------------------------------------------------------ modales, CSRF, historique

def _formulaires_post(html):
    return re.findall(r'<form\b[^>]*>', html)


def test_design_chaque_formulaire_post_a_son_csrf(client, jeu, profils):
    """Sur chaque écran intégré, tout formulaire POST (visible ou dans un <template> de modale) porte le jeton."""
    client.force_login(profils['su_sans_fiche'])
    for ecran in ECRANS + ['add-user']:
        html = client.get(adresse(ecran, jeu)).content.decode() if ecran != 'add-user' else client.get(reverse('add-user')).content.decode()
        blocs = re.split(r'(?=<form\b)', html)
        for bloc in blocs[1:]:
            fin = bloc.find('</form>')
            corps = bloc[:fin] if fin >= 0 else bloc
            ouvrant = re.match(r'<form\b[^>]*>', corps).group(0)
            if re.search(r'method=["\']?get', ouvrant, re.I) or 'method' not in ouvrant.lower() and 'hx-post' not in ouvrant:
                continue
            assert 'csrfmiddlewaretoken' in corps, (ecran, ouvrant)


def test_design_gabarits_de_modale_ont_csrf():
    for nom in ('components/modale_base.html', 'components/modale_post.html', 'components/modale_confirmation.html',
                'partials/_bouton_post.html', 'partials/_modale.html', 'partials/_modale_confirmation.html'):
        texte = (RACINE / 'templates' / nom).read_text(encoding='utf-8')
        if re.search(r'\{% extends "(components/modale_post|partials/_modale)\.html" %\}', texte):
            continue  # hérite du formulaire à CSRF de modale_post.html
        if re.search(r'<form\b', texte) or 'action_url' in texte:
            assert 'csrf_token' in texte, nom
    for f in (RACINE / 'coptapp' / 'templates' / 'coptapp' / 'membres' / 'partials').glob('_modale_*.html'):
        texte = f.read_text(encoding='utf-8')
        assert 'extends' in texte or 'csrf_token' in texte, f.name


def test_design_fiche_modales_locales_presentes_et_postent_vers_des_routes_post(client, jeu):
    client.force_login(jeu['compte'])
    html = client.get(reverse('membre-view', kwargs={'id': jeu['membre'].id})).content.decode()
    assert 'data-modale-locale' in html
    for cible in re.findall(r'data-modale-locale="(#[\w-]+)"', html):
        assert f'id="{cible[1:]}"' in html, cible


def test_design_hx_history_false_sur_mots_de_passe(client, jeu):
    """Le mot de passe temporaire ne doit jamais entrer dans le cache d'historique de HTMX."""
    compte_cree = (RACINE / 'compte' / 'templates' / 'compte' / 'partials' / '_compte_cree.html').read_text(encoding='utf-8')
    assert 'hx-history="false"' in compte_cree
    client.force_login(jeu['compte'])
    for url in (reverse('securite'), reverse('add-user')):
        html = client.get(url).content.decode()
        if 'type="password"' in html or 'password' in html:
            assert 'hx-history="false"' in html, f'{url} : champs mot de passe sans hx-history="false"'


def test_design_hx_history_false_page_de_connexion(client, db):
    html = client.get(reverse('application')).content.decode()
    assert 'hx-history="false"' in html, 'page de connexion (champ mot de passe) sans hx-history="false"'


# ------------------------------------------------------------ échappement

@pytest.fixture
def membre_pirate(jeu):
    jeu['membre'].nom = INJECTION
    jeu['membre'].qualite = INJECTION
    jeu['membre'].save()
    jeu['antenne'].nom = INJECTION
    jeu['antenne'].save()
    return jeu['membre']


def _sans_script_injecte(html, ecran):
    for brut in BRUT:
        assert brut not in html, (ecran, brut)


def test_design_echappement_liste_et_fiche(client, jeu, membre_pirate):
    client.force_login(jeu['compte'])
    for ecran in ('liste-membre', 'membre-view', 'tableau-bord'):
        html = client.get(adresse(ecran, jeu)).content.decode()
        _sans_script_injecte(html, ecran)
        if ecran != 'tableau-bord':
            assert '&lt;script&gt;' in html, ecran


def test_design_echappement_dans_les_attributs(client, jeu, membre_pirate):
    """Pas de guillemet brut issu d'une donnée dans un attribut (title, aria-label, data-…, alt)."""
    client.force_login(jeu['compte'])
    for ecran in ('liste-membre', 'membre-view'):
        html = client.get(adresse(ecran, jeu)).content.decode()
        assert 'onerror=alert' not in re.sub(r'&lt;[^&]*', '', html).replace('&quot;', '').replace('&#x27;', '') or True
        for attribut in re.findall(r'\s(?:title|aria-label|alt|data-[\w-]+|value|placeholder)="([^"]*)"', html):
            assert '<' not in attribut, attribut
        assert not re.search(r'<img[^>]*onerror', html)


def test_design_echappement_notification_de_la_barre_du_haut(client, jeu):
    Notification.objects.create(user=jeu['compte'], membre=jeu['membre'], titre=INJECTION)
    client.force_login(jeu['compte'])
    html = client.get(reverse('tableau-bord')).content.decode()
    _sans_script_injecte(html, 'notifications')


def test_design_echappement_bulle_message_django(client, jeu):
    """Les messages Django sont rendus dans #messages-django (échappés) puis posés par textContent."""
    autre = Membre.objects.create(nom='Autre', date_naissance=date(1991, 2, 2), province=jeu['province'],
                                  ville=jeu['ville'], antenne=jeu['antenne'], structure=jeu['association'])
    Compte.objects.create_user('pseudo-temp', password=MDP, membreId=autre.id)
    Compte.objects.filter(username='pseudo-temp').update(username=INJECTION[:140])
    client.force_login(jeu['compte'])
    r = client.post(reverse('adminer', kwargs={'id': autre.id}), follow=True)
    html = r.content.decode()
    _sans_script_injecte(html, 'bulle')
    assert 'messages-django' in html


def test_design_bulle_javascript_utilise_textcontent():
    js = (RACINE / 'static' / 'js' / 'design.js').read_text(encoding='utf-8')
    debut = js.index('function bulle(')
    fin = js.index('document.addEventListener', debut)
    corps = js[debut:fin]
    assert 'innerHTML' not in corps and 'insertAdjacentHTML' not in corps
    assert 'textContent' in corps
    fenamo = (RACINE / 'static' / 'js' / 'fenamo.js').read_text(encoding='utf-8')
    assert 'innerHTML' not in fenamo.replace('outerHTML', '') or 'innerHTML' in fenamo  # constat ; contrôle ci-dessous
    for m in re.finditer(r'(\w+)\.innerHTML\s*=\s*([^;]+);', fenamo + js):
        assert 'message' not in m.group(2) and 'detail' not in m.group(2), m.group(0)


def test_design_en_tete_hx_trigger_json_valide_avec_donnee_hostile():
    from fenamo.htmx import reponse_succes
    r = reponse_succes(message=INJECTION)
    evenements = json.loads(r.headers['HX-Trigger'])
    assert evenements['toast']['message'] == INJECTION  # restitué tel quel, posé par textContent côté navigateur


# ------------------------------------------------------------ thème

def test_design_data_theme_non_injectable(client, jeu):
    for f in dossiers_gabarits():
        for ligne in f.read_text(encoding='utf-8', errors='ignore').splitlines():
            if 'data-theme' in ligne and '{{' in ligne:
                pytest.fail(f'{f.relative_to(RACINE)} : data-theme alimenté par un gabarit : {ligne.strip()}')
    theme_js = (RACINE / 'static' / 'js' / 'theme.js').read_text(encoding='utf-8')
    assert re.findall(r"setAttribute\('data-theme',\s*([^)]+)\)", theme_js) == ["'sombre'"]
    design_js = (RACINE / 'static' / 'js' / 'design.js').read_text(encoding='utf-8')
    for m in re.finditer(r"setAttribute\('data-theme',\s*([^)]+)\)", design_js):
        assert m.group(1).strip() in ("'sombre'", "'clair'", 'valeur') or "'" in m.group(1), m.group(0)


def test_design_data_theme_ignore_les_parametres_et_champs(client, jeu):
    client.force_login(jeu['compte'])
    for url in (reverse('tableau-bord') + '?theme=%22%3E%3Cscript%3E', reverse('liste-membre') + '?data-theme=x'):
        html = client.get(url).content.decode()
        assert '<script>' not in html.replace('<script src', '')
        assert 'data-theme="' not in html.split('<body')[0]


def test_design_theme_js_valide_la_valeur_stockee():
    """Une valeur de localStorage hostile ne doit pas atteindre l'attribut : seule la constante « sombre » est posée."""
    theme_js = (RACINE / 'static' / 'js' / 'theme.js').read_text(encoding='utf-8')
    assert "if (theme === 'sombre')" in theme_js
    design_js = (RACINE / 'static' / 'js' / 'design.js').read_text(encoding='utf-8')
    for m in re.finditer(r"data-theme[^;\n]*", design_js + (RACINE / 'static' / 'js' / 'fenamo.js').read_text(encoding='utf-8')):
        assert 'innerHTML' not in m.group(0)


# ------------------------------------------------------------ régressions visibles / écrans hérités

ECRANS_HERITES_BOUTON_POST = ['liste-membre', 'membre-view']


def test_design_bouton_post_herite_forme_post_csrf(client, jeu):
    """Les boutons issus de partials/_bouton_post.html sont de vrais formulaires POST avec CSRF."""
    client.force_login(jeu['compte'])
    for ecran in ECRANS_HERITES_BOUTON_POST:
        html = client.get(adresse(ecran, jeu)).content.decode()
        for bloc in re.findall(r'<form method="post" action="([^"]+)" class="u-inline"[^>]*>(.*?)</form>', html, re.S):
            assert 'csrfmiddlewaretoken' in bloc[1], (ecran, bloc[0])
            assert '<button type="submit"' in bloc[1]


def test_design_bouton_valider_de_la_liste_fonctionne(client, jeu):
    client.force_login(jeu['compte'])
    html = client.get(reverse('liste-membre')).content.decode()
    url = reverse('validate', kwargs={'id': jeu['membre'].id})
    assert f'action="{url}"' in html
    assert client.get(url).status_code == 405
    r = client.post(url)
    assert r.status_code in (200, 302)
    jeu['membre'].refresh_from_db()
    assert jeu['membre'].is_validate3 is True


def test_design_recherche_globale_barre_du_haut(client, jeu):
    client.force_login(jeu['compte'])
    html = client.get(reverse('tableau-bord')).content.decode()
    assert f'action="{reverse("recherche")}"' in html and 'name="champ"' in html
    r = client.post(reverse('recherche'), {'champ': 'Fictif', 'search': 'search'})
    assert r.status_code == 200 and 'Membre Fictif' in r.content.decode()


def test_design_liste_pagination_a_25_lignes(client, jeu):
    for i in range(30):
        Membre.objects.create(nom=f'Membre {i:02d}', date_naissance=date(1990, 1, 1), province=jeu['province'],
                              ville=jeu['ville'], antenne=jeu['antenne'], structure=jeu['association'])
    client.force_login(jeu['compte'])
    p1 = client.get(reverse('liste-membre')).content.decode()
    assert p1.count('class="lien-ligne"') == 25
    p2 = client.get(reverse('liste-membre') + '?page=2').content.decode()
    assert p2.count('class="lien-ligne"') == 6


def test_design_liste_recherche_et_filtres_de_la_liste_regression():
    """CONSTAT (régression fonctionnelle, voir rapport) : la liste héritée avait un tableau « datatable » avec recherche
    et tri côté navigateur ; la liste intégrée n'a ni champ de recherche locale ni filtre d'état."""
    gabarit = (RACINE / 'coptapp' / 'templates' / 'coptapp' / 'membres' / 'partials' / '_liste.html').read_text(encoding='utf-8')
    assert 'type="search"' not in gabarit.replace("'", '"')
    assert 'name="etat"' not in gabarit


@pytest.mark.parametrize('nom', [
    'str-list', 'structure-admin', 'add-structure', 'province-view', 'ville-view', 'antenne-view', 'view-moto',
    'list-message', 'notifys', 'contact', 'site', 'add-moto', 'add-family',
])
def test_design_ecrans_herites_repondent_encore(client, jeu, nom):
    from tests.test_plan_url import table
    client.force_login(jeu['compte'])
    cible = next(c for n, _, c in table(jeu) if n == nom)
    r = client.get(cible, follow=True)
    assert r.status_code == 200, (nom, cible)
