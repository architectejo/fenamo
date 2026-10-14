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


def est_editeur(user):
    """Éditeur du contenu du site : SU, rôle ED, ou champ hérité ``editor`` (compte sans nomination). Voir compte/services/droits.py."""
    from compte.services.droits import est_editeur as regle
    return regle(user)


def peut_ecrire_referentiel(user):
    """Écriture sur la géographie et les associations membres : SU, PR, VN (ou privilege5 hérité). Voir compte/services/droits.py."""
    from compte.services.droits import peut_ecrire_referentiel as regle
    return regle(user)


def editeur_requis(vue):
    """Réserve la vue aux éditeurs du site et aux SU : 403 sinon."""
    @wraps(vue)
    def enveloppe(request, *args, **kwargs):
        if not est_editeur(request.user):
            raise PermissionDenied
        return vue(request, *args, **kwargs)
    return enveloppe


def referentiel_ecriture_requis(vue):
    """Réserve la vue aux SU et au privilege5 (hors lecture seule) : 403 sinon."""
    @wraps(vue)
    def enveloppe(request, *args, **kwargs):
        if not peut_ecrire_referentiel(request.user):
            raise PermissionDenied
        return vue(request, *args, **kwargs)
    return enveloppe
