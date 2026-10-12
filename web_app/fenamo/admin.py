"""Site d'administration technique (/gestion-technique/) réservé aux super-utilisateurs (rôle SU)."""
from django.contrib.admin import AdminSite


class SiteAdminFenamo(AdminSite):
    site_header = 'FENAMO-RDC : gestion technique'
    site_title = 'FENAMO-RDC'

    def has_permission(self, request):
        user = request.user
        return user.is_active and user.is_superuser
