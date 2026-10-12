"""T7 : gabarit commun HTMX + Alpine (cahier des charges web § 6, § 8)."""
import json
import re
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.urls import reverse

from compte.models import Compte
from fenamo.htmx import HtmxSessionMessagesMiddleware, reponse_succes


@pytest.fixture(autouse=True)
def hachage_rapide(settings):
    settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']


@pytest.fixture
def utilisateur(db):
    return Compte.objects.create_user(username='essai', password='mdp-essai-fictif')


def test_page_connexion_sans_ressource_externe(client):
    reponse = client.get(reverse('application'))
    assert reponse.status_code == 200
    html = reponse.content.decode()
    assert 'Unité, Discipline et Progrès' in html
    assert 'FENAMO-RDC' in html
    externes = [u for u in re.findall(r'(?:src|href)="(https?://[^"]+)"', html)]
    assert externes == []


def test_page_connexion_legere(client):
    """Poids de la page de connexion (HTML + ressources locales) < 500 Ko."""
    html = client.get(reverse('application')).content.decode()
    total = len(html.encode())
    for chemin in set(re.findall(r'(?:src|href)="/static/([^"#]+)', html)):
        fichier = Path(settings.BASE_DIR) / 'static' / chemin
        if not fichier.exists():
            fichier = Path(settings.BASE_DIR) / 'coptapp' / 'static' / chemin
        total += fichier.stat().st_size
    assert total < 500 * 1024


def test_tableau_de_bord_exige_connexion(client):
    reponse = client.get(reverse('tableau-bord'))
    assert reponse.status_code == 302
    assert reponse['Location'].startswith(reverse('application'))


def test_tableau_de_bord_connecte(client, utilisateur):
    client.force_login(utilisateur)
    html = client.get(reverse('tableau-bord')).content.decode()
    assert 'hx-headers' in html and 'X-CSRFToken' in html
    assert 'id="modale-contenu"' in html
    assert 'class="modale"' in html  # feuille plein écran sous 576 px (CSS)
    assert 'class="bulles"' in html


def test_session_expiree_redirige_en_htmx(client):
    reponse = client.get(reverse('tableau-bord'), HTTP_HX_REQUEST='true')
    assert reponse.status_code == 200
    assert reponse['HX-Redirect'].startswith(reverse('application'))


def test_messages_django_vers_hx_trigger(rf):
    def vue(request):
        messages.success(request, "Membre enregistré")
        return HttpResponse(status=204)

    # on passe par la pile complète en appelant le middleware avec une requête htmx
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware

    requete = rf.get('/', HTTP_HX_REQUEST='true')
    SessionMiddleware(lambda r: None).process_request(requete)
    MessageMiddleware(lambda r: None).process_request(requete)
    requete.htmx = True  # normalement posé par django_htmx.middleware.HtmxMiddleware
    reponse = HtmxSessionMessagesMiddleware(vue)(requete)
    evenements = json.loads(reponse['HX-Trigger'])
    assert evenements['toast'] == {'message': 'Membre enregistré', 'niveau': 'success'}


def test_reponse_succes_ferme_la_modale_et_rafraichit():
    reponse = reponse_succes("Enregistré", evenements=['membresModifies'])
    assert reponse.status_code == 204
    evenements = json.loads(reponse['HX-Trigger'])
    assert evenements['modaleFermer'] is True
    assert evenements['toast']['message'] == 'Enregistré'
    assert evenements['membresModifies'] is True


def test_aucune_ressource_externe_dans_les_gabarits():
    racine = Path(settings.BASE_DIR)
    fautifs = []
    for fichier in racine.rglob('*.html'):
        if 'vendor' in fichier.parts or 'node_modules' in fichier.parts:
            continue
        texte = fichier.read_text(encoding='utf-8')
        if re.search(r'<(?:script|link|img)[^>]+(?:src|href)=["\']https?://', texte):
            fautifs.append(str(fichier.relative_to(racine)))
    assert fautifs == []
