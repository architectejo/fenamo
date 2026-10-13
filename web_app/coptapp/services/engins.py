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


# ---------------------------------------------------------------- enregistrement et numérotation (F-30, F-31)

class CoordinationInconnue(Exception):
    """Le membre n'a pas de coordination provinciale (ou elle n'a pas de code officiel) : numérotation impossible."""


class EnginDejaEnregistre(Exception):
    """Ce propriétaire a déjà un engin avec le même numéro de châssis et de moteur."""


def un_an_apres(jour):
    try:
        return jour.replace(year=jour.year + 1)
    except ValueError:  # 29 février
        return jour.replace(year=jour.year + 1, day=28)


def numero_suivant(province):
    """Numéro suivant de la coordination : compteur (plus grand numéro attribué + 1) suivi du code officiel (sigle).

    PROVISOIRE (F-31) : le code officiel est `Province.sigle` ; l'annexe C et la contrainte d'unicité viendront avec
    le lot Engins. À appeler sous le verrou de la coordination (voir `enregistrer_engin`).
    """
    sigle = province.sigle
    plus_grand = 0
    for numero in Moto.objects.filter(province=province, numero__endswith=sigle).values_list('numero', flat=True):
        debut = numero[:-len(sigle)]
        if debut.isdigit():
            plus_grand = max(plus_grand, int(debut))
    return f'{plus_grand + 1:03d}{sigle}'


@transaction.atomic
def enregistrer_engin(membre, auteur, donnees, photo=None):
    """Crée l'engin de `membre` (``donnees`` : num_plaque, num_moteur, num_chassie, marque, couleur) avec son numéro.

    Le numéro est attribué SOUS VERROU : la ligne de la coordination est verrouillée (``select_for_update``) dans la
    transaction, deux enregistrements simultanés ne peuvent donc pas recevoir le même numéro. Lève CoordinationInconnue
    si le membre n'a pas de coordination avec un code, EnginDejaEnregistre si le châssis et le moteur existent déjà.
    """
    from datetime import date

    from coptapp.models import Province
    if membre.province_id is None:
        raise CoordinationInconnue
    province = Province.objects.select_for_update().get(pk=membre.province_id)
    if not province.sigle:
        raise CoordinationInconnue
    if Moto.objects.filter(proprietaire=membre, num_chassie=donnees.get('num_chassie'),
                           num_moteur=donnees.get('num_moteur')).exists():
        raise EnginDejaEnregistre
    return Moto.objects.create(
        user=auteur if getattr(auteur, 'pk', None) else None, structure=membre.structure, proprietaire=membre,
        antenne=membre.antenne, ville=membre.ville, province=province, numero=numero_suivant(province), photo=photo,
        abonnement=un_an_apres(date.today()), **donnees)
