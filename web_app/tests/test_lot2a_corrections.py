"""Passe de corrections du sous-lot 2a (rapports sécurité et relecteur)."""
import pytest
from django.urls import reverse

from compte.models import Compte
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401

MDP = 'Bon-mot-de-passe-1x'


# ------------------------------------------------------------- C1 : privilèges réservés aux SU

@pytest.fixture
def pirate(jeu):
    Compte.objects.filter(pk=jeu['compte'].pk).update(membreId=None)
    return Compte.objects.create_user('pirate', password=MDP, membreId=jeu['membre'].id)


def test_F02_non_su_ne_peut_pas_s_attribuer_privilege5(client, jeu, pirate):
    client.force_login(pirate)
    url = reverse('membre-view', kwargs={'id': jeu['membre'].id})
    r = client.post(url, {'privilege': '1', 'privilege5': 'on', 'privilege1': 'on'})
    assert r.status_code == 403
    pirate.refresh_from_db()
    assert not any(getattr(pirate, f'privilege{i}') for i in range(1, 6))


def test_F02_su_attribue_les_privileges_et_journalise(client, jeu, pirate):
    from coptapp.models import Notification
    client.force_login(jeu['compte'])
    url = reverse('membre-view', kwargs={'id': jeu['membre'].id})
    assert client.post(url, {'privilege': '1', 'privilege3': 'on'}).status_code == 200
    pirate.refresh_from_db()
    assert pirate.privilege3 and not pirate.privilege5
    assert Notification.objects.filter(titre="Attribution des privilèges").exists()
