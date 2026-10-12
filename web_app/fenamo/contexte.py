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
