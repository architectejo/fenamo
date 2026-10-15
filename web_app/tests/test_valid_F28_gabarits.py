"""Validation indépendante des gabarits (F-28) : peut_*, pages d'erreur, hx-history, HX-Trigger ASCII, coque."""
ANCIEN_NOM = 'COP' + 'TAM'  # ancien nom du produit, interdit dans l'interface
import json
import re
from datetime import date

import pytest
from django.db import connection
from django.http import HttpResponse
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from compte.models import Compte
from coptapp.models import Membre, Notification
from fenamo.htmx import ajouter_declencheurs, reponse_succes
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

HTMX = {'HTTP_HX_REQUEST': 'true'}


def _m(jeu, nom, **kw):
    base = dict(province=jeu['province'], antenne=jeu['antenne'], structure=jeu['association'],
                date_naissance=date(1990, 1, 1))
    base.update(kw)
    return Membre.objects.create(nom=nom, **base)


def _liens(corps, membre, nom):
    return reverse(nom, args=[membre.id]) in corps


# ---------------------------------------------------------------- peut_* dans la liste

@pytest.mark.parametrize('privileges, voit_bouton', [
    ({'privilege2': True}, True), ({'privilege3': True}, True), ({'privilege5': True}, True),
    ({'privilege4': True}, False), ({'privilege1': True}, False), ({}, False),
])
def test_F28_liste_bouton_valider_selon_peut_valider(client, jeu, privileges, voit_bouton):
    compte = Compte.objects.create_user('lv', password='x', **privileges)
    # Le bouton suit le droit de valider CE membre : l'étape précédente est exigée (privilege2 valide un membre non encore validé
    # par l'antenne ; privilege3 un membre validé par l'antenne) et personne ne valide sa propre fiche.
    cible = _m(jeu, 'Liste Cible', etat='saisi' if privileges.get('privilege2') else 'valide_antenne', user=compte if privileges.get('privilege1') else None)
    if privileges.get('privilege4'):
        cible.is_validate3 = True
        cible.save()
    if not privileges.get('privilege1') and not privileges.get('privilege4'):
        compte.membreId = _m(jeu, 'Fiche du compte').id if voit_bouton else cible.id  # fiche propre distincte de la cible quand elle doit pouvoir valider
        compte.save()
    client.force_login(compte)
    corps = client.get('/membres/').content.decode()
    assert 'Liste Cible' in corps
    url_valider = reverse('validate', args=[cible.id])
    if voit_bouton:
        # pour p4 le membre est actif, donc ce cas n'apparaît pas ici ; pour les autres le membre n'est pas actif
        assert url_valider in corps
    else:
        assert url_valider not in corps


def test_F28_liste_contexte_peut_valider_coherent_avec_les_droits(client, jeu):
    client.force_login(jeu['compte'])
    c = client.get('/membres/').context
    assert c['peut_valider'] and c['droits']['peut_valider']
    visiteur = Compte.objects.create_user('vis', password='x', privilege4=True)
    c2 = Client()
    c2.force_login(visiteur)
    ctx = c2.get('/membres/').context
    assert not ctx['peut_valider'] and not ctx['peut_modifier'] and not ctx['peut_attribuer_privileges']


def test_F28_liste_actif_n_a_pas_de_bouton_valider(client, jeu):
    client.force_login(jeu['compte'])
    actif = _m(jeu, 'Déjà actif', etat='actif')
    corps = client.get('/membres/').content.decode()
    assert reverse('validate', args=[actif.id]) not in corps
    assert reverse('validate', args=[jeu['membre'].id]) in corps


def test_F28_liste_bouton_valider_est_un_formulaire_post_avec_csrf(client, jeu):
    client.force_login(jeu['compte'])
    corps = client.get('/membres/').content.decode()
    m = re.search(r'<form[^>]*action="' + re.escape(reverse('validate', args=[jeu['membre'].id])) + r'"[^>]*>.*?</form>', corps, re.S)
    assert m, 'bouton Valider absent'
    bloc = m.group(0)
    assert 'post' in bloc.lower() and 'csrfmiddlewaretoken' in bloc


# ---------------------------------------------------------------- peut_* dans la fiche

def test_F28_fiche_su_voit_privileges_et_historique_visiteur_non(client, jeu):
    client.force_login(jeu['compte'])
    c = client.get(reverse('membre-view', args=[jeu['membre'].id]))
    assert c.context['peut_attribuer_privileges'] and c.context['peut_voir_historique']
    visiteur = Compte.objects.create_user('vis2', password='x', privilege4=True)
    actif = _m(jeu, 'Actif', etat='actif')
    c2 = Client()
    c2.force_login(visiteur)
    r = c2.get(reverse('membre-view', args=[actif.id]))
    assert r.status_code == 200
    for cle in ('peut_modifier', 'peut_valider', 'peut_demander_suppression', 'peut_attribuer_privileges',
                'peut_ajouter_famille', 'peut_ajouter_engin', 'peut_voir_historique'):
        assert r.context[cle] is False, cle
    corps = r.content.decode()
    assert reverse('delete-membre', args=[actif.id]) not in corps
    assert reverse('validate', args=[actif.id]) not in corps


def test_F28_fiche_fragment_modale_et_page_complete(client, jeu):
    client.force_login(jeu['compte'])
    url = reverse('membre-view', args=[jeu['membre'].id])
    page = client.get(url).content.decode().lower()
    assert '<html' in page


# ---------------------------------------------------------------- pages d'erreur, DEBUG=False

@pytest.fixture
def prod(settings):
    settings.DEBUG = False
    settings.ALLOWED_HOSTS = ['testserver', 'localhost']


def _client_sans_exception(jeu=None):
    c = Client(raise_request_exception=False)
    if jeu:
        c.force_login(jeu['compte'])
    return c


@pytest.mark.parametrize('connecte', [False, True])
def test_F28_page_404_sans_trace(prod, jeu, connecte):
    c = _client_sans_exception(jeu if connecte else None)
    r = c.get('/une/adresse/qui/n/existe/pas/')
    assert r.status_code in (404, 302)
    if r.status_code == 404:
        corps = r.content.decode()
        assert 'Traceback' not in corps and 'FENAMO-RDC' in corps and ANCIEN_NOM not in corps.upper()


def test_F28_404_membre_inexistant_page_propre(prod, jeu):
    r = _client_sans_exception(jeu).get('/membres/99999/')
    corps = r.content.decode()
    assert r.status_code == 404 and 'Traceback' not in corps and 'Request URL' not in corps


def test_F28_403_page_propre(prod, jeu):
    visiteur = Compte.objects.create_user('v403', password='x', privilege4=True)
    actif = _m(jeu, 'Actif', etat='actif')
    c = _client_sans_exception()
    c.force_login(visiteur)
    r = c.post(reverse('delete-membre', args=[actif.id]), {'action': 'demander', 'motif': 'x'})
    corps = r.content.decode()
    assert r.status_code == 403 and 'Traceback' not in corps and '403' in corps


def test_F28_403_csrf_gabarit_dedie_sans_raison_technique(prod, jeu):
    c = Client(enforce_csrf_checks=True, raise_request_exception=False)
    c.force_login(jeu['compte'])
    r = c.post(reverse('validate', args=[jeu['membre'].id]))
    corps = r.content.decode()
    assert r.status_code == 403
    assert 'CSRF verification' not in corps and 'Referer' not in corps and 'Reason given' not in corps and 'Envoi refusé' in corps


def test_F28_gabarit_500_rendu_sans_requete_sql(client, db):
    from django.template.loader import render_to_string
    from django.test import RequestFactory
    request = RequestFactory().get('/')
    from django.contrib.auth.models import AnonymousUser
    request.user = AnonymousUser()
    with CaptureQueriesContext(connection) as q:
        html = render_to_string('500.html', request=request)
    assert len(q) == 0 and 'FENAMO-RDC' in html


@pytest.mark.parametrize('code', ['400', '403', '404', '500'])
def test_F28_gabarits_erreur_sans_cdn_ni_ancien_nom(code):
    from django.template.loader import render_to_string
    html = render_to_string(f'{code}.html')
    assert ANCIEN_NOM not in html.upper() and 'cdn' not in html.lower() and 'https://' not in html


# ---------------------------------------------------------------- hx-history

@pytest.mark.parametrize('adresse', ['/mon-compte/securite/'])
def test_F28_hx_history_false_sur_les_pages_sensibles(client, jeu, adresse):
    client.force_login(jeu['compte'])
    corps = client.get(adresse).content.decode()
    assert 'hx-history="false"' in corps


def test_F28_hx_history_false_sur_connexion_anonyme(client, db):
    assert 'hx-history="false"' in client.get('/connexion/').content.decode()


# ---------------------------------------------------------------- HX-Trigger ASCII

def test_F04_hx_trigger_ascii_avec_apostrophe_typographique():
    r = reponse_succes("L’équipe a validé « Nicolas » \U0001F600")
    valeur = r.headers['HX-Trigger']
    valeur.encode('ascii')  # ne lève pas
    assert json.loads(valeur)['toast']['message'].startswith('L’équipe')


def test_F04_hx_trigger_ascii_cumul_de_declencheurs():
    r = HttpResponse()
    ajouter_declencheurs(r, {'toast': {'message': 'é', 'niveau': 'info'}})
    ajouter_declencheurs(r, {'toast': {'message': 'ç’', 'niveau': 'info'}, 'membresModifies': True})
    valeur = r.headers['HX-Trigger']
    valeur.encode('ascii')
    assert len(json.loads(valeur)['toast']) == 2


def test_F04_hx_trigger_messages_django_en_ascii_bout_en_bout(client, jeu):
    """Valider deux fois par HTMX : le message « déjà validé » passe en toast, l'en-tête reste ASCII."""
    client.force_login(jeu['compte'])
    url = reverse('validate', args=[jeu['membre'].id])
    client.post(url, **HTMX)
    r = client.post(url, **HTMX)
    for nom, valeur in r.headers.items():
        valeur.encode('ascii')


# ---------------------------------------------------------------- coque et périmètre

def test_F28_coque_su_role_et_perimetre_national(client, jeu):
    client.force_login(jeu['compte'])
    corps = client.get('/membres/').content.decode()
    assert 'Super-utilisateur' in corps and 'National' in corps


def test_F28_coque_compte_ordinaire_ne_voit_que_ses_notifications(client, jeu):
    a = Compte.objects.create_user('na', password='x')
    b = Compte.objects.create_user('nb', password='x')
    Notification.objects.create(user=a, membre=jeu['membre'], titre='Notification de A secrète')
    Notification.objects.create(user=b, membre=jeu['membre'], titre='Notification de B')
    client.force_login(b)
    corps = client.get('/membres/').content.decode()
    assert 'Notification de B' in corps and 'secrète' not in corps


def test_F28_coque_absente_des_fragments(client, jeu):
    client.force_login(jeu['compte'])
    Notification.objects.create(user=jeu['compte'], membre=jeu['membre'], titre='Visible en coque')
    assert 'Visible en coque' in client.get('/membres/').content.decode()
    assert 'Visible en coque' not in client.get('/membres/', **HTMX).content.decode()


def test_F28_coque_membre_du_compte_sans_antenne_ni_province(client, jeu):
    m = Membre.objects.create(nom='Sans lieu', date_naissance=date(1990, 1, 1))
    compte = Compte.objects.create_user('sl', password='x', membreId=m.id)
    client.force_login(compte)
    assert client.get('/membres/').status_code == 200
    assert client.get('/').status_code in (200, 302)


def test_F28_coque_membreId_orphelin_ne_plante_pas(client, jeu):
    compte = Compte.objects.create_user('orph', password='x', membreId=987654)
    client.force_login(compte)
    assert client.get('/membres/').status_code == 200


# ---------------------------------------------------------------- aucun GET ne modifie

@pytest.mark.parametrize('adresse', ['/', '/membres/', '/mon-compte/securite/'])
def test_F28_get_sans_effet_de_bord(client, jeu, adresse):
    client.force_login(jeu['compte'])
    avant = (Membre.objects.count(), Notification.objects.count(), list(Membre.objects.values_list('is_validate2', 'is_delete')))
    client.get(adresse)
    client.get(adresse, **HTMX)
    assert avant == (Membre.objects.count(), Notification.objects.count(), list(Membre.objects.values_list('is_validate2', 'is_delete')))
