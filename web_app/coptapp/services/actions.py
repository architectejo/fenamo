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
    """Suppression logique (ou annulation) d'un membre ou d'un engin ; journalisée."""
    avant = {'is_delete': bool(objet.is_delete)}
    objet.is_delete = supprime
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
