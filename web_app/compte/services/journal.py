"""Journal d'activités (F-70) : une fonction pour écrire, une liste noire pour ne jamais stocker de secret."""
import json
import re

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from compte.models import JournalAction

# Toute clé dont le nom (en minuscules) contient l'un de ces fragments est supprimée de avant/apres.
CHAMPS_INTERDITS = (
    'password', 'passwd', 'mot_de_passe', 'motdepasse', 'pass1', 'pass2', 'secret', 'token', 'jeton',
    'csrf', 'session', 'api_key', 'apikey', 'cle_api', 'qr',
    'photo', 'piece', 'fichier', 'document', 'image', 'file', 'attachment', 'signature',
)
LIBELLE_MAX = 255


def _interdit(cle):
    cle = str(cle).lower()
    return any(f in cle for f in CHAMPS_INTERDITS)


IDENTIFIANT_INITIAL = re.compile(r'^([a-z0-9]+)\d{4}(@fenamordc\.hub)$', re.IGNORECASE)


def masquer_identifiant_initial(valeur):
    """L'identifiant « prenom1234@fenamordc.hub » d'un compte qui n'a pas encore changé son mot de passe EST son mot de passe initial
    (dérogation F-02, docs/decisions.md) : il ne s'écrit jamais au journal, remplacé par « prenom****@fenamordc.hub »."""
    if not isinstance(valeur, str):
        return valeur
    trouve = IDENTIFIANT_INITIAL.match(valeur.strip())
    if trouve and get_user_model().objects.filter(username__iexact=valeur.strip(), doit_changer_mot_de_passe=True).exists():
        return f'{trouve.group(1)}****{trouve.group(2)}'
    return valeur


def identifiant_affichable(compte):
    """Identifiant d'un compte à AFFICHER (fiches, listes, modales) : masqué tant que le mot de passe initial n'est pas changé
    (même règle que `masquer_identifiant_initial`, sans requête). Chaîne vide si `compte` est vide."""
    if compte is None:
        return ''
    if isinstance(compte, str):  # un nom complet déjà choisi par le gabarit : rien à masquer
        return compte
    nom = compte.get_username()
    trouve = IDENTIFIANT_INITIAL.match(nom.strip())
    if trouve and getattr(compte, 'doit_changer_mot_de_passe', False):
        return f'{trouve.group(1)}****{trouve.group(2)}'
    return nom


def purger(donnees):
    """Copie sérialisable en JSON de `donnees`, sans aucune clé de la liste noire (récursif)."""
    if donnees is None:
        return None
    if isinstance(donnees, dict) or hasattr(donnees, 'lists'):
        return {str(k): purger(v) for k, v in dict(donnees).items() if not _interdit(k)}
    if isinstance(donnees, (list, tuple, set)):
        return [purger(v) for v in donnees]
    if isinstance(donnees, str):
        return masquer_identifiant_initial(donnees)
    return json.loads(json.dumps(donnees, cls=DjangoJSONEncoder, default=str))


def instantane(objet, champs):
    """Dictionnaire {champ: valeur} d'un objet ; les clés de la liste noire sont ignorées par `purger`."""
    resultat = {}
    for champ in champs:
        valeur = getattr(objet, champ, None)
        resultat[champ] = valeur.pk if isinstance(valeur, models.Model) else valeur
    return resultat


def role_de(auteur):
    """Rôle de l'auteur au moment de l'action : code de son rôle (SU, PR, VN, VP, VA, AT, VI, ED) d'après sa nomination active ;
    sans nomination, ses privilèges hérités (« privilèges P1,P3 ») ou « utilisateur »."""
    if auteur is None or not getattr(auteur, 'pk', None):
        return ''
    if auteur.is_superuser:
        return 'SU'
    from compte.services.droits import profil_de
    profil = profil_de(auteur)
    if profil.mode == 'nomination':
        return profil.role
    herites = [f'P{i}' for i in range(1, 6) if getattr(auteur, f'privilege{i}', False)]
    return 'privilèges ' + ','.join(herites) if herites else 'utilisateur'


def _perimetre(objet):
    """Coordination (Province) et antenne de l'objet, quand il en porte."""
    from coptapp.models import Antenne, Province
    coordination = getattr(objet, 'province', None)
    antenne = getattr(objet, 'antenne', None)
    if isinstance(objet, Province):
        coordination = objet
    if isinstance(objet, Antenne):
        antenne = objet
    return (coordination if isinstance(coordination, Province) else None,
            antenne if isinstance(antenne, Antenne) else None)


def journaliser(auteur, action, objet=None, avant=None, apres=None, motif='', libelle=None,
                coordination=None, antenne=None):
    """Écrit une ligne du journal. `auteur` peut être None (échec de connexion) ou anonyme.

    Ne stocke jamais de mot de passe, de jeton ni de pièce : voir CHAMPS_INTERDITS."""
    if action not in JournalAction.Action.values:
        raise ValueError(f"Action de journal inconnue : {action}")
    if auteur is not None and not getattr(auteur, 'pk', None):
        auteur = None
    objet_type = objet_id = None
    if isinstance(objet, models.Model) and objet.pk:
        objet_type = ContentType.objects.get_for_model(objet, for_concrete_model=False)
        objet_id = objet.pk
        c, a = _perimetre(objet)
        coordination = coordination or c
        antenne = antenne or a
    if libelle is None:
        libelle = ''
        if objet is not None:
            libelle = (getattr(objet, 'nom', None) or getattr(objet, 'numero', None)
                       or getattr(objet, 'username', None) or str(objet))
    return JournalAction.objects.create(
        auteur=auteur, role=role_de(auteur), action=action,
        objet_type=objet_type, objet_id=objet_id, objet_libelle=masquer_identifiant_initial(str(libelle))[:LIBELLE_MAX],
        avant=purger(avant), apres=purger(apres), motif=motif or '',
        coordination=coordination, antenne=antenne,
    )
