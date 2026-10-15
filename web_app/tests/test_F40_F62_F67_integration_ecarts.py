"""Rendu : résumé des destinataires de la modale (F-40), nombres des puces rafraîchis hors zone (F-40, F-62), focus de la modale, détail des toasts, historique (F-67)."""
import re
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

from tests.test_F02_droits_roles import acteurs_roles, monde  # noqa: F401
from tests.test_F40_communiques import equipe  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401
from virtrine.models import Contact
from virtrine.services import contenu

pytestmark = pytest.mark.django_db
HX = {'HTTP_HX_REQUEST': 'true'}


def _html(r):
    return r.content.decode()


def test_F40_modale_resume_destinataires_rafraichi_par_hx_get_et_apercu(client, monde, equipe):
    client.force_login(equipe['ED'])
    html = _html(client.get(reverse('message'), **HX))
    assert 'hx-get="' in html and 'hx-select="#apercu-nb"' in html and 'change from:[name=cible]' in html
    assert 'aria-live="polite"' in html and 'id="apercu-nb"' in html and 'value="national" x-model="cible" checked' in html
    ok = _html(client.get(reverse('message'), {'cible': 'national'}, **HX))
    assert re.search(r'id="apercu-nb"[^>]*><strong>\d+ comptes? actifs? recevr', ok)
    err = _html(client.get(reverse('message'), {'cible': 'antenne'}, **HX))
    assert 'id="apercu-nb"' in err and 'Choisissez l&#x27;antenne' in err or 'Choisissez l\'antenne' in err


def test_F40_modale_garde_le_ciblage_coche_apres_erreur(client, monde, equipe):
    client.force_login(equipe['ED'])
    r = client.post(reverse('message'), {'cible': 'antenne', 'titre': '', 'message': ''}, **HX)
    assert r.status_code == 422 and 'value="antenne" x-model="cible" checked' in _html(r) and 'value="national" x-model="cible" checked' not in _html(r)


def test_F40_puces_nombres_hors_zone_en_oob_seulement_pour_la_zone(client, monde, equipe):
    client.force_login(equipe['PR'])
    zone = _html(client.get(reverse('list-message'), {'q': 'x'}, HTTP_HX_REQUEST='true', HTTP_HX_TARGET='liste-zone'))
    assert 'id="nombre-tous"' in zone and 'hx-swap-oob="true"' in zone and 'id="nombre-non-lus"' in zone
    page = _html(client.get(reverse('list-message')))
    assert page.count('id="nombre-tous"') == 1 and 'hx-swap-oob' not in page
    boost = _html(client.get(reverse('list-message'), HTTP_HX_REQUEST='true', HTTP_HX_BOOSTED='true', HTTP_HX_TARGET='contenu'))
    assert boost.count('id="nombre-tous"') == 1 and 'hx-swap-oob' not in boost


def test_F62_puces_messages_nombres_suivent_la_recherche(client, acteurs_roles, monde):
    Contact.objects.all().delete()
    Contact.objects.create(nom='Alice', description='x' * 12)
    Contact.objects.create(nom='Bob', description='x' * 12, traiter=True)
    client.force_login(acteurs_roles['ED'])
    zone = _html(client.get(reverse('contact'), {'q': 'Alice'}, HTTP_HX_REQUEST='true', HTTP_HX_TARGET='liste-zone'))
    for i in ('a-traiter', 'traites', 'tous'):
        assert f'id="nombre-{i}"' in zone
    assert re.search(r'id="nombre-tous" hx-swap-oob="true">1<', zone) and re.search(r'id="nombre-traites" hx-swap-oob="true">0<', zone)
    page = _html(client.get(reverse('contact')))
    assert page.count('id="nombre-tous"') == 1 and 'hx-swap-oob' not in page


def test_F40_design_js_focus_sur_option_cochee():
    js = (Path(settings.BASE_DIR) / 'static' / 'js' / 'design.js').read_text(encoding='utf-8')
    assert "cible.type === 'radio'" in js and 'r.checked' in js


def test_F40_toast_detail_affiche_par_design_js():
    js = (Path(settings.BASE_DIR) / 'static' / 'js' / 'design.js').read_text(encoding='utf-8')
    assert "if (d.detail)" in js and "createElement('small')" in js


def test_F67_historique_rendu_dans_la_carte(client, jeu):
    client.force_login(jeu['compte'])
    contenu.definir_donnees_reelles(jeu['compte'], True, 'Relu')
    contenu.definir_donnees_reelles(jeu['compte'], False, '')
    carte = _html(client.get(reverse('donnees-reelles-etat'), **HX))
    assert carte.count('class="point') == 2 and 'Motif&nbsp;: Relu' in carte and 'Sans motif' in carte
