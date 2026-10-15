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


CIBLES = ('national', 'coordination', 'antenne')


class ErreurCommunique(ValueError):
    """Donnée invalide (titre, message, ciblage) : la vue répond 422 avec ce texte. ``champ`` désigne le champ fautif
    (``titre``, ``message``, ``coordination``, ``antenne``, ``cible``) pour l'afficher sous lui ; ``None`` = erreur générale."""

    def __init__(self, message, champ=None):
        super().__init__(message)
        self.champ = champ


def peut_publier(user):
    """Éditeur (ED, ou champ hérité ``editor``) ou super-utilisateur ; jamais un compte inactif ni anonyme."""
    return bool(user is not None and user.is_authenticated and user.is_active and est_editeur(user))


# ---------------------------------------------------------------- choix de ciblage

def choix_ciblage():
    """Listes pour cibler ou filtrer : ``coordinations`` (coordinations provinciales, ordre officiel) et ``antennes`` (liste de dictionnaires
    ``id``, ``nom``, ``coordination`` = identifiant de sa coordination), sans les antennes qui n'ont pas de coordination : elles ne peuvent
    pas être ciblées. Référentiel national, sans donnée personnelle."""
    coordinations = list(Province.objects.filter(code__isnull=False).order_by('ordre', 'nom'))
    antennes = [{'id': a.pk, 'nom': a.nom, 'coordination': a.coordination_id}
                for a in Antenne.objects.exclude(nom=None).filter(coordination__isnull=False).order_by('nom')]
    return {'coordinations': coordinations, 'antennes': antennes}


# ---------------------------------------------------------------- publication

def _cible(coordination, antenne, cible=None):
    """(coordination, antenne) cohérents : l'antenne impose sa coordination ; ErreurCommunique si elles se contredisent.

    ``cible`` (``national``, ``coordination``, ``antenne``) est le choix de l'auteur dans la modale. Il fait foi : ``coordination`` sans
    coordination ou ``antenne`` sans antenne est refusé (jamais élargi en silence au niveau national) ; ``national`` ignore les listes.
    ``None`` (appel sans choix explicite) : le ciblage se déduit de ce qui est fourni, comme avant."""
    if cible is not None:
        if cible not in CIBLES:
            raise ErreurCommunique(_("Choisissez qui reçoit le communiqué."), 'cible')
        if cible == 'national':
            return None, None
        if cible == 'coordination':
            if coordination is None:
                raise ErreurCommunique(_("Choisissez la coordination qui reçoit le communiqué."), 'coordination')
            antenne = None
        elif antenne is None:
            raise ErreurCommunique(_("Choisissez l'antenne qui reçoit le communiqué."), 'antenne')
    if antenne is not None:
        if coordination is not None and antenne.coordination_id != coordination.pk:
            raise ErreurCommunique(_("Cette antenne n'appartient pas à la coordination choisie."))
        if antenne.coordination_id is None:
            raise ErreurCommunique(_("Cette antenne n'a pas de coordination : elle ne peut pas être ciblée."))
        coordination = Province.objects.get(pk=antenne.coordination_id)
    return coordination, antenne


@transaction.atomic
def publier(auteur, titre, message, coordination=None, antenne=None, cible=None):
    """Publie un communiqué et notifie ses destinataires ; retourne le Communique.

    PermissionDenied si `auteur` ne peut pas publier ; ErreurCommunique si le titre (120 au plus), le message (5000 au plus) ou le ciblage
    est invalide (rien n'est écrit ; voir ``_cible`` pour ``cible``). Journalisé (F-70) avec le nombre de destinataires."""
    if not peut_publier(auteur):
        raise PermissionDenied
    titre, message = (titre or '').strip(), (message or '').strip()
    if not titre or len(titre) > TITRE_MAX:
        raise ErreurCommunique(_("Le titre est obligatoire (120 caractères au plus)."), 'titre')
    if not message or len(message) > MESSAGE_MAX:
        raise ErreurCommunique(_("Le message est obligatoire (5000 caractères au plus)."), 'message')
    coordination, antenne = _cible(coordination, antenne, cible)
    communique = Communique.objects.create(user=auteur, titre=titre, message=message, publie_le=timezone.now(),
                                           province=coordination, antenne=antenne)
    destinataires = list(destinataires_ids(communique))
    Notification.objects.bulk_create([
        Notification(user_id=compte_id, titre=_("Communiqué : %(titre)s") % {'titre': titre}, description=message[:500])
        for compte_id in destinataires], batch_size=500)
    journaliser(auteur, JournalAction.Action.CREATION, communique,
                apres={'type': 'communique', 'coordination': getattr(coordination, 'pk', None),
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


def _non_lus(jeu, user):
    """SEULE règle du « non lu » (liste, filtre, compteur, suivant) : ni écrit par `user`, ni publié avant la création de son compte
    (``date_joined`` : l'historique d'avant son arrivée est considéré lu), ni déjà lu PAR lui."""
    return jeu.exclude(user=user).filter(publie_le__gte=user.date_joined).filter(_non_lu(user))


def nombre_non_lus(user):
    """Communiqués visibles non lus par `user` (compteur du badge) : même règle que la liste, voir ``_non_lus``."""
    if user is None or not user.is_authenticated:
        return 0
    return _non_lus(communiques_visibles(user), user).count()


def suivant_non_lu(user, apres=None):
    """Le communiqué non lu le plus récent visible par `user`, hors `apres` (celui qu'on vient de lire) ; ``None`` s'il n'en reste pas."""
    if user is None or not user.is_authenticated:
        return None
    jeu = _non_lus(communiques_visibles(user), user).select_related('user', 'province', 'antenne')
    if apres is not None:
        jeu = jeu.exclude(pk=apres.pk)
    return jeu.order_by('-publie_le', '-pk').first()


def est_lu(user, communique):
    """Vrai si `communique` est lu pour `user` selon la règle unique (auteur, antérieur au compte, ou lecture enregistrée)."""
    return (communique.user_id == user.pk or (communique.publie_le is not None and communique.publie_le < user.date_joined)
            or LectureCommunique.objects.filter(compte=user, communique=communique).exists())


def titre_affiche(communique):
    """Titre à montrer : le titre, ou les 80 premiers caractères du message pour un ancien communiqué sans titre."""
    titre = (communique.titre or '').strip()
    return titre or (communique.message or '').strip()[:80] or _("Communiqué")


def nombres_liste(user, filtres=None):
    """Nombres des puces « Tous » (``tous``) et « Non lus » (``non_lus``), selon les filtres ``q``, ``coordination``, ``antenne`` (sans ``etat``)."""
    filtres = {cle: valeur for cle, valeur in (filtres or {}).items() if cle != 'etat'}
    jeu = _filtrer(communiques_visibles(user), filtres)
    return {'tous': jeu.count(), 'non_lus': _non_lus(jeu, user).count()}


def marquer_lu(user, communique):
    """Marque `communique` lu pour `user` ; retourne True à la première lecture. Communique.DoesNotExist s'il n'est pas visible (404)."""
    if not communiques_visibles(user).filter(pk=communique.pk).exists():
        raise Communique.DoesNotExist
    _lecture, cree = LectureCommunique.objects.get_or_create(compte=user, communique=communique)
    return cree


def _filtrer(jeu, filtres):
    q = (filtres.get('q') or '').strip()[:100]
    if q:
        jeu = jeu.filter(Q(titre__icontains=q) | Q(message__icontains=q))
    for cle, champ in (('coordination', 'province_id'), ('antenne', 'antenne_id')):
        try:
            valeur = int(filtres.get(cle) or 0)
        except (TypeError, ValueError):
            valeur = 0
        if 0 < valeur <= 2**31 - 1:
            jeu = jeu.filter(**{champ: valeur})
    return jeu


def lister_communiques(user, filtres=None, numero_page=None, par_page=PAR_PAGE):
    """Page de communiqués visibles (récents d'abord), chacun portant ``lu`` (règle unique, voir ``_non_lus``) et ``titre_affiche``. Filtres :
    ``q`` (titre, message), ``etat`` (« non_lus »), ``coordination`` et ``antenne`` (identifiants). Page illisible ou hors bornes :
    première ou dernière page."""
    filtres = filtres or {}
    jeu = _filtrer(communiques_visibles(user).select_related('user', 'province', 'antenne'), filtres)
    if filtres.get('etat') == 'non_lus':
        jeu = _non_lus(jeu, user)
    jeu = jeu.annotate(lu_par_moi=Exists(LectureCommunique.objects.filter(compte=user, communique=OuterRef('pk')))).order_by('-publie_le', '-pk')
    page = Paginator(jeu, par_page).get_page(numero_page)
    page.object_list = list(page.object_list)
    for communique in page.object_list:
        communique.lu = bool(communique.lu_par_moi or communique.user_id == user.pk
                             or (communique.publie_le is not None and communique.publie_le < user.date_joined))
        communique.titre_affiche = titre_affiche(communique)
    return page
