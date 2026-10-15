"""Verrouillage de l'application (F-07, cahier des charges § 5.1 et § 4.3 : super-utilisateur seul).

L'état est UNE ligne (``compte.EtatApplication``, pk=1). ``etat()`` ne fait que LIRE (le middleware l'appelle à chaque requête, sans
cache) ; ``verrouiller`` et ``deverrouiller`` écrivent sous ``select_for_update`` et journalisent (auteur, avant / après, motif).
Le message du super-utilisateur est le seul texte exposé aux utilisateurs bloqués ; le motif, l'auteur et la date restent internes.
Ne pas confondre avec ``compte.services.verrou`` (blocage d'une adresse IP après des échecs de connexion).
"""
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from compte.models import EtatApplication, JournalAction
from compte.services.journal import journaliser

logger = logging.getLogger(__name__)
MESSAGE_MAX = 500
MOTIF_MAX = 500
# /gestion-technique/ n'est PAS exempté : son formulaire de connexion accepterait un compte non SU pendant le verrou. Un SU se connecte
# par /connexion/ puis atteint l'administration (le middleware le laisse passer).
PREFIXES_EXEMPTES = ('/connexion/', '/deconnexion/')
SESSIONS_MAX = 500  # sessions examinées au plus pour le décompte annoncé avant de verrouiller


class RegleVerrou(ValueError):
    """Message ou motif invalide, ou état incohérent avec la demande."""


def etat():
    """État courant, LU en base (jamais écrit ici ; jamais de cache). Sans ligne (base vidée), une instance déverrouillée non enregistrée."""
    return EtatApplication.objects.filter(pk=1).first() or EtatApplication(pk=1)


def est_verrouillee():
    return etat().verrouillee


def message_public():
    """Le message saisi par le super-utilisateur, seul texte montré aux utilisateurs bloqués (jamais le motif, l'auteur ni la date)."""
    return etat().message


def chemin_exempte(chemin):
    """Chemins qui passent TOUJOURS, même verrouillée : fichiers statiques, connexion, déconnexion. `chemin` est un ``path_info``
    (sans préfixe de script) : l'application peut être servie sous un sous-dossier (Passenger)."""
    statique = '/' + settings.STATIC_URL.strip('/') + '/'
    return chemin.startswith(statique) or chemin.startswith(PREFIXES_EXEMPTES)


def _controler_super_utilisateur(auteur):
    if not (auteur is not None and getattr(auteur, 'pk', None) and auteur.is_active and auteur.is_superuser):
        raise PermissionDenied


@transaction.atomic
def verrouiller(auteur, message, motif=''):
    """Verrouille l'application. Réservé aux super-utilisateurs (PermissionDenied sinon). Message OBLIGATOIRE, 500 caractères au plus,
    montré aux utilisateurs bloqués ; motif interne facultatif (journal seulement). Déjà verrouillée : le message et le motif sont remplacés (journalisé), l'heure de début et l'auteur d'origine sont conservés.
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
    if not ligne.verrouillee:  # depuis et par ne changent QU'au passage déverrouillée -> verrouillée ; re-verrouiller remplace le message seul
        ligne.depuis, ligne.par = timezone.now(), auteur
    ligne.verrouillee, ligne.message, ligne.motif = True, message, motif
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


# ---------------------------------------------------------------- lecture pour l'écran (la vue reste mince)

ACTIONS_VERROU = (JournalAction.Action.VERROUILLAGE_APPLICATION, JournalAction.Action.DEVERROUILLAGE_APPLICATION)


def duree_en_texte(ecart):
    """« 3 j 4 h », « 2 h 15 », « 35 min » à partir d'un timedelta (unités traduisibles)."""
    minutes = max(int(ecart.total_seconds() // 60), 0)
    jours, reste = divmod(minutes, 1440)
    heures, minutes = divmod(reste, 60)
    if jours:
        return _("%(j)s j %(h)s h") % {'j': jours, 'h': heures}
    if heures:
        return _("%(h)s h %(m)02d") % {'h': heures, 'm': minutes}
    return _("%(m)s min") % {'m': minutes}


def sessions_ouvertes():
    """(super-utilisateurs connectés, autres comptes connectés) parmi les sessions non expirées : les autres seront fermés à leur prochaine
    requête une fois verrouillé. Borné à SESSIONS_MAX sessions (les plus récentes) ; une session illisible est ignorée et signalée."""
    ids_su = {str(pk) for pk in get_user_model().objects.filter(is_superuser=True).values_list('pk', flat=True)}
    su = autres = 0
    sessions = Session.objects.filter(expire_date__gt=timezone.now()).order_by('-expire_date').only('session_data')[:SESSIONS_MAX]
    for session in sessions:
        try:
            auteur = str(session.get_decoded().get('_auth_user_id', ''))
        except (ValueError, TypeError, KeyError, AttributeError) as erreur:  # session illisible (clé secrète changée, données corrompues)
            logger.warning("Session illisible ignorée dans le décompte du verrouillage : %s", erreur)
            continue
        if not auteur:
            continue
        if auteur in ids_su:
            su += 1
        else:
            autres += 1
    return su, autres


def historique_verrou(limite=5):
    """Derniers changements d'état (journal), du plus récent au plus ancien ; durée d'un verrouillage rapportée à son déverrouillage."""
    lignes = list(JournalAction.objects.filter(action__in=ACTIONS_VERROU).select_related('auteur').defer('avant', 'apres')
                  .order_by('-date', '-id')[:limite + 1])
    entrees = []
    for i, ligne in enumerate(lignes[:limite]):
        verrouillage = ligne.action == JournalAction.Action.VERROUILLAGE_APPLICATION
        precedent = next((x for x in lignes[i + 1:] if x.action == JournalAction.Action.VERROUILLAGE_APPLICATION), None)
        entrees.append({'verrouillage': verrouillage, 'date': ligne.date, 'auteur': ligne.auteur.get_username() if ligne.auteur else '',
                        'motif': ligne.motif, 'duree': duree_en_texte(ligne.date - precedent.date) if (not verrouillage and precedent) else ''})
    return entrees


def contexte_etat(courant):
    """Contexte de la zone d'état de l'écran : état, historique, décompte des sessions, durée du verrouillage en cours."""
    contexte = {'etat': courant, 'historique': historique_verrou()}
    contexte['sessions_su'], contexte['sessions_hors_su'] = sessions_ouvertes()
    contexte['sessions_total'] = contexte['sessions_su'] + contexte['sessions_hors_su']
    if courant.verrouillee and courant.depuis:
        contexte['duree'] = duree_en_texte(timezone.now() - courant.depuis)
    contexte['derniere_periode'] = next((e for e in contexte['historique'] if not e['verrouillage'] and e['duree']), None)
    return contexte
