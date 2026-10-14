"""Contrôles de déploiement propres à FENAMO-RDC (``python manage.py check --deploy``)."""
from django.conf import settings
from django.core.checks import Tags, Warning, register


@register(Tags.security, deploy=True)
def droits_herites_en_production(app_configs, **kwargs):
    """Avertit quand les droits hérités (privilege1 à privilege5) restent actifs : en production, un compte sans nomination ne doit
    voir que sa propre fiche (FENAMO_DROITS_HERITES=False) une fois les nominations créées."""
    if getattr(settings, 'FENAMO_DROITS_HERITES', False):
        return [Warning(
            "FENAMO_DROITS_HERITES est actif : les comptes sans nomination gardent les droits hérités (privilege1 à privilege5).",
            hint="Créer les nominations (commande attribuer_roles_initiaux, écran Utilisateurs) puis mettre FENAMO_DROITS_HERITES=False dans .env.",
            id='fenamo.W001')]
    return []
