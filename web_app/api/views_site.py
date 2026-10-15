"""Points d'accès en lecture de `/api/v1/site/` (cahier des charges § 2.4, lot 2a). Vues minces : lecture, sérialiseur à liste blanche."""
import json
import logging
import math

from django.core.exceptions import RequestDataTooBig
from django.db.models import Max, Prefetch, Q
from django.utils import timezone

from api import reponses, serialiseurs
from virtrine.services import contact as service_contact
from api.decorateurs import cle_site_requise
from coptapp.models import Antenne, Province
from coptapp.services.statistiques_publiques import statistiques_publiques
from virtrine.models import Article, ArticleTraduction, Config, DocumentPublic, Galery, MembreComite, Partenaire, TelephoneSite

logger = logging.getLogger('api.contact')
TAILLE_DEFAUT = 12
TAILLE_MAX = 50
Q_MIN = 2
Q_MAX = 100


class ParametreInvalide(Exception):
    def __init__(self, champ, message):
        super().__init__(message)
        self.champ, self.message = champ, message


def _entier(request, nom, defaut, minimum, maximum=None):
    brut = request.GET.get(nom)
    if brut in (None, ''):
        return defaut
    if not brut.isascii() or not brut.isdigit() or int(brut) < minimum or (maximum is not None and int(brut) > maximum):
        borne = f'entre {minimum} et {maximum}' if maximum else f'au moins {minimum}'
        raise ParametreInvalide(nom, f'Indiquez un nombre entier {borne}.')
    return int(brut)


def _langue(request):
    """Langue demandée : inconnue ou non activée -> français."""
    demandee = request.GET.get('lang', 'fr')
    if demandee in serialiseurs.LANGUES[1:] and demandee in Config.instance().langues():
        return demandee
    return 'fr'


def _page(request, queryset):
    """(éléments de la page, total, page, pages). Page hors limite : ParametreInvalide interne -> 404 par l'appelant."""
    taille = _entier(request, 'taille', TAILLE_DEFAUT, 1, TAILLE_MAX)
    page = _entier(request, 'page', 1, 1)
    total = queryset.count()
    pages = math.ceil(total / taille)
    if page > max(pages, 1):
        return None
    debut = (page - 1) * taille
    return list(queryset[debut:debut + taille]), total, page, pages


def _enveloppe(elements, total, page, pages):
    return {'total': total, 'page': page, 'pages': pages, 'resultats': elements}


def _articles_publies():
    return Article.objects.filter(statut=Article.Statut.PUBLIE, date_publication__isnull=False, date_publication__lte=timezone.now())


# ---------------------------------------------------------------- points d'accès

@cle_site_requise(donnees_reelles=False)
def config(request):
    cfg = Config.instance()
    if not cfg.donnees_reelles_actif:  # strict nécessaire à l'affichage du jeu d'exemple : aucune donnée saisie dans l'application web
        return reponses.json_ok({'nom': 'FENAMO-RDC', 'devise': 'Unité, Discipline et Progrès', 'langues_actives': cfg.langues(),
                                 'donnees_reelles': False})
    derniere = _articles_publies().aggregate(m=Max('mise_a_jour'))['m']
    donnees = serialiseurs.config(request, cfg, TelephoneSite.objects.all(), Partenaire.objects.all(), DocumentPublic.objects.all(), derniere)
    return reponses.json_ok({**donnees, 'donnees_reelles': True})


@cle_site_requise()
def articles(request):
    langue = _langue(request)
    try:
        type_ = request.GET.get('type', '')
        if type_ and type_ not in Article.Type.values:
            raise ParametreInvalide('type', 'Type inconnu : article ou communique.')
        q = request.GET.get('q', '').strip()
        if 'q' in request.GET and not (Q_MIN <= len(q) <= Q_MAX):
            raise ParametreInvalide('q', f'La recherche doit contenir de {Q_MIN} à {Q_MAX} caractères.')
        jeu = _articles_publies()
        if type_:
            jeu = jeu.filter(type=type_)
        if q:
            jeu = jeu.filter(Q(titre__icontains=q) | Q(resume__icontains=q)
                             | Q(traductions__langue=langue, traductions__titre__icontains=q)).distinct()
        jeu = jeu.order_by('-date_publication', '-pk').prefetch_related(
            Prefetch('traductions', queryset=ArticleTraduction.objects.filter(langue=langue)))
        resultat = _page(request, jeu)
    except ParametreInvalide as e:
        return reponses.champs_invalides({e.champ: e.message})
    if resultat is None:
        return reponses.introuvable()
    elements, total, page, pages = resultat
    return reponses.json_ok(_enveloppe([serialiseurs.article_liste(request, a, langue) for a in elements], total, page, pages))


def _galerie_publique():
    return Galery.objects.filter(publie=True).exclude(is_delete=True).exclude(principale=True)


@cle_site_requise()
def article(request, slug):
    langue = _langue(request)
    a = _articles_publies().filter(slug=slug).prefetch_related('traductions').first()
    if a is None:  # inexistant, brouillon ou date future : même réponse
        return reponses.introuvable()
    galerie = [g for g in _galerie_publique().filter(Images_article=a).order_by('ordre', 'pk')
               if (g.type == 'video' and serialiseurs.video(g.lien_video)) or (g.type == 'photo' and g.image)]
    return reponses.json_ok(serialiseurs.article_detail(request, a, langue, Config.instance().langues(), galerie))


@cle_site_requise()
def galerie(request):
    try:
        type_ = request.GET.get('type', '')
        if type_ and type_ not in Galery.Type.values:
            raise ParametreInvalide('type', 'Type inconnu : photo ou video.')
        jeu = _galerie_publique().exclude(type='photo', image='').exclude(type='photo', image__isnull=True)
        if type_:
            jeu = jeu.filter(type=type_)
        jeu = jeu.order_by('ordre', '-date', '-pk').prefetch_related(
            Prefetch('Images_article', queryset=_articles_publies().only('slug').order_by('-date_publication', 'pk'), to_attr='articles_publics'))
        resultat = _page(request, jeu)
    except ParametreInvalide as e:
        return reponses.champs_invalides({e.champ: e.message})
    if resultat is None:
        return reponses.introuvable()
    elements, total, page, pages = resultat
    sortie = []
    for g in elements:
        if g.type == 'video' and not serialiseurs.video(g.lien_video):
            continue  # lien non reconnu : jamais exposé
        sortie.append(serialiseurs.element_galerie(request, g, g.articles_publics[0].slug if g.articles_publics else None))
    return reponses.json_ok(_enveloppe(sortie, total, page, pages))


@cle_site_requise()
def comite(request):
    return reponses.json_ok(serialiseurs.comite(request, MembreComite.objects.all()))


@cle_site_requise()
def coordinations(request):
    antennes = Antenne.objects.filter(code__isnull=False).exclude(code='').order_by('nom', 'pk')
    jeu = Province.objects.filter(code__isnull=False).order_by('ordre', 'nom').prefetch_related(
        Prefetch('antennes', queryset=antennes, to_attr='antennes_publiques'))
    return reponses.json_ok([serialiseurs.coordination(c, c.antennes_publiques) for c in jeu])


@cle_site_requise()
def statistiques(request):
    return reponses.json_ok(serialiseurs.statistiques(statistiques_publiques(), timezone.now()))


CORPS_MAX = 20_000  # octets : un message de contact ne dépasse jamais cela


class CorpsInvalide(Exception):
    pass


def _corps_depot(request):
    """Champs d'un dépôt : JSON (objet) ou formulaire encodé. Lève CorpsInvalide (illisible) ; RequestDataTooBig si trop gros."""
    if int(request.META.get('CONTENT_LENGTH') or 0) > CORPS_MAX:
        raise RequestDataTooBig('corps trop gros')
    if request.content_type == 'application/json':
        brut = request.body
        if len(brut) > CORPS_MAX:
            raise RequestDataTooBig('corps trop gros')
        try:
            donnees = json.loads(brut.decode('utf-8'))
        except (UnicodeDecodeError, ValueError) as erreur:
            raise CorpsInvalide from erreur
        if not isinstance(donnees, dict):
            raise CorpsInvalide
        return donnees
    return request.POST.dict()


@cle_site_requise(methodes=('POST',))
def contact(request):
    """S-07 : message de contact. 201 ``{"statut": "recu", "detail": accusé}`` ; 400 ``{"champ": ["message"]}`` ; 413 ; 429. Refusé en 403
    ``inactif`` en mode exemple (le jeu d'exemple ne doit jamais alimenter la boîte réelle des éditeurs). Champ piège rempli : faux succès."""
    try:
        donnees = _corps_depot(request)
    except RequestDataTooBig:
        return reponses.erreur(413, 'Requête trop volumineuse.')
    except CorpsInvalide:
        return reponses.champs_invalides({'non_field_errors': 'Corps de requête illisible : JSON objet ou formulaire attendu.'})
    propres, erreurs, piege = service_contact.valider(donnees)
    if piege:
        logger.info("Message de contact écarté : champ piège rempli.")
        return reponses.json_ok({'statut': 'recu', 'detail': service_contact.ACCUSE}, 201)
    if erreurs:
        return reponses.champs_invalides(erreurs)
    attente = service_contact.limite_atteinte(propres)
    if attente is not None:
        return reponses.erreur(429, 'Trop de messages envoyés : réessayez plus tard.', Retry_After=attente)
    service_contact.enregistrer(propres)
    return reponses.json_ok({'statut': 'recu', 'detail': service_contact.ACCUSE}, 201)


@cle_site_requise(methodes=None, donnees_reelles=False)
def inconnu(request, reste=''):
    """Route inexistante sous /api/v1/site/ : 404 JSON (après la clé et la limite)."""
    return reponses.introuvable()
