"""Décorateurs de droits communs (cahier des charges web § 4). La connexion est exigée par
LoginRequiredMiddleware ; ces décorateurs ajoutent le contrôle du rôle."""
from functools import wraps

from django.core.exceptions import PermissionDenied


def superuser_requis(vue):
    """Réserve la vue aux super-utilisateurs (rôle SU) : 403 sinon."""
    @wraps(vue)
    def enveloppe(request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_active and request.user.is_superuser):
            raise PermissionDenied
        return vue(request, *args, **kwargs)
    return enveloppe
