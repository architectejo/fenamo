"""Vues du site public (lot 2a) : minces, elles appellent `services/site_api.py` et rendent un gabarit.

Aucune vue n'appelle l'API autrement que par `services.site_api` / `services.api_client`.
Quand l'API est absente, chaque page s'affiche avec la dernière copie (bandeau) ou avec un état vide soigné.
"""
import hashlib
import hmac
import logging
import time
from urllib.parse import quote

from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpResponse, HttpResponseNotAllowed, HttpResponseRedirect, HttpResponseServerError
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import translation
from django.utils.cache import patch_vary_headers
from django.utils.safestring import mark_safe
from django.utils.translation import get_language, gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from services import api_client, site_api
from services import contact as contact_service
from services.api_client import ApiErreur
from services.langues import langues_actives

from . import carte, telechargements
from .context_processors import contexte_minimal

logger = logging.getLogger(__name__)

PAR_PAGE_ARTICLES = 12
PAR_PAGE_GALERIE = 24


def _court(texte: str, maxi: int = 160) -> str:
    texte = " ".join((texte or "").split())
    return texte if len(texte) <= maxi else texte[: maxi - 1].rsplit(" ", 1)[0] + "…"


def _numero_page(request) -> int:
    brut = request.GET.get("page", "1")
    return int(brut) if brut.isdigit() and 0 < int(brut) < 10000 else 1


def _page(request, gabarit, contexte, titre, description, **meta):
    contexte = {**contexte, "page_title": titre, "page_description": _court(description), **meta}
    return render(request, gabarit, contexte)


# ---------- Accueil ----------

def _chiffres(stats):
    """Chiffres clés (4 au plus). Aucun chiffre d'engins tant que l'API ne le fournit pas (null)."""
    if not stats:
        return []
    chiffres = []
    if stats["membres_actifs"] is not None:
        chiffres.append({"valeur": stats["membres_actifs"], "libelle": _("membres actifs"), "compteur": True})
    if stats["engins_actifs"] is not None:
        chiffres.append({"valeur": stats["engins_actifs"], "libelle": _("engins identifiés, motos et tricycles"), "compteur": True})
    if stats["associations_membres"] is not None:
        chiffres.append({"valeur": stats["associations_membres"], "libelle": _("associations membres"), "compteur": True})
    if stats["coordinations"] is not None:
        antennes = [c["antennes"] for c in stats["par_coordination"]]
        total_antennes = sum(antennes) if antennes and all(a is not None for a in antennes) else None
        chiffres.append({"valeur": stats["coordinations"], "libelle": _("coordinations provinciales"), "compteur": False, "antennes": total_antennes})
    return chiffres[:4]


def accueil(request):
    langue = get_language()
    stats = site_api.statistiques()
    liste = site_api.articles(langue, page=1, taille=4)
    config = site_api.config()
    recents = liste["resultats"] if liste else []
    return _page(
        request,
        "pages/accueil.html",
        {
            "chiffres": _chiffres(stats),
            "stats": stats,
            "une": recents[0] if recents else None,
            "suivants": recents[1:4],
            "articles_indisponibles": liste is None,
            "application": config["application"],
        },
        _("Accueil"),
        _("Fédération Nationale des Associations des Motocyclistes Taximen de la RDC : vérifier une carte de membre, adhérer, actualités."),
    )


# ---------- La FENAMO-RDC ----------

def a_propos(request):
    config = site_api.config()
    stats = site_api.statistiques()
    charte = next((d for d in telechargements.documents_avec_slug(config) if d["type"] == "charte"), None)
    return _page(
        request,
        "pages/a_propos.html",
        {"stats": stats, "charte": charte},
        _("La FENAMO-RDC"),
        _("But, objectifs et catégories de membres de la Fédération Nationale des Associations des Motocyclistes Taximen de la RDC, d'après sa charte."),
    )


def _president(membre) -> bool:
    return membre["fonction_code"].upper().startswith("PRESIDENT") or membre["fonction"].lower().startswith("président national")


def comite(request):
    donnees = site_api.comite()
    stats = site_api.statistiques()
    membres = donnees["membres"] if donnees else []
    tete = membres[0] if membres and _president(membres[0]) else None
    autres = membres[1:] if tete else membres
    antennes = None
    if stats:
        valeurs = [c["antennes"] for c in stats["par_coordination"]]
        antennes = sum(valeurs) if valeurs and all(v is not None for v in valeurs) else None
    return _page(
        request,
        "pages/comite.html",
        {
            "comite": donnees,
            "tete": tete,
            "autres": autres,
            "membres_indisponibles": donnees is None,
            "stats": stats,
            "nb_antennes": antennes,
        },
        _("Comité exécutif national"),
        _("Les dirigeants du comité exécutif national de la FENAMO-RDC et l'organisation de la fédération, du siège national jusqu'au parking."),
    )


# ---------- Coordinations ----------

def coordinations(request):
    liste = site_api.coordinations()
    stats = site_api.statistiques()
    par_code = {c["code"]: c for c in stats["par_coordination"]} if stats else {}
    lignes, tuiles = [], []
    for c in liste or []:
        chiffres = par_code.get(c["code"], {})
        membres = chiffres.get("membres_actifs")
        ligne = {
            **c,
            "membres_actifs": membres,
            "associations_membres": chiffres.get("associations_membres"),
            "engins_actifs": chiffres.get("engins_actifs"),
            "nb_antennes": len(c["antennes"]) or chiffres.get("antennes") or 0,
            "classe": carte.classe_effectif(membres),
        }
        lignes.append(ligne)
        geometrie = carte.tuile(c["code"])
        if geometrie:
            tuiles.append({**geometrie, "code": c["code"], "nom": c["nom"], "classe": ligne["classe"], "membres": membres})
    return _page(
        request,
        "pages/coordinations.html",
        {"lignes": lignes, "tuiles": tuiles, "indisponible": liste is None, "stats": stats},
        _("Coordinations provinciales"),
        _("Les coordinations provinciales de la FENAMO-RDC, leurs codes, leurs antennes et leurs effectifs actifs."),
    )


# ---------- Documents et application (S-10) ----------

def documents(request):
    config = site_api.config()
    docs = telechargements.documents_avec_slug(config)
    nombres = telechargements.totaux([d["cle"] for d in docs])
    for d in docs:
        d["telechargements"] = nombres.get(d["cle"], 0)
    return _page(
        request,
        "pages/documents.html",
        {
            "fondateurs": [d for d in docs if d["groupe"] == "fondateurs"],
            "formulaires": [d for d in docs if d["groupe"] == "formulaires"],
            "aucun": not docs,
        },
        _("Documents"),
        _("La charte, le règlement d'ordre intérieur et les formulaires de la FENAMO-RDC, à télécharger au format PDF."),
    )


def _qr_svg(adresse: str) -> str:
    """QR code (SVG inline) de l'adresse de téléchargement ; chaîne vide si la bibliothèque `segno` manque."""
    try:
        import segno
    except ImportError:
        logger.warning("segno n'est pas installé : pas de QR code sur la page Application mobile")
        return ""
    qr = segno.make(adresse, error="m", micro=False)
    svg = qr.svg_inline(scale=4, border=0, dark="#000000", light=None, omitsize=True, svgclass="", lineclass="")
    # La couleur suit le texte (thème clair ou sombre) : segno n'accepte pas currentColor, on le pose ensuite.
    return mark_safe(svg.replace("#000000", "currentColor").replace("#000", "currentColor"))


def application(request):
    config = site_api.config()
    appli = config["application"]
    slug = telechargements.slug_application(appli) if appli else ""
    adresse = request.build_absolute_uri(reverse("pages:telecharger", args=["application", slug])) if appli else ""
    nombre = telechargements.totaux([f"application:{slug}"]).get(f"application:{slug}", 0) if appli else 0
    return _page(
        request,
        "pages/application.html",
        {
            "appli": appli,
            "slug": slug,
            "telechargements": nombre,
            "qr": _qr_svg(settings.SITE_URL + reverse("pages:telecharger", args=["application", slug])) if appli else "",
        },
        _("Application mobile"),
        _("L'application mobile de la FENAMO-RDC pour les téléphones Android : version, taille, téléchargement et installation."),
    )


@require_GET
def telecharger(request, type_, slug):
    """Compte le téléchargement (compteur SQLite du site) puis redirige vers le fichier de l'application web."""
    config = site_api.config()
    if type_ == "document":
        cible = next((d for d in telechargements.documents_avec_slug(config) if d["slug"] == slug), None)
        cle = cible and cible["cle"]
    elif type_ == "application":
        cible = config["application"] if config["application"] and telechargements.slug_application(config["application"]) == slug else None
        cle = f"application:{slug}"
    else:
        cible = cle = None
    if not cible:
        raise Http404
    telechargements.compter(cle)
    reponse = HttpResponseRedirect(cible["url"])
    reponse["Cache-Control"] = "no-store"
    return reponse


# ---------- Actualités (S-01, S-02) ----------

def _parametres_liste(request):
    type_ = request.GET.get("type")
    type_ = type_ if type_ in site_api.TYPES_ARTICLE else None
    q = " ".join(request.GET.get("q", "").split())[:100]
    return type_, q


def actualites(request):
    langue = get_language()
    type_, q = _parametres_liste(request)
    page = _numero_page(request)
    try:
        liste = site_api.articles(langue, type_, q, page, PAR_PAGE_ARTICLES)
    except ApiErreur:
        raise Http404  # page au-delà de la dernière
    compte = {}
    if liste is not None and len(q) < 2:
        for t in site_api.TYPES_ARTICLE:
            try:
                reponse = site_api.articles(langue, t, None, 1, 1)
            except ApiErreur:
                reponse = None
            compte[t] = reponse["total"] if reponse else None
        compte["tout"] = sum(v for v in compte.values() if v is not None) if all(v is not None for v in compte.values()) else None
    contexte = {
        "liste": liste,
        "type": type_,
        "q": q if len(q) >= 2 else "",
        "q_trop_court": 0 < len(q) < 2,
        "page": page,
        "compte": compte,
        "indisponible": liste is None,
    }
    if request.headers.get("HX-Request") and not request.headers.get("HX-History-Restore-Request"):
        reponse = render(request, "partials/_resultats.html", contexte)
    else:
        reponse = _page(
            request,
            "pages/actualites.html",
            contexte,
            _("Actualités et communiqués"),
            _("Les nouvelles et les communiqués officiels de la FENAMO-RDC et de ses coordinations."),
        )
    patch_vary_headers(reponse, ["HX-Request"])
    return reponse


def _liens_partage(titre: str, adresse: str) -> dict:
    return {
        "whatsapp": "https://wa.me/?text=" + quote(f"{titre} {adresse}"),
        "facebook": "https://www.facebook.com/sharer/sharer.php?u=" + quote(adresse, safe=""),
        "x": "https://twitter.com/intent/tweet?text=" + quote(titre) + "&url=" + quote(adresse, safe=""),
    }


def article(request, slug):
    langue = get_language()
    try:
        contenu = site_api.article(slug, langue)
    except ApiErreur:
        raise Http404
    if contenu is None:
        reponse = _page(
            request, "pages/indisponible.html", {},
            _("Page momentanément indisponible"),
            _("Cet article ne peut pas être affiché pour le moment."), noindex=True,
        )
        reponse.status_code = 503
        return reponse
    suite = site_api.articles(langue, page=1, taille=4)
    autres = [a for a in (suite["resultats"] if suite else []) if a["slug"] != slug][:3]
    adresse = settings.SITE_URL + reverse("pages:article", args=[slug])
    nom_fr = {"ln": "lingala", "sw": "kiswahili", "lua": "tshiluba", "kg": "kikongo"}.get(langue, "")
    return _page(
        request,
        "pages/article.html",
        {
            "article": contenu,
            "autres": autres,
            "partage": _liens_partage(contenu["titre"], adresse),
            "adresse": adresse,
            "langue_nom": nom_fr,
            "og_image": contenu["image"]["url"] if contenu["image"] else None,
        },
        contenu["titre"],
        contenu["resume"] or contenu["titre"],
    )


# ---------- Galerie ----------

def galerie(request):
    type_ = request.GET.get("type")
    type_ = type_ if type_ in site_api.TYPES_GALERIE else None
    page = _numero_page(request)
    try:
        liste = site_api.galerie(type_, page, PAR_PAGE_GALERIE)
    except ApiErreur:
        raise Http404
    return _page(
        request,
        "pages/galerie.html",
        {"liste": liste, "type": type_, "page": page, "indisponible": liste is None},
        _("Galerie"),
        _("Les photos et vidéos des activités de la FENAMO-RDC, dans les coordinations et les antennes."),
    )


# ---------- Contact, adhésion, vérification (pages d'information du lot 2a) ----------

@require_http_methods(["GET", "HEAD", "POST"])
def contact(request):
    """Contact (S-07) : coordonnées et formulaire. HTMX renvoie seulement le fragment du formulaire."""
    config = site_api.config()
    if request.method == "POST":
        etat = contact_service.traiter(request.POST, request.META.get("REMOTE_ADDR", ""))
    else:
        etat = contact_service.afficher()
    htmx = request.headers.get("HX-Request") and not request.headers.get("HX-History-Restore-Request")
    if htmx:
        # htmx n'échange pas le contenu d'une réponse 4xx/5xx : le fragment est toujours servi en 200
        reponse = render(request, "partials/_contact_formulaire.html", {"etat": etat})
    else:
        carte_url = ""
        if settings.GOOGLE_MAPS_KEY and config["siege"]:
            carte_url = "https://www.google.com/maps/embed/v1/place?key=" + quote(settings.GOOGLE_MAPS_KEY) + "&q=" + quote(config["siege"] + ", Kinshasa")
        reponse = _page(
            request,
            "pages/contact.html",
            {"carte_url": carte_url, "etat": etat},
            _("Contact"),
            _("Coordonnées du siège national de la FENAMO-RDC à Kinshasa : adresse, téléphones, e-mail et réseaux sociaux."),
        )
        reponse.status_code = etat.status
    if etat.attente:
        reponse["Retry-After"] = str(etat.attente)
    reponse["Cache-Control"] = "no-store"  # le formulaire porte un jeton d'ouverture et le jeton CSRF
    patch_vary_headers(reponse, ["HX-Request"])
    return reponse


def adhesion(request):
    config = site_api.config()
    return _page(
        request,
        "pages/adhesion.html",
        {"paiement": config["paiement_en_ligne"]},
        _("Adhérer à la fédération"),
        _("Conditions d'adhésion d'une association à la FENAMO-RDC (article 9 de la charte) et pièces à préparer."),
    )


def verifier(request):
    """Page provisoire du lot 2a : la vérification (S-03) arrive au lot 3. Gère déjà le verrou F-07."""
    site_api.config()  # un appel suffit à apprendre un verrou F-07 avant le choix de l'affichage
    suspendu = api_client.etat_service() == "suspendu"
    reponse = _page(
        request,
        "pages/service_suspendu.html",
        {"cas": "suspendu" if suspendu else "en_cours", "message": api_client.message_verrou() if suspendu else ""},
        _("Vérifier une carte ou un engin"),
        _("Vérification d'une carte de membre ou d'un engin de la FENAMO-RDC."),
        noindex=True,
    )
    if suspendu:
        reponse.status_code = 503
    return reponse


def service_suspendu(request, cas="panne", message=""):
    """Page « service momentanément indisponible » ou « suspendu » (F-07), pour les fonctions du lot 3."""
    reponse = _page(
        request,
        "pages/service_suspendu.html",
        {"cas": cas, "message": message},
        _("Service momentanément indisponible"),
        _("Le service demandé est momentanément indisponible."),
        noindex=True,
    )
    reponse.status_code = 503
    return reponse


def mentions_legales(request):
    return _page(
        request, "pages/mentions_legales.html", {},
        _("Mentions légales"),
        _("Éditeur, hébergement et propriété des contenus du site de la FENAMO-RDC."),
    )


def confidentialite(request):
    return _page(
        request, "pages/confidentialite.html", {},
        _("Confidentialité"),
        _("Ce que le site de la FENAMO-RDC collecte, à quoi cela sert, et ce que montre la vérification publique."),
    )


# ---------- Erreurs ----------

def page_404(request, exception=None):
    reponse = render(
        request, "pages/404.html",
        {"page_title": _("Page introuvable"), "page_description": _("Cette page n'existe pas ou a changé d'adresse."), "noindex": True},
        status=404,
    )
    return reponse


def page_500(request):
    """Page autonome : aucun appel à l'API, aucun processeur de contexte (valeurs fixes)."""
    with translation.override(settings.LANGUAGE_CODE):
        contexte = {**contexte_minimal(), "page_title": _("Erreur du site"), "page_description": "", "noindex": True}
        return HttpResponseServerError(render_to_string("pages/500.html", contexte))


# ---------- Purge du cache (appelée par l'application web après une publication) ----------

def _signature(horodatage: str) -> str:
    return hmac.new(settings.PURGE_SECRET.encode(), horodatage.encode(), hashlib.sha256).hexdigest()


@csrf_exempt
@require_POST
def purge(request):
    """POST /_purge/ : vide les copies fraîches du cache (les copies de secours restent).

    En-têtes : X-Purge-Horodatage ou X-Purge-Timestamp (secondes Unix) et X-Purge-Signature (HMAC-SHA256 hexadécimal de cet
    horodatage, clé PURGE_SECRET). Réponses : 204 ; 403 signature absente, fausse, trop ancienne ou déjà
    utilisée ; 429 au-delà de 10 appels par minute. Pas de CSRF : l'appelant est un serveur, il s'authentifie
    par signature.
    """
    fenetre = f"purge:minute:{int(time.time() // 60)}"
    cache.add(fenetre, 0, 120)
    try:
        appels = cache.incr(fenetre)
    except ValueError:
        appels = 1
    if appels > settings.PURGE_LIMITE_PAR_MINUTE:
        return HttpResponse(status=429, headers={"Retry-After": "60"})
    # web_app envoie X-Purge-Horodatage ; X-Purge-Timestamp reste accepté (compatibilité)
    horodatage = request.headers.get("X-Purge-Horodatage") or request.headers.get("X-Purge-Timestamp", "")
    signature = request.headers.get("X-Purge-Signature", "").strip().lower()
    if not settings.PURGE_SECRET or not horodatage.isdigit() or not signature:
        return HttpResponse(status=403)
    if abs(time.time() - int(horodatage)) > settings.PURGE_TOLERANCE:
        return HttpResponse(status=403)
    if not hmac.compare_digest(signature.encode(), _signature(horodatage).encode()):
        logger.warning("Purge refusée : signature invalide (%s)", request.META.get("REMOTE_ADDR", "?"))
        return HttpResponse(status=403)
    if not cache.add(f"purge:vu:{signature}", 1, 2 * settings.PURGE_TOLERANCE):
        logger.warning("Purge refusée : signature déjà utilisée")
        return HttpResponse(status=403)
    api_client.purger_cache()
    return HttpResponse(status=204)


# ---------- sitemap.xml et robots.txt ----------

ROUTES_PUBLIQUES = [
    "pages:accueil", "pages:a-propos", "pages:comite", "pages:coordinations", "pages:documents",
    "pages:application", "pages:actualites", "pages:galerie", "pages:contact", "pages:adhesion",
    "pages:mentions-legales", "pages:confidentialite",
]


def _urls_sitemap():
    """[(chemin_par_langue: {code: chemin}, lastmod|None)] pour les pages fixes puis les articles."""
    actives = langues_actives()
    entrees = []

    def chemins(nom, *args):
        resultat = {}
        for code in actives:
            with translation.override(code):
                resultat[code] = reverse(nom, args=args)
        return resultat

    for nom in ROUTES_PUBLIQUES:
        entrees.append((chemins(nom), None))
    for page in range(1, 5):  # 200 articles au plus : suffisant, et les appels sont en cache
        try:
            liste = site_api.articles(settings.LANGUAGE_CODE, page=page, taille=50)
        except ApiErreur:
            break
        if not liste or not liste["resultats"]:
            break
        for a in liste["resultats"]:
            entrees.append((chemins("pages:article", a["slug"]), a["date_publication"]))
        if page >= liste["pages"]:
            break
    return entrees


@require_GET
def sitemap(request):
    lignes = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">']
    for chemins, dernier in _urls_sitemap():
        principal = chemins[settings.LANGUAGE_CODE]
        lignes.append("<url>")
        lignes.append(f"<loc>{settings.SITE_URL}{principal}</loc>")
        if dernier:
            lignes.append(f"<lastmod>{dernier.date().isoformat()}</lastmod>")
        if len(chemins) > 1:
            for code, chemin in chemins.items():
                lignes.append(f'<xhtml:link rel="alternate" hreflang="{code}" href="{settings.SITE_URL}{chemin}"/>')
        lignes.append("</url>")
    lignes.append("</urlset>")
    return HttpResponse("\n".join(lignes), content_type="application/xml; charset=utf-8")


@require_GET
def robots(request):
    if settings.SITE_NOINDEX or site_api.config()["statique"]:
        corps = "User-agent: *\nDisallow: /\n"
    else:
        corps = (
            "User-agent: *\n"
            "Disallow: /verifier/\nDisallow: /v/\nDisallow: /adhesion/suivi/\nDisallow: /adhesion/paiement/\n"
            "Disallow: /telecharger/\nDisallow: /_purge/\n"
            f"Sitemap: {settings.SITE_URL}/sitemap.xml\n"
        )
    return HttpResponse(corps, content_type="text/plain; charset=utf-8")


@require_http_methods(["GET", "HEAD"])
def ancienne_adresse_supprimee(request):
    """/configuration/ de l'ancien site : supprimée volontairement (annexe B), 410."""
    return HttpResponse(status=410)
