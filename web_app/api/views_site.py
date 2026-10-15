"""Points d'accès en lecture de `/api/v1/site/` (cahier des charges § 2.4, lot 2a). Vues minces : lecture, sérialiseur à liste blanche."""
import math

from django.db.models import Max, Prefetch, Q
from django.utils import timezone

from api import reponses, serialiseurs
from api.decorateurs import cle_site_requise
from coptapp.models import Antenne, Province
from coptapp.services.statistiques_publiques import statistiques_publiques
from virtrine.models import Article, ArticleTraduction, Config, DocumentPublic, Galery, MembreComite, Partenaire, TelephoneSite

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

@cle_site_requise()
def config(request):
    cfg = Config.instance()
    derniere = _articles_publies().aggregate(m=Max('mise_a_jour'))['m']
    return reponses.json_ok(serialiseurs.config(request, cfg, TelephoneSite.objects.all(), Partenaire.objects.all(),
                                                DocumentPublic.objects.all(), derniere))


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


@cle_site_requise(methodes=None)
def inconnu(request, reste=''):
    """Route inexistante sous /api/v1/site/ : 404 JSON (après la clé et la limite)."""
    return reponses.introuvable()
