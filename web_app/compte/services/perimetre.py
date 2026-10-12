"""Rôle et périmètre affichés par la coque, et périmètre des notifications de la barre du haut.

PROVISOIRE : les rôles nommés (PR, VN, VP, VA, AT…) arrivent avec les nominations (F-02) et
compte/services/droits.py (sous-lot 2e). En attendant, seul le super-utilisateur est nommé ; les autres comptes
sont rattachés à l'antenne ou à la coordination de leur fiche membre.
"""
from django.utils.translation import gettext as _


def role_et_perimetre(user):
    """(rôle, lieu) affichés en bas du menu ; le périmètre s'exerce toujours quelque part."""
    if user.is_superuser:
        return _('Super-utilisateur'), _('National')
    from coptapp.models import Membre
    membre = Membre.objects.filter(id=user.membreId).select_related('antenne', 'province').first() if user.membreId else None
    lieu = ''
    if membre is not None:
        lieu = (membre.antenne.nom if membre.antenne else '') or (membre.province.nom if membre.province else '')
    return _('Compte'), lieu


def notifications_du_perimetre(user):
    """Notifications visibles par `user` : toutes pour un SU ou privilege5, les siennes sinon.

    Même périmètre que l'écran hérité des notifications (coptapp.views.myNotify, au filtre par fiche près).
    """
    from coptapp.models import Notification
    if user.is_superuser or user.privilege5:
        return Notification.objects.all()
    return Notification.objects.filter(user=user)


def donnees_coque(user, nombre=5):
    """Données de la barre du haut : (total non lues, dernières non lues, rôle, périmètre)."""
    non_lues = notifications_du_perimetre(user).exclude(is_validate=True)
    role, lieu = role_et_perimetre(user)
    return non_lues.count(), list(non_lues.select_related('membre').order_by('-id')[:nombre]), role, lieu
