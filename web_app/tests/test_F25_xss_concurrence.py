"""F-25 (revalidation) : motif hostile réaffiché échappé partout, double soumission, verrou, statuts d'erreur.

Données fictives uniquement. Les « deux transactions » sont simulées : deux instances lues AVANT l'action
(état périmé) puis deux appels successifs du service, le second doit se heurter à l'état réel lu sous verrou.
"""
from unittest import mock

import pytest
from django.db.models.query import QuerySet
from django.urls import reverse

from compte.models import JournalAction
from coptapp.models import Membre
from coptapp.services.actions import MOTIF_MAX, EtatIncoherent, traiter_suppression_membre
from tests.test_F21_matrice_routes import acteurs  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

XSS = '<script>alert("x")</script><img src=x onerror=alert(1)>'
XSS_ECHAPPE = '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;'
A = JournalAction.Action


def _url(m):
    return reverse('delete-membre', kwargs={'id': m.id})


def _pages_a_lire(client, acteurs, membre):
    """Contenus de toutes les pages qui peuvent réafficher le motif : fiche, liste, historique (admin), puis toast."""
    pages = []
    client.force_login(acteurs['comptes']['su'])
    pages.append(client.get(reverse('membre-view', kwargs={'id': membre.id})).content.decode())
    pages.append(client.get(reverse('membre-view', kwargs={'id': membre.id}), HTTP_HX_REQUEST='true').content.decode())
    pages.append(client.get(reverse('liste-membre')).content.decode())
    pages.append(client.get(reverse('admin:compte_journalaction_changelist')).content.decode())
    ligne = JournalAction.objects.filter(motif__contains='script').first()
    if ligne:
        pages.append(client.get(reverse('admin:compte_journalaction_change', args=[ligne.pk])).content.decode())
    return pages


@pytest.mark.parametrize('action', ['demander', 'executer'])
def test_F25_motif_xss_reaffiche_echappe_fiche_modale_historique_toast(client, acteurs, action):
    membre = acteurs['membre']
    profil = 'p1' if action == 'demander' else 'su'
    client.force_login(acteurs['comptes'][profil])
    r = client.post(_url(membre), {'action': action, 'motif': XSS}, follow=True)
    assert r.status_code == 200
    toast = r.content.decode()  # page après redirection : les messages (toasts) y sont rendus
    assert '<script>alert("x")' not in toast and 'onerror=alert(1)>' not in toast
    for page in [toast] + _pages_a_lire(client, acteurs, membre):
        assert '<script>alert("x")' not in page
        assert '<img src=x onerror' not in page
    assert JournalAction.objects.filter(motif__contains='script').exists()  # stocké tel quel, échappé à l'affichage


def test_F25_motif_xss_apparait_echappe_dans_la_fiche_quand_il_est_affiche(client, acteurs):
    membre = acteurs['membre']
    client.force_login(acteurs['comptes']['p1'])
    client.post(_url(membre), {'action': 'demander', 'motif': XSS})
    fiche = client.get(reverse('membre-view', kwargs={'id': membre.id})).content.decode()
    if 'alert(' in fiche:  # si la fiche réaffiche le motif, ce ne peut être qu'échappé
        assert XSS_ECHAPPE in fiche


@pytest.mark.parametrize('donnees', [{}, {'action': ''}, {'action': 'detruire'}, {'action': 'EXECUTER'}, {'motif': 'x'}])
def test_F25_action_absente_ou_inconnue_donne_400_sans_effet(client, acteurs, donnees):
    client.force_login(acteurs['comptes']['su'])
    r = client.post(_url(acteurs['membre']), donnees)
    assert r.status_code == 400
    acteurs['membre'].refresh_from_db()
    assert not acteurs['membre'].is_delete and not acteurs['membre'].suppression_demandee
    assert not JournalAction.objects.filter(objet_id=acteurs['membre'].id, action__in=[
        A.DEMANDE_SUPPRESSION, A.SUPPRESSION]).exists()


@pytest.mark.parametrize('profil, action, prealable', [
    ('su', 'restaurer', None),            # restaurer un membre non supprimé
    ('su', 'executer', 'executer'),       # exécuter deux fois
    ('p1', 'demander', 'demander'),       # demander deux fois
    ('p1', 'annuler', None),              # annuler sans demande
])
def test_F25_etat_incoherent_donne_409(client, acteurs, profil, action, prealable):
    if prealable:
        client.force_login(acteurs['comptes']['su' if prealable == 'executer' else 'p1'])
        client.post(_url(acteurs['membre']), {'action': prealable, 'motif': 'premier'})
    client.force_login(acteurs['comptes'][profil])
    r = client.post(_url(acteurs['membre']), {'action': action, 'motif': 'second'})
    assert r.status_code == 409


def test_F25_motif_de_501_caracteres_refuse_et_500_accepte(client, acteurs):
    client.force_login(acteurs['comptes']['su'])
    r = client.post(_url(acteurs['membre']), {'action': 'executer', 'motif': 'a' * (MOTIF_MAX + 1)})
    acteurs['membre'].refresh_from_db()
    assert r.status_code in (302, 400) and acteurs['membre'].is_delete is False
    client.post(_url(acteurs['membre']), {'action': 'executer', 'motif': 'a' * MOTIF_MAX})
    acteurs['membre'].refresh_from_db()
    assert acteurs['membre'].is_delete is True


def test_F25_double_soumission_une_seule_execution_une_seule_ligne_de_journal(acteurs):
    """Deux transactions concurrentes : les deux ont lu l'état « actif » avant le verrou. Une seule gagne."""
    su = acteurs['comptes']['su']
    lecture_a = Membre.objects.get(pk=acteurs['membre'].pk)
    lecture_b = Membre.objects.get(pk=acteurs['membre'].pk)
    assert lecture_a.is_delete is False and lecture_b.is_delete is False  # état périmé pour la seconde
    assert traiter_suppression_membre(su, lecture_a, 'executer', 'premier') == 'supprime'
    with pytest.raises(EtatIncoherent):
        traiter_suppression_membre(su, lecture_b, 'executer', 'second')
    assert JournalAction.objects.filter(objet_id=acteurs['membre'].pk, action=A.SUPPRESSION).count() == 1


def test_F25_le_service_relit_le_membre_sous_verrou(acteurs):
    """select_for_update est bien demandé (SQLite l'ignore ; MySQL en production verrouille la ligne)."""
    su = acteurs['comptes']['su']
    with mock.patch.object(QuerySet, 'select_for_update', autospec=True, side_effect=QuerySet.select_for_update) as verrou:
        traiter_suppression_membre(su, acteurs['membre'], 'executer', 'motif')
    assert verrou.called
