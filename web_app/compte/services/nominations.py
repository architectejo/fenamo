"""Nominations : création, fin, cohérence rôle / périmètre, groupes Django miroirs (cahier des charges web § 4 et F-02).

Règles de cohérence rôle / périmètre :
- SU, PR, VN : national, aucun périmètre géographique ;
- VP : une coordination provinciale (pas d'antenne) ;
- VA : une antenne ; AT : une antenne, éventuellement une association membre ;
- VI : national (aucun périmètre), OU une coordination, OU une antenne (fixé à la création) ;
- ED : aucun périmètre (le contenu du site n'est pas géographique).
Un compte n'a qu'UNE nomination active. Ce module ne contrôle PAS qui peut nommer qui (§ 4.2) : c'est l'affaire de la vue de nomination.
"""
from datetime import date

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from compte import roles
from compte.models import JournalAction, Nomination
from compte.services.journal import journaliser


def valider_coherence(role, coordination_id=None, antenne_id=None, association_id=None):
    """Lève ValidationError si le périmètre ne convient pas au rôle."""
    if role not in roles.ROLES:
        raise ValidationError({'role': _("Rôle inconnu.")})
    erreurs = {}
    if role in (roles.SU, roles.PR, roles.VN, roles.ED):
        if coordination_id or antenne_id or association_id:
            erreurs['__all__'] = _("Ce rôle n'a pas de périmètre géographique.")
    elif role == roles.VP:
        if not coordination_id:
            erreurs['coordination'] = _("Le validateur provincial exerce dans une coordination provinciale.")
        elif antenne_id or association_id:
            erreurs['__all__'] = _("Le validateur provincial n'a pas d'antenne ni d'association : sa coordination suffit.")
    elif role in (roles.VA, roles.AT):
        if not antenne_id:
            erreurs['antenne'] = _("Ce rôle exerce dans une antenne.")
        elif coordination_id:
            erreurs['__all__'] = _("Ce rôle se définit par son antenne, pas par une coordination.")
        elif association_id and role == roles.VA:
            erreurs['__all__'] = _("Le validateur d'antenne n'est pas limité à une association membre.")
    elif role == roles.VI:
        if coordination_id and antenne_id:
            erreurs['__all__'] = _("Le visiteur a un seul périmètre : national, une coordination OU une antenne.")
        elif association_id:
            erreurs['__all__'] = _("Le visiteur n'est pas limité à une association membre.")
    if erreurs:
        raise ValidationError(erreurs)


def synchroniser_groupe(compte):
    """Groupes Django miroirs : le compte est dans le groupe ``role_<ROLE>`` de sa nomination active, dans aucun autre."""
    voulu = Nomination.objects.filter(compte=compte, active=True).values_list('role', flat=True).first()
    miroirs = Group.objects.filter(name__startswith=roles.PREFIXE_GROUPE)
    compte.groups.remove(*miroirs.exclude(name=roles.nom_du_groupe(voulu))) if voulu else compte.groups.remove(*miroirs)
    if voulu:
        groupe, _cree = Group.objects.get_or_create(name=roles.nom_du_groupe(voulu))
        compte.groups.add(groupe)


@transaction.atomic
def creer_nomination(auteur, compte, role, *, membre=None, coordination=None, antenne=None, association=None,
                     debut=None, fin=None, duree_mandat_ans=None):
    """Nomme `compte` dans `role` ; retourne la Nomination. Une seule nomination active par compte (ValidationError sinon).

    Sans `fin`, elle est calculée à partir de la durée de mandat du rôle (``roles.duree_par_defaut``) quand il en a une.
    `auteur` est inscrit comme ayant nommé et au journal d'activités (NOMINATION).
    """
    valider_coherence(role, getattr(coordination, 'pk', None), getattr(antenne, 'pk', None), getattr(association, 'pk', None))
    if Nomination.objects.select_for_update().filter(compte=compte, active=True).exists():
        raise ValidationError(_("Ce compte a déjà une nomination active : terminez-la d'abord."))
    debut = debut or timezone.localdate()
    duree = duree_mandat_ans if duree_mandat_ans is not None else roles.duree_par_defaut(role)
    if fin is None and duree:
        try:
            fin = debut.replace(year=debut.year + duree)
        except ValueError:  # 29 février
            fin = date(debut.year + duree, 3, 1)
    nomination = Nomination.objects.create(
        compte=compte, membre=membre, role=role, coordination=coordination, antenne=antenne, association=association,
        debut=debut, fin=fin, duree_mandat_ans=duree, nomme_par=auteur if getattr(auteur, 'pk', None) else None)
    synchroniser_groupe(compte)
    oublier_profil(compte)
    journaliser(auteur, JournalAction.Action.NOMINATION, compte, apres={'role': role, 'debut': debut, 'fin': fin},
                libelle=getattr(compte, 'username', ''))
    return nomination


@transaction.atomic
def terminer_nomination(auteur, nomination, motif=''):
    """Met fin à la nomination (elle est conservée, marquée terminée) ; le compte perd ses droits de rôle."""
    if not nomination.active:
        return nomination
    nomination.active = False
    nomination.terminee_le = timezone.now()
    nomination.terminee_par = auteur if getattr(auteur, 'pk', None) else None
    nomination.motif_fin = motif or ''
    nomination.save(update_fields=['active', 'terminee_le', 'terminee_par', 'motif_fin'])
    synchroniser_groupe(nomination.compte)
    oublier_profil(nomination.compte)
    journaliser(auteur, JournalAction.Action.FIN_NOMINATION, nomination.compte, avant={'role': nomination.role, 'active': True},
                apres={'active': False}, motif=motif or '', libelle=getattr(nomination.compte, 'username', ''))
    return nomination


def oublier_profil(compte):
    """Efface le profil de droits mis en cache sur l'objet `compte` (voir ``compte.services.droits``)."""
    for attribut in ('_fenamo_profil',):
        if hasattr(compte, attribut):
            delattr(compte, attribut)


# ================================================================ gestion des nominations et des comptes (F-02, F-03, F-05, F-06)
#
# Règles : on nomme seulement un rôle inférieur au sien (table roles.NOMMABLES, § 4.3), dans son périmètre ; on ne gère jamais son
# propre compte ; on ne gère jamais un SU sans l'être soi-même ; un compte sans nomination n'est géré que par un SU. Les
# mots de passe temporaires sont renvoyés UNE seule fois à l'appelant et ne figurent jamais au journal.
#
# Exceptions : HorsPerimetre (404 côté vue : l'objet n'existe pas pour l'auteur), DroitInsuffisant (403 : périmètre ok, droit non),
# RegleMetier (400 / message : état ou donnée refusés).

class ErreurNomination(Exception):
    """Base des refus métier de ce module."""


class HorsPerimetre(ErreurNomination):
    """L'objet visé est hors du périmètre de l'auteur : la vue répond 404."""


class DroitInsuffisant(ErreurNomination):
    """Dans son périmètre mais sans le droit (rôle supérieur ou égal, soi-même, rôle non nommable) : la vue répond 403."""


class RegleMetier(ErreurNomination):
    """Donnée ou état refusés (membre non actif, nomination déjà active, rôle de compte externe invalide…)."""


def _role_de(auteur):
    from compte.services.droits import role_de
    return role_de(auteur)


def roles_nommables(auteur):
    """Rôles que `auteur` peut nommer (SU : tous sauf SU ; PR, VN, VP, VA : voir roles.NOMMABLES ; autres : aucun)."""
    return roles.roles_nommables_par(_role_de(auteur))


def _dans_portee_auteur(auteur, coordination=None, antenne=None, association=None):
    """Vrai si le périmètre visé (coordination, antenne, association) est dans celui de `auteur`.

    National (SU, PR, VN) : tout. VP : sa coordination et ses antennes. VA : son antenne et les associations de son périmètre.
    Les autres rôles : rien."""
    from compte.services.droits import associations_du_compte, profil_de
    profil = profil_de(auteur)
    if profil.mode == 'su':
        return True
    if profil.mode != 'nomination':
        return False
    role, nomination = profil.role, profil.nomination
    if role in (roles.PR, roles.VN):
        return True
    if role == roles.VP:
        if coordination is not None:
            return coordination.pk == nomination.coordination_id
        if antenne is not None:
            return antenne.coordination_id == nomination.coordination_id
        return False
    if role == roles.VA:
        if coordination is not None or antenne is None:
            return False
        if antenne.pk != nomination.antenne_id:
            return False
        return association is None or associations_du_compte(auteur).filter(pk=association.pk).exists()
    return False


def _verifier_nommable(auteur, role, coordination=None, antenne=None, association=None):
    """Lève DroitInsuffisant (rôle non nommable) ou HorsPerimetre (périmètre visé hors du sien)."""
    if role not in roles_nommables(auteur):
        raise DroitInsuffisant(_("Vous ne pouvez pas nommer ce rôle."))
    if not _dans_portee_auteur(auteur, coordination, antenne, association):
        raise HorsPerimetre(_("Ce périmètre n'est pas le vôtre."))


def _nomination_active(compte):
    return Nomination.objects.filter(compte=compte, active=True).select_related('coordination', 'antenne', 'association').first()


def _verifier_gestion(auteur, compte):
    """Lève HorsPerimetre ou DroitInsuffisant si `auteur` ne peut pas gérer `compte` (réinitialiser, désactiver, changer, terminer).

    Jamais soi-même ; jamais un SU sans l'être ; SU : tout autre compte ; sinon la nomination active du compte doit porter un rôle
    nommable par `auteur` DANS son périmètre, ou avoir été faite par `auteur` (« celui qui a nommé »)."""
    if auteur.pk == compte.pk:
        raise DroitInsuffisant(_("Vous ne pouvez pas gérer votre propre compte."))
    if compte.is_superuser:
        if not auteur.is_superuser:
            raise HorsPerimetre(_("Compte introuvable."))
        return
    if auteur.is_superuser:
        return
    nomination = _nomination_active(compte)
    if nomination is None:
        raise HorsPerimetre(_("Compte introuvable."))  # compte sans nomination : réservé au SU
    if nomination.nomme_par_id == auteur.pk and _role_de(auteur):
        return
    if _dans_portee_auteur(auteur, nomination.coordination, nomination.antenne, nomination.association):
        if nomination.role in roles_nommables(auteur):
            return
        raise DroitInsuffisant(_("Ce compte a un rôle supérieur ou égal au vôtre."))
    raise HorsPerimetre(_("Compte introuvable."))


def peut_gerer(auteur, compte):
    """Vrai si `auteur` peut gérer `compte` (jamais soi-même, jamais un SU sans l'être, rôle supérieur dans le périmètre)."""
    try:
        _verifier_gestion(auteur, compte)
    except ErreurNomination:
        return False
    return True


def comptes_gerables(auteur):
    """Comptes que `auteur` peut gérer : tous les autres comptes non SU pour un SU ; sinon ceux dont la nomination active porte un
    rôle nommable par `auteur` dans son périmètre, plus ceux qu'il a nommés lui-même. Jamais lui-même, jamais un SU."""
    from django.contrib.auth import get_user_model
    Compte = get_user_model()
    base = Compte.objects.exclude(pk=auteur.pk).exclude(is_superuser=True)
    if auteur.is_superuser:
        return base
    ids = set()
    for nomination in Nomination.objects.filter(active=True).exclude(compte=auteur).select_related('coordination', 'antenne', 'association'):
        if nomination.nomme_par_id == auteur.pk or (
                nomination.role in roles_nommables(auteur)
                and _dans_portee_auteur(auteur, nomination.coordination, nomination.antenne, nomination.association)):
            ids.add(nomination.compte_id)
    return base.filter(pk__in=ids)


def membres_nommables(auteur):
    """Membres que `auteur` peut choisir pour une nomination : ACTIFS (validés au dernier niveau), non supprimés, de son périmètre,
    sans compte SU et sans nomination active. Vide si `auteur` ne peut nommer aucun rôle."""
    from compte.services.droits import membres_du_perimetre
    from coptapp.models import Membre
    if not roles_nommables(auteur):
        return Membre.objects.none()
    avec_nomination = Nomination.objects.filter(active=True).values('compte__membreId')
    from django.contrib.auth import get_user_model
    superutilisateurs = get_user_model().objects.filter(is_superuser=True).values('membreId')
    return (membres_du_perimetre(auteur).filter(is_validate3=True, is_delete=False)
            .exclude(pk__in=[m for m in avec_nomination.values_list('compte__membreId', flat=True) if m])
            .exclude(pk__in=[m for m in superutilisateurs.values_list('membreId', flat=True) if m]))


@transaction.atomic
def nommer(auteur, membre, role, *, coordination=None, antenne=None, association=None, debut=None, fin=None):
    """F-02 : nomme un membre ACTIF du périmètre de `auteur` dans `role`. Retourne (nomination, mot_de_passe_ou_None).

    Si le membre n'a pas de compte, il en reçoit un avec un mot de passe temporaire (retourné UNE fois, changement forcé à la
    première connexion) ; sinon on réutilise son compte. Refus : HorsPerimetre (membre ou périmètre hors du sien),
    DroitInsuffisant (rôle non nommable), RegleMetier (membre non actif, compte SU, nomination déjà active)."""
    from compte.services.comptes import creer_compte_pour_membre
    from compte.services.droits import membres_du_perimetre
    if role not in roles_nommables(auteur):  # d'abord le droit (403) : sans droit de nommer, la question du périmètre ne se pose pas
        raise DroitInsuffisant(_("Vous ne pouvez pas nommer ce rôle."))
    if not membres_du_perimetre(auteur).filter(pk=membre.pk).exists():
        raise HorsPerimetre(_("Membre introuvable."))
    _verifier_nommable(auteur, role, coordination, antenne, association)
    if not membre.is_validate3 or membre.is_delete:
        raise RegleMetier(_("Le membre nommé doit être actif (validé au dernier niveau)."))
    try:
        valider_coherence(role, getattr(coordination, 'pk', None), getattr(antenne, 'pk', None), getattr(association, 'pk', None))
    except ValidationError as erreur:
        raise RegleMetier(' '.join(erreur.messages)) from erreur
    compte, mot_de_passe = creer_compte_pour_membre(membre, auteur=auteur)
    if compte.is_superuser:
        raise RegleMetier(_("Un compte super-utilisateur ne se nomme pas."))
    if Nomination.objects.select_for_update().filter(compte=compte, active=True).exists():
        raise RegleMetier(_("Ce compte a déjà une nomination active : changez son rôle au lieu d'en créer une autre."))
    nomination = creer_nomination(auteur, compte, role, membre=membre, coordination=coordination, antenne=antenne,
                                  association=association, debut=debut, fin=fin)
    return nomination, mot_de_passe


@transaction.atomic
def creer_compte_externe(auteur, username, role, *, email='', coordination=None, antenne=None):
    """F-03 : compte SANS fiche membre pour un visiteur (par PR ou SU) ou un éditeur (par SU seulement).

    Retourne (compte, nomination, mot_de_passe) : mot de passe temporaire à lecture unique, changement forcé à la première
    connexion. Le périmètre d'un visiteur est fixé ici (national, coordination OU antenne) et doit être dans celui de `auteur`."""
    from compte.services.comptes import creer_compte
    if role not in (roles.VI, roles.ED):
        raise RegleMetier(_("Seuls un visiteur ou un éditeur se créent sans fiche membre."))
    _verifier_nommable(auteur, role, coordination, antenne)
    username = (username or '').strip()
    if not username:
        raise RegleMetier(_("Indiquez un nom d'utilisateur."))
    from django.contrib.auth import get_user_model
    if get_user_model().objects.filter(username__iexact=username).exists():
        raise RegleMetier(_("Ce nom d'utilisateur existe déjà."))
    try:
        valider_coherence(role, getattr(coordination, 'pk', None), getattr(antenne, 'pk', None), None)
    except ValidationError as erreur:
        raise RegleMetier(' '.join(erreur.messages)) from erreur
    compte, mot_de_passe = creer_compte(username, email=email, membre=None, auteur=auteur)
    nomination = creer_nomination(auteur, compte, role, coordination=coordination, antenne=antenne)
    return compte, nomination, mot_de_passe


@transaction.atomic
def reinitialiser_mot_de_passe(auteur, compte):
    """F-05 : génère un mot de passe temporaire (retourné UNE fois), change forcé à la prochaine connexion ; journalisé sans le mot
    de passe. Droits : voir `_verifier_gestion` (celui qui a nommé, rôles supérieurs dans le périmètre, SU)."""
    from compte.services.comptes import mot_de_passe_temporaire
    _verifier_gestion(auteur, compte)
    mot_de_passe = mot_de_passe_temporaire()
    compte.set_password(mot_de_passe)
    compte.doit_changer_mot_de_passe = True
    compte.save(update_fields=['password', 'doit_changer_mot_de_passe'])
    journaliser(auteur, JournalAction.Action.REINITIALISATION_MOT_DE_PASSE, compte, apres={'changement_impose': True},
                motif=_("Mot de passe réinitialisé (temporaire, à changer)."), libelle=compte.username)
    return mot_de_passe


@transaction.atomic
def desactiver(auteur, compte, motif):
    """F-06 : désactive le compte (jamais supprimé). Le MOTIF est obligatoire (RegleMetier s'il est vide) et conservé au journal.
    La nomination est conservée ; le compte ne se connecte plus."""
    _verifier_gestion(auteur, compte)
    motif = (motif or '').strip()
    if not motif:
        raise RegleMetier(_("Indiquez le motif de la désactivation."))
    if not compte.is_active:
        return compte
    compte.is_active = False
    compte.save(update_fields=['is_active'])
    oublier_profil(compte)
    journaliser(auteur, JournalAction.Action.DESACTIVATION_COMPTE, compte, avant={'is_active': True}, apres={'is_active': False},
                motif=motif, libelle=compte.username)
    return compte


@transaction.atomic
def reactiver(auteur, compte, motif=''):
    """F-06 : réactive un compte désactivé. Ne génère PAS de mot de passe temporaire : le mot de passe du compte est conservé (pour
    en donner un nouveau, utiliser `reinitialiser_mot_de_passe`)."""
    _verifier_gestion(auteur, compte)
    if compte.is_active:
        return compte
    compte.is_active = True
    compte.save(update_fields=['is_active'])
    oublier_profil(compte)
    journaliser(auteur, JournalAction.Action.REACTIVATION_COMPTE, compte, avant={'is_active': False}, apres={'is_active': True},
                motif=motif or '', libelle=compte.username)
    return compte


@transaction.atomic
def terminer(auteur, compte, motif=''):
    """F-06 : met fin à la nomination active de `compte` (droits de rôle retirés) ; elle est conservée."""
    _verifier_gestion(auteur, compte)
    nomination = Nomination.objects.select_for_update().filter(compte=compte, active=True).first()
    if nomination is None:
        raise RegleMetier(_("Ce compte n'a pas de nomination active."))
    return terminer_nomination(auteur, nomination, motif)


@transaction.atomic
def changer_role_perimetre(auteur, compte, role, *, coordination=None, antenne=None, association=None, motif='', fin=None):
    """F-06 : clôt la nomination en cours de `compte` et en ouvre une autre (nouveau rôle ou nouveau périmètre) dans UNE transaction,
    sous verrou. Il faut pouvoir gérer le compte ET nommer le nouveau rôle dans le nouveau périmètre. Retourne la nouvelle nomination."""
    _verifier_gestion(auteur, compte)
    _verifier_nommable(auteur, role, coordination, antenne, association)
    ancienne = Nomination.objects.select_for_update().filter(compte=compte, active=True).first()
    if ancienne is None:
        raise RegleMetier(_("Ce compte n'a pas de nomination active."))
    try:
        valider_coherence(role, getattr(coordination, 'pk', None), getattr(antenne, 'pk', None), getattr(association, 'pk', None))
    except ValidationError as erreur:
        raise RegleMetier(' '.join(erreur.messages)) from erreur
    terminer_nomination(auteur, ancienne, motif or _("Changement de rôle ou de périmètre."))
    nouvelle = creer_nomination(auteur, compte, role, membre=ancienne.membre, coordination=coordination, antenne=antenne,
                                association=association, fin=fin)
    journaliser(auteur, JournalAction.Action.CHANGEMENT_ROLE, compte, avant={'role': ancienne.role}, apres={'role': role},
                motif=motif or '', libelle=compte.username)
    return nouvelle


# ================================================================ alertes de fin de mandat et nominations initiales (commandes)

JOURS_ALERTE = 60


def attribuer_nomination_su(pseudo, dry_run=False):
    """Nomination SU du SEUL compte `pseudo`, qui doit déjà être super-utilisateur actif. Retourne (compte, nomination ou None, cree).

    ``dry_run`` : ne crée rien. Aucun autre compte n'est touché. Un compte qui a déjà une nomination active est laissé tel quel."""
    from django.contrib.auth import get_user_model
    compte = get_user_model().objects.filter(username=pseudo).first()
    if compte is None:
        raise RegleMetier(_("Compte inconnu."))
    if not (compte.is_superuser and compte.is_active):
        raise RegleMetier(_("Ce compte n'est pas un super-utilisateur actif : aucune nomination SU."))
    existante = _nomination_active(compte)
    if existante is not None:
        return compte, existante, False
    if dry_run:
        return compte, None, False
    return compte, creer_nomination(None, compte, roles.SU), True


def etat_des_comptes():
    """Description des comptes SANS nomination active (rien n'est modifié) : [(compte, resume)], pour l'état avant les rôles."""
    from django.contrib.auth import get_user_model
    resultat = []
    actifs = set(Nomination.objects.filter(active=True).values_list('compte_id', flat=True))
    for compte in get_user_model().objects.order_by('pk'):
        if compte.pk in actifs:
            continue
        herites = [f'P{i}' for i in range(1, 6) if getattr(compte, f'privilege{i}', False)]
        if compte.is_superuser:
            resume = 'super-utilisateur'
        else:
            resume = 'droits hérités : ' + (','.join(herites) or 'aucun') + (' + éditeur' if compte.editor else '')
        resume += f' · membre #{compte.membreId}' if compte.membreId else ' · sans fiche'
        resultat.append((compte, resume + ('' if compte.is_active else ' · INACTIF')))
    return resultat


def alertes_de_mandat(aujourdhui=None, jours=JOURS_ALERTE, dry_run=False):
    """Alertes de fin de mandat : UNE notification à celui qui a nommé (s'il est actif), sinon à tous les présidents.

    Deux alertes par nomination : `jours` jours avant la fin, puis à l'échéance. ``alerte_envoyee_le`` rend l'envoi idempotent
    (relancer le même jour n'envoie rien). Les droits NE sont JAMAIS retirés : une nomination échue reste active jusqu'à clôture
    manuelle. Retourne {'envoyees': [...], 'echues': [...], 'a_venir': [...]} (listes de Nomination)."""
    from datetime import timedelta

    from coptapp.models import Notification
    jour = aujourdhui or timezone.localdate()
    rapport = {'envoyees': [], 'echues': [], 'a_venir': []}
    nominations = Nomination.objects.filter(active=True, fin__isnull=False).select_related('compte', 'nomme_par').order_by('fin', 'pk')
    for nomination in nominations:
        echue = nomination.fin <= jour
        proche = (not echue) and nomination.fin - jour <= timedelta(days=jours)
        if echue:
            rapport['echues'].append(nomination)
        elif proche:
            rapport['a_venir'].append(nomination)
        deja = nomination.alerte_envoyee_le
        if not ((echue and (deja is None or deja < nomination.fin)) or (proche and deja is None)):
            continue
        rapport['envoyees'].append(nomination)
        if dry_run:
            continue
        if nomination.nomme_par and nomination.nomme_par.is_active:
            destinataires = [nomination.nomme_par]
        else:
            destinataires = list(_comptes_avec_role(roles.PR))
        donnees = {'compte': nomination.compte.username, 'role': nomination.role, 'fin': nomination.fin.strftime('%d/%m/%Y'),
                   'jours': (nomination.fin - jour).days}
        if echue:
            titre = _("Mandat échu : %(compte)s (%(role)s)") % donnees
            description = _("Le mandat de %(compte)s (%(role)s) est arrivé à échéance le %(fin)s ; il reste actif jusqu'à clôture manuelle.") % donnees
        else:
            titre = _("Mandat bientôt échu : %(compte)s (%(role)s)") % donnees
            description = _("Le mandat de %(compte)s (%(role)s) prend fin le %(fin)s (dans %(jours)s jours).") % donnees
        for destinataire in destinataires:
            Notification.objects.create(user=destinataire, membre=nomination.membre, titre=titre, description=description)
        Nomination.objects.filter(pk=nomination.pk).update(alerte_envoyee_le=jour)
        journaliser(None, JournalAction.Action.ALERTE_MANDAT, nomination.compte, apres={'fin': nomination.fin, 'echue': echue},
                    libelle=nomination.compte.username)
    return rapport


def _comptes_avec_role(role):
    from django.contrib.auth import get_user_model
    return get_user_model().objects.filter(is_active=True, nominations__active=True, nominations__role=role).distinct()


# ================================================================ renouvellement, listes pour l'écran Utilisateurs

@transaction.atomic
def renouveler_mandat(auteur, compte, motif=''):
    """Renouvelle le mandat de `compte` : MÊME rôle et MÊME périmètre ; la nomination en cours est clôturée (motif « renouvellement »)
    et une nouvelle est ouverte, avec une nouvelle fin (début aujourd'hui + durée du rôle), dans UNE transaction sous verrou.

    Mêmes contrôles de droit que `changer_role_perimetre` (gérer le compte ET pouvoir nommer ce rôle dans ce périmètre).
    RegleMetier si le compte n'a pas de nomination active ou si son rôle n'a pas de mandat (SU, VI, ED). Journal : CHANGEMENT_ROLE
    (rôle identique avant / après, fin avant / après, motif « renouvellement »). Retourne la nouvelle nomination."""
    _verifier_gestion(auteur, compte)
    ancienne = Nomination.objects.select_for_update().select_related('coordination', 'antenne', 'association').filter(
        compte=compte, active=True).first()
    if ancienne is None:
        raise RegleMetier(_("Ce compte n'a pas de nomination active."))
    if roles.duree_par_defaut(ancienne.role) is None:
        raise RegleMetier(_("Ce rôle n'a pas de mandat à renouveler."))
    _verifier_nommable(auteur, ancienne.role, ancienne.coordination, ancienne.antenne, ancienne.association)
    raison = (motif or '').strip() or _("renouvellement")
    terminer_nomination(auteur, ancienne, raison)
    nouvelle = creer_nomination(auteur, compte, ancienne.role, membre=ancienne.membre, coordination=ancienne.coordination,
                                antenne=ancienne.antenne, association=ancienne.association)
    journaliser(auteur, JournalAction.Action.CHANGEMENT_ROLE, compte, avant={'role': ancienne.role, 'fin': ancienne.fin},
                apres={'role': nouvelle.role, 'fin': nouvelle.fin}, motif=raison, libelle=compte.username)
    return nouvelle


ETATS_COMPTE = ('actif', 'temporaire', 'desactive')
ETATS_MANDAT = ('echu', 'a_echoir', 'sans_fin')


def lister_comptes_gerables(auteur, filtres=None):
    """Comptes que `auteur` peut gérer (voir `comptes_gerables`), filtrés, triés par nom d'utilisateur, prêts à paginer.

    ``filtres`` (dict ; toute clé absente ou vide est ignorée) :
    - ``q`` : texte cherché dans le nom d'utilisateur, l'e-mail, le prénom, le nom et le nom du membre lié ;
    - ``role`` : code du rôle de la nomination active (PR, VN…) ; la valeur ``sans`` : comptes sans nomination active ;
    - ``coordination`` : identifiant d'une coordination (nomination dans cette coordination ou dans une de ses antennes) ;
    - ``antenne`` : identifiant d'une antenne ;
    - ``etat`` : ``actif`` (actif, mot de passe déjà changé), ``temporaire`` (actif, mot de passe temporaire à changer),
      ``desactive`` ;
    - ``mandat`` : ``echu`` (fin dépassée), ``a_echoir`` (fin dans les 60 jours), ``sans_fin``.
    Chaque compte porte ``nomination_active_liste`` (liste d'au plus une Nomination, ses lieux déjà chargés : aucune requête de plus
    par ligne)."""
    from datetime import timedelta

    from django.db.models import Prefetch, Q

    from coptapp.models import Membre
    filtres = filtres or {}
    comptes = comptes_gerables(auteur)
    q = (filtres.get('q') or '').strip()
    if q:
        comptes = comptes.filter(Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q)
                                 | Q(last_name__icontains=q) | Q(membreId__in=Membre.objects.filter(nom__icontains=q).values('pk')))
    role = (filtres.get('role') or '').strip().upper()
    if role == 'SANS':
        comptes = comptes.exclude(pk__in=Nomination.objects.filter(active=True).values('compte_id'))
    etat = filtres.get('etat')
    if etat == 'actif':
        comptes = comptes.filter(is_active=True, doit_changer_mot_de_passe=False)
    elif etat == 'temporaire':
        comptes = comptes.filter(is_active=True, doit_changer_mot_de_passe=True)
    elif etat == 'desactive':
        comptes = comptes.filter(is_active=False)
    # filtres sur la nomination ACTIVE : tous dans UN seul filter(), pour qu'ils portent sur la même ligne de nomination
    conditions = Q(nominations__active=True)
    voulu = False
    if role and role != 'SANS':
        conditions &= Q(nominations__role=role)
        voulu = True
    if filtres.get('coordination'):
        coordination = filtres['coordination']
        conditions &= Q(nominations__coordination_id=coordination) | Q(nominations__antenne__coordination_id=coordination)
        voulu = True
    if filtres.get('antenne'):
        conditions &= Q(nominations__antenne_id=filtres['antenne'])
        voulu = True
    jour = timezone.localdate()
    mandat = filtres.get('mandat')
    if mandat == 'echu':
        conditions &= Q(nominations__fin__lt=jour)
        voulu = True
    elif mandat == 'a_echoir':
        conditions &= Q(nominations__fin__gte=jour, nominations__fin__lte=jour + timedelta(days=JOURS_ALERTE))
        voulu = True
    elif mandat == 'sans_fin':
        conditions &= Q(nominations__fin__isnull=True)
        voulu = True
    if voulu:
        comptes = comptes.filter(conditions)
    active = Nomination.objects.filter(active=True).select_related('coordination', 'antenne', 'association', 'nomme_par')
    return (comptes.distinct().order_by('username')
            .prefetch_related(Prefetch('nominations', queryset=active, to_attr='nomination_active_liste')))


def etat_mandat(nomination, aujourdhui=None, jours=JOURS_ALERTE):
    """'echu' (fin dépassée), 'a_echoir' (fin dans les `jours` jours), 'en_cours' ou 'sans_fin'."""
    from datetime import timedelta
    jour = aujourdhui or timezone.localdate()
    if nomination.fin is None:
        return 'sans_fin'
    if nomination.fin < jour:
        return 'echu'
    return 'a_echoir' if nomination.fin - jour <= timedelta(days=jours) else 'en_cours'


def mandats_a_traiter(auteur, jours=JOURS_ALERTE):
    """Nominations ACTIVES des comptes gérables par `auteur` dont le mandat est échu ou finit dans les `jours` jours, triées par fin
    (les plus urgentes d'abord). QuerySet avec ``select_related`` du compte, du périmètre et de qui a nommé : prêt à paginer.
    Utiliser ``etat_mandat`` pour distinguer 'echu' et 'a_echoir'."""
    from datetime import timedelta
    limite = timezone.localdate() + timedelta(days=jours)
    return (Nomination.objects.filter(active=True, fin__isnull=False, fin__lte=limite, compte__in=comptes_gerables(auteur))
            .select_related('compte', 'coordination', 'antenne', 'association', 'nomme_par', 'membre')
            .order_by('fin', 'pk'))
