"""Engins : attribution d'un motard à un engin (F-33, journalisée)."""
from django.core.exceptions import PermissionDenied
from django.db import transaction

from compte.models import JournalAction
from compte.services.journal import journaliser
from coptapp.models import Moto
from coptapp.services.droits_provisoires import droits_membre, engins_visibles


@transaction.atomic
def attribuer_engin(auteur, membre_cible, numero):
    """Rattache `membre_cible` comme motard à l'engin de numéro `numero` ; retourne le code du résultat.

    Codes : 'numero_requis', 'introuvable' (aucun engin visible de `auteur` ne porte ce numéro), 'ambigu' (plusieurs),
    'attribue'. Droits (PermissionDenied sinon) : ajouter un engin pour le membre cible (``peut_ajouter_engin``) ET
    modifier l'engin sur son propriétaire (``peut_modifier_engin``, F-35). L'engin est relu sous verrou ; seules les
    colonnes concernées sont écrites ; l'attribution est journalisée (avant / après).
    """
    if not droits_membre(auteur, membre_cible)['peut_ajouter_engin']:
        raise PermissionDenied
    numero = (numero or '').strip()
    if not numero:
        return 'numero_requis'
    ids = list(engins_visibles(auteur).filter(numero=numero).values_list('pk', flat=True)[:2])
    if not ids:
        return 'introuvable'
    if len(ids) > 1:
        return 'ambigu'
    moto = Moto.objects.select_for_update().select_related('proprietaire').get(pk=ids[0])
    if moto.proprietaire is None or not droits_membre(auteur, moto.proprietaire)['peut_modifier_engin']:
        raise PermissionDenied
    avant = {'motard_id': moto.motard_id}
    moto.motard_id = str(membre_cible.id)
    moto.save(update_fields=['motard_id', 'mise_a_jour'])
    journaliser(auteur, JournalAction.Action.RATTACHEMENT, moto, avant=avant,
                apres={'motard_id': moto.motard_id}, libelle=f"Engin {moto.numero}")
    return 'attribue'
