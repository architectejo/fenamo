"""Compléments au verrou django-axes : normalisation du pseudo et seuil par adresse IP seule."""
from axes.helpers import get_client_ip_address
from axes.models import AccessFailureLog
from django.conf import settings
from django.utils import timezone


def nom_utilisateur_normalise(request, credentials=None):
    """Pseudo servant de clé de verrou : sans espaces autour, en minuscules."""
    brut = (credentials or {}).get('username') or getattr(request, 'POST', {}).get('username') or ''
    return brut.strip().lower()


def ip_bloquee(request):
    """Vrai si l'adresse IP a cumulé IP_ECHECS_MAX échecs de CONNEXION WEB (tous pseudos confondus) pendant la durée de blocage.

    Les lignes de l'espace mobile (pseudos ``mob:…`` et ``mob-inscription``) sont exclues : les échecs et les inscriptions
    de /mob/ ne bloquent pas /connexion/. /mob/ a son propre compteur (``compte.services.mobile``).
    """
    depuis = timezone.now() - settings.AXES_COOLOFF_TIME
    echecs = AccessFailureLog.objects.filter(
        ip_address=get_client_ip_address(request), attempt_time__gte=depuis).exclude(username__startswith='mob')
    return echecs.count() >= settings.IP_ECHECS_MAX
