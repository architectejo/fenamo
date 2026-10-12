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
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404

from coptapp.models import Antenne, AssociationMembre, Membre, Moto, Province, Ville


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
        'peut_creer_membre': False, 'peut_modifier': False, 'peut_valider': False, 'peut_demander_suppression': False,
        'peut_attribuer_privileges': False, 'peut_gerer_famille': False, 'peut_gerer_engins': False,
        'peut_voir_historique': False, 'peut_demander_modification': False,
    }
    if not _actif(user):
        return nul
    su = user.is_superuser
    maitre = voit_tout(user)
    lecture_seule = est_visiteur(user)
    ecriture = not lecture_seule and (maitre or any((user.privilege1, user.privilege2, user.privilege3)))

    saisie_perso = bool(membre is not None and user.privilege1 and membre.user_id == user.pk)
    chez_lui = False  # le membre appartient à une association membre du compte
    if membre is not None and membre.structure_id:
        chez_lui = _associations_de(user).filter(pk=membre.structure_id).exists()

    peut_modifier = not lecture_seule and (maitre or (bool(user.privilege3) and (membre is None or chez_lui)))

    if membre is None:
        peut_valider = not lecture_seule and (maitre or bool(user.privilege2) or bool(user.privilege3))
    else:
        peut_valider = bool(_etapes(user, membre))

    return {
        'peut_creer_membre': ecriture,
        'peut_modifier': peut_modifier,
        'peut_valider': peut_valider,
        'peut_demander_suppression': ecriture,
        # Réservé aux SU (correctif C1) : le privilege5 hérité ne suffit pas.
        'peut_attribuer_privileges': su,
        # F-26 : l'agent gère la famille de ses saisies comme leurs engins ; privilege2 et 3 dans leur association.
        'peut_gerer_famille': ecriture and (maitre or membre is None or chez_lui or saisie_perso),
        'peut_gerer_engins': ecriture and (maitre or membre is None or chez_lui or saisie_perso),
        'peut_voir_historique': not lecture_seule and (maitre or bool(user.privilege2) or bool(user.privilege3)),
        'peut_demander_modification': su or bool(user.privilege1 and not lecture_seule),
    }


def _etapes(user, membre):
    """Drapeaux que `user` peut poser sur `membre` maintenant (voir `etapes_a_valider`)."""
    if not _actif(user) or est_visiteur(user):
        return []
    if not user.is_superuser and (membre.pk == user.membreId or membre.user_id == user.pk):
        return []  # jamais sa propre fiche ni ses propres saisies (séparation des tâches)
    manquantes = [c for c in ('is_validate1', 'is_validate2', 'is_validate3') if not getattr(membre, c)]
    if voit_tout(user):
        return manquantes  # SU et privilege5 : plusieurs niveaux d'un coup, chacun reste tracé
    if not manquantes:
        return []
    suivante = manquantes[0]  # une seule étape à la fois, dans l'ordre : l'étape précédente est exigée
    if suivante == 'is_validate2' and user.privilege2:
        return [suivante]
    if suivante == 'is_validate3' and user.privilege3:
        return [suivante]
    return []


def etapes_a_valider(user, membre):
    """Drapeaux de validation que `user` pose sur `membre` (idempotent : jamais de retrait).

    Règles (M2) : l'étape précédente est exigée (privilege2 pose is_validate2 si is_validate1 ; privilege3 pose
    is_validate3 si is_validate2) et une seule étape par action ; SU et privilege5 posent toutes les étapes
    manquantes ; personne ne valide sa propre fiche (membreId) ni ses propres saisies (Membre.user), sauf le
    super-utilisateur (compte technique du prestataire) ; privilege4 (lecture seule) ne valide jamais.

    Correspondance héritée à confirmer : privilege2 -> is_validate2 est affiché « validé antenne »
    (etats.etat_de) ; privilege3 -> is_validate3 est l'état « actif ». Le circuit cible a une étape de plus
    (validé province) que les deux drapeaux hérités ne représentent pas : il viendra avec le champ d'état unique.
    """
    return _etapes(user, membre)


# ---------------------------------------------------------------- accès par identifiant (404 hors périmètre, 403 sans droit)

def membre_pour(user, id, droit=None, avec_supprimes=False):
    """Membre `id` visible par `user` (404 sinon) ; 403 si `droit` (clé de `droits_membre`) n'est pas accordé."""
    membre = get_object_or_404(membres_du_perimetre(user, avec_supprimes=avec_supprimes), id=id)
    if droit and not droits_membre(user, membre)[droit]:
        raise PermissionDenied
    return membre


def engins_visibles(user):
    """Engins non supprimés dont le propriétaire est visible par `user` (tous pour SU / privilege5)."""
    engins = Moto.objects.filter(is_delete=False)
    if voit_tout(user):
        return engins
    return engins.filter(proprietaire__in=membres_du_perimetre(user).values('pk'))


def engin_pour(user, id, droit=None):
    """Engin `id` visible par `user` (404 sinon) ; `droit` est contrôlé sur le propriétaire (403 sinon)."""
    moto = get_object_or_404(engins_visibles(user), id=id)
    if droit:
        proprietaire = moto.proprietaire
        if proprietaire is None or not droits_membre(user, proprietaire)[droit]:
            raise PermissionDenied
    return moto


def associations_du_compte(user):
    """Associations membres visibles : toutes pour SU / privilege5, celles du compte sinon (aucune si non connecté)."""
    if not _actif(user):
        return AssociationMembre.objects.none()
    if voit_tout(user):
        return AssociationMembre.objects.all()
    return AssociationMembre.objects.filter(users=user)


def _lieux_du_compte(user):
    """(ids de coordinations, de villes, d'antennes) liés au compte : ses associations et sa fiche membre."""
    provinces, villes, antennes = set(), set(), set()
    for a in associations_du_compte(user).prefetch_related('antenne_set'):
        provinces.add(a.province_id)
        villes.add(a.ville_id)
        antennes.update(x.pk for x in a.antenne_set.all())
    if user.membreId:
        fiche = Membre.objects.filter(pk=user.membreId).first()
        if fiche:
            provinces.add(fiche.province_id)
            villes.add(fiche.ville_id)
            antennes.add(fiche.antenne_id)
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
        return associations.filter(pk=cible.structure_id).exists() if cible.structure_id else False
    if champ == 'ville':
        return associations.filter(ville=cible).exists()
    return False
