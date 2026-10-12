"""Attribution des privilèges hérités (privilege1 à privilege5). Correctif minimal avant les rôles (sous-lot 2e)."""
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils.translation import gettext as _

from compte.models import JournalAction
from compte.services.journal import journaliser

PRIVILEGES = ('privilege1', 'privilege2', 'privilege3', 'privilege4', 'privilege5')


@transaction.atomic
def attribuer_privileges(auteur, compte, membre, donnees):
    """Réservé aux super-utilisateurs (PermissionDenied sinon). `donnees` : QueryDict ou dict ;
    un privilège présent est accordé, absent est retiré. Journalise l'avant/après."""
    if not (auteur.is_authenticated and auteur.is_active and auteur.is_superuser):
        raise PermissionDenied
    avant = {p: bool(getattr(compte, p)) for p in PRIVILEGES}
    for p in PRIVILEGES:
        setattr(compte, p, p in donnees)
    compte.save(update_fields=list(PRIVILEGES))
    apres = {p: bool(getattr(compte, p)) for p in PRIVILEGES}
    journaliser(auteur, JournalAction.Action.ATTRIBUTION_PRIVILEGES, compte, avant=avant, apres=apres,
                libelle=compte.username)
    return compte
