"""Espace mobile /mob/ : limitation des tentatives, mot de passe temporaire d'un membre, antirobot d'inscription.

Les échecs sont écrits dans le journal d'échecs de django-axes (``AccessFailureLog``) sous le pseudo ``mob:<identifiant>`` :
même table, même durée de blocage (``AXES_COOLOFF_TIME``) et mêmes seuils que la connexion de l'application web, et
``manage.py debloquer_ip`` les efface aussi. Aucun nouveau modèle.
"""
import secrets
from datetime import timedelta

from axes.helpers import get_client_ip_address
from axes.models import AccessFailureLog
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from compte.models import JournalAction
from compte.services.journal import journaliser

PREFIXE = 'mob:'
INSCRIPTION = 'mob-inscription'
ALPHABET = 'abcdefghjkmnpqrstuvwxyz23456789'  # sans caractères ambigus (0/o, 1/l/i)


def _depuis():
    return timezone.now() - settings.AXES_COOLOFF_TIME


def _journal(requete, pseudo, chemin):
    return AccessFailureLog.objects.create(
        user_agent=(requete.META.get('HTTP_USER_AGENT') or '')[:255], ip_address=get_client_ip_address(requete),
        username=pseudo[:255], http_accept='', path_info=chemin, attempt_time=timezone.now(), locked_out=False)


def connexion_bloquee(requete, identifiant):
    """Vrai si l'identifiant a cumulé AXES_FAILURE_LIMIT échecs depuis cette adresse IP, ou si l'adresse a cumulé
    IP_ECHECS_MAX échecs mobiles (tous identifiants confondus), pendant la durée de blocage. Les identifiants inconnus
    comptent aussi : on ne peut pas deviner des identifiants à la chaîne."""
    ip = get_client_ip_address(requete)
    recents = AccessFailureLog.objects.filter(ip_address=ip, attempt_time__gte=_depuis(), username__startswith=PREFIXE)
    return (recents.filter(username=PREFIXE + identifiant.strip().lower()[:200]).count() >= settings.AXES_FAILURE_LIMIT
            or recents.count() >= settings.IP_ECHECS_MAX)


def noter_echec(requete, identifiant):
    _journal(requete, PREFIXE + identifiant.strip().lower()[:200], requete.path)


def effacer_echecs(requete, identifiant):
    AccessFailureLog.objects.filter(ip_address=get_client_ip_address(requete),
                                    username=PREFIXE + identifiant.strip().lower()[:200]).delete()


def inscriptions_trop_nombreuses(requete):
    """Antirobot : plus de MOB_INSCRIPTIONS_PAR_HEURE inscriptions depuis la même adresse IP en une heure."""
    limite = getattr(settings, 'MOB_INSCRIPTIONS_PAR_HEURE', 5)
    depuis = timezone.now() - timedelta(hours=1)
    return AccessFailureLog.objects.filter(ip_address=get_client_ip_address(requete), username=INSCRIPTION,
                                           attempt_time__gte=depuis).count() >= limite


def noter_inscription(requete):
    _journal(requete, INSCRIPTION, requete.path)


def mot_de_passe_temporaire(longueur=8):
    return ''.join(secrets.choice(ALPHABET) for _ in range(longueur))


@transaction.atomic
def definir_mot_de_passe_membre(auteur, membre, mot_de_passe=None):
    """Définit le mot de passe de l'espace mobile de `membre` et le retourne EN CLAIR (à afficher UNE seule fois).

    Un mot de passe temporaire aléatoire est généré si `mot_de_passe` est None. Seul le hachage est enregistré ; le
    journal garde l'auteur, la date et le membre, JAMAIS le mot de passe. Droits : SU, ou compte qui peut enregistrer
    des membres (jamais en lecture seule) et voit ce membre dans son périmètre ; PermissionDenied sinon.
    """
    from coptapp.services.droits_provisoires import droits_membre, membres_du_perimetre
    if not auteur.is_superuser and not (
        membres_du_perimetre(auteur).filter(pk=membre.pk).exists() and droits_membre(auteur, membre)['peut_creer_membre']
    ):
        raise PermissionDenied
    clair = mot_de_passe or mot_de_passe_temporaire()
    membre.password = make_password(clair)
    membre.save(update_fields=['password', 'mise_a_jour'])
    journaliser(auteur, JournalAction.Action.CHANGEMENT_MOT_DE_PASSE, membre, apres={'defini': True},
                motif="Mot de passe de l'espace mobile défini (temporaire)", libelle=membre.nom or '')
    return clair
