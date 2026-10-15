"""Transitions du champ d'état unique des membres (cahier des charges § 4.4) : SEUL endroit qui écrit ``Membre.etat``.

Circuit : saisi -> valide_antenne (VA) -> valide_province (VP) -> actif (VN) ; le PR et le SU enchaînent toutes les étapes restantes.
Renvoi : le validateur recule le dossier d'UN cran (valide_province -> valide_antenne, valide_antenne -> saisi) ; l'état « renvoye »
est réservé au retour vers l'agent de terrain (depuis saisi, par le validateur d'antenne). Le motif reste affiché (``motif_renvoi``)
jusqu'à ce que le dossier avance de nouveau.

Chaque fonction : ``select_for_update`` sur la ligne du membre, droits relus via ``compte.services.droits``, UNE ligne de journal
par étape (auteur, date, objet, avant / après de ``etat``, motif). Les anciens booléens (is_delete, is_validate2, is_validate3,
renvoye) sont des miroirs recalculés par ``Membre.save`` : jamais écrits ici.
"""
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext as _

from compte.models import JournalAction, Nomination
from compte.services.droits import droits_membre, etapes_a_valider, etats_de_depart
from compte.services.journal import journaliser
from coptapp.models import CIRCUIT, Membre, Notification

MOTIF_MAX = 500
PLAFOND_PAR_DEFAUT = 100  # « Valider tout le monde » : membres par appel (réglage VALIDER_TOUS_PLAFOND)
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


@transaction.atomic
def valider(auteur, membre):
    """Valide `membre` pour `auteur` (F-23) et retourne la liste des ÉTATS atteints (vide : rien à valider, rien n'est écrit).

    Idempotente : ne dévalide jamais. L'état est relu sous verrou ; chaque étape franchie écrit sa propre ligne de journal (VALIDATION,
    avant / après). Le motif de renvoi affiché est effacé dès que le dossier avance."""
    membre = _verrouiller(membre)
    etapes = etapes_a_valider(auteur, membre)
    if not etapes:
        return []
    courant = membre.etat
    for etape in etapes:
        journaliser(auteur, JournalAction.Action.VALIDATION, membre, avant={'etat': courant}, apres={'etat': etape})
        courant = etape
    _ecrire(membre, courant, motif_renvoi='')
    return etapes


def _destinataires_du_renvoi(membre, cible):
    """Comptes prévenus d'un renvoi, selon le niveau où le dossier retourne : « renvoye » -> l'auteur de la saisie ; « saisi » (renvoi
    par le VP) -> les VA de l'antenne du membre ; « valide_antenne » (renvoi par le VN) -> les VP de sa coordination. À défaut de
    destinataire à ce niveau, l'auteur de la saisie est prévenu (personne ne reste sans nouvelle)."""
    if cible == 'saisi' and membre.antenne_id:
        filtre = {'role': 'VA', 'antenne_id': membre.antenne_id}
    elif cible == 'valide_antenne':
        coordination = membre.antenne.coordination_id if membre.antenne_id else None
        coordination = coordination or membre.province_id
        filtre = {'role': 'VP', 'coordination_id': coordination} if coordination else None
    else:
        filtre = None
    ids = []
    if filtre:
        ids = list(Nomination.objects.filter(active=True, compte__is_active=True, **filtre).values_list('compte_id', flat=True).distinct())
    if not ids and membre.user_id:
        ids = [membre.user_id]
    return ids


@transaction.atomic
def renvoyer(auteur, membre, motif):
    """Renvoie `membre` un cran en arrière avec un motif obligatoire (F-23) ; retourne 'renvoye', 'motif_requis' ou 'motif_trop_long'.

    Droit : celui de valider ce membre à son étape courante (``peut_renvoyer``), sinon PermissionDenied. Recul : valide_province ->
    valide_antenne, valide_antenne -> saisi, saisi -> renvoye (retour à l'agent de terrain). Journal RENVOI (avant / après / motif) ;
    les comptes du niveau destinataire sont notifiés (``_destinataires_du_renvoi``)."""
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
    titre = _("Fiche renvoyée : %(nom)s") % {'nom': membre.nom or membre.idf or membre.pk}
    for destinataire_id in _destinataires_du_renvoi(membre, cible):
        Notification.objects.create(user_id=destinataire_id, membre=membre, titre=titre, description=motif)
    return 'renvoye'


@transaction.atomic
def reprendre(auteur, membre):
    """Remet un membre RENVOYÉ dans le circuit (saisi) quand l'AUTEUR DE LA SAISIE (ou le SU) reprend la fiche ; PermissionDenied pour
    tout autre compte ou sans droit de modifier, EtatIncoherent si le membre n'est pas renvoyé. Journalisé (MODIFICATION, avant / après)."""
    membre = _verrouiller(membre)
    if membre.etat != 'renvoye':
        raise EtatIncoherent("Le membre n'a pas été renvoyé.")
    if not (auteur.is_superuser or membre.user_id == auteur.pk) or not droits_membre(auteur, membre)['peut_modifier']:
        raise PermissionDenied
    journaliser(auteur, JournalAction.Action.MODIFICATION, membre, avant={'etat': 'renvoye'}, apres={'etat': 'saisi'},
                motif='Fiche reprise après renvoi : remise dans le circuit.')
    _ecrire(membre, 'saisi', motif_renvoi='')
    return membre


@transaction.atomic
def supprimer(auteur, membre, motif):
    """Suppression logique (F-25) : l'état d'avant est gardé pour la restauration. Droit : exécuter les suppressions
    (``peut_executer_suppression``), PermissionDenied sinon ; EtatIncoherent si déjà supprimé."""
    membre = _verrouiller(membre)
    if membre.etat == 'supprime':
        raise EtatIncoherent('Membre déjà supprimé.')
    if not droits_membre(auteur, membre)['peut_executer_suppression']:
        raise PermissionDenied
    journaliser(auteur, JournalAction.Action.SUPPRESSION, membre, avant={'etat': membre.etat}, apres={'etat': 'supprime'}, motif=motif)
    _ecrire(membre, 'supprime', precedent=membre.etat, suppression_demandee=False, suppression_demandee_par=None, motif_suppression=motif)
    return membre


@transaction.atomic
def restaurer(auteur, membre, motif):
    """Annule une suppression : le membre retrouve l'état d'avant la suppression (saisi si on ne le connaît pas). Droit :
    ``peut_restaurer``, PermissionDenied sinon ; EtatIncoherent si le membre n'est pas supprimé."""
    membre = _verrouiller(membre)
    if membre.etat != 'supprime':
        raise EtatIncoherent("Le membre n'est pas supprimé.")
    if not droits_membre(auteur, membre)['peut_restaurer']:
        raise PermissionDenied
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

def _a_l_etape(auteur, filtres):
    """Membres du périmètre, avec les filtres de la liste, qui sont à une étape que `auteur` valide (propres saisies comprises)."""
    from coptapp.services.membres import membres_filtres, normaliser_filtres
    return membres_filtres(auteur, normaliser_filtres(filtres or {})).filter(etat__in=etats_de_depart(auteur))


def _candidats_propres(auteur, filtres):
    """Parmi ces membres, ses propres saisies et sa propre fiche (ignorées, sauf pour le SU) : MÊMES filtres que les candidats."""
    propres = Q(user=auteur)
    if auteur.membreId:
        propres |= Q(pk=auteur.membreId)
    return _a_l_etape(auteur, filtres).filter(propres)


def _candidats(auteur, filtres):
    """Membres que `auteur` peut valider à l'étape courante, hors propres saisies sauf SU."""
    membres = _a_l_etape(auteur, filtres)
    if not auteur.is_superuser:
        membres = membres.exclude(pk__in=_candidats_propres(auteur, filtres).values('pk'))
    return membres


def compter_validables(auteur, filtres=None):
    """Nombre de membres que `valider_tous` validerait (modale de confirmation) : périmètre, filtres, étape de l'auteur."""
    if not droits_membre(auteur)['peut_valider_tous']:
        return 0
    return _candidats(auteur, filtres).count()


def plafond_valider_tous():
    """Membres validés au plus par appel de « Valider tout le monde » (réglage VALIDER_TOUS_PLAFOND, 100 par défaut)."""
    return max(int(getattr(settings, 'VALIDER_TOUS_PLAFOND', PLAFOND_PAR_DEFAUT)), 1)


def valider_tous(auteur, filtres=None, plafond=None):
    """Valide, étape courante comprise, tous les membres du périmètre (et des filtres) que `auteur` a le droit de valider.

    Fonction EXPLICITEMENT demandée par la FENAMO (voir docs/valider-tout-le-monde.md). PermissionDenied si l'auteur n'a pas le droit
    (``peut_valider_tous``). Jamais ses propres saisies ni sa propre fiche (sauf le SU), jamais hors de son périmètre. BORNÉ : au plus
    `plafond` membres par appel (réglage ``VALIDER_TOUS_PLAFOND``, 100 par défaut), le reste est compté dans ``restants`` ; idempotent
    (relancer valide la suite, jamais deux fois le même membre). Chaque membre est validé par ``valider`` (verrou, droits relus, une
    ligne de journal par étape). Compte rendu : {'valides': nb de membres, 'etapes': nb d'étapes franchies, 'restants': membres non
    traités (plafond), 'ignores': {raison: nombre}, 'plafond': plafond}."""
    if not droits_membre(auteur)['peut_valider_tous']:
        raise PermissionDenied
    plafond = plafond or plafond_valider_tous()
    candidats = _candidats(auteur, filtres)
    ids = list(candidats.order_by('pk').values_list('pk', flat=True)[:plafond + 1])
    restants = 0
    if len(ids) > plafond:
        restants = candidats.count() - plafond
        ids = ids[:plafond]
    compte_rendu = {'valides': 0, 'etapes': 0, 'restants': restants, 'ignores': {}, 'plafond': plafond}
    for membre in Membre.objects.select_related('antenne').filter(pk__in=ids).order_by('pk'):
        etapes = valider(auteur, membre)
        if etapes:
            compte_rendu['valides'] += 1
            compte_rendu['etapes'] += len(etapes)
        else:  # changé entre-temps (autre validateur, renvoi, suppression)
            compte_rendu['ignores']['etat_change'] = compte_rendu['ignores'].get('etat_change', 0) + 1
    propres = _candidats_propres(auteur, filtres).count() if not auteur.is_superuser else 0
    if propres:
        compte_rendu['ignores']['propres_saisies'] = propres
    return compte_rendu
