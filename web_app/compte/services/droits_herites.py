"""Droits HÉRITÉS sur les membres, déduits des privilèges hérités (privilege1 à privilege5).

Corps de l'ancien ``coptapp/services/droits_provisoires.py``, déplacé ici au sous-lot 2e. ``compte/services/droits.py`` est le point
d'entrée : il applique les rôles (nominations) et ne renvoie à ce module que pour les comptes SANS nomination active tant que
``settings.FENAMO_DROITS_HERITES`` est vrai (et pour le super-utilisateur, dont le comportement est inchangé). Ce module est le SEUL
endroit qui lit les privilèges hérités pour décider de ce qu'un compte voit ou fait sur un membre.

Lecture des privilèges, d'après les libellés et conditions de l'écran hérité (membreListe, validate, gabarits
membre.html / _fiche_entete.html) :

- SU ou privilege5 : tout voir, tout modifier, valider à tous les niveaux ;
- privilege4 (visiteur) : lecture seule, uniquement les membres actifs (is_validate3) ; ce privilège PRIME sur
  les autres : aucun droit d'écriture même cumulé avec un autre privilège ;
- privilege3 : voit les membres validés aux deux premières étapes, valide l'étape finale, modifie les membres
  de SA association membre (condition `membre.structure == structure` du gabarit hérité) ;
- privilege2 : voit les membres de la première étape (is_validate1) et valide l'étape intermédiaire ;
- privilege1 (agent) : ne voit que SES saisies (Membre.user) et sa propre fiche ; n'envoie qu'une « demande de
  modification » (jamais de modification directe, d'après l'écran hérité) ;
- aucun privilège : sa propre fiche seulement.

Ambiguïtés, appliquées dans le sens le plus restrictif et à confirmer par la FENAMO : voir le rapport du lot.
"""
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from compte.models import JournalAction
from coptapp.models import CIRCUIT, Antenne, AssociationMembre, Membre, Province, Ville


def _actif(user):
    return bool(user is not None and user.is_authenticated and user.is_active)


def voit_tout(user):
    """SU ou privilege5 : aucun filtre de périmètre."""
    return _actif(user) and (user.is_superuser or bool(user.privilege5))


def est_visiteur(user):
    """Lecture seule (privilege4). Un super-utilisateur n'est jamais réduit à la lecture."""
    return _actif(user) and not user.is_superuser and bool(user.privilege4)


def membres_du_perimetre(user, avec_supprimes=False):
    """Membres visibles par `user` : seul point d'entrée des listes, des fiches et des compteurs.

    Par défaut les membres supprimés logiquement sont exclus ; `avec_supprimes=True` les inclut (fiche d'un
    membre dont la suppression est demandée, pour l'annuler). Sans droit : queryset vide (jamais « tout »).
    """
    membres = Membre.objects.all() if avec_supprimes else Membre.objects.exclude(etat='supprime')
    if not _actif(user):
        return membres.none()
    if voit_tout(user):
        return membres
    filtre = Q(pk__in=[])  # Q vide : rien
    if user.membreId:
        filtre |= Q(pk=user.membreId)  # sa propre fiche
    if user.privilege1:
        filtre |= Q(user=user)  # ses saisies
    if user.privilege2:
        filtre |= ~Q(etat='supprime')  # tous les dossiers : il valide l'étape d'antenne
    if user.privilege3:
        filtre |= Q(etat__in=('valide_antenne', 'valide_province', 'actif', 'a_renouveler'))
    if user.privilege4:
        filtre |= Q(etat='actif')  # comme le visiteur du rôle VI : seulement les membres actifs
    return membres.filter(filtre)


def _associations_de(user):
    return AssociationMembre.objects.filter(users=user)


def droits_membre(user, membre=None):
    """Booléens de droits pour les gabarits (liste : `membre` absent, droit « en général » ; fiche : `membre` donné).

    Clés : peut_creer_membre, peut_modifier, peut_valider, peut_demander_suppression, peut_attribuer_privileges
    (SU seulement), peut_voir_historique, peut_demander_modification (demande à un validateur) ;
    ajout : peut_ajouter_engin, peut_ajouter_famille ; modification et suppression des engins et de la famille
    (F-35, F-26 : agent seul avant la 1re validation) : peut_modifier_engin, peut_supprimer_engin,
    peut_modifier_famille, peut_supprimer_famille ; suppression du membre (F-25) : peut_executer_suppression,
    peut_restaurer, peut_annuler_demande_suppression (ces deux dernières exigent un `membre`).
    """
    nul = {
        'peut_creer_membre': False, 'peut_modifier': False, 'peut_valider': False, 'peut_demander_suppression': False,
        'peut_attribuer_privileges': False, 'peut_ajouter_famille': False, 'peut_ajouter_engin': False,
        'peut_voir_historique': False, 'peut_demander_modification': False,
        'peut_modifier_engin': False, 'peut_supprimer_engin': False, 'peut_modifier_famille': False,
        'peut_supprimer_famille': False, 'peut_executer_suppression': False, 'peut_restaurer': False,
        'peut_annuler_demande_suppression': False, 'peut_renvoyer': False, 'peut_voir_pieces': False,
        'peut_definir_mot_de_passe_mobile': False,
        'peut_valider_tous': False,
    }
    if not _actif(user):
        return nul
    su = user.is_superuser
    maitre = voit_tout(user)
    lecture_seule = est_visiteur(user)
    ecriture = not lecture_seule and (maitre or any((user.privilege1, user.privilege2, user.privilege3)))

    supprime = membre is not None and membre.etat == 'supprime'  # un membre supprimé n'est plus modifiable : seule la restauration reste
    saisie_perso = bool(membre is not None and user.privilege1 and membre.user_id == user.pk)
    chez_lui = False  # le membre appartient à une association membre du compte
    if membre is not None and membre.structure_id:
        chez_lui = _associations_de(user).filter(pk=membre.structure_id).exists()

    peut_modifier = not lecture_seule and not supprime and (maitre or (bool(user.privilege3) and (membre is None or chez_lui)))

    if membre is None:
        peut_valider = not lecture_seule and (maitre or bool(user.privilege2) or bool(user.privilege3))
    else:
        peut_valider = bool(_etapes(user, membre))

    gerer = ecriture and not supprime and (maitre or membre is None or chez_lui or saisie_perso)
    # F-35 / F-26 « AT avant V1, ensuite rôles supérieurs » : un agent seul (privilege1 sans privilege2, 3 ni 5) modifie
    # et supprime engins et famille tant que le propriétaire n'a pas passé la 1re validation (is_validate2). L'engin n'a
    # pas de drapeau de validation : l'état du propriétaire en tient lieu (limite à lever avec le champ d'état unique).
    agent_seul = bool(user.privilege1) and not (maitre or user.privilege2 or user.privilege3)
    avant_v1 = membre is None or membre.etat in ('saisi', 'renvoye')
    gerer_apres_saisie = gerer and (not agent_seul or avant_v1)
    executer = maitre and ecriture
    return {
        'peut_modifier_engin': gerer_apres_saisie,
        'peut_supprimer_engin': gerer_apres_saisie,
        'peut_modifier_famille': gerer_apres_saisie,
        'peut_supprimer_famille': gerer_apres_saisie,
        'peut_executer_suppression': executer,
        'peut_restaurer': bool(executer and membre is not None and membre.etat == 'supprime'),
        'peut_annuler_demande_suppression': bool(
            ecriture and membre is not None and membre.suppression_demandee and membre.etat != 'supprime'
            and (executer or membre.suppression_demandee_par_id == user.pk)),
        'peut_creer_membre': ecriture,
        'peut_voir_pieces': ecriture,  # inchangé pour les droits hérités : mêmes conditions que la création
        'peut_definir_mot_de_passe_mobile': ecriture,
        'peut_modifier': peut_modifier,
        'peut_valider': peut_valider,
        'peut_valider_tous': not lecture_seule and maitre,  # SU et privilege5 seulement : jamais privilege2 ou privilege3
        'peut_renvoyer': peut_valider,  # renvoyer = refuser à son niveau : mêmes conditions que valider
        'peut_demander_suppression': ecriture,
        # Réservé aux SU (correctif C1) : le privilege5 hérité ne suffit pas.
        'peut_attribuer_privileges': su,
        # F-26 : l'agent gère la famille de ses saisies comme leurs engins ; privilege2 et 3 dans leur association.
        'peut_ajouter_famille': gerer,
        'peut_ajouter_engin': gerer,
        'peut_voir_historique': not lecture_seule and (maitre or bool(user.privilege2) or bool(user.privilege3)),
        'peut_demander_modification': not supprime and (su or bool(user.privilege1 and not lecture_seule)),
    }


def _a_deja_valide(user, membre):
    """Vrai si `user` a déjà validé une étape de ce dossier (lecture du journal des validations)."""
    return JournalAction.objects.filter(
        action=JournalAction.Action.VALIDATION, auteur=user, objet_id=membre.pk,
        objet_type=ContentType.objects.get_for_model(Membre, for_concrete_model=False),
    ).exists()


def _etapes(user, membre):
    """États que `user` peut faire atteindre à `membre` maintenant (voir `etapes_a_valider`)."""
    if not _actif(user) or est_visiteur(user) or membre.etat not in CIRCUIT[:-1]:
        return []  # supprimé, renvoyé (attend sa reprise par l'auteur de la saisie), déjà actif ou à renouveler
    if not user.is_superuser and (membre.pk == user.membreId or membre.user_id == user.pk):
        return []  # jamais sa propre fiche ni ses propres saisies (séparation des tâches)
    reste = list(CIRCUIT[CIRCUIT.index(membre.etat) + 1:])
    if voit_tout(user):
        return reste  # SU et privilege5 : plusieurs niveaux d'un coup, chacun reste tracé
    if user.privilege2 and user.privilege3 and _a_deja_valide(user, membre):
        return []  # cumul des privilèges 2 et 3 : jamais V2 puis V3 sur le même dossier (réservé à privilege5 et SU)
    if membre.etat == 'saisi' and user.privilege2:
        return ['valide_antenne']
    if membre.etat in ('valide_antenne', 'valide_province') and user.privilege3:
        return ['actif']  # privilege3 : étape nationale seule (l'héritage n'a pas d'étape « province »)
    return []


def etats_de_depart(user):
    """États dans lesquels `user` valide un membre (réduit les candidats de « Valider tout le monde » avant le contrôle membre par membre)."""
    if not _actif(user) or est_visiteur(user):
        return []
    if voit_tout(user):
        return list(CIRCUIT[:-1])
    return [e for e, ok in (('saisi', user.privilege2), ('valide_antenne', user.privilege3), ('valide_province', user.privilege3)) if ok]


def etapes_a_valider(user, membre):
    """États que `user` fait atteindre à `membre` par une validation (liste vide : rien à valider).

    Règles (M2) : un compte qui cumule privilege2 et privilege3 ne valide qu'UNE étape par dossier (jamais V2 puis V3 :
    plusieurs niveaux sont réservés à privilege5 et SU) ; l'étape précédente est exigée (privilege2 pose is_validate2 si is_validate1 ; privilege3 pose
    is_validate3 si is_validate2) et une seule étape par action ; SU et privilege5 posent toutes les étapes
    manquantes ; personne ne valide sa propre fiche (membreId) ni ses propres saisies (Membre.user), sauf le
    super-utilisateur (compte technique du prestataire) ; privilege4 (lecture seule) ne valide jamais.

    Correspondance héritée à confirmer : privilege2 -> is_validate2 est affiché « validé antenne »
    (etats.etat_de) ; privilege3 -> is_validate3 est l'état « actif ». Le circuit cible a une étape de plus
    (validé province) que les deux drapeaux hérités ne représentent pas : il viendra avec le champ d'état unique.
    """
    return _etapes(user, membre)


def associations_du_compte(user):
    """Associations membres visibles : toutes pour SU / privilege5, celles du compte sinon (aucune si non connecté)."""
    if not _actif(user):
        return AssociationMembre.objects.none()
    if voit_tout(user):
        return AssociationMembre.objects.all()
    return AssociationMembre.objects.filter(users=user)


def _lieux_du_compte(user):
    """(ids de coordinations, de villes, d'antennes) liés au compte : ses associations et sa fiche membre.

    Tient compte des antennes issues des villes héritées (``Antenne.ville_origine``) et de ``AssociationMembre.antenne`` : une
    ville du compte donne son antenne, une antenne du compte donne sa ville d'origine et sa coordination.
    """
    provinces, villes, antennes = set(), set(), set()
    for a in associations_du_compte(user).prefetch_related('antennes_heritees'):
        provinces.add(a.province_id)
        villes.add(a.ville_id)
        antennes.add(a.antenne_id)
        antennes.update(x.pk for x in a.antennes_heritees.all())
    if user.membreId:
        fiche = Membre.objects.filter(pk=user.membreId).first()
        if fiche:
            provinces.add(fiche.province_id)
            villes.add(fiche.ville_id)
            antennes.add(fiche.antenne_id)
    villes.discard(None)
    antennes.discard(None)
    antennes.update(Antenne.objects.filter(ville_origine_id__in=villes).values_list('pk', flat=True))
    for ville_id, coordination_id in Antenne.objects.filter(pk__in=antennes).values_list('ville_origine_id', 'coordination_id'):
        villes.add(ville_id)
        provinces.add(coordination_id)
    return provinces - {None}, villes - {None}, antennes - {None}


def provinces_du_perimetre(user):
    """Coordinations visibles : toutes pour SU / privilege5, celles du compte (associations, fiche) sinon."""
    if not _actif(user):
        return Province.objects.none()
    if voit_tout(user):
        return Province.objects.all()
    return Province.objects.filter(pk__in=_lieux_du_compte(user)[0])


def villes_du_perimetre(user):
    if not _actif(user):
        return Ville.objects.none()
    if voit_tout(user):
        return Ville.objects.all()
    return Ville.objects.filter(pk__in=_lieux_du_compte(user)[1])


def antennes_du_perimetre(user):
    if not _actif(user):
        return Antenne.objects.none()
    if voit_tout(user):
        return Antenne.objects.all()
    return Antenne.objects.filter(pk__in=_lieux_du_compte(user)[2])


def cible_rattachable(user, champ, cible):
    """Vrai si `user` peut rattacher un membre à `cible` (champ : 'structure', 'antenne' ou 'ville').

    SU / privilege5 : toute cible. Autres : seulement leurs associations, les antennes de celles-ci et leur ville
    (ferme l'escalade « privilege3 rattache un membre à une association qui n'est pas la sienne »).
    """
    if cible is None or not _actif(user) or est_visiteur(user):
        return False
    if voit_tout(user):
        return True
    associations = AssociationMembre.objects.filter(users=user)
    if champ == 'structure':
        return associations.filter(pk=cible.pk).exists()
    if champ == 'antenne':
        # l'ancienne antenne d'une association du compte, l'antenne choisie par une association, ou l'antenne issue de sa ville
        return (bool(cible.structure_id) and associations.filter(pk=cible.structure_id).exists()
                or associations.filter(antenne=cible).exists() or associations.filter(ville__antenne_issue=cible).exists())
    if champ == 'ville':
        return associations.filter(ville=cible).exists() or associations.filter(antenne__ville_origine=cible).exists()
    return False
