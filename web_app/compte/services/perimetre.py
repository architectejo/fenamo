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


def notifications_du_perimetre(user):
    """Notifications visibles par `user` : toutes pour un SU, un PR (ou privilege5 hérité), les siennes sinon.

    Même périmètre que l'écran hérité des notifications (coptapp.views.myNotify, au filtre par fiche près)."""
    from compte.services.droits import profil_de
    from coptapp.models import Notification
    profil = profil_de(user)
    voit_tout = profil.mode == 'su' or (profil.mode == 'nomination' and profil.role == 'PR') or (
        profil.mode == 'herite' and bool(user.privilege5))
    if voit_tout:
        return Notification.objects.all()
    return Notification.objects.filter(user=user)


def donnees_coque(user, nombre=5):
    """Données de la barre du haut : (total non lues, dernières non lues, rôle, périmètre)."""
    non_lues = notifications_du_perimetre(user).exclude(is_validate=True)
    role, lieu = role_et_perimetre(user)
    return non_lues.count(), list(non_lues.select_related('membre').order_by('-id')[:nombre]), role, lieu
