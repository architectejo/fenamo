"""Site d'administration technique (/gestion-technique/) réservé aux super-utilisateurs (rôle SU)."""
from django.contrib.admin import AdminSite
from django.contrib.auth.decorators import login_not_required
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters

from compte.services.verrou import ip_bloquee


class SiteAdminFenamo(AdminSite):
    site_header = 'FENAMO-RDC : gestion technique'
    site_title = 'FENAMO-RDC'

    def has_permission(self, request):
        user = request.user
        return user.is_active and user.is_superuser

    @login_not_required  # la vue d'origine l'est aussi ; l'attribut doit être porté par la surcharge
    @method_decorator(sensitive_post_parameters('password'))
    def login(self, request, extra_context=None):
        """Même verrou par adresse IP que /connexion/ (F-01), en plus du verrou django-axes."""
        if request.method == 'POST' and ip_bloquee(request):
            return render(request, 'compte/verrou.html', status=429)
        return super().login(request, extra_context)
