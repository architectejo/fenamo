"""Géographie : coordinations provinciales, antennes et « villes » héritées (sous-lot 2d, F-10 et F-11).

Le niveau « ville » n'existe plus dans la charte : chaque ville héritée a une ANTENNE (``Antenne.ville_origine``). Tant que
``mobapp`` et les écrans hérités lisent ``ville``, tout rattachement d'un membre ou d'une association membre à une ville écrit
ENSEMBLE ``ville`` et ``antenne`` : ce module est le SEUL endroit qui écrit ``ville`` sur un membre ou une association.
"""
from django.db import transaction

from compte.models import JournalAction
from compte.services.journal import journaliser
from coptapp.models import Antenne, Province


def coordination_par_code(code):
    """Coordination dont le code officiel est `code` (casse et espaces ignorés) ; None si le code est vide ou inconnu."""
    code = (code or '').strip().upper()
    return Province.objects.filter(code=code).first() if code else None


def antenne_depuis_ville(ville, creer=False):
    """Antenne issue de `ville` (None si `ville` est None, ou si elle n'en a pas et que `creer` est faux).

    Avec ``creer=True`` l'antenne est créée au besoin (nom de la ville, coordination de la ville) : une ville ajoutée après la
    reprise des données reçoit ainsi son antenne. La contrainte d'unicité de ``ville_origine`` rend l'appel sûr en concurrence.
    """
    if ville is None:
        return None
    antenne = Antenne.objects.filter(ville_origine=ville).first()
    if antenne is None and creer:
        antenne, _cree = Antenne.objects.get_or_create(
            ville_origine=ville, defaults={'nom': ville.nom, 'coordination': ville.province})
    return antenne


def ville_depuis_antenne(antenne):
    """Ville héritée dont `antenne` est issue (None si l'antenne est nouvelle, sans ville d'origine)."""
    return antenne.ville_origine if antenne is not None else None


@transaction.atomic
def rattacher_ville(auteur, objet, ville):
    """Rattache `objet` (Membre ou AssociationMembre) à `ville` ET à l'antenne qui en est issue, dans UNE transaction.

    ``ville`` None détache les deux. Écrit seulement les colonnes concernées et journalise (avant / après, ville et antenne).
    `auteur` peut être None (espace mobile : le membre agit sans compte). Aucun contrôle de droit ici : c'est l'affaire de la vue.
    """
    antenne = antenne_depuis_ville(ville, creer=True)
    avant = {'ville': objet.ville_id, 'antenne': objet.antenne_id}
    objet.ville, objet.antenne = ville, antenne
    champs = ['ville', 'antenne'] + (['mise_a_jour'] if any(f.name == 'mise_a_jour' for f in objet._meta.concrete_fields) else [])
    objet.save(update_fields=champs)
    journaliser(auteur, JournalAction.Action.RATTACHEMENT, objet, avant=avant,
                apres={'ville': objet.ville_id, 'antenne': objet.antenne_id})
    return objet


def completer_antenne(membre):
    """Après un formulaire qui a écrit ``ville`` : renseigne ``antenne`` d'après la ville si elle manque (sans écrire ``ville``)."""
    if membre.ville_id and not membre.antenne_id:
        membre.antenne = antenne_depuis_ville(membre.ville, creer=True)
        membre.save(update_fields=['antenne'])
    return membre


@transaction.atomic
def rattacher_antenne(auteur, objet, antenne):
    """Rattache `objet` (Membre) à `antenne` ET, si l'antenne est issue d'une ville héritée, à cette ville (même transaction).

    Une antenne nouvelle (sans ville d'origine) laisse la ville inchangée. Écrit seulement les colonnes concernées et journalise.
    """
    ville = ville_depuis_antenne(antenne)
    avant = {'ville': objet.ville_id, 'antenne': objet.antenne_id}
    objet.antenne = antenne
    champs = ['antenne']
    if ville is not None:
        objet.ville = ville
        champs.append('ville')
    if any(f.name == 'mise_a_jour' for f in objet._meta.concrete_fields):
        champs.append('mise_a_jour')
    objet.save(update_fields=champs)
    journaliser(auteur, JournalAction.Action.RATTACHEMENT, objet, avant=avant,
                apres={'ville': objet.ville_id, 'antenne': objet.antenne_id})
    return objet
