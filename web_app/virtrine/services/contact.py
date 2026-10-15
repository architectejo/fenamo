"""Messages de contact du site public (S-07 côté site, F-62 côté application web).

Règles :
- validation stricte, texte brut seulement : aucune balise HTML n'est conservée (``texte_brut``), les caractères de contrôle sont retirés ;
- nom, téléphone ou e-mail (au moins un des deux), objet, message ; tailles maximales fixées ci-dessous ;
- anti-spam : champ piège (``site_web``, doit rester vide ; rempli = faux succès silencieux, rien n'est enregistré), délai minimal entre
  l'affichage du formulaire (``ouvert_le``, horodatage fourni par le site) et l'envoi, limite par contact (e-mail ou téléphone) dans le
  cache ``limites`` ;
- journal F-70 sans donnée personnelle (ni nom, ni e-mail, ni téléphone, ni texte) ;
- notification des destinataires de F-62 (SU et président voient toutes les notifications ; les éditeurs ont le compteur « à traiter »).
"""
import hashlib
import logging
import re
import time
from html.parser import HTMLParser

from django.core.cache import caches
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import DatabaseError, transaction
from django.utils import timezone

from virtrine.models import Contact

logger = logging.getLogger('virtrine.contact')

NOM_MAX = 100
MAIL_MAX = 254
TELEPHONE_MAX = 20
OBJET_MAX = 100
MESSAGE_MIN = 10
MESSAGE_MAX = 3000
LIENS_MAX = 2
DELAI_MIN = 3  # secondes entre l'affichage et l'envoi : un humain ne remplit pas ce formulaire plus vite
DELAI_MAX = 24 * 3600  # un formulaire resté ouvert plus d'un jour doit être rechargé
LIMITE_PAR_CONTACT = 3  # messages par heure pour un même e-mail ou téléphone
FENETRE_CONTACT = 3600
CHAMP_PIEGE = 'site_web'
CHAMPS = ('nom', 'mail', 'telephone', 'objet', 'message')
ACCUSE = 'Votre message a bien été reçu. La FENAMO-RDC vous répondra dès que possible.'

_CONTROLES = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏‪-‮⁦-⁩﻿]')
_ESPACES = re.compile(r'[ \t ]+')
_TELEPHONE = re.compile(r'^\+?[0-9][0-9 .\-()]*$')
_LIEN = re.compile(r'(https?://|www\.)', re.IGNORECASE)
EFFACER = frozenset({'script', 'style', 'iframe', 'object', 'embed', 'template', 'noscript', 'svg', 'math'})


class _Extracteur(HTMLParser):
    """Ne garde que le texte : balises retirées, contenu de script et style effacé avec la balise."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.morceaux, self.ignore = [], 0

    def handle_starttag(self, balise, attributs):
        if balise in EFFACER:
            self.ignore += 1
        elif balise in ('br', 'p', 'div', 'li') and not self.ignore:
            self.morceaux.append('\n')

    def handle_startendtag(self, balise, attributs):
        if balise in ('br', 'p', 'div', 'li') and not self.ignore:
            self.morceaux.append('\n')

    def handle_endtag(self, balise):
        if balise in EFFACER:
            self.ignore = max(self.ignore - 1, 0)

    def handle_data(self, donnees):
        if not self.ignore:
            self.morceaux.append(donnees)


def texte_brut(valeur, multiligne=False):
    """Texte sans aucun HTML : balises et commentaires retirés, entités décodées puis ``<`` et ``>`` supprimés (ce qui reste ne peut plus
    former une balise), caractères de contrôle retirés, espaces normalisés. Sans ``multiligne``, tout est sur une ligne."""
    extracteur = _Extracteur()
    extracteur.feed(str(valeur))
    extracteur.close()
    texte = _CONTROLES.sub('', ''.join(extracteur.morceaux)).replace('<', '').replace('>', '').replace('\r\n', '\n').replace('\r', '\n')
    if not multiligne:
        return _ESPACES.sub(' ', texte.replace('\n', ' ')).strip()
    lignes = [_ESPACES.sub(' ', ligne).strip() for ligne in texte.split('\n')]
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lignes)).strip()


def _chaine(donnees, champ, erreurs):
    """Valeur texte d'un champ ; une valeur qui n'est pas un texte (liste, nombre, objet JSON) est refusée."""
    brut = donnees.get(champ)
    if brut is None:
        return ''
    if not isinstance(brut, str):
        erreurs[champ] = ['Texte attendu.']
        return None
    return brut


def valider(donnees, maintenant=None):
    """(valeurs nettoyées, erreurs, piege). ``erreurs`` : ``{champ: [messages]}`` (clé ``non_field_errors`` hors champ) ; ``piege`` vrai si
    le champ piège est rempli ou si l'horodatage est absurde de façon typique d'un robot (dans ce cas rien n'est enregistré)."""
    erreurs = {}
    maintenant = maintenant or time.time()
    piege = bool(str(donnees.get(CHAMP_PIEGE) or '').strip())
    brut = {c: _chaine(donnees, c, erreurs) for c in CHAMPS}
    propres = {c: ('' if brut[c] is None else texte_brut(brut[c], multiligne=(c == 'message'))) for c in CHAMPS}

    def limite(champ, maximum, libelle):
        if brut[champ] is not None and len(brut[champ]) > maximum * 4 + 200:  # avant nettoyage : refus net des envois démesurés
            erreurs.setdefault(champ, [f'{libelle} : {maximum} caractères au plus.'])
        elif champ not in erreurs and len(propres[champ]) > maximum:
            erreurs[champ] = [f'{libelle} : {maximum} caractères au plus.']

    if not propres['nom'] and 'nom' not in erreurs:
        erreurs['nom'] = ['Indiquez votre nom.']
    elif len(propres['nom']) < 2 and 'nom' not in erreurs:
        erreurs['nom'] = ['Indiquez votre nom (2 caractères au moins).']
    limite('nom', NOM_MAX, 'Le nom')
    if not propres['objet'] and 'objet' not in erreurs:
        erreurs['objet'] = ["Indiquez l'objet de votre message."]
    limite('objet', OBJET_MAX, "L'objet")
    if not propres['message'] and 'message' not in erreurs:
        erreurs['message'] = ['Écrivez votre message.']
    elif 'message' not in erreurs and len(propres['message']) < MESSAGE_MIN:
        erreurs['message'] = [f'Le message est trop court ({MESSAGE_MIN} caractères au moins).']
    limite('message', MESSAGE_MAX, 'Le message')
    if 'message' not in erreurs and len(_LIEN.findall(propres['message'])) > LIENS_MAX:
        erreurs['message'] = [f'Le message ne peut contenir plus de {LIENS_MAX} liens.']

    propres['mail'] = propres['mail'].lower()
    propres['telephone'] = propres['telephone']
    if not propres['mail'] and not propres['telephone'] and not ({'mail', 'telephone'} & set(erreurs)):
        erreurs['non_field_errors'] = ['Indiquez un numéro de téléphone ou une adresse e-mail pour que nous puissions vous répondre.']
    if propres['mail'] and 'mail' not in erreurs:
        try:
            if len(propres['mail']) > MAIL_MAX:
                raise ValidationError('trop long')
            validate_email(propres['mail'])
        except ValidationError:
            erreurs['mail'] = ["Cette adresse e-mail n'est pas valide."]
    if propres['telephone'] and 'telephone' not in erreurs:
        chiffres = re.sub(r'\D', '', propres['telephone'])
        if not _TELEPHONE.match(propres['telephone']) or not 8 <= len(chiffres) <= 15 or len(propres['telephone']) > TELEPHONE_MAX:
            erreurs['telephone'] = [f"Ce numéro de téléphone n'est pas valide (chiffres, espaces et « + » ; {TELEPHONE_MAX} caractères au plus)."]

    ouvert = donnees.get('ouvert_le')
    try:
        ouvert = float(ouvert) if isinstance(ouvert, (str, int, float)) and not isinstance(ouvert, bool) else None
    except ValueError:
        ouvert = None
    if ouvert is None or ouvert != ouvert or ouvert in (float('inf'), float('-inf')):
        erreurs.setdefault('ouvert_le', ["Le formulaire n'est pas valide : rechargez la page."])
    else:
        ecart = maintenant - ouvert
        if ecart < -60 or ecart > DELAI_MAX:
            erreurs.setdefault('ouvert_le', ['Le formulaire a expiré : rechargez la page.'])
        elif ecart < DELAI_MIN:
            erreurs.setdefault('non_field_errors', ["Envoi trop rapide : patientez quelques secondes puis réessayez."])
    return propres, erreurs, piege


def _identite(propres):
    brut = propres['mail'] or re.sub(r'\D', '', propres['telephone'])
    return hashlib.sha256(brut.encode()).hexdigest()[:24]  # jamais l'adresse elle-même dans le cache


def limite_atteinte(propres, maintenant=None):
    """None si l'envoi passe ; sinon les secondes à attendre. Compte par e-mail ou téléphone dans le cache ``limites`` (partagé)."""
    maintenant = maintenant or time.time()
    fenetre = int(maintenant // FENETRE_CONTACT)
    cle = f'site-contact:{_identite(propres)}:{fenetre}'
    cache = caches['limites']
    try:
        cache.add(cle, 0, FENETRE_CONTACT + 5)
        compte = cache.incr(cle)
    except (DatabaseError, ValueError) as erreur:
        logger.error("Limite de contact indisponible (%s) : envoi accepté.", erreur)
        return None
    if compte > LIMITE_PAR_CONTACT:
        return max(1, int(FENETRE_CONTACT - maintenant % FENETRE_CONTACT) + 1)
    return None


@transaction.atomic
def enregistrer(propres):
    """Crée le message, écrit le journal F-70 (sans donnée personnelle) et notifie. Retourne le ``Contact``."""
    from compte.models import JournalAction
    from compte.services.journal import journaliser
    from coptapp.models import Notification
    contact = Contact.objects.create(
        nom=propres['nom'], mail=propres['mail'] or None, phone=propres['telephone'] or None, raison=propres['objet'],
        description=propres['message'], traiter=False, date=timezone.localdate(), cree_le=timezone.now())
    journaliser(None, JournalAction.Action.CREATION, contact, avant=None,
                apres={'origine': 'site public', 'avec_mail': bool(contact.mail), 'avec_telephone': bool(contact.phone),
                       'taille_message': len(contact.description)},
                libelle=f'Message du site n°{contact.pk}')
    Notification.objects.create(
        titre='Nouveau message du site', description=f'Un message a été reçu par le formulaire de contact du site (n°{contact.pk}).')
    return contact


def messages_a_traiter():
    return Contact.objects.filter(traiter=False).count()


def lister(numero_page, par_page=20):
    """Page de messages, du plus récent au plus ancien."""
    from django.core.paginator import Paginator
    return Paginator(Contact.objects.select_related('traite_par').order_by('-id'), par_page).get_page(numero_page)


@transaction.atomic
def marquer_traite(auteur, contact):
    """Marque « traité » (idempotent : un second appel ne change rien et n'écrit rien). Retourne vrai si l'état a changé."""
    from compte.models import JournalAction
    from compte.services.journal import journaliser
    contact = Contact.objects.select_for_update().get(pk=contact.pk)
    if contact.traiter:
        return False
    contact.traiter, contact.traite_par, contact.traite_le = True, auteur, timezone.now()
    contact.save(update_fields=['traiter', 'traite_par', 'traite_le', 'mise_a_jour'])
    journaliser(auteur, JournalAction.Action.MODIFICATION, contact, avant={'traiter': False}, apres={'traiter': True},
                libelle=f'Message du site n°{contact.pk}')
    return True
