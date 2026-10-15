"""Rôle et périmètre affichés par la coque, et périmètre des notifications de la barre du haut.

Les rôles viennent des nominations (compte/services/droits.py).
"""
from django.utils.translation import gettext as _


def role_et_perimetre(user):
    """(rôle, lieu) affichés en bas du menu ; le périmètre s'exerce toujours quelque part.

    Avec une nomination : le libellé du rôle et son lieu (antenne, coordination, ou « National »). Sans nomination : le
    super-utilisateur, ou « Compte » rattaché à l'antenne ou à la coordination de sa fiche membre."""
    from compte import roles
    from compte.services.droits import profil_de
    profil = profil_de(user)
    if profil.mode == 'su':
        return _('Super-utilisateur'), _('National')
    if profil.mode == 'nomination':
        nomination = profil.nomination
        lieu = (nomination.antenne.nom if nomination.antenne_id else nomination.coordination.nom if nomination.coordination_id
                else _('National') if profil.role != roles.ED else '')
        return roles.LIBELLES[profil.role], lieu or ''
    from coptapp.models import Membre
    membre = Membre.objects.filter(id=user.membreId).select_related('antenne', 'province').first() if user.membreId else None
    lieu = ''
    if membre is not None:
        lieu = (membre.antenne.nom if membre.antenne else '') or (membre.province.nom if membre.province else '')
    return _('Compte'), lieu


def voit_toutes_notifications(user):
    """SU, rôle PR, ou (compte sans nomination, droits hérités actifs) privilege5."""
    from compte.services.droits import profil_de
    profil = profil_de(user)
    return profil.mode == 'su' or (profil.mode == 'nomination' and profil.role == 'PR') or (
        profil.mode == 'herite' and bool(user.privilege5))


def notifications_du_perimetre(user):
    """Notifications visibles par `user` (matrice § 4.3, § 4.2) :
    - SU : toutes ; PR (et privilege5 hérité) : toutes sauf « Nouveau message du site » ;
    - ED : seulement « Nouveau message du site » (F-62) ;
    - VN, VP, VA : les siennes, celles des dossiers (membres) de leur périmètre et celles des comptes qu'ils ont nommés ;
    - AT : les siennes (ses dossiers : renvois, demandes) ; VI : aucune ;
    - compte sans nomination : les siennes."""
    from django.db.models import Q

    from compte import roles
    from compte.models import Nomination
    from compte.services.droits import membres_du_perimetre, profil_de
    from coptapp.models import Notification
    from virtrine.services.contact import TITRE_NOTIFICATION
    profil = profil_de(user)
    messages_site = Q(titre=TITRE_NOTIFICATION, user__isnull=True)  # « Nouveau message du site » : ED et SU seulement (F-62)
    if profil.mode == 'su':
        return Notification.objects.all()
    if voit_toutes_notifications(user):  # PR, ou droits hérités (privilege5) : tout sauf les messages du site
        return Notification.objects.exclude(messages_site)
    if profil.mode == 'aucun':
        return Notification.objects.none()
    if profil.mode == 'nomination':
        if profil.role == roles.ED:
            return Notification.objects.filter(messages_site)
        if profil.role == roles.VI:
            return Notification.objects.none()
        if profil.role in (roles.VN, roles.VP, roles.VA):
            nommes = Nomination.objects.filter(nomme_par=user, active=True).values('compte_id')
            return Notification.objects.filter(
                Q(user=user) | Q(membre__in=membres_du_perimetre(user).values('pk')) | Q(user__in=nommes)).distinct()
    return Notification.objects.filter(user=user)


def donnees_coque(user, nombre=5):
    """Données de la barre du haut : (total non lues, dernières non lues, rôle, périmètre)."""
    non_lues = notifications_du_perimetre(user).exclude(is_validate=True)
    role, lieu = role_et_perimetre(user)
    return non_lues.count(), list(non_lues.select_related('membre').order_by('-id')[:nombre]), role, lieu
