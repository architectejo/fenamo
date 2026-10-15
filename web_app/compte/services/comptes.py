"""Création de comptes : mot de passe aléatoire à usage unique, changement imposé à la première connexion."""
import re
import secrets
import unicodedata

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.translation import gettext as _

from compte.models import JournalAction
from compte.services.journal import journaliser

# Sans caractères ambigus (0/O, 1/l/I) : le mot de passe est communiqué de vive voix ou par message.
ALPHABET = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'


def generer_mot_de_passe(longueur=12):
    """Mot de passe aléatoire (module secrets) contenant minuscule, majuscule et chiffre."""
    while True:
        mdp = ''.join(secrets.choice(ALPHABET) for _ in range(longueur))
        if (re.search('[a-z]', mdp) and re.search('[A-Z]', mdp) and re.search('[2-9]', mdp)):
            return mdp


LONGUEUR_TEMPORAIRE = 12
CARACTERES_INTERDITS = '0O1lI'  # ambigus à l'écrit ou à l'oral : jamais dans un mot de passe temporaire


def mot_de_passe_temporaire():
    """Mot de passe temporaire : 12 caractères tirés avec ``secrets`` dans un alphabet sans 0, O, 1, l, I, avec minuscule,
    majuscule et chiffre. Utilisé par la nomination (F-02), la création de compte externe (F-03) et la réinitialisation (F-05)."""
    return generer_mot_de_passe(LONGUEUR_TEMPORAIRE)


def en_groupes(mot_de_passe, taille=4):
    """Mot de passe présenté par groupes de `taille` caractères (``abcd efgh ijkl``), pour la lecture à voix haute ou la copie."""
    return ' '.join(mot_de_passe[i:i + taille] for i in range(0, len(mot_de_passe), taille))


def _base_pseudo(nom, membre_id):
    brut = unicodedata.normalize('NFKD', (nom or '').split(' ')[0]).encode('ascii', 'ignore').decode()
    brut = re.sub(r'[^a-z0-9]', '', brut.lower())
    return f'{brut or "membre"}{membre_id}'


@transaction.atomic
def creer_compte(username, email='', membre=None, auteur=None):
    """Crée un compte avec un mot de passe aléatoire et doit_changer_mot_de_passe=True.

    Retourne (compte, mot_de_passe_en_clair) : le mot de passe n'est connu qu'ici, à afficher une fois.
    """
    Compte = get_user_model()
    mdp = mot_de_passe_temporaire()
    compte = Compte.objects.create_user(
        username=username, email=email or '', password=mdp,
        membreId=membre.id if membre else None, doit_changer_mot_de_passe=True,
    )
    journaliser(auteur, JournalAction.Action.CREATION_COMPTE, compte,
                apres={'username': compte.username, 'membreId': compte.membreId, 'changement_impose': True},
                motif=_('Compte créé avec un mot de passe temporaire à changer.'))
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
    membre.save(update_fields=['is_user', 'mise_a_jour'])  # jamais l'état ni les miroirs
    if membre.structure:
        membre.structure.users.add(compte)
    return compte, mdp


@transaction.atomic
def changer_mot_de_passe(compte, form):
    """Enregistre le nouveau mot de passe d'un formulaire valide et lève l'obligation de changement."""
    avant = {'changement_impose': compte.doit_changer_mot_de_passe}
    form.save()
    if compte.doit_changer_mot_de_passe:
        compte.doit_changer_mot_de_passe = False
        compte.save(update_fields=['doit_changer_mot_de_passe'])
    journaliser(compte, JournalAction.Action.CHANGEMENT_MOT_DE_PASSE, compte,
                avant=avant, apres={'changement_impose': False},
                motif=_("Mot de passe modifié par son titulaire."))
    return compte


def compte_du_membre(membre_id):
    """Compte rattaché à un membre : le plus ancien s'il y en a plusieurs, None s'il n'y en a pas.

    Remplace `Compte.objects.get(membreId=…)`, qui lève MultipleObjectsReturned quand plusieurs comptes
    partagent un membre, et filtre sur « membreId IS NULL » (donc tous les comptes sans membre) si l'identifiant est None.
    """
    if not membre_id:
        return None
    return get_user_model().objects.filter(membreId=membre_id).order_by('pk').first()
