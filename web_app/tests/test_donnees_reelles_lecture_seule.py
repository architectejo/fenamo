"""Interrupteur « données réelles » (mode exemple du site, décision DR-01) : la lecture ne crée rien, une seule constante de motif ; aides de nomination
déplacées dans les services."""
import pytest
from django.urls import reverse

from compte.models import JournalAction
from virtrine.models import Config
from virtrine.services import contenu
from tests.test_plan_url import hachage_rapide, jeu  # noqa: F401


def test_DR01_get_de_la_modale_et_de_l_etat_ne_creent_pas_la_configuration(client, jeu):
    assert Config.objects.count() == 0
    client.force_login(jeu['compte'])
    assert client.get(reverse('donnees-reelles')).status_code == 200
    assert client.get(reverse('donnees-reelles-etat')).status_code == 200
    assert Config.objects.count() == 0


def test_DR01_une_seule_constante_de_motif(client, jeu):
    import virtrine.views_donnees_reelles as vue
    assert not hasattr(vue, 'MOTIF_MAX') and contenu.MOTIF_MAX == 500
    client.force_login(jeu['compte'])
    assert client.get(reverse('donnees-reelles')).context['motif_max'] == contenu.MOTIF_MAX
    refus = client.post(reverse('donnees-reelles'), {'actif': '1', 'motif': 'm' * (contenu.MOTIF_MAX + 1)})
    assert refus.status_code == 422 and not JournalAction.objects.filter(action=JournalAction.Action.MODIFICATION, objet_type__model='config').exists()
    assert client.post(reverse('donnees-reelles'), {'actif': '1', 'motif': 'm' * contenu.MOTIF_MAX}).status_code == 302
    assert Config.objects.get().donnees_reelles_actif is True


def test_F02_aides_de_nomination_dans_les_services():
    from compte.services.nommage import annoter_nommage, raison_non_nommable
    import compte.views_utilisateurs as vue
    assert callable(annoter_nommage) and callable(raison_non_nommable) and 'def annoter_nommage' not in open(vue.__file__, encoding='utf-8').read()
