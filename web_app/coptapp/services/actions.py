"""Actions d'état sur les membres et les engins, avec écriture au journal d'activités (F-70)."""
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


def changer_suppression(auteur, objet, supprime, motif=''):
    """Suppression logique (ou annulation) d'un membre ou d'un engin ; journalisée. Exécution réservée à l'appelant
    (voir `traiter_suppression_membre`) : cette fonction ne contrôle aucun droit."""
    avant = {'is_delete': bool(objet.is_delete)}
    objet.is_delete = supprime
    if hasattr(objet, 'suppression_demandee'):
        objet.suppression_demandee = False  # la demande est exécutée ou annulée
    objet.save()
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


def traiter_suppression_membre(auteur, membre, motif=''):
    """Applique l'action de suppression adaptée au droit de `auteur` (F-25) et retourne le code du résultat.

    - SU / privilege5 (exécution) : membre non supprimé -> suppression logique, motif obligatoire ('supprime') ;
      membre supprimé -> annulation ('restaure') ;
    - autres (agent, validateurs) : pas de demande en cours -> demande de suppression, motif obligatoire ('demande') ;
      demande en cours -> annulation de la demande ('demande_annulee') ; membre déjà supprimé -> PermissionDenied.
    Retourne 'motif_requis' (sans rien changer) quand un motif manque. Toute action est journalisée.
    """
    from django.core.exceptions import PermissionDenied

    from coptapp.services.droits_provisoires import voit_tout
    motif = (motif or '').strip()
    if voit_tout(auteur):
        if membre.is_delete:
            changer_suppression(auteur, membre, False, motif)
            return 'restaure'
        if not motif:
            return 'motif_requis'
        membre.motif_suppression = motif
        changer_suppression(auteur, membre, True, motif)
        return 'supprime'
    if membre.is_delete:
        raise PermissionDenied
    if membre.suppression_demandee:
        avant = {'suppression_demandee': True}
        membre.suppression_demandee = False
        membre.save(update_fields=['suppression_demandee'])
        journaliser(auteur, JournalAction.Action.RESTAURATION, membre, avant=avant,
                    apres={'suppression_demandee': False}, motif=motif)
        return 'demande_annulee'
    if not motif:
        return 'motif_requis'
    membre.suppression_demandee = True
    membre.motif_suppression = motif
    membre.save(update_fields=['suppression_demandee', 'motif_suppression'])
    journaliser(auteur, JournalAction.Action.DEMANDE_SUPPRESSION, membre, avant={'suppression_demandee': False},
                apres={'suppression_demandee': True}, motif=motif)
    return 'demande'
