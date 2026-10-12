"""Connexions, déconnexions, échecs et blocages dans le journal d'activités (F-70). Aucun mot de passe."""
from axes.helpers import get_client_ip_address
from axes.signals import user_locked_out
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from compte.models import JournalAction
from compte.services.journal import journaliser


def _ip(request):
    return get_client_ip_address(request) if request is not None else None


@receiver(user_logged_in)
def journaliser_connexion(sender, request, user, **kwargs):
    journaliser(user, JournalAction.Action.CONNEXION, user, apres={'ip': _ip(request)})


@receiver(user_logged_out)
def journaliser_deconnexion(sender, request, user, **kwargs):
    if user is not None:
        journaliser(user, JournalAction.Action.DECONNEXION, user, apres={'ip': _ip(request)})


@receiver(user_login_failed)
def journaliser_echec(sender, credentials, request=None, **kwargs):
    # Seul le pseudo est retenu : jamais le mot de passe présent dans `credentials`.
    pseudo = str((credentials or {}).get('username') or '')[:150]
    journaliser(None, JournalAction.Action.ECHEC_CONNEXION, libelle=pseudo, apres={'ip': _ip(request)})


@receiver(user_locked_out)
def journaliser_blocage(sender, request, username, ip_address, **kwargs):
    journaliser(None, JournalAction.Action.VERROUILLAGE_CONNEXION, libelle=str(username or '')[:150],
                apres={'ip': ip_address})
