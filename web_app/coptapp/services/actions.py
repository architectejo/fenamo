"""Actions d'état sur les membres et les engins, avec écriture au journal d'activités (F-70)."""
from django.core.exceptions import PermissionDenied
from django.db import transaction

from compte.models import JournalAction
from compte.services.journal import journaliser
from coptapp.models import Membre
from coptapp.services import transitions
from coptapp.services.transitions import MOTIF_MAX, EtatIncoherent
from compte.services.droits import droits_membre

def changer_suppression(auteur, objet, supprime, motif=''):
    """Suppression logique (ou annulation) d'un ENGIN ; journalisée. Ne contrôle aucun droit. Un membre se supprime et se
    restaure par son état unique : ``traiter_suppression_membre`` (actions explicites) ou ``transitions.supprimer`` / ``restaurer``."""
    if isinstance(objet, Membre):
        raise TypeError("Un membre se supprime par coptapp.services.transitions (état unique).")
    avant = {'is_delete': bool(objet.is_delete)}
    objet.is_delete = supprime
    champs = ['is_delete', 'mise_a_jour']
    if hasattr(objet, 'suppression_demandee'):
        objet.suppression_demandee = False  # la demande est exécutée ou annulée
        objet.suppression_demandee_par = None
        champs += ['suppression_demandee', 'suppression_demandee_par']
        objet.motif_suppression = motif if supprime else ''  # la restauration vide le motif (le journal le garde)
        champs.append('motif_suppression')
    objet.save(update_fields=champs)
    action = JournalAction.Action.SUPPRESSION if supprime else JournalAction.Action.RESTAURATION
    journaliser(auteur, action, objet, avant=avant, apres={'is_delete': bool(supprime)}, motif=motif)
    return objet


def rattacher(auteur, objet, champ, cible):
    """Rattache `objet` à `cible` par la clé étrangère `champ` ; journalise l'ancien et le nouveau rattachement.
    N'écrit que la colonne du rattachement (et la date de mise à jour si l'objet en a une)."""
    ancien = getattr(objet, champ)
    setattr(objet, champ, cible)
    champs = [champ] + (['mise_a_jour'] if any(f.name == 'mise_a_jour' for f in objet._meta.concrete_fields) else [])
    objet.save(update_fields=champs)
    journaliser(auteur, JournalAction.Action.RATTACHEMENT, objet,
                avant={champ: getattr(ancien, 'pk', None), f'{champ}_libelle': str(ancien) if ancien else None},
                apres={champ: getattr(cible, 'pk', None), f'{champ}_libelle': str(cible) if cible else None})
    return objet


ACTIONS_SUPPRESSION = ('demander', 'annuler', 'executer', 'restaurer')


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
    if action not in ACTIONS_SUPPRESSION:
        raise ValueError(f'Action de suppression inconnue : {action}')
    membre = Membre.objects.select_for_update().get(pk=membre.pk)
    droits = droits_membre(auteur, membre)
    if not droits['peut_demander_suppression']:
        raise PermissionDenied
    motif = (motif or '').strip()
    if len(motif) > MOTIF_MAX:
        return 'motif_trop_long'  # valable pour toutes les actions, annulation comprise

    if action == 'annuler':
        if not membre.suppression_demandee or membre.etat == 'supprime':
            raise EtatIncoherent('Aucune demande de suppression en cours.')
        if not droits['peut_annuler_demande_suppression']:
            raise PermissionDenied
        membre.suppression_demandee = False
        membre.suppression_demandee_par = None
        membre.save(update_fields=['suppression_demandee', 'suppression_demandee_par', 'mise_a_jour'])
        journaliser(auteur, JournalAction.Action.ANNULATION_DEMANDE_SUPPRESSION, membre,
                    avant={'suppression_demandee': True}, apres={'suppression_demandee': False}, motif=motif)
        return 'demande_annulee'

    if action == 'demander':
        if membre.etat == 'supprime' or membre.suppression_demandee:
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
        if membre.etat == 'supprime':
            raise EtatIncoherent('Membre déjà supprimé.')
        if not droits['peut_executer_suppression']:
            raise PermissionDenied
        if not motif:
            return 'motif_requis'
        transitions.supprimer(auteur, membre, motif)
        return 'supprime'
    # restaurer
    if membre.etat != 'supprime':
        raise EtatIncoherent("Le membre n'est pas supprimé.")
    if not droits['peut_restaurer']:
        raise PermissionDenied
    if not motif:
        return 'motif_requis'
    transitions.restaurer(auteur, membre, motif)
    return 'restaure'
