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
    ``notifications``…) qui masqueraient les noms habituels. Les requêtes HTMX qui ne rendent pas la coque
    (fragments, modales) ne déclenchent aucune requête de base de données ici.
    """
    from fenamo.htmx import veut_fragment

    donnees = {}
    if hasattr(request, '_messages'):
        from django.contrib.messages import get_messages
        donnees['fn_messages'] = get_messages(request)
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated and not veut_fragment(request):
        from compte.services.perimetre import donnees_coque
        (donnees['fn_notifs_total'], donnees['fn_notifs'],
         donnees['fn_role'], donnees['fn_perimetre']) = donnees_coque(user)
    return donnees


def droits_menu(request):
    """Droits du compte pour le menu et la coque (variable ``fn_droits``) : rôle, libellé, ce qu'il peut ouvrir.

    Clés : role, role_libelle, est_su, voit_membres, voit_associations, voit_geographie, peut_creer_membre,
    peut_ecrire_referentiel, est_editeur, voit_journal (voir compte.services.droits.droits_menu). Aucune requête pour les requêtes
    HTMX qui ne rendent pas la coque, ni pour un anonyme."""
    from fenamo.htmx import veut_fragment

    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated or veut_fragment(request):
        return {}
    from compte.services.droits import droits_menu as calcul
    return {'fn_droits': calcul(user)}
