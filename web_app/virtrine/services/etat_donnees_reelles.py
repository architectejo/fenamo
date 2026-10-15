"""Lecture de l'état de l'interrupteur « données réelles » du site (écran Contenu du site, super-utilisateur seul) : lecture seule, sans écriture."""
from django.contrib.contenttypes.models import ContentType

from compte.models import JournalAction
from virtrine.models import Config

CHAMP = 'donnees_reelles_actif'
RECHERCHE = 30  # derniers changements de configuration examinés (le champ est cherché en Python : pas de recherche JSON propre à un moteur)


def etat_donnees_reelles():
    """Dictionnaire pour le gabarit : ``actif`` ; ``depuis`` (date du dernier changement), ``par`` (nom de l'auteur) et ``motif`` seulement si le
    journal (F-70) en garde la trace, sinon None / ''. N'invente rien : un site jamais basculé n'a ni date ni auteur."""
    config = Config.instance()
    etat = {'actif': config.donnees_reelles_actif, 'depuis': None, 'par': '', 'motif': ''}
    lignes = (JournalAction.objects.filter(action=JournalAction.Action.MODIFICATION, objet_type=ContentType.objects.get_for_model(Config, for_concrete_model=False), objet_id=config.pk)
              .select_related('auteur').order_by('-date', '-id')[:RECHERCHE])
    for ligne in lignes:
        if CHAMP in ((ligne.apres or {}).get('champs_modifies') or []):
            etat['depuis'] = ligne.date
            etat['par'] = (ligne.auteur.get_full_name() or ligne.auteur.get_username()) if ligne.auteur else ''
            etat['motif'] = ligne.motif
            break
    return etat
