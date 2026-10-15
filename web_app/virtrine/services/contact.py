"""Messages de contact du site public (S-07 côté site, F-62 côté application web).

Règles :
- validation stricte, texte brut seulement : aucune balise HTML n'est conservée (``texte_brut``), les caractères de contrôle sont retirés ;
- nom, téléphone ou e-mail (au moins un des deux), objet, message ; tailles maximales fixées ci-dessous ;
- anti-spam : champ piège (``site_web``, doit rester vide ; rempli = faux succès silencieux, rien n'est enregistré), délai minimal entre
  l'affichage du formulaire (``ouvert_le``, horodatage fourni par le site) et l'envoi, limite par contact (e-mail ou téléphone) dans le
  cache ``limites`` ;
- journal F-70 sans donnée personnelle (ni nom, ni e-mail, ni téléphone, ni texte) ;
- notification des destinataires de F-62 (éditeurs et super-utilisateurs seulement ; le président ne la voit pas, ``notifications_du_perimetre`` la filtre ; les éditeurs ont aussi le compteur « à traiter »).
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
TITRE_NOTIFICATION = 'Nouveau message du site'  # visible des seuls ED et SU (F-62) : voir compte.services.perimetre
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
    """(valeurs nettoyées, erreurs, piege). ``erreurs`` : ``{champ: [messages]}`` (clé ``non_field_errors`` hors champ) ; ``piege`` vrai
    seulement si le champ piège ``site_web`` est rempli (faux succès, rien n'est enregistré). Un ``ouvert_le`` absent, illisible ou
    hors délai est une erreur de champ (400), pas un piège."""
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
        titre=TITRE_NOTIFICATION, description=f'Un message a été reçu par le formulaire de contact du site (n°{contact.pk}).')
    return contact


def messages_a_traiter():
    return Contact.objects.filter(traiter=False).count()


PAR_PAGE = 25
ETATS = ('a_traiter', 'traites', 'tous')


def _filtrer(filtres):
    """Messages selon ``q`` (nom, téléphone, e-mail ou objet) et ``etat`` (``a_traiter`` par défaut, ``traites``, ``tous``)."""
    from django.db.models import Q
    filtres = filtres or {}
    jeu = Contact.objects.all()
    q = (filtres.get('q') or '').strip()[:100]
    if q:
        jeu = jeu.filter(Q(nom__icontains=q) | Q(phone__icontains=q) | Q(mail__icontains=q) | Q(raison__icontains=q))
    return jeu


def nombres_messages(filtres=None):
    """Nombres des puces : ``a_traiter``, ``traites``, ``tous`` (selon la recherche ``q`` seulement, pas selon l'état)."""
    jeu = _filtrer(filtres)
    a_traiter = jeu.filter(traiter=False).count()
    total = jeu.count()
    return {'a_traiter': a_traiter, 'traites': total - a_traiter, 'tous': total}


def lister(numero_page, filtres=None, par_page=PAR_PAGE):
    """Page de messages (25 par défaut), du plus récent au plus ancien. ``filtres`` : ``q`` et ``etat`` (voir ``ETATS`` ; défaut
    ``a_traiter`` ; valeur inconnue = défaut). Chaque message porte ``recu_le`` (``cree_le``, à défaut la date de réception d'origine)."""
    from django.core.paginator import Paginator
    jeu = _filtrer(filtres)
    etat = (filtres or {}).get('etat')
    etat = etat if etat in ETATS else 'a_traiter'
    if etat == 'a_traiter':
        jeu = jeu.filter(traiter=False)
    elif etat == 'traites':
        jeu = jeu.filter(traiter=True)
    page = Paginator(jeu.select_related('traite_par').order_by('-id'), par_page).get_page(numero_page)
    page.object_list = list(page.object_list)
    for message in page.object_list:
        message.recu_le = message.cree_le or message.date
    return page


def suivant_a_traiter(contact):
    """Le message à traiter le plus récent après avoir lu `contact` (hors lui) ; ``None`` s'il n'en reste pas."""
    return Contact.objects.filter(traiter=False).exclude(pk=contact.pk).order_by('-id').first()


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
