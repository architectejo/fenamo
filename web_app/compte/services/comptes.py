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


DOMAINE_IDENTIFIANT = '@fenamordc.hub'
TENTATIVES_NOMBRE = 50  # tirages au plus avant de renoncer (boucle bornée)
_LIGATURES = {'œ': 'oe', 'æ': 'ae', 'ß': 'ss', 'ø': 'o', 'đ': 'd', 'ł': 'l'}


def prenom_ascii(nom):
    """Premier mot du nom, en minuscules ASCII sans accents, espaces, apostrophes ni tirets : « Jean-Pierre » -> « jeanpierre »,
    « Élise » -> « elise », « N'Golo » -> « ngolo ». « membre » si rien d'exploitable ne reste."""
    mot = (nom or '').strip().split(' ')[0].lower()
    for origine, remplacement in _LIGATURES.items():
        mot = mot.replace(origine, remplacement)
    brut = unicodedata.normalize('NFKD', mot).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]', '', brut) or 'membre'


def identifiant_de_nomination(nom):
    """« prenom[nombre]@fenamordc.hub » : prénom translittéré suivi d'un nombre de 4 chiffres (1000 à 9999) tiré avec ``secrets`` (jamais un
    compteur prévisible), unique sans tenir compte de la casse. Nouveau tirage en cas de collision, au plus TENTATIVES_NOMBRE fois :
    ensuite RegleMetier explicite. DÉROGATION décidée par l'utilisateur à F-02 : voir docs/decisions.md."""
    from compte.services.nominations import RegleMetier
    Compte = get_user_model()
    base = prenom_ascii(nom)
    for _tentative in range(TENTATIVES_NOMBRE):
        candidat = f'{base}{secrets.randbelow(9000) + 1000}{DOMAINE_IDENTIFIANT}'
        if not Compte.objects.filter(username__iexact=candidat).exists():
            return candidat
    raise RegleMetier(_("Impossible de générer un identifiant unique pour ce prénom : réessayez."))


def mot_de_passe_contient_identifiant(mot_de_passe, username):
    """Vrai si le mot de passe contient le nom d'utilisateur entier ou sa partie locale (avant @), sans tenir compte de la casse."""
    bas = (mot_de_passe or '').lower()
    nom = (username or '').lower()
    locale = nom.split('@')[0]
    # Seuil de 4 caractères : un identifiant très court (« u ») serait contenu dans presque tout mot de passe.
    return bool(len(nom) >= 4 and nom in bas) or bool(len(locale) >= 4 and locale in bas)


@transaction.atomic
def creer_compte(username, email='', membre=None, auteur=None, mot_de_passe=None):
    """Crée un compte avec un mot de passe aléatoire et doit_changer_mot_de_passe=True (F-03 : compte externe).

    `mot_de_passe` n'est donné que par la nomination d'un membre (dérogation F-02 : identifiant = mot de passe initial). Retourne
    (compte, mot_de_passe_en_clair) : le mot de passe n'est connu qu'ici, à afficher une fois ; le journal ne le contient jamais.
    """
    Compte = get_user_model()
    mdp = mot_de_passe or mot_de_passe_temporaire()
    compte = Compte.objects.create_user(
        username=username, email=email or '', password=mdp,
        membreId=membre.id if membre else None, doit_changer_mot_de_passe=True,
    )
    journaliser(auteur, JournalAction.Action.CREATION_COMPTE, compte,
                apres={'username': compte.username, 'membreId': compte.membreId, 'changement_impose': True},
                motif=_('Compte créé avec un mot de passe temporaire à changer.'))
    return compte, mdp


@transaction.atomic
def creer_compte_pour_membre(membre, auteur=None, identifiants_de_nomination=False):
    """Compte d'un membre ; retourne (compte, mot_de_passe_initial) ou (compte_existant, None). Avec ``identifiants_de_nomination`` (appelé
    par ``nominations.nommer`` seulement) le mot de passe initial est égal à l'identifiant « prenom[nombre]@fenamordc.hub » (dérogation décidée
    par l'utilisateur) ; sinon, mot de passe aléatoire."""
    Compte = get_user_model()
    existant = Compte.objects.filter(membreId=membre.id).first()
    if existant:
        return existant, None
    if identifiants_de_nomination:
        # DÉROGATION F-02 (décision de l'utilisateur, docs/decisions.md) : identifiant ET mot de passe initial « prenom[nombre]@fenamordc.hub »,
        # mot de passe à changer à la première connexion ; un compte existant n'est jamais modifié.
        username = identifiant_de_nomination(membre.nom)
        compte, mdp = creer_compte(username, membre=membre, auteur=auteur, mot_de_passe=username)
    else:  # « Créer le compte » par un super-utilisateur (hors nomination) : identifiant « prenomID » et mot de passe aléatoire
        base = prenom_ascii(membre.nom) + str(membre.id)
        username, n = base, 1
        while Compte.objects.filter(username__iexact=username).exists():
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
