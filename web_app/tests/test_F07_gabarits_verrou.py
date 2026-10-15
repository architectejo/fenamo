"""F-07 : gabarits du verrouillage (écran du SU, modales, bandeau, 503 autonome, connexion, espace mobile suspendu, menu)."""
import re

from django.urls import reverse

from compte import roles
from compte.models import Compte, Nomination
from compte.services import verrou_application as verrou
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

SCRIPT = '<script>alert(1)</script>'
HX = {'HTTP_HX_REQUEST': 'true'}


def _verrouiller(jeu, message='Maintenance : retour à 12 h.\nMerci.'):
    verrou.verrouiller(jeu['compte'], message, 'Bascule MySQL')


def test_F07_ecran_deverrouille_puis_verrouille_sans_safe(client, jeu):
    client.force_login(jeu['compte'])
    html = client.get(reverse('verrou-application')).content.decode()
    assert 'Déverrouillée' in html and "Verrouiller l'application" in html and 'verrou-effets' in html and 'hx-history="false"' in html
    verrou.verrouiller(jeu['compte'], SCRIPT, '<b>motif</b>')
    html = client.get(reverse('verrou-application')).content.decode()
    assert 'Verrouillée' in html and "Déverrouiller l'application" in html and 'verrou--ferme' in html
    assert SCRIPT not in html and '&lt;script&gt;' in html and '<b>motif</b>' not in html  # échappé, jamais |safe
    frag = client.get(reverse('verrou-application'), **HX).content.decode()
    assert '<html' not in frag and 'verrou-sceau change' in frag and 'Changements d' in frag


def test_F07_modales_compteur_commun_et_erreur_a_cote_du_champ(client, jeu):
    client.force_login(jeu['compte'])
    html = client.get(reverse('verrou-verrouiller'), **HX).content.decode()
    assert html.count('data-compte-caracteres') == 2 and 'maxlength="500"' in html and 'Dès que vous confirmez' in html
    r = client.post(reverse('verrou-verrouiller'), {'message': '  ', 'motif': ''}, **HX)
    assert r.status_code == 422
    corps = r.content.decode()
    assert 'id="v-message-erreur"' in corps and 'aria-invalid="true"' in corps and 'class="feuille' in corps
    r = client.post(reverse('verrou-verrouiller'), {'message': 'Retour demain', 'motif': ''}, **HX)
    assert r.status_code == 204 and 'verrouModifie' in r['HX-Trigger']
    html = client.get(reverse('verrou-deverrouiller'), **HX).content.decode()
    assert 'data-compte-caracteres' in html and 'Verrouillée le' in html
    r = client.post(reverse('verrou-deverrouiller'), {'motif': 'Terminé'}, **HX)
    assert r.status_code == 204


def test_F07_bandeau_seulement_pour_le_su_et_si_verrouille(client, jeu):
    client.force_login(jeu['compte'])
    assert 'bandeau-verrou' not in client.get(reverse('liste-membre')).content.decode()
    _verrouiller(jeu)
    assert 'bandeau-verrou' in client.get(reverse('liste-membre')).content.decode()
    page = client.get(reverse('verrou-application')).content.decode()
    assert 'aria-current="page"' in page.split('class="bandeau-verrou"')[1].split('</div>')[0]
    assert 'bandeau-verrou' not in client.get(reverse('liste-membre'), **HX).content.decode()  # fragment : pas de coque


def test_F07_503_autonome_sans_coque_ni_script_et_message_echappe(client, jeu):
    verrou.verrouiller(jeu['compte'], SCRIPT, '')
    pr = Compte.objects.create_user('simple-pr', password='x')
    Nomination.objects.create(compte=pr, role=roles.PR, nomme_par=jeu['compte'])
    client.force_login(pr)
    r = client.get(reverse('liste-membre'))
    if r.status_code != 503:  # le middleware ferme la session puis répond selon le chemin
        r = client.get(reverse('liste-membre'))
    html = r.content.decode()
    assert r.status_code == 503 and 'porte--suspendue' in html and 'Application suspendue' in html
    assert 'class="coque"' not in html and 'fenamo.js' not in html and 'htmx' not in html and 'alpine' not in html
    assert SCRIPT not in html and '&lt;script&gt;' in html
    assert re.findall(r'<script[^>]*src="([^"]+)"', html) == [re.findall(r'<script[^>]*src="([^"]+theme\.js)"', html)[0]]


def test_F07_connexion_alerte_avant_le_titre(client, jeu):
    verrou.verrouiller(jeu['compte'], SCRIPT, '')
    html = client.get(reverse('application')).content.decode()
    assert html.index('Application suspendue') < html.index('<h1', html.index('porte-cadre'))
    assert 'role="status"' in html and 'seuls les super-utilisateurs peuvent se connecter' in html
    assert SCRIPT not in html and '&lt;script&gt;' in html


def test_F07_espace_mobile_suspendu_sur_base_mob(client, jeu):
    verrou.verrouiller(jeu['compte'], SCRIPT, '')
    r = client.get('/mob/')
    html = r.content.decode()
    assert r.status_code == 503 and 'mob--suspendu' in html and 'Espace membre suspendu' in html and 'tokens.css' in html
    assert '<svg' not in html and SCRIPT not in html and '&lt;script&gt;' in html


def test_F07_menu_verrouillage_pour_le_su_seulement(client, jeu):
    client.force_login(jeu['compte'])
    html = client.get(reverse('liste-membre')).content.decode()
    assert reverse('verrou-application') in html and 'Administration' in html
    pr = Compte.objects.create_user('pr-menu', password='x')
    Nomination.objects.create(compte=pr, role=roles.PR, nomme_par=jeu['compte'])
    client.force_login(pr)
    assert reverse('verrou-application') not in client.get(reverse('liste-membre')).content.decode()
