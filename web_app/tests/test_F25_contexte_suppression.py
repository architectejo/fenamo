"""F-25 : clés de droits de suppression dans le contexte de la fiche (exécuter, restaurer, annuler une demande)."""
from django.urls import reverse

from compte.services.droits import droits_membre
from tests.test_F35_droits_engins_famille import _compte, saisie  # noqa: F401
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def test_F25_contexte_suppression(client, saisie):
    membre = saisie['membre']
    agent = saisie['agent']
    url = reverse('delete-membre', args=[membre.id])
    client.force_login(agent)
    ctx = client.get(reverse('membre-view', args=[membre.id])).context
    assert not ctx['peut_executer_suppression'] and not ctx['peut_annuler_demande_suppression'] and not ctx['peut_restaurer']
    client.post(url, {'action': 'demander', 'motif': 'Doublon'})
    membre.refresh_from_db()
    assert membre.suppression_demandee and membre.suppression_demandee_par == agent
    ctx = client.get(reverse('membre-view', args=[membre.id])).context
    assert ctx['peut_annuler_demande_suppression'] and not ctx['peut_executer_suppression']
    # un autre compte qui voit la fiche ne peut pas annuler la demande d'autrui
    client.force_login(_compte('autre', privilege2=True))
    assert not client.get(reverse('membre-view', args=[membre.id])).context['peut_annuler_demande_suppression']
    assert client.post(url, {'action': 'annuler'}).status_code == 403
    membre.refresh_from_db()
    assert membre.suppression_demandee
    # qui exécute peut annuler et exécuter ; après exécution il peut restaurer
    client.force_login(saisie['compte'])
    ctx = client.get(reverse('membre-view', args=[membre.id])).context
    assert ctx['peut_executer_suppression'] and ctx['peut_annuler_demande_suppression'] and not ctx['peut_restaurer']
    client.post(url, {'action': 'executer', 'motif': 'Confirmé'})
    membre.refresh_from_db()
    assert membre.is_delete and membre.suppression_demandee_par is None
    ctx = client.get(reverse('membre-view', args=[membre.id])).context
    assert ctx['peut_restaurer'] and not ctx['peut_annuler_demande_suppression']


def test_F25_visiteur_sans_droits_de_suppression(saisie):
    droits = droits_membre(_compte('v', privilege4=True, privilege5=True), saisie['membre'])
    assert not (droits['peut_executer_suppression'] or droits['peut_restaurer'] or droits['peut_annuler_demande_suppression'])
