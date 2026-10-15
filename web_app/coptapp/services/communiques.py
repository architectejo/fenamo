"""Communiqués (F-40) : messages aux utilisateurs, reçus comme NOTIFICATIONS dans l'application (pas de push navigateur).

- **Qui publie** : cahier des charges F-40 et § 4.3 (ligne « Communiqués ») : l'éditeur (ED) et le super-utilisateur, à tous les niveaux de
  ciblage (national, une coordination, une antenne). ``ROLES_PUBLIANTS`` est le seul endroit à changer si la FENAMO étend ce droit (PR, VN, VP, VA).
- **Ciblage** : ni coordination ni antenne = national ; une coordination ; une antenne (sa coordination est alors posée avec elle).
- **Destinataires** : comptes actifs dans le périmètre ciblé PLUS les niveaux au-dessus (coordination parente, national : PR, VN), plus les
  super-utilisateurs, sauf l'auteur ; ni le visiteur ni l'éditeur ne reçoivent l'alerte. Chacun reçoit une ``Notification``.
- **Lecture** : le visiteur (VI) lit les communiqués de son périmètre ; chacun voit ceux de son périmètre et des niveaux au-dessus ;
  PR, VN, ED et SU voient tout. Le « lu » est PAR compte (``LectureCommunique``).
- Chaque publication est journalisée (F-70). Le verrouillage de l'application (F-07) s'applique par le middleware, comme pour toute vue.
"""
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from django.utils.translation import gettext as _

from compte import roles
from compte.models import JournalAction, Nomination
from compte.services.droits import est_editeur, profil_de
from compte.services.journal import journaliser
from coptapp.models import Antenne, Communique, LectureCommunique, Notification, Province

ROLES_PUBLIANTS = (roles.ED, roles.SU)
TITRE_MAX = 120
MESSAGE_MAX = 5000
PAR_PAGE = 20


class ErreurCommunique(ValueError):
    """Donnée invalide (titre, message, ciblage) : la vue répond 422 avec ce texte."""


def peut_publier(user):
    """Éditeur (ED, ou champ hérité ``editor``) ou super-utilisateur ; jamais un compte inactif ni anonyme."""
    return bool(user is not None and user.is_authenticated and user.is_active and est_editeur(user))


# ---------------------------------------------------------------- publication

def _cible(coordination, antenne):
    """(coordination, antenne) cohérents : l'antenne impose sa coordination ; ErreurCommunique si elles se contredisent."""
    if antenne is not None:
        if coordination is not None and antenne.coordination_id != coordination.pk:
            raise ErreurCommunique(_("Cette antenne n'appartient pas à la coordination choisie."))
        if antenne.coordination_id is None:
            raise ErreurCommunique(_("Cette antenne n'a pas de coordination : elle ne peut pas être ciblée."))
        coordination = Province.objects.get(pk=antenne.coordination_id)
    return coordination, antenne


@transaction.atomic
def publier(auteur, titre, message, coordination=None, antenne=None):
    """Publie un communiqué et notifie ses destinataires ; retourne le Communique.

    PermissionDenied si `auteur` ne peut pas publier ; ErreurCommunique si le titre (120 au plus), le message (5000 au plus) ou le ciblage
    est invalide (rien n'est écrit). Journalisé (F-70) avec le nombre de destinataires."""
    if not peut_publier(auteur):
        raise PermissionDenied
    titre, message = (titre or '').strip(), (message or '').strip()
    if not titre or len(titre) > TITRE_MAX:
        raise ErreurCommunique(_("Le titre est obligatoire (120 caractères au plus)."))
    if not message or len(message) > MESSAGE_MAX:
        raise ErreurCommunique(_("Le message est obligatoire (5000 caractères au plus)."))
    coordination, antenne = _cible(coordination, antenne)
    communique = Communique.objects.create(user=auteur, titre=titre, message=message, publie_le=timezone.now(),
                                           province=coordination, antenne=antenne)
    destinataires = list(destinataires_ids(communique))
    Notification.objects.bulk_create([
        Notification(user_id=compte_id, titre=_("Communiqué : %(titre)s") % {'titre': titre}, description=message[:500])
        for compte_id in destinataires], batch_size=500)
    journaliser(auteur, JournalAction.Action.MODIFICATION, communique,
                apres={'creation': True, 'type': 'communique', 'coordination': getattr(coordination, 'pk', None),
                       'antenne': getattr(antenne, 'pk', None), 'destinataires': len(destinataires)},
                motif=_("Publication d'un communiqué"), libelle=titre[:200])
    return communique


def destinataires_ids(communique):
    """Identifiants des comptes à alerter : voir le module. Jamais l'auteur, jamais VI ni ED."""
    from django.contrib.auth import get_user_model
    coordination_id = communique.province_id
    antenne = communique.antenne if communique.antenne_id else None
    if antenne is not None and antenne.coordination_id:
        coordination_id = coordination_id or antenne.coordination_id
    niveaux = Q(role__in=(roles.PR, roles.VN))  # national : toujours au-dessus
    if coordination_id is None and antenne is None:  # communiqué national : tous les rôles de terrain
        niveaux |= Q(role__in=(roles.VP, roles.VA, roles.AT))
    else:
        if coordination_id is not None:
            niveaux |= Q(role=roles.VP, coordination_id=coordination_id)
        if antenne is None:
            niveaux |= Q(role__in=(roles.VA, roles.AT), antenne__coordination_id=coordination_id)
        else:
            niveaux |= Q(role__in=(roles.VA, roles.AT), antenne_id=antenne.pk)
    comptes = Nomination.objects.filter(niveaux, active=True, compte__is_active=True).values('compte_id')
    Compte = get_user_model()
    ids = Compte.objects.filter(is_active=True).filter(Q(pk__in=comptes) | Q(is_superuser=True))
    if communique.user_id:
        ids = ids.exclude(pk=communique.user_id)
    return ids.values_list('pk', flat=True).distinct()


def destinataires(communique):
    """Comptes à alerter (QuerySet de Compte)."""
    from django.contrib.auth import get_user_model
    return get_user_model().objects.filter(pk__in=list(destinataires_ids(communique)))


# ---------------------------------------------------------------- lecture

def _publies():
    return Communique.objects.filter(publie_le__isnull=False, publie_le__lte=timezone.now())


def communiques_visibles(user):
    """Communiqués publiés que `user` peut lire : national + son périmètre ; tout pour SU, PR, VN, ED ; les siens toujours."""
    publies = _publies()
    if user is None or not user.is_authenticated or not user.is_active:
        return publies.none()
    profil = profil_de(user)
    propres = Q(user=user)
    if profil.mode == 'su' or est_editeur(user) or (profil.mode == 'nomination' and profil.role in (roles.PR, roles.VN)):
        return publies
    nomination = profil.nomination if profil.mode == 'nomination' else None
    national = Q(province__isnull=True, antenne__isnull=True)
    if nomination is not None and nomination.role == roles.VI and not nomination.coordination_id and not nomination.antenne_id:
        return publies  # visiteur national : tout, en lecture seule
    coordination_id = antenne_id = None
    if nomination is not None:
        antenne_id = nomination.antenne_id
        coordination_id = nomination.coordination_id or (nomination.antenne.coordination_id if nomination.antenne_id else None)
    elif user.membreId:
        from coptapp.models import Membre
        fiche = Membre.objects.filter(pk=user.membreId).values('antenne', 'antenne__coordination', 'province').first()
        if fiche:
            antenne_id, coordination_id = fiche['antenne'], fiche['antenne__coordination'] or fiche['province']
    portee = national
    if coordination_id is not None:
        # le communiqué d'une coordination vise toutes ses antennes ; celui d'une antenne ne vise que cette antenne (ou toute la
        # coordination pour un rôle de coordination)
        portee |= Q(province_id=coordination_id, antenne__isnull=True)
        if nomination is not None and nomination.coordination_id:
            portee |= Q(province_id=coordination_id) | Q(antenne__coordination_id=coordination_id)
    if antenne_id is not None:
        portee |= Q(antenne_id=antenne_id)
    return publies.filter(portee | propres).distinct()


def _non_lu(user):
    return ~Exists(LectureCommunique.objects.filter(compte=user, communique=OuterRef('pk')))


def nombre_non_lus(user):
    """Communiqués visibles, publiés depuis la création du compte, non écrits par `user` et pas encore lus PAR lui (compteur du badge)."""
    if user is None or not user.is_authenticated:
        return 0
    return (communiques_visibles(user).exclude(user=user).filter(publie_le__gte=user.date_joined).filter(_non_lu(user)).count())


def marquer_lu(user, communique):
    """Marque `communique` lu pour `user` ; retourne True à la première lecture. Communique.DoesNotExist s'il n'est pas visible (404)."""
    if not communiques_visibles(user).filter(pk=communique.pk).exists():
        raise Communique.DoesNotExist
    _lecture, cree = LectureCommunique.objects.get_or_create(compte=user, communique=communique)
    return cree


def lister_communiques(user, filtres=None, numero_page=None, par_page=PAR_PAGE):
    """Page de communiqués visibles (récents d'abord), chacun portant ``lu`` (pour `user`). Filtres : ``q`` (titre, message), ``etat``
    (« non_lus »), ``coordination`` et ``antenne`` (identifiants). Page illisible ou hors bornes : première ou dernière page."""
    filtres = filtres or {}
    jeu = communiques_visibles(user).select_related('user', 'province', 'antenne')
    q = (filtres.get('q') or '').strip()[:100]
    if q:
        jeu = jeu.filter(Q(titre__icontains=q) | Q(message__icontains=q))
    if filtres.get('etat') == 'non_lus':
        jeu = jeu.filter(_non_lu(user))
    for cle, champ in (('coordination', 'province_id'), ('antenne', 'antenne_id')):
        try:
            valeur = int(filtres.get(cle) or 0)
        except (TypeError, ValueError):
            valeur = 0
        if 0 < valeur <= 2**31 - 1:
            jeu = jeu.filter(**{champ: valeur})
    jeu = jeu.annotate(lu_par_moi=Exists(LectureCommunique.objects.filter(compte=user, communique=OuterRef('pk')))).order_by('-publie_le', '-pk')
    page = Paginator(jeu, par_page).get_page(numero_page)
    page.object_list = list(page.object_list)
    for communique in page.object_list:
        communique.lu = communique.lu_par_moi or communique.user_id == user.pk
    return page
