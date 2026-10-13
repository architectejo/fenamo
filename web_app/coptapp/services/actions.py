"""Actions d'état sur les membres et les engins, avec écriture au journal d'activités (F-70)."""
from django.db import transaction

from compte.models import JournalAction
from compte.services.journal import instantane, journaliser

DRAPEAUX_VALIDATION = ('is_validate1', 'is_validate2', 'is_validate3')


def drapeaux_validation(membre):
    return instantane(membre, DRAPEAUX_VALIDATION)


def journaliser_validation(auteur, membre, avant, motif=''):
    """VALIDATION si des étapes sont franchies, RENVOI si elles sont retirées (circuit de validation)."""
    apres = drapeaux_validation(membre)
    if apres == avant:
        return None
    franchies = sum(bool(v) for v in apres.values())
    precedentes = sum(bool(v) for v in avant.values())
    action = JournalAction.Action.VALIDATION if franchies > precedentes else JournalAction.Action.RENVOI
    return journaliser(auteur, action, membre, avant=avant, apres=apres, motif=motif)


@transaction.atomic
def valider_membre(auteur, membre):
    """Valide `membre` pour `auteur` (F-23) et retourne la liste des drapeaux posés (vide : rien à valider).

    Règles de `droits_provisoires.etapes_a_valider` (étape précédente exigée, jamais sa propre fiche ni ses saisies,
    une seule étape pour privilege2 / privilege3, jamais V2 puis V3 par un compte qui cumule les deux ; plusieurs
    niveaux d'un coup pour SU et privilege5 seulement). Idempotente : ne dévalide jamais. L'état est relu sous
    verrou ; seules les colonnes de validation sont écrites ; chaque validation est journalisée.
    """
    from coptapp.models import Membre
    from coptapp.services.droits_provisoires import etapes_a_valider
    membre = Membre.objects.select_for_update().get(pk=membre.pk)
    etapes = etapes_a_valider(auteur, membre)
    if not etapes:
        return []
    avant = drapeaux_validation(membre)
    for etape in etapes:
        setattr(membre, etape, True)
    membre.save(update_fields=etapes + ['mise_a_jour'])
    journaliser_validation(auteur, membre, avant)
    return etapes


def changer_suppression(auteur, objet, supprime, motif=''):
    """Suppression logique (ou annulation) d'un membre ou d'un engin ; journalisée. Ne contrôle aucun droit :
    pour un membre, passer par `traiter_suppression_membre`. N'écrit que les colonnes concernées."""
    avant = {'is_delete': bool(objet.is_delete)}
    objet.is_delete = supprime
    champs = ['is_delete', 'mise_a_jour']
    if hasattr(objet, 'suppression_demandee'):
        objet.suppression_demandee = False  # la demande est exécutée ou annulée
        objet.suppression_demandee_par = None
        champs += ['suppression_demandee', 'suppression_demandee_par']
        if supprime:
            objet.motif_suppression = motif
            champs.append('motif_suppression')
    objet.save(update_fields=champs)
    action = JournalAction.Action.SUPPRESSION if supprime else JournalAction.Action.RESTAURATION
    journaliser(auteur, action, objet, avant=avant, apres={'is_delete': bool(supprime)}, motif=motif)
    return objet


def rattacher(auteur, objet, champ, cible):
    """Rattache `objet` à `cible` par la clé étrangère `champ` ; journalise l'ancien et le nouveau rattachement."""
    ancien = getattr(objet, champ)
    setattr(objet, champ, cible)
    objet.save()
    journaliser(auteur, JournalAction.Action.RATTACHEMENT, objet,
                avant={champ: getattr(ancien, 'pk', None), f'{champ}_libelle': str(ancien) if ancien else None},
                apres={champ: getattr(cible, 'pk', None), f'{champ}_libelle': str(cible) if cible else None})
    return objet


ACTIONS_SUPPRESSION = ('demander', 'annuler', 'executer', 'restaurer')
MOTIF_MAX = 500


class EtatIncoherent(Exception):
    """L'action demandée ne correspond pas à l'état courant du membre (déjà supprimé, demande déjà faite…) : HTTP 409."""


@transaction.atomic
def traiter_suppression_membre(auteur, membre, action, motif=''):
    """Applique l'action EXPLICITE de suppression sur `membre` (F-25) et retourne le code du résultat.

    Actions : ``demander`` (dépose une demande, motif obligatoire), ``annuler`` (annule la demande en cours),
    ``executer`` (suppression logique, motif obligatoire), ``restaurer`` (annule une suppression, motif obligatoire).
    Chaque action est confrontée à l'ÉTAT COURANT lu sous verrou (``select_for_update``) : écart -> EtatIncoherent.
    Les droits viennent d'une seule source, ``droits_membre`` : PermissionDenied sans droit. Motif limité à
    MOTIF_MAX caractères. Retourne 'motif_requis' ou 'motif_trop_long' sans rien changer. Seules les colonnes
    concernées sont écrites (une modification concurrente d'une autre colonne n'est pas écrasée).
    """
    from django.core.exceptions import PermissionDenied

    from coptapp.models import Membre
    from coptapp.services.droits_provisoires import droits_membre
    if action not in ACTIONS_SUPPRESSION:
        raise ValueError(f'Action de suppression inconnue : {action}')
    membre = Membre.objects.select_for_update().get(pk=membre.pk)
    droits = droits_membre(auteur, membre)
    if not droits['peut_demander_suppression']:
        raise PermissionDenied
    motif = (motif or '').strip()

    if action == 'annuler':
        if not membre.suppression_demandee or membre.is_delete:
            raise EtatIncoherent('Aucune demande de suppression en cours.')
        if not droits['peut_annuler_demande_suppression']:
            raise PermissionDenied
        membre.suppression_demandee = False
        membre.suppression_demandee_par = None
        membre.save(update_fields=['suppression_demandee', 'suppression_demandee_par', 'mise_a_jour'])
        journaliser(auteur, JournalAction.Action.ANNULATION_DEMANDE_SUPPRESSION, membre,
                    avant={'suppression_demandee': True}, apres={'suppression_demandee': False}, motif=motif)
        return 'demande_annulee'

    if len(motif) > MOTIF_MAX:
        return 'motif_trop_long'
    if action == 'demander':
        if membre.is_delete or membre.suppression_demandee:
            raise EtatIncoherent('Membre déjà supprimé ou demande déjà en cours.')
        if not motif:
            return 'motif_requis'
        membre.suppression_demandee = True
        membre.motif_suppression = motif
        membre.suppression_demandee_par = auteur
        membre.save(update_fields=['suppression_demandee', 'motif_suppression', 'suppression_demandee_par', 'mise_a_jour'])
        journaliser(auteur, JournalAction.Action.DEMANDE_SUPPRESSION, membre, avant={'suppression_demandee': False},
                    apres={'suppression_demandee': True}, motif=motif)
        return 'demande'
    if action == 'executer':
        if membre.is_delete:
            raise EtatIncoherent('Membre déjà supprimé.')
        if not droits['peut_executer_suppression']:
            raise PermissionDenied
        if not motif:
            return 'motif_requis'
        changer_suppression(auteur, membre, True, motif)
        return 'supprime'
    # restaurer
    if not membre.is_delete:
        raise EtatIncoherent("Le membre n'est pas supprimé.")
    if not droits['peut_restaurer']:
        raise PermissionDenied
    if not motif:
        return 'motif_requis'
    changer_suppression(auteur, membre, False, motif)
    return 'restaure'
