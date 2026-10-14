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


def _colonnes(objet, *champs):
    """Colonnes à écrire : `champs` plus la date de mise à jour si le modèle en a une (Membre, pas AssociationMembre)."""
    return list(champs) + (['mise_a_jour'] if any(f.name == 'mise_a_jour' for f in objet._meta.concrete_fields) else [])


@transaction.atomic
def rattacher_ville(auteur, objet, ville):
    """Rattache `objet` (Membre ou AssociationMembre) à `ville` ET à l'antenne qui en est issue, dans UNE transaction.

    Sur une action explicite de rattachement à une ville, l'antenne actuelle de `objet` est REMPLACÉE par celle de la ville (même
    si une autre antenne avait été choisie avant) : la ville et l'antenne ne se contredisent jamais. ``ville`` None détache les deux. Écrit seulement les colonnes concernées et journalise (avant / après, ville et antenne).
    `auteur` peut être None (espace mobile : le membre agit sans compte). Aucun contrôle de droit ici : c'est l'affaire de la vue.
    """
    antenne = antenne_depuis_ville(ville, creer=True)
    avant = {'ville': objet.ville_id, 'antenne': objet.antenne_id, 'province': objet.province_id}
    objet.ville, objet.antenne = ville, antenne
    champs = ['ville', 'antenne']
    coordination_id = (antenne.coordination_id if antenne is not None else None) or (ville.province_id if ville is not None else None)
    if coordination_id:  # la coordination suit le rattachement : elle ne contredit jamais l'antenne
        objet.province_id = coordination_id
        champs.append('province')
    objet.save(update_fields=_colonnes(objet, *champs))
    journaliser(auteur, JournalAction.Action.RATTACHEMENT, objet, avant=avant,
                apres={'ville': objet.ville_id, 'antenne': objet.antenne_id, 'province': objet.province_id})
    return objet


def completer_antenne(membre):
    """Après un formulaire qui a écrit ``ville`` : renseigne ``antenne`` d'après la ville si elle manque (sans écrire ``ville``)."""
    if membre.ville_id and not membre.antenne_id:
        membre.antenne = antenne_depuis_ville(membre.ville, creer=True)
        membre.save(update_fields=['antenne'])
    return membre


@transaction.atomic
def rattacher_antenne(auteur, objet, antenne):
    """Rattache `objet` (Membre) à `antenne`.

    Si l'antenne est issue d'une ville héritée, la ville de `objet` devient cette ville d'origine (même transaction). Si
    l'antenne est nouvelle (sans ville d'origine), la ville actuelle est CONSERVÉE (jamais vidée) : une antenne créée après
    la reprise ne sait pas dire de quelle ville héritée elle dépend. Écrit seulement les colonnes concernées et journalise.
    """
    ville = antenne.ville_origine if antenne is not None else None
    avant = {'ville': objet.ville_id, 'antenne': objet.antenne_id, 'province': objet.province_id}
    objet.antenne = antenne
    champs = ['antenne']
    if ville is not None:
        objet.ville = ville
        champs.append('ville')
    if antenne is not None and antenne.coordination_id:  # la coordination de l'objet suit celle de l'antenne
        objet.province_id = antenne.coordination_id
        champs.append('province')
    objet.save(update_fields=_colonnes(objet, *champs))
    journaliser(auteur, JournalAction.Action.RATTACHEMENT, objet, avant=avant,
                apres={'ville': objet.ville_id, 'antenne': objet.antenne_id, 'province': objet.province_id})
    return objet


@transaction.atomic
def rattacher_association(auteur, membre, association):
    """Rattache `membre` à l'association membre `association` ET met sa ville et son antenne en cohérence avec elle (une transaction).

    - association avec une ville : la ville du membre devient cette ville, son antenne celle de l'association (à défaut, l'antenne
      issue de la ville, créée au besoin) ;
    - association avec seulement une antenne : l'antenne du membre devient celle-ci, la ville celle d'origine de l'antenne si elle
      en a une (sinon la ville actuelle est conservée) ;
    - association sans ville ni antenne : seule l'association est écrite.
    Écrit seulement les colonnes concernées et journalise l'avant / après (association, ville, antenne).
    """
    avant = {'structure': membre.structure_id, 'ville': membre.ville_id, 'antenne': membre.antenne_id, 'province': membre.province_id}
    membre.structure = association
    champs = ['structure']
    if association.ville_id:
        membre.ville = association.ville
        membre.antenne = association.antenne or antenne_depuis_ville(association.ville, creer=True)
        champs += ['ville', 'antenne']
    elif association.antenne_id:
        membre.antenne = association.antenne
        champs.append('antenne')
        if association.antenne.ville_origine_id:
            membre.ville = association.antenne.ville_origine
            champs.append('ville')
    coordination_id = (membre.antenne.coordination_id if membre.antenne_id else None) or association.province_id
    if coordination_id and 'antenne' in champs:  # la coordination suit l'antenne (ou, à défaut, celle de l'association)
        membre.province_id = coordination_id
        champs.append('province')
    membre.save(update_fields=_colonnes(membre, *champs))
    journaliser(auteur, JournalAction.Action.RATTACHEMENT, membre, avant=avant,
                apres={'structure': membre.structure_id, 'ville': membre.ville_id, 'antenne': membre.antenne_id,
                       'province': membre.province_id})
    return membre
