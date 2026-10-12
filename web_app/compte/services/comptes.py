"""Création de comptes : mot de passe aléatoire à usage unique, changement imposé à la première connexion."""
import re
import secrets
import unicodedata

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.translation import gettext as _

from coptapp.models import Notification

# Sans caractères ambigus (0/O, 1/l/I) : le mot de passe est communiqué de vive voix ou par message.
ALPHABET = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'


def generer_mot_de_passe(longueur=12):
    """Mot de passe aléatoire (module secrets) contenant minuscule, majuscule et chiffre."""
    while True:
        mdp = ''.join(secrets.choice(ALPHABET) for _ in range(longueur))
        if (re.search('[a-z]', mdp) and re.search('[A-Z]', mdp) and re.search('[2-9]', mdp)):
            return mdp


def _base_pseudo(nom, membre_id):
    brut = unicodedata.normalize('NFKD', (nom or '').split(' ')[0]).encode('ascii', 'ignore').decode()
    brut = re.sub(r'[^a-z0-9]', '', brut.lower())
    return f'{brut or "membre"}{membre_id}'


@transaction.atomic
def creer_compte(username, email='', membre=None, auteur=None, **extra):
    """Crée un compte avec un mot de passe aléatoire et doit_changer_mot_de_passe=True.

    Retourne (compte, mot_de_passe_en_clair) : le mot de passe n'est connu qu'ici, à afficher une fois.
    """
    Compte = get_user_model()
    mdp = generer_mot_de_passe()
    compte = Compte.objects.create_user(
        username=username, email=email or '', password=mdp,
        membreId=membre.id if membre else None, doit_changer_mot_de_passe=True, **extra,
    )
    Notification.objects.create(
        user=auteur, membre=membre, titre='Création de compte',
        description=f'Compte {compte.username} créé (mot de passe temporaire à changer).',
    )
    return compte, mdp


@transaction.atomic
def creer_compte_pour_membre(membre, auteur=None):
    """Compte d'un membre ; retourne (compte, mot_de_passe) ou (compte_existant, None)."""
    Compte = get_user_model()
    existant = Compte.objects.filter(membreId=membre.id).first()
    if existant:
        return existant, None
    base = _base_pseudo(membre.nom, membre.id)
    username, n = base, 1
    while Compte.objects.filter(username=username).exists():
        n += 1
        username = f'{base}-{n}'
    compte, mdp = creer_compte(username, membre=membre, auteur=auteur)
    membre.is_user = True
    membre.save()
    if membre.structure:
        membre.structure.users.add(compte)
    return compte, mdp


@transaction.atomic
def changer_mot_de_passe(compte, form):
    """Enregistre le nouveau mot de passe d'un formulaire valide et lève l'obligation de changement."""
    form.save()
    if compte.doit_changer_mot_de_passe:
        compte.doit_changer_mot_de_passe = False
        compte.save(update_fields=['doit_changer_mot_de_passe'])
    Notification.objects.create(user=compte, titre=_("Changement de mot de passe"),
                                description=_("Mot de passe modifié par son titulaire."))
    return compte
