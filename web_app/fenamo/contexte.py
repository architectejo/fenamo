"""Variables de gabarit communes à toutes les pages."""
from django.utils.translation import gettext as _


def textes_interface(request):
    """Messages d'erreur réseau lus par static/js/fenamo.js (sérialisés par json_script, sans script inline)."""
    return {
        'textes_interface': {
            'connexionPerdue': _('Connexion perdue, réessayez'),
            'erreurServeur': _('Erreur du serveur, réessayez'),
            'refuse': _('Accès refusé'),
            'introuvable': _('Page ou élément introuvable'),
        },
    }


def coque(request):
    """Données de la coque (barre du haut) : messages Django et cloche de notifications.

    Noms préfixés ``fn_`` : les vues héritées passent ``locals()`` au gabarit (variables ``messages``,
    ``notifications``…) qui masqueraient les noms habituels.
    """
    donnees = {}
    if hasattr(request, '_messages'):
        from django.contrib.messages import get_messages
        donnees['fn_messages'] = get_messages(request)
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated:
        from coptapp.models import Notification
        # Mêmes périmètre que l'écran hérité des notifications : tout pour les SU, les siennes sinon.
        notifications = Notification.objects.all() if (user.is_superuser or user.privilege5) else Notification.objects.filter(user=user)
        non_lues = notifications.exclude(is_validate=True)
        donnees['fn_notifs_total'] = non_lues.count()
        donnees['fn_notifs'] = list(non_lues.select_related('membre').order_by('-id')[:5])
        donnees['fn_role'], donnees['fn_perimetre'] = _role_et_perimetre(user)
    return donnees


def _role_et_perimetre(user):
    """Rôle et périmètre affichés en bas du menu (le périmètre s'exerce toujours quelque part).

    Provisoire : les rôles nommés (PR, VN, VP, VA, AT…) arrivent avec les nominations (F-02) ; en attendant,
    seul le super-utilisateur est nommé, les autres comptes sont rattachés à l'antenne ou à la coordination de leur fiche membre.
    """
    if user.is_superuser:
        return _('Super-utilisateur'), _('National')
    from coptapp.models import Membre
    membre = Membre.objects.filter(id=user.membreId).select_related('antenne', 'province').first() if user.membreId else None
    lieu = ''
    if membre is not None:
        lieu = (membre.antenne.nom if membre.antenne else '') or (membre.province.nom if membre.province else '')
    return _('Compte'), lieu
