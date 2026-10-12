"""Coque (barre du haut) : services dans compte/services, requêtes sautées pour les fragments HTMX ; vues qui fournissent les données."""
import pytest
from django.test import RequestFactory
from django.urls import reverse
from django_htmx.middleware import HtmxDetails

from compte.models import Compte, JournalAction
from compte.services.journal import journaliser
from compte.services.perimetre import donnees_coque, notifications_du_perimetre, role_et_perimetre
from coptapp.models import Membre, Notification
from fenamo.contexte import coque
from fenamo.htmx import veut_fragment
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def _requete(user, **entetes):
    requete = RequestFactory().get('/', **entetes)
    requete.user = user
    requete.htmx = HtmxDetails(requete)
    return requete


def test_F28_role_et_perimetre(jeu):
    assert [str(x) for x in role_et_perimetre(jeu['compte'])] == ['Super-utilisateur', 'National']
    membre = jeu['membre']
    simple = Compte.objects.create_user('simple', password='x', membreId=membre.id)
    assert [str(x) for x in role_et_perimetre(simple)] == ['Compte', 'Antenne A']
    Membre.objects.filter(pk=membre.pk).update(antenne=None)
    assert role_et_perimetre(simple)[1] == 'Province fictive'
    assert role_et_perimetre(Compte.objects.create_user('sans', password='x'))[1] == ''


def test_F28_notifications_du_perimetre(jeu):
    autre = Compte.objects.create_user('autre', password='x')
    Notification.objects.create(user=jeu['compte'], titre='A')
    Notification.objects.create(user=autre, titre='B')
    assert notifications_du_perimetre(jeu['compte']).count() == 2
    assert [n.titre for n in notifications_du_perimetre(autre)] == ['B']
    p5 = Compte.objects.create_user('p5', password='x', privilege5=True)
    assert notifications_du_perimetre(p5).count() == 2


def test_F28_donnees_coque_exclut_les_notifications_lues(jeu):
    Notification.objects.create(user=jeu['compte'], titre='non lue')
    Notification.objects.create(user=jeu['compte'], titre='lue', is_validate=True)
    total, dernieres, role, lieu = donnees_coque(jeu['compte'])
    assert total == 1 and [n.titre for n in dernieres] == ['non lue'] and role and lieu


def test_F28_veut_fragment():
    assert not veut_fragment(RequestFactory().get('/'))
    assert not veut_fragment(_requete(None))
    assert veut_fragment(_requete(None, HTTP_HX_REQUEST='true'))
    assert not veut_fragment(_requete(None, HTTP_HX_REQUEST='true', HTTP_HX_BOOSTED='true'))


def test_F28_contexte_coque_page_complete(jeu):
    donnees = coque(_requete(jeu['compte']))
    assert {'fn_notifs_total', 'fn_notifs', 'fn_role', 'fn_perimetre'} <= set(donnees)


def test_F28_contexte_coque_fragment_htmx_sans_requete(jeu, django_assert_num_queries):
    requete = _requete(jeu['compte'], HTTP_HX_REQUEST='true')
    with django_assert_num_queries(0):
        donnees = coque(requete)
    assert 'fn_notifs' not in donnees and 'fn_role' not in donnees


def test_F28_contexte_coque_navigation_boostee_garde_la_coque(jeu):
    donnees = coque(_requete(jeu['compte'], HTTP_HX_REQUEST='true', HTTP_HX_BOOSTED='true'))
    assert 'fn_notifs' in donnees


def test_F28_fragment_de_la_liste_ne_lit_pas_les_notifications(client, jeu, django_assert_max_num_queries):
    Notification.objects.create(user=jeu['compte'], titre='X')
    client.force_login(jeu['compte'])
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    with CaptureQueriesContext(connection) as requetes:
        r = client.get(reverse('liste-membre'), HTTP_HX_REQUEST='true')
    assert r.status_code == 200
    assert not [q for q in requetes if 'coptapp_notification' in q['sql']]


def test_F28_vue_tableau_de_bord_fournit_les_indicateurs(client, jeu):
    client.force_login(jeu['compte'])
    r = client.get(reverse('tableau-bord'))
    assert r.status_code == 200
    ind = r.context['indicateurs']
    assert (ind['saisis'], ind['engins'], ind['associations']) == (1, 1, 1)
    assert {'actifs', 'valides_antenne', 'en_attente_total', 'en_attente', 'graphique'} <= set(ind)


def test_F28_tableau_de_bord_respecte_le_perimetre_du_compte(client, jeu):
    client.force_login(Compte.objects.create_user('rien', password='x'))
    ind = client.get(reverse('tableau-bord')).context['indicateurs']
    assert (ind['saisis'], ind['engins'], ind['associations']) == (0, 0, 0)


def test_F28_fiche_fournit_l_historique_selon_le_droit(client, jeu):
    journaliser(jeu['compte'], JournalAction.Action.VALIDATION, jeu['membre'], motif='premier')
    url = reverse('membre-view', kwargs={'id': jeu['membre'].id})
    client.force_login(jeu['compte'])
    assert [ligne.motif for ligne in client.get(url).context['historique']] == ['premier']
    client.force_login(Compte.objects.create_user('p2h', password='x', privilege2=True))
    assert len(client.get(url).context['historique']) == 1
    client.force_login(Compte.objects.create_user('p1h', password='x', privilege1=True, membreId=jeu['membre'].id))
    assert client.get(url).context['historique'] == []
