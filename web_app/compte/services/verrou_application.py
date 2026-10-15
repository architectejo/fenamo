"""Verrouillage de l'application (F-07, cahier des charges § 5.1 et § 4.3 : super-utilisateur seul).

L'état est UNE ligne (``compte.EtatApplication``, pk=1). ``etat()`` ne fait que LIRE (le middleware l'appelle à chaque requête, sans
cache) ; ``verrouiller`` et ``deverrouiller`` écrivent sous ``select_for_update`` et journalisent (auteur, avant / après, motif).
Le message du super-utilisateur est le seul texte exposé aux utilisateurs bloqués ; le motif, l'auteur et la date restent internes.
Ne pas confondre avec ``compte.services.verrou`` (blocage d'une adresse IP après des échecs de connexion).
"""
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from compte.models import EtatApplication, JournalAction
from compte.services.journal import journaliser

MESSAGE_MAX = 500
MOTIF_MAX = 500
PREFIXES_EXEMPTES = ('/connexion/', '/deconnexion/', '/gestion-technique/')


class RegleVerrou(ValueError):
    """Message ou motif invalide, ou état incohérent avec la demande."""


def etat():
    """État courant, LU en base (jamais écrit ici ; jamais de cache). Sans ligne (base vidée), une instance déverrouillée non enregistrée."""
    return EtatApplication.objects.filter(pk=1).select_related(None).first() or EtatApplication(pk=1)


def est_verrouillee():
    return etat().verrouillee


def message_public():
    """Le message saisi par le super-utilisateur, seul texte montré aux utilisateurs bloqués (jamais le motif, l'auteur ni la date)."""
    return etat().message


def chemin_exempte(chemin):
    """Chemins qui passent TOUJOURS, même verrouillée : fichiers statiques, connexion, déconnexion, administration technique."""
    statique = '/' + settings.STATIC_URL.strip('/') + '/'
    return chemin.startswith(statique) or chemin.startswith(PREFIXES_EXEMPTES)


def _controler_super_utilisateur(auteur):
    if not (auteur is not None and getattr(auteur, 'pk', None) and auteur.is_active and auteur.is_superuser):
        raise PermissionDenied


@transaction.atomic
def verrouiller(auteur, message, motif=''):
    """Verrouille l'application. Réservé aux super-utilisateurs (PermissionDenied sinon). Message OBLIGATOIRE, 500 caractères au plus,
    montré aux utilisateurs bloqués ; motif interne facultatif (journal seulement). Déjà verrouillée : le message est remplacé.
    Journalise VERROUILLAGE_APPLICATION (avant / après / motif)."""
    _controler_super_utilisateur(auteur)
    message, motif = (message or '').strip(), (motif or '').strip()
    if not message:
        raise RegleVerrou(_("Indiquez le message affiché aux utilisateurs."))
    if len(message) > MESSAGE_MAX or len(motif) > MOTIF_MAX:
        raise RegleVerrou(_("Le message et le motif sont limités à 500 caractères."))
    EtatApplication.objects.get_or_create(pk=1)
    ligne = EtatApplication.objects.select_for_update().get(pk=1)
    avant = {'verrouillee': ligne.verrouillee}
    ligne.verrouillee, ligne.message, ligne.motif, ligne.depuis, ligne.par = True, message, motif, timezone.now(), auteur
    ligne.save()
    journaliser(auteur, JournalAction.Action.VERROUILLAGE_APPLICATION, ligne, avant=avant, apres={'verrouillee': True, 'message': message},
                motif=motif, libelle=_("Application"))
    return ligne


@transaction.atomic
def deverrouiller(auteur, motif=''):
    """Déverrouille l'application ; retourne False (rien écrit, rien journalisé) si elle ne l'était pas.

    `auteur` : un super-utilisateur ; None n'est accepté QUE pour la commande d'urgence ``deverrouiller_application`` (journalisé sans
    auteur). Tout autre compte : PermissionDenied. Journalise DEVERROUILLAGE_APPLICATION (avant / après / motif)."""
    if auteur is not None:
        _controler_super_utilisateur(auteur)
    motif = (motif or '').strip()
    if len(motif) > MOTIF_MAX:
        raise RegleVerrou(_("Le motif est limité à 500 caractères."))
    EtatApplication.objects.get_or_create(pk=1)
    ligne = EtatApplication.objects.select_for_update().get(pk=1)
    if not ligne.verrouillee:
        return False
    ligne.verrouillee, ligne.message, ligne.motif, ligne.depuis, ligne.par = False, '', '', None, None
    ligne.save()
    journaliser(auteur, JournalAction.Action.DEVERROUILLAGE_APPLICATION, ligne, avant={'verrouillee': True}, apres={'verrouillee': False},
                motif=motif, libelle=_("Application"))
    return True
