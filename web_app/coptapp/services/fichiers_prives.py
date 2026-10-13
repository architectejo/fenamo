"""Déplacement des fichiers privés de MEDIA_ROOT vers PRIVATE_MEDIA_ROOT (cahier des charges web § 9.4).

Champs concernés : Membre.fiche_id, Membre.photo, AssociationMembre.capture_justice, AssociationMembre.preuve_de_paiement
(et la vignette ``xxx_vignette.ext`` des images). Le nom stocké en base ne change pas : seul l'emplacement change.

Rejouable : pour chaque fichier, copie vers la destination, VÉRIFIE les hachages SHA-256 des deux copies et seulement
alors supprime la source. Jamais de perte : un hachage différent, une destination déjà occupée par un autre contenu ou
une source illisible sont signalés et laissés intacts.
"""
import hashlib
import shutil
from pathlib import Path

from django.conf import settings

from coptapp.models import AssociationMembre, Membre
from coptapp.validators import nom_vignette

CHAMPS_PRIVES = (
    (Membre, 'fiche_id', False),
    (Membre, 'photo', True),
    (AssociationMembre, 'capture_justice', True),
    (AssociationMembre, 'preuve_de_paiement', True),
)


def hachage(chemin):
    h = hashlib.sha256()
    with open(chemin, 'rb') as f:
        for bloc in iter(lambda: f.read(1024 * 1024), b''):
            h.update(bloc)
    return h.hexdigest()


def _noms_a_deplacer():
    for modele, champ, avec_vignette in CHAMPS_PRIVES:
        for nom in modele._default_manager.exclude(**{champ: ''}).exclude(**{f'{champ}__isnull': True}).values_list(champ, flat=True):
            yield f'{modele.__name__}.{champ}', nom
            if avec_vignette:
                yield f'{modele.__name__}.{champ}', nom_vignette(nom)


def deplacer_fichiers_prives(dry_run=False, source=None, destination=None):
    """Retourne un dictionnaire de listes : deplaces, deja_deplaces, absents, conflits (nom, champ)."""
    source = Path(source or settings.MEDIA_ROOT).resolve()
    destination = Path(destination or settings.PRIVATE_MEDIA_ROOT).resolve()
    rapport = {'deplaces': [], 'deja_deplaces': [], 'absents': [], 'conflits': []}
    if source == destination:
        return rapport
    for champ, nom in _noms_a_deplacer():
        origine = (source / nom).resolve()
        cible = (destination / nom).resolve()
        if source not in origine.parents or destination not in cible.parents:
            rapport['conflits'].append((champ, nom, 'chemin hors des dossiers'))  # nom suspect : jamais touché
            continue
        if not origine.exists():
            rapport['deja_deplaces' if cible.exists() else 'absents'].append((champ, nom))
            continue
        if cible.exists():
            if hachage(cible) != hachage(origine):
                rapport['conflits'].append((champ, nom, 'destination différente'))
                continue
        elif not dry_run:
            cible.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origine, cible)
            if hachage(cible) != hachage(origine):
                cible.unlink()
                rapport['conflits'].append((champ, nom, 'copie différente'))
                continue
        if not dry_run:
            origine.unlink()  # copie vérifiée (ou déjà identique) : la source peut disparaître
        rapport['deplaces'].append((champ, nom))
    return rapport
