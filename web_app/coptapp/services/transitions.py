"""Transitions du champ d'état unique des membres (cahier des charges § 4.4) : SEUL endroit qui écrit ``Membre.etat``.

Circuit : saisi -> valide_antenne (VA) -> valide_province (VP) -> actif (VN) ; le PR et le SU enchaînent toutes les étapes restantes.
Renvoi : le validateur recule le dossier d'UN cran (valide_province -> valide_antenne, valide_antenne -> saisi) ; l'état « renvoye »
est réservé au retour vers l'agent de terrain (depuis saisi, par le validateur d'antenne). Le motif reste affiché (``motif_renvoi``)
jusqu'à ce que le dossier avance de nouveau.

Chaque fonction : ``select_for_update`` sur la ligne du membre, droits relus via ``compte.services.droits``, UNE ligne de journal
par étape (auteur, date, objet, avant / après de ``etat``, motif). Les anciens booléens (is_delete, is_validate2, is_validate3,
renvoye) sont des miroirs recalculés par ``Membre.save`` : jamais écrits ici.
"""
from django.core.exceptions import PermissionDenied
from django.db import transaction

from compte.models import JournalAction
from compte.services.droits import droits_membre, etapes_a_valider, etats_de_depart, membres_du_perimetre
from compte.services.journal import journaliser
from coptapp.models import Membre, Notification

CIRCUIT = ('saisi', 'valide_antenne', 'valide_province', 'actif')
MOTIF_MAX = 500
PLAFOND_VALIDER_TOUS = 500
# Recul d'un cran lors d'un renvoi : seul « saisi -> renvoye » rend le dossier à l'agent de terrain.
RECUL = {'saisi': 'renvoye', 'valide_antenne': 'saisi', 'valide_province': 'valide_antenne'}


class EtatIncoherent(Exception):
    """L'action demandée ne correspond pas à l'état courant du membre (déjà supprimé, demande déjà faite…) : HTTP 409."""


def _verrouiller(membre):
    return Membre.objects.select_for_update().get(pk=membre.pk)


def _ecrire(membre, etat, precedent='', **champs):
    """Pose le nouvel état (et ses colonnes annexes) ; Membre.save recalcule les miroirs."""
    membre.etat = etat
    membre.etat_precedent = precedent
    for nom, valeur in champs.items():
        setattr(membre, nom, valeur)
    membre.save(update_fields=['etat', 'etat_precedent', 'mise_a_jour', *champs])


def etapes_possibles(auteur, membre):
    """États que `auteur` peut faire atteindre à `membre` par une validation maintenant (un seul pour VA, VP, VN ; tous les
    restants pour PR et SU). Liste vide : rien à valider (pas son tour, propre saisie, membre renvoyé, supprimé ou déjà actif)."""
    return etapes_a_valider(auteur, membre)


@transaction.atomic
def valider(auteur, membre):
    """Valide `membre` pour `auteur` (F-23) et retourne la liste des ÉTATS atteints (vide : rien à valider, rien n'est écrit).

    Idempotente : ne dévalide jamais. L'état est relu sous verrou ; chaque étape franchie écrit sa propre ligne de journal (VALIDATION,
    avant / après). Le motif de renvoi affiché est effacé dès que le dossier avance."""
    membre = _verrouiller(membre)
    etapes = etapes_possibles(auteur, membre)
    if not etapes:
        return []
    courant = membre.etat
    for etape in etapes:
        journaliser(auteur, JournalAction.Action.VALIDATION, membre, avant={'etat': courant}, apres={'etat': etape})
        courant = etape
    _ecrire(membre, courant, motif_renvoi='')
    return etapes


@transaction.atomic
def renvoyer(auteur, membre, motif):
    """Renvoie `membre` un cran en arrière avec un motif obligatoire (F-23) ; retourne 'renvoye', 'motif_requis' ou 'motif_trop_long'.

    Droit : celui de valider ce membre à son étape courante (``peut_renvoyer``), sinon PermissionDenied. Recul : valide_province ->
    valide_antenne, valide_antenne -> saisi, saisi -> renvoye (retour à l'agent de terrain). Journal RENVOI (avant / après / motif) ;
    l'auteur de la saisie est notifié."""
    membre = _verrouiller(membre)
    if not droits_membre(auteur, membre)['peut_renvoyer']:
        raise PermissionDenied
    motif = (motif or '').strip()
    if not motif:
        return 'motif_requis'
    if len(motif) > MOTIF_MAX:
        return 'motif_trop_long'
    cible = RECUL[membre.etat]
    journaliser(auteur, JournalAction.Action.RENVOI, membre, avant={'etat': membre.etat}, apres={'etat': cible}, motif=motif)
    _ecrire(membre, cible, motif_renvoi=motif)
    if membre.user_id:
        Notification.objects.create(user_id=membre.user_id, membre=membre, titre=f'Fiche renvoyée : {membre.nom or membre.idf}',
                                    description=motif)
    return 'renvoye'


@transaction.atomic
def reprendre(auteur, membre):
    """Remet un membre RENVOYÉ dans le circuit (saisi) quand son auteur reprend la fiche ; PermissionDenied sans droit de modifier,
    EtatIncoherent si le membre n'est pas renvoyé. Journalisé (MODIFICATION, avant / après)."""
    membre = _verrouiller(membre)
    if membre.etat != 'renvoye':
        raise EtatIncoherent("Le membre n'a pas été renvoyé.")
    if not droits_membre(auteur, membre)['peut_modifier']:
        raise PermissionDenied
    journaliser(auteur, JournalAction.Action.MODIFICATION, membre, avant={'etat': 'renvoye'}, apres={'etat': 'saisi'},
                motif='Fiche reprise après renvoi : remise dans le circuit.')
    _ecrire(membre, 'saisi', motif_renvoi='')
    return membre


@transaction.atomic
def supprimer(auteur, membre, motif):
    """Suppression logique (F-25) : l'état d'avant est gardé pour la restauration. Aucun contrôle de droit ici (voir
    ``actions.traiter_suppression_membre``). EtatIncoherent si déjà supprimé."""
    membre = _verrouiller(membre)
    if membre.etat == 'supprime':
        raise EtatIncoherent('Membre déjà supprimé.')
    journaliser(auteur, JournalAction.Action.SUPPRESSION, membre, avant={'etat': membre.etat}, apres={'etat': 'supprime'}, motif=motif)
    _ecrire(membre, 'supprime', precedent=membre.etat, suppression_demandee=False, suppression_demandee_par=None, motif_suppression=motif)
    return membre


@transaction.atomic
def restaurer(auteur, membre, motif):
    """Annule une suppression : le membre retrouve l'état d'avant la suppression (saisi si on ne le connaît pas). EtatIncoherent si le
    membre n'est pas supprimé."""
    membre = _verrouiller(membre)
    if membre.etat != 'supprime':
        raise EtatIncoherent("Le membre n'est pas supprimé.")
    retour = membre.etat_precedent if membre.etat_precedent in CIRCUIT + ('renvoye', 'a_renouveler') else 'saisi'
    journaliser(auteur, JournalAction.Action.RESTAURATION, membre, avant={'etat': 'supprime'}, apres={'etat': retour}, motif=motif)
    _ecrire(membre, retour, suppression_demandee=False, suppression_demandee_par=None, motif_suppression='')
    return membre


@transaction.atomic
def marquer_a_renouveler(auteur, membre, motif=''):
    """actif -> a_renouveler (identification annuelle échue). Pas encore produit automatiquement. Droit : modifier le membre."""
    membre = _verrouiller(membre)
    if membre.etat != 'actif':
        raise EtatIncoherent("Seul un membre actif peut être marqué « à renouveler ».")
    if not droits_membre(auteur, membre)['peut_modifier']:
        raise PermissionDenied
    journaliser(auteur, JournalAction.Action.MODIFICATION, membre, avant={'etat': 'actif'}, apres={'etat': 'a_renouveler'}, motif=motif)
    _ecrire(membre, 'a_renouveler')
    return membre


@transaction.atomic
def renouveler(auteur, membre, motif=''):
    """a_renouveler -> actif (identification renouvelée). Droit : modifier le membre."""
    membre = _verrouiller(membre)
    if membre.etat != 'a_renouveler':
        raise EtatIncoherent("Le membre n'est pas à renouveler.")
    if not droits_membre(auteur, membre)['peut_modifier']:
        raise PermissionDenied
    journaliser(auteur, JournalAction.Action.MODIFICATION, membre, avant={'etat': 'a_renouveler'}, apres={'etat': 'actif'}, motif=motif)
    _ecrire(membre, 'actif')
    return membre


# ---------------------------------------------------------------- « Valider tout le monde »

def _candidats(auteur, filtres):
    """Membres du périmètre (mêmes filtres que la liste) que `auteur` peut valider à l'étape courante, hors propres saisies sauf SU."""
    from coptapp.services.membres import membres_filtres, normaliser_filtres
    membres = membres_filtres(auteur, normaliser_filtres(filtres or {})).filter(etat__in=etats_de_depart(auteur))
    if not auteur.is_superuser:
        membres = membres.exclude(user=auteur)
        if auteur.membreId:
            membres = membres.exclude(pk=auteur.membreId)
    return membres


def compter_validables(auteur, filtres=None):
    """Nombre de membres que `valider_tous` validerait (modale de confirmation) : périmètre, filtres, étape de l'auteur."""
    if not droits_membre(auteur)['peut_valider_tous']:
        return 0
    return _candidats(auteur, filtres).count()


def valider_tous(auteur, filtres=None, plafond=PLAFOND_VALIDER_TOUS):
    """Valide, étape courante comprise, tous les membres du périmètre (et des filtres) que `auteur` a le droit de valider.

    PermissionDenied si l'auteur ne valide aucune étape. Jamais ses propres saisies ni sa propre fiche (sauf le SU), jamais hors de son
    périmètre. BORNÉ : au plus `plafond` (500) membres par appel, le reste est compté dans ``restants`` ; idempotent (relancer valide la
    suite, jamais deux fois le même membre). Chaque membre est validé par ``valider`` (verrou, droits relus, une ligne de journal par
    étape). Compte rendu : {'valides': nb de membres, 'etapes': nb d'étapes franchies, 'restants': membres non traités (plafond),
    'ignores': {raison: nombre}, 'plafond': plafond}."""
    if not droits_membre(auteur)['peut_valider_tous']:
        raise PermissionDenied
    ids = list(_candidats(auteur, filtres).order_by('pk').values_list('pk', flat=True)[:plafond + 1])
    restants = max(len(ids) - plafond, 0)
    if restants:
        restants = compter_validables(auteur, filtres) - plafond
        ids = ids[:plafond]
    compte_rendu = {'valides': 0, 'etapes': 0, 'restants': restants, 'ignores': {}, 'plafond': plafond}
    for pk in ids:
        membre = Membre.objects.filter(pk=pk).first()
        etapes = valider(auteur, membre) if membre is not None else []
        if etapes:
            compte_rendu['valides'] += 1
            compte_rendu['etapes'] += len(etapes)
        else:  # changé entre-temps (autre validateur, renvoi, suppression)
            compte_rendu['ignores']['etat_change'] = compte_rendu['ignores'].get('etat_change', 0) + 1
    ignores_propres = membres_du_perimetre(auteur).filter(etat__in=etats_de_depart(auteur))
    ignores_propres = ignores_propres.filter(user=auteur).count() if not auteur.is_superuser else 0
    if ignores_propres:
        compte_rendu['ignores']['propres_saisies'] = ignores_propres
    return compte_rendu
