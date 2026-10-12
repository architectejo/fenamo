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


def _actif(user):
    return bool(user is not None and user.is_authenticated and user.is_active)


def est_editeur(user):
    """Éditeur du contenu du site (champ `editor`) ou super-utilisateur. Un visiteur (privilege4) n'écrit jamais.

    PROVISOIRE : remplacé par le rôle ED au sous-lot 2e.
    """
    return _actif(user) and (user.is_superuser or (bool(user.editor) and not user.privilege4))


def peut_ecrire_referentiel(user):
    """Écriture sur la géographie et les associations membres : SU ou privilege5, jamais en lecture seule (privilege4).

    PROVISOIRE : remplacé par les droits des rôles au sous-lot 2e.
    """
    return _actif(user) and (user.is_superuser or (bool(user.privilege5) and not user.privilege4))


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
