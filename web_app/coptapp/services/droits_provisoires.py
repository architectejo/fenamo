"""Droits provisoires sur les membres, déduits des privilèges hérités (privilege1 à privilege5).

TODO : remplacé par compte/services/droits.py au sous-lot 2e (rôles SU, PR, VN, VP, VA, AT, VI, ED et
périmètres national / coordination / antenne). Tant que ce module existe, il est le SEUL endroit qui lit
les privilèges hérités pour décider de ce qu'un compte voit ou fait sur un membre.

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
from django.db.models import Q

from coptapp.models import AssociationMembre, Membre


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
    membres = Membre.objects.all() if avec_supprimes else Membre.objects.filter(is_delete=False)
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
        filtre |= Q(is_validate1=True)
    if user.privilege3:
        filtre |= Q(is_validate1=True, is_validate2=True)
    if user.privilege4:
        filtre |= Q(is_validate3=True)
    return membres.filter(filtre)


def _associations_de(user):
    return AssociationMembre.objects.filter(users=user)


def droits_membre(user, membre=None):
    """Booléens de droits pour les gabarits (liste : `membre` absent, droit « en général » ; fiche : `membre` donné).

    Clés : peut_modifier, peut_valider, peut_demander_suppression, peut_attribuer_privileges, peut_gerer_famille,
    peut_gerer_engins, peut_voir_historique, plus peut_demander_modification (envoi d'une demande de modification).
    """
    nul = {
        'peut_modifier': False, 'peut_valider': False, 'peut_demander_suppression': False,
        'peut_attribuer_privileges': False, 'peut_gerer_famille': False, 'peut_gerer_engins': False,
        'peut_voir_historique': False, 'peut_demander_modification': False,
    }
    if not _actif(user):
        return nul
    su = user.is_superuser
    maitre = voit_tout(user)
    lecture_seule = est_visiteur(user)
    ecriture = not lecture_seule and (maitre or any((user.privilege1, user.privilege2, user.privilege3)))

    chez_lui = False  # le membre appartient à une association membre du compte
    if membre is not None and membre.structure_id:
        chez_lui = _associations_de(user).filter(pk=membre.structure_id).exists()

    peut_modifier = not lecture_seule and (maitre or (bool(user.privilege3) and (membre is None or chez_lui)))

    if lecture_seule:
        peut_valider = False
    else:
        if membre is None:
            peut_valider = maitre or bool(user.privilege2) or bool(user.privilege3)
        else:
            peut_valider = bool(
                (maitre and not membre.is_validate3)
                or (user.privilege2 and not membre.is_validate2)
                or (user.privilege3 and not membre.is_validate3)
            )

    return {
        'peut_modifier': peut_modifier,
        'peut_valider': peut_valider,
        'peut_demander_suppression': ecriture,
        # Réservé aux SU (correctif C1) : le privilege5 hérité ne suffit pas.
        'peut_attribuer_privileges': su,
        'peut_gerer_famille': ecriture and (maitre or membre is None or chez_lui),
        'peut_gerer_engins': ecriture,
        'peut_voir_historique': not lecture_seule and (maitre or bool(user.privilege2) or bool(user.privilege3)),
        'peut_demander_modification': su or bool(user.privilege1 and not lecture_seule),
    }


def etapes_a_valider(user, membre):
    """Drapeaux de validation que `user` pose sur `membre` (idempotent : jamais de retrait).

    Retourne la liste des noms de champs à mettre à True, vide si rien à faire ou si `user` ne peut pas valider.
    """
    if not droits_membre(user, membre)['peut_valider']:
        return []
    if voit_tout(user):
        return [c for c in ('is_validate1', 'is_validate2', 'is_validate3') if not getattr(membre, c)]
    etapes = []
    if user.privilege2 and not membre.is_validate2:
        etapes.append('is_validate2')
    if user.privilege3 and not membre.is_validate3:
        etapes.append('is_validate3')
    return etapes
