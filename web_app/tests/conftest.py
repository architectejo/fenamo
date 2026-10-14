"""Utilitaires communs aux tests."""
import pytest

from coptapp.models import Membre


def forcer_etat(membre, etat, precedent=''):
    """Pose l'état unique d'un membre (les anciens booléens suivent, recalculés par le modèle) et recharge l'objet.
    Remplace les écritures directes de is_validate2, is_validate3, renvoye ou is_delete dans les tests."""
    champs = {'etat': etat}
    if etat == 'supprime':
        champs['etat_precedent'] = precedent or 'saisi'
    Membre.objects.filter(pk=membre.pk).update(**champs)
    membre.refresh_from_db()
    return membre


@pytest.fixture
def forcer():
    """Fixture : ``forcer(membre, 'valide_antenne')``."""
    return forcer_etat
