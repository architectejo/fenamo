"""Lecture de l'état de l'interrupteur « données réelles » du site (écran Contenu du site, super-utilisateur seul) : lecture seule, sans écriture."""
from django.contrib.contenttypes.models import ContentType

from compte.models import JournalAction
from compte.services.journal import identifiant_affichable
from virtrine.models import Config

CHAMP = 'donnees_reelles_actif'
HISTORIQUE = 5  # bascules montrées dans « Changements récents »
RECHERCHE = 30  # derniers changements de configuration examinés (le champ est cherché en Python : pas de recherche JSON propre à un moteur)


def _nom(auteur):
    return (auteur.get_full_name() or identifiant_affichable(auteur)) if auteur else ''


def etat_donnees_reelles():
    """Dictionnaire pour le gabarit : ``actif`` ; ``depuis`` (date du dernier changement), ``par`` (nom de l'auteur) et ``motif`` seulement si le
    journal (F-70) en garde la trace, sinon None / ''. ``historique`` : les 5 dernières bascules, la plus récente d'abord, chacune
    ``{actif, par, date, motif}`` (``par`` : nom complet, sinon identifiant masqué si initial). N'invente rien : un site jamais basculé
    n'a ni date ni auteur."""
    config = Config.objects.order_by('pk').first()  # jamais ``Config.instance()`` ici : il créerait la ligne lors d'un simple GET
    if config is None:
        return {'actif': False, 'depuis': None, 'par': '', 'motif': '', 'historique': []}
    etat = {'actif': config.donnees_reelles_actif, 'depuis': None, 'par': '', 'motif': '', 'historique': []}
    lignes = (JournalAction.objects.filter(action=JournalAction.Action.MODIFICATION, objet_type=ContentType.objects.get_for_model(Config, for_concrete_model=False), objet_id=config.pk)
              .select_related('auteur').order_by('-date', '-id')[:RECHERCHE])
    for ligne in lignes:
        apres = ligne.apres or {}
        if CHAMP in (apres.get('champs_modifies') or []):
            etat['historique'].append({'actif': bool(apres.get(CHAMP)), 'par': _nom(ligne.auteur), 'date': ligne.date, 'motif': ligne.motif})
            if len(etat['historique']) == HISTORIQUE:
                break
    if etat['historique']:
        derniere = etat['historique'][0]
        etat['depuis'], etat['par'], etat['motif'] = derniere['date'], derniere['par'], derniere['motif']
    return etat
