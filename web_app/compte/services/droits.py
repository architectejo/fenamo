"""Droits des comptes selon leur RÔLE (cahier des charges web § 4) : point d'entrée unique des droits sur les membres, les engins,
les associations membres et la géographie.

Interface identique à l'ancien ``droits_provisoires`` : mêmes fonctions et mêmes 16 clés ``peut_*`` de ``droits_membre``.

PROFIL EFFECTIF d'un compte (``profil_de``) :
1. ``is_superuser`` : rôle SU (comportement inchangé, il garde l'exception de valider ses propres saisies) ;
2. sinon, sa NOMINATION ACTIVE (``compte.Nomination``, ``active`` vrai, début atteint). Une nomination ÉCHUE reste valable tant
   qu'elle n'est pas terminée à la main : la fin de mandat déclenche une alerte, jamais une coupure ;
3. sinon, si ``settings.FENAMO_DROITS_HERITES`` : droits hérités (privilege1 à privilege5, ``droits_herites``) ;
4. sinon : uniquement sa propre fiche, en lecture.
Aucune nomination n'est créée automatiquement. Un compte n'a qu'une nomination active.

RÈGLES DE RÔLE (matrice du § 4.3), pour un compte avec nomination :
- PR, VN : national, tout voir ; PR modifie, valide à tous les niveaux d'un coup, exécute les suppressions ; VN modifie, pose la
  3e validation, exécute les suppressions ;
- VP : sa coordination ; modifie, demande les suppressions ; son étape de validation (province) n'est PAS représentable avec les
  booléens hérités (``is_validate1..3``) : voir ``ETAPES_PAR_ROLE`` et ``_etapes_role``, point d'extension du futur champ d'état
  unique ; en attendant le VP ne pose aucune étape ;
- VA : son antenne ; modifie, pose ``is_validate2`` (1re validation) ; AT : ses PROPRES saisies, les modifie seulement tant que la
  1re validation n'a pas eu lieu, puis ne peut que demander une modification ;
- VI : lecture seule des membres ACTIFS (``is_validate3``) de son périmètre (national, coordination ou antenne), jamais les pièces ;
- ED : contenu du site seulement, aucun membre (sa propre fiche mise à part) ;
- personne (sauf le SU) ne valide sa propre fiche ni ses propres saisies ; l'attribution des privilèges reste réservée au SU.
"""
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone

from compte import roles
from compte.models import Nomination
from compte.services import droits_herites as herites
from coptapp.models import Antenne, AssociationMembre, Membre, Moto, Province, Ville

CLES_DROITS = (
    'peut_creer_membre', 'peut_modifier', 'peut_valider', 'peut_demander_suppression', 'peut_attribuer_privileges',
    'peut_voir_historique', 'peut_demander_modification', 'peut_ajouter_engin', 'peut_ajouter_famille',
    'peut_modifier_engin', 'peut_supprimer_engin', 'peut_modifier_famille', 'peut_supprimer_famille',
    'peut_executer_suppression', 'peut_restaurer', 'peut_annuler_demande_suppression',
)

# Drapeaux de validation posés par chaque rôle, dans l'ordre du circuit (§ 4.4). POINT D'EXTENSION : quand le champ d'état unique
# (saisi, valide_antenne, valide_province, actif…) remplacera les booléens, le VP y posera l'étape « province » ; aujourd'hui
# elle n'existe pas dans les booléens hérités (is_validate2 = « validé antenne », is_validate3 = « actif »).
ETAPES_PAR_ROLE = {roles.VA: 'is_validate2', roles.VP: None, roles.VN: 'is_validate3'}
ROLES_ECRITURE = (roles.AT, roles.VA, roles.VP, roles.VN, roles.PR)
ROLES_VOIENT_HISTORIQUE = (roles.VA, roles.VP, roles.VN, roles.PR)
ROLES_EXECUTENT_SUPPRESSION = (roles.VN, roles.PR)


# ---------------------------------------------------------------- profil effectif

@dataclass(frozen=True)
class Profil:
    """mode : 'su', 'nomination', 'herite', 'fiche' (propre fiche seulement) ou 'aucun' (compte inactif ou anonyme)."""
    mode: str
    role: str = ''
    nomination: object = None


def _actif(user):
    return bool(user is not None and user.is_authenticated and user.is_active)


def profil_de(user, aujourdhui=None):
    """Profil effectif de `user`, mémorisé sur l'objet pour la durée de la requête (``nominations.oublier_profil`` l'efface)."""
    if not _actif(user):
        return Profil('aucun')
    jour = aujourdhui or timezone.localdate()
    memo = getattr(user, '_fenamo_profil', None)
    if memo is not None and memo[0] == jour:
        return memo[1]
    if user.is_superuser:
        profil = Profil('su', roles.SU)
    else:
        nomination = (Nomination.objects.filter(compte=user, active=True, debut__lte=jour)
                      .select_related('coordination', 'antenne', 'association').order_by('-debut', '-id').first())
        if nomination is not None:
            profil = Profil('nomination', nomination.role, nomination)
        elif getattr(settings, 'FENAMO_DROITS_HERITES', True):
            profil = Profil('herite')
        else:
            profil = Profil('fiche')
    user._fenamo_profil = (jour, profil)
    return profil


def role_de(user):
    """Code du rôle effectif (SU, PR…), ou '' pour un compte sans nomination (droits hérités ou propre fiche)."""
    return profil_de(user).role


def _herite(profil):
    return profil.mode in ('su', 'herite')


def _role(profil):
    return profil.role if profil.mode == 'nomination' else ''


# ---------------------------------------------------------------- portée d'un rôle sur les membres

def _q_antenne(antenne):
    """Membres d'une antenne : rattachés à elle, ou à la ville héritée dont elle est issue."""
    q = Q(antenne_id=antenne.pk)
    if antenne.ville_origine_id:
        q |= Q(ville_id=antenne.ville_origine_id)
    return q


def _q_coordination(coordination_id):
    return Q(province_id=coordination_id) | Q(antenne__coordination_id=coordination_id)


def _q_portee(user, nomination):
    """Filtre (Q) des membres que `nomination` donne le droit de lire / gérer, SANS la propre fiche (ajoutée à part)."""
    role = nomination.role
    if role in (roles.PR, roles.VN):
        return Q()
    if role == roles.VP:
        return _q_coordination(nomination.coordination_id)
    if role == roles.VA:
        return _q_antenne(nomination.antenne)
    if role == roles.AT:
        return Q(user=user)
    if role == roles.VI:
        if nomination.coordination_id:
            portee = _q_coordination(nomination.coordination_id)
        elif nomination.antenne_id:
            portee = _q_antenne(nomination.antenne)
        else:
            portee = Q()
        return portee & Q(is_validate3=True)  # le visiteur ne voit que les membres ACTIFS
    return Q(pk__in=[])  # ED : aucun membre


def _dans_portee(user, nomination, membre):
    """Même règle que ``_q_portee``, évaluée en mémoire sur un membre déjà chargé (sans requête)."""
    role = nomination.role
    if role in (roles.PR, roles.VN):
        return True
    if role == roles.AT:
        return membre.user_id == user.pk
    if role == roles.ED:
        return False

    def dans_antenne(antenne):
        return membre.antenne_id == antenne.pk or bool(antenne.ville_origine_id and membre.ville_id == antenne.ville_origine_id)

    def dans_coordination(coordination_id):
        return membre.province_id == coordination_id or (
            membre.antenne_id is not None and Antenne.objects.filter(pk=membre.antenne_id, coordination_id=coordination_id).exists())

    if role == roles.VP:
        return dans_coordination(nomination.coordination_id)
    if role == roles.VA:
        return dans_antenne(nomination.antenne)
    if role == roles.VI:
        if nomination.coordination_id:
            portee = dans_coordination(nomination.coordination_id)
        elif nomination.antenne_id:
            portee = dans_antenne(nomination.antenne)
        else:
            portee = True
        return portee and bool(membre.is_validate3)
    return False


# ---------------------------------------------------------------- périmètre : membres

def voit_tout(user):
    """Aucun filtre de périmètre : SU (et privilege5 hérité) ; avec nomination, PR et VN (national)."""
    profil = profil_de(user)
    if _herite(profil):
        return herites.voit_tout(user)
    return _role(profil) in (roles.PR, roles.VN)


def est_visiteur(user):
    """Lecture seule : rôle VI (ou privilege4 hérité)."""
    profil = profil_de(user)
    if _herite(profil):
        return herites.est_visiteur(user)
    return _role(profil) == roles.VI


def membres_du_perimetre(user, avec_supprimes=False):
    """Membres visibles par `user` : seul point d'entrée des listes, des fiches et des compteurs (jamais « tout » sans droit)."""
    profil = profil_de(user)
    if _herite(profil):
        return herites.membres_du_perimetre(user, avec_supprimes)
    membres = Membre.objects.all() if avec_supprimes else Membre.objects.filter(is_delete=False)
    if profil.mode == 'aucun':
        return membres.none()
    if profil.mode == 'nomination' and profil.role in (roles.PR, roles.VN):
        return membres  # national : aucun filtre (un Q() vide ajouté par « | » serait ignoré, d'où ce cas à part)
    filtre = Q(pk=user.membreId) if user.membreId else Q(pk__in=[])  # sa propre fiche
    if profil.mode == 'nomination':
        filtre |= _q_portee(user, profil.nomination)
    return membres.filter(filtre)


# ---------------------------------------------------------------- droits sur un membre

def _droits_nuls():
    return {cle: False for cle in CLES_DROITS}


def _etapes_role(user, profil, membre):
    """Drapeaux de validation que le rôle pose sur `membre` maintenant (liste vide : rien).

    PR pose toutes les étapes manquantes ; VA pose is_validate2 ; VN pose is_validate3 (après is_validate2) ; VP n'a pas d'étape
    représentable (point d'extension ``ETAPES_PAR_ROLE``). Jamais sur un membre supprimé, ni sur sa propre fiche ou ses propres
    saisies. Le SU, qui a l'exception, est traité par les droits hérités."""
    nomination, role = profil.nomination, profil.role
    if membre.is_delete or membre.pk == user.membreId or membre.user_id == user.pk:
        return []
    if role not in (roles.PR, roles.VA, roles.VP, roles.VN) or not _dans_portee(user, nomination, membre):
        return []
    manquantes = [c for c in ('is_validate1', 'is_validate2', 'is_validate3') if not getattr(membre, c)]
    if role == roles.PR:
        return manquantes
    drapeau = ETAPES_PAR_ROLE.get(role)
    if drapeau and manquantes and manquantes[0] == drapeau:
        return [drapeau]  # l'étape précédente est exigée : on pose seulement la PREMIÈRE étape manquante, si c'est la sienne
    return []


def etapes_a_valider(user, membre):
    """Drapeaux de validation que `user` pose sur `membre` (idempotent : jamais de retrait)."""
    profil = profil_de(user)
    if _herite(profil):
        return herites.etapes_a_valider(user, membre)
    if profil.mode != 'nomination':
        return []
    return _etapes_role(user, profil, membre)


def droits_membre(user, membre=None):
    """Booléens de droits (16 clés ``peut_*``, voir CLES_DROITS) : en général (`membre` absent) ou sur un membre précis."""
    profil = profil_de(user)
    if _herite(profil):
        return herites.droits_membre(user, membre)
    droits = _droits_nuls()
    if profil.mode != 'nomination':
        return droits
    nomination, role = profil.nomination, profil.role
    ecriture_role = role in ROLES_ECRITURE
    portee = membre is None or _dans_portee(user, nomination, membre)
    ecriture = ecriture_role and portee
    supprime = membre is not None and bool(membre.is_delete)
    avant_v1 = membre is None or not membre.is_validate2
    saisie_perso = membre is None or membre.user_id == user.pk
    gerer = ecriture and not supprime
    gerer_apres_saisie = gerer and (role != roles.AT or (avant_v1 and saisie_perso))  # AT : seulement avant la 1re validation
    executer = ecriture and role in ROLES_EXECUTENT_SUPPRESSION
    droits.update({
        'peut_creer_membre': ecriture_role,
        'peut_modifier': gerer_apres_saisie,
        'peut_valider': (role in (roles.PR, roles.VA, roles.VN)) if membre is None else bool(_etapes_role(user, profil, membre)),
        'peut_demander_suppression': ecriture,
        'peut_attribuer_privileges': False,  # réservé au SU (correctif C1)
        'peut_voir_historique': role in ROLES_VOIENT_HISTORIQUE and portee,
        'peut_demander_modification': role == roles.AT and portee and not supprime,
        'peut_ajouter_engin': gerer,
        'peut_ajouter_famille': gerer,
        'peut_modifier_engin': gerer_apres_saisie,
        'peut_supprimer_engin': gerer_apres_saisie,
        'peut_modifier_famille': gerer_apres_saisie,
        'peut_supprimer_famille': gerer_apres_saisie,
        'peut_executer_suppression': executer,
        'peut_restaurer': bool(executer and supprime),
        'peut_annuler_demande_suppression': bool(
            ecriture and membre is not None and membre.suppression_demandee and not supprime
            and (executer or membre.suppression_demandee_par_id == user.pk)),
    })
    return droits


# ---------------------------------------------------------------- accès par identifiant

def membre_et_droits(user, id, droit=None, supprimes_visibles=False):
    """(membre, droits) : membre `id` visible par `user` (404 sinon) et ses droits ; 403 si `droit` manque.

    Un membre supprimé logiquement n'est visible que si `supprimes_visibles` ET si `user` peut le restaurer (404 sinon)."""
    membre = get_object_or_404(membres_du_perimetre(user, avec_supprimes=supprimes_visibles), id=id)
    droits = droits_membre(user, membre)
    if membre.is_delete and not droits['peut_restaurer']:
        raise Http404
    if droit and not droits[droit]:
        raise PermissionDenied
    return membre, droits


def membre_pour(user, id, droit=None, supprimes_visibles=False):
    """Membre `id` visible par `user` (404 sinon) ; 403 si `droit` (clé de `droits_membre`) n'est pas accordé."""
    return membre_et_droits(user, id, droit, supprimes_visibles)[0]


def engins_visibles(user):
    """Engins non supprimés dont le propriétaire est visible par `user` (tous pour qui voit tout)."""
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


# ---------------------------------------------------------------- périmètre : associations membres et géographie

def _associations_de_portee(profil):
    """Filtre (Q) des associations membres du périmètre de la nomination."""
    nomination, role = profil.nomination, profil.role
    if role in (roles.PR, roles.VN):
        return Q()
    if role == roles.VP or (role == roles.VI and nomination.coordination_id):
        return Q(province_id=nomination.coordination_id) | Q(antenne__coordination_id=nomination.coordination_id)
    if role in (roles.VA, roles.AT) or (role == roles.VI and nomination.antenne_id):
        antenne = nomination.antenne
        q = Q(antenne_id=antenne.pk) | Q(antennes_heritees__pk=antenne.pk)
        if antenne.ville_origine_id:
            q |= Q(ville_id=antenne.ville_origine_id)
        if nomination.association_id:
            q |= Q(pk=nomination.association_id)
        return q
    if role == roles.VI:
        return Q()  # visiteur national
    return Q(pk__in=[])  # ED


def associations_du_compte(user):
    """Associations membres visibles : celles du périmètre du rôle, plus celles auxquelles le compte est rattaché."""
    profil = profil_de(user)
    if _herite(profil):
        return herites.associations_du_compte(user)
    if profil.mode == 'aucun':
        return AssociationMembre.objects.none()
    rattachees = Q(users=user)
    if profil.mode == 'nomination':
        portee = _associations_de_portee(profil)
        if not portee:  # Q() vide : périmètre national, toutes les associations
            return AssociationMembre.objects.all()
        rattachees |= portee
    return AssociationMembre.objects.filter(rattachees).distinct()


def _lieux_fiche(user):
    """(coordinations, villes, antennes) de la propre fiche du compte."""
    provinces, villes, antennes = set(), set(), set()
    fiche = Membre.objects.filter(pk=user.membreId).first() if user.membreId else None
    if fiche:
        provinces.add(fiche.province_id)
        villes.add(fiche.ville_id)
        antennes.add(fiche.antenne_id)
    return provinces - {None}, villes - {None}, antennes - {None}


def _geographie(user, modele):
    """Queryset de `modele` (Province, Ville ou Antenne) dans le périmètre : rôle + propre fiche."""
    profil = profil_de(user)
    if profil.mode == 'aucun':
        return modele.objects.none()
    tout = profil.mode == 'nomination' and (profil.role in (roles.PR, roles.VN) or (
        profil.role == roles.VI and not profil.nomination.coordination_id and not profil.nomination.antenne_id))
    if tout:
        return modele.objects.all()
    provinces, villes, antennes = _lieux_fiche(user)
    nomination = profil.nomination if profil.mode == 'nomination' else None
    if nomination is not None and profil.role != roles.ED:
        if nomination.coordination_id:
            provinces.add(nomination.coordination_id)
        if nomination.antenne_id:
            antennes.add(nomination.antenne_id)
            provinces.add(nomination.antenne.coordination_id) if nomination.antenne.coordination_id else None
            if nomination.antenne.ville_origine_id:
                villes.add(nomination.antenne.ville_origine_id)
    if modele is Province:
        return Province.objects.filter(pk__in=provinces)
    if modele is Ville:
        q = Q(pk__in=villes)
        if nomination is not None and nomination.coordination_id and profil.role != roles.ED:
            q |= Q(province_id=nomination.coordination_id)
        return Ville.objects.filter(q)
    q = Q(pk__in=antennes)
    if nomination is not None and nomination.coordination_id and profil.role != roles.ED:
        q |= Q(coordination_id=nomination.coordination_id)
    return Antenne.objects.filter(q)


def provinces_du_perimetre(user):
    """Coordinations visibles : toutes pour PR, VN (national) et SU, celle du rôle ou de la propre fiche sinon."""
    if _herite(profil_de(user)):
        return herites.provinces_du_perimetre(user)
    return _geographie(user, Province)


def villes_du_perimetre(user):
    if _herite(profil_de(user)):
        return herites.villes_du_perimetre(user)
    return _geographie(user, Ville)


def antennes_du_perimetre(user):
    if _herite(profil_de(user)):
        return herites.antennes_du_perimetre(user)
    return _geographie(user, Antenne)


def cible_rattachable(user, champ, cible):
    """Vrai si `user` peut rattacher un membre à `cible` (champ : 'structure', 'antenne' ou 'ville').

    PR et VN : toute cible. VP : une cible de sa coordination. VA : une cible de son antenne. AT, VI, ED : jamais."""
    profil = profil_de(user)
    if _herite(profil):
        return herites.cible_rattachable(user, champ, cible)
    if cible is None or profil.mode != 'nomination':
        return False
    role, nomination = profil.role, profil.nomination
    if role in (roles.PR, roles.VN):
        return True
    if role == roles.VP:
        coordination = nomination.coordination_id
        if champ == 'structure':
            return cible.province_id == coordination or (cible.antenne_id is not None and cible.antenne.coordination_id == coordination)
        if champ == 'antenne':
            return cible.coordination_id == coordination
        if champ == 'ville':
            return cible.province_id == coordination
        return False
    if role == roles.VA:
        antenne = nomination.antenne
        if champ == 'antenne':
            return cible.pk == antenne.pk
        if champ == 'ville':
            return bool(antenne.ville_origine_id) and cible.pk == antenne.ville_origine_id
        if champ == 'structure':
            return associations_du_compte(user).filter(pk=cible.pk).exists()
    return False


# ---------------------------------------------------------------- rôles transverses : contenu du site, référentiel

def est_editeur(user):
    """Éditeur du contenu du site : SU, rôle ED, ou champ hérité ``editor`` (hors lecture seule) pour un compte sans nomination."""
    profil = profil_de(user)
    if profil.mode == 'su':
        return True
    if profil.mode == 'nomination':
        return profil.role == roles.ED
    if profil.mode == 'herite':
        return bool(user.editor) and not user.privilege4
    return False


def peut_ecrire_referentiel(user):
    """Écriture sur la géographie et les associations membres : SU, PR et VN ; privilege5 hérité (hors lecture seule) sans nomination."""
    profil = profil_de(user)
    if profil.mode == 'su':
        return True
    if profil.mode == 'nomination':
        return profil.role in (roles.PR, roles.VN)
    if profil.mode == 'herite':
        return bool(user.privilege5) and not user.privilege4
    return False


def droits_menu(user):
    """Booléens pour le menu et la coque : ce que le compte peut ouvrir (sans requête de plus que le profil)."""
    profil = profil_de(user)
    if profil.mode == 'aucun':
        return {'role': '', 'role_libelle': '', 'est_su': False, 'voit_membres': False, 'voit_associations': False,
                'voit_geographie': False, 'peut_creer_membre': False, 'peut_ecrire_referentiel': False, 'est_editeur': False,
                'voit_journal': False}
    role = profil.role
    en_general = droits_membre(user)
    return {
        'role': role,
        'role_libelle': str(roles.LIBELLES[role]) if role else '',
        'est_su': profil.mode == 'su',
        'voit_membres': profil.mode != 'nomination' or role != roles.ED,
        'voit_associations': profil.mode != 'nomination' or role != roles.ED,
        'voit_geographie': profil.mode != 'nomination' or role != roles.ED,
        'peut_creer_membre': en_general['peut_creer_membre'],
        'peut_ecrire_referentiel': peut_ecrire_referentiel(user),
        'est_editeur': est_editeur(user),
        'voit_journal': profil.mode == 'su',
    }
