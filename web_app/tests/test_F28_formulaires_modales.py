"""F-28 : les formulaires d'ajout et de modification s'ouvrent dans la modale commune (GET HTMX), refusent avec 422, réussissent avec HX-Refresh ;
la page complète reste le repli sans JavaScript ; message de vue : un seul composant."""
import pytest
from django.urls import reverse

from coptapp.models import Province
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

HX = {'HTTP_HX_REQUEST': 'true'}


def _urls(jeu):
    return [
        ('add-province', {}), ('add-ville', {'id': jeu['province'].id}), ('add-antenne', {'id': jeu['association'].id}),
        ('add-membre', {'id': jeu['association'].id}), ('add-fenamo-membre', {}), ('add-moto', {'id': jeu['membre'].id}),
        ('edit-moto', {'id': jeu['moto'].id}), ('add-family', {'id': jeu['membre'].id}), ('edit-family', {'id': jeu['famille'].id}),
        ('message', {}), ('add-user', {}), ('add-structure', {}), ('edit-structure', {'id': jeu['association'].id}), ('site', {}),
        ('article', {'id': jeu['article'].id}),
    ]


def test_F28_chaque_formulaire_est_servi_en_modale_et_en_page_de_repli(client, jeu):
    client.force_login(jeu['compte'])
    for nom, kw in _urls(jeu):
        url = reverse(nom, kwargs=kw)
        frag = client.get(url, **HX)
        assert frag.status_code == 200, nom
        html = frag.content.decode()
        assert '<html' not in html and 'class="feuille' in html and 'hx-post=' in html and 'csrfmiddlewaretoken' in html, nom
        page = client.get(url)
        assert page.status_code == 200 and 'class="coque"' in page.content.decode(), nom


def test_F28_province_avec_code_et_ordre_refus_422_puis_succes(client, jeu):
    client.force_login(jeu['compte'])
    url = reverse('add-province')
    r = client.post(url, {'nom': 'Province Neuve', 'code': 'PN', 'ordre': '4'}, **HX)
    assert r.status_code == 200 and r['HX-Refresh'] == 'true'
    cree = Province.objects.get(nom='Province Neuve')
    assert cree.code == 'PN' and cree.ordre == 4
    r = client.post(url, {'nom': 'Autre', 'code': 'pn'}, **HX)  # code déjà pris (normalisé en majuscules)
    assert r.status_code == 422 and 'code officiel' in r.content.decode() and 'class="feuille' in r.content.decode()
    r = client.post(url, {'nom': 'Autre', 'ordre': 'abc'}, **HX)
    assert r.status_code == 422
    r = client.post(url, {'nom': ''}, **HX)
    assert r.status_code == 422 and 'name="nom"' in r.content.decode()


def test_F28_creation_de_compte_en_modale_mot_de_passe_jamais_en_message(client, jeu):
    client.force_login(jeu['compte'])
    r = client.post(reverse('add-user'), {'username': 'nouveau.compte', 'email': 'n@example.invalid'}, **HX)
    assert r.status_code == 200 and 'no-store' in r['Cache-Control'] and 'HX-Refresh' not in r
    html = r.content.decode()
    assert 'nouveau.compte' in html and 'class="feuille' in html
    assert not list(client.session.get('_messages', ''))  # rien dans les messages de session
    suite = client.get(reverse('liste-membre')).content.decode()
    assert 'mot de passe temporaire :' not in suite.lower()


def test_F28_un_seul_composant_pour_le_niveau_de_message():
    from pathlib import Path

    from django.conf import settings
    racine = Path(settings.BASE_DIR)
    fautifs = [f.relative_to(racine).as_posix() for f in (racine / 'coptapp' / 'templates').rglob('*.html')
               if '"success" in classe' in f.read_text(encoding='utf-8')]
    assert fautifs == []


def test_F28_aucun_ancien_gabarit_niceadmin(client):
    from pathlib import Path

    from django.conf import settings
    racine = Path(settings.BASE_DIR)
    assert not (racine / 'templates' / 'base-app.html').exists()
    for f in (racine / 'coptapp' / 'templates' / 'app').glob('*.html'):
        texte = f.read_text(encoding='utf-8')
        assert 'base-app.html' not in texte and 'class="card-body' not in texte and 'data-bs-toggle' not in texte, f.name
