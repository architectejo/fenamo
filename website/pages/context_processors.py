"""Variables communes à toutes les pages : configuration publique, langues, hreflang, mode dégradé."""
from datetime import datetime, timezone as fuseau_utc

from django.conf import settings
from django.templatetags.static import static
from django.urls import translate_url
from django.utils import timezone
from django.utils.translation import get_language

from services import api_client, langues, site_api

# Rubrique du menu selon le nom de la route (aria-current sur l'en-tête)
RUBRIQUES = {
    "a-propos": "fenamo", "comite": "fenamo", "coordinations": "fenamo", "documents": "fenamo",
    "adhesion": "associations", "verifier": "verifier",
    "actualites": "actualites", "article": "actualites", "galerie": "actualites",
    "application": "application",
    "contact": "contact",
}


def contexte_minimal() -> dict:
    """Valeurs fixes de l'en-tête et du pied de page (page 500 : aucun appel à l'API, § 6.2 du design)."""
    return {
        "site_url": settings.SITE_URL,
        "config": dict(site_api.CONFIG_DEFAUT),
        "show_language_switcher": False,
        "language_links": [],
        "hreflang_alternates": [],
        "api_etat": {"degrade": False, "copie_le": None, "suspendu": False, "panne": False, "statique": False},
        "statique": False,
        "bandeau_degrade": False,
        "og_image_defaut": settings.SITE_URL + static("img/logo-160.webp"),
        "sans_api": True,
        "app_url": settings.APP_URL,
        "langue_courante": {"code": "fr", "nom": "Français", "nom_fr": "", "url": "/", "courant": True},
    }


def site(request):
    """Variables communes : configuration, langues actives, hreflang, noindex global, état du service."""
    path = request.path
    config = site_api.config()
    actives = langues.langues_actives()  # lit la configuration déjà chargée (copie fraîche)
    noms = [(c, langues.NOMS[c]) for c in actives]
    courant = get_language() or settings.LANGUAGE_CODE
    routable = getattr(request, "resolver_match", None) is not None and request.resolver_match.url_name not in (None, "")
    etat = dict(api_client.suivi())
    copie = etat.get("copie_le")
    bandeau = bool(etat.get("degrade"))
    liens = [
        {"code": c, "nom": nom[0], "nom_fr": nom[1], "url": translate_url(path, c), "courant": c == courant}
        for c, nom in noms
    ]
    return {
        "site_url": settings.SITE_URL,
        "site_noindex": settings.SITE_NOINDEX,
        "config": config,
        "show_language_switcher": len(actives) > 1,
        "language_links": liens,
        "hreflang_alternates": [(c, settings.SITE_URL + translate_url(path, c)) for c in actives] if routable else [],
        "langue_courante": next((l for l in liens if l["courant"]), {"code": courant, "nom": courant, "nom_fr": "", "url": path, "courant": True}),
        "app_url": settings.APP_URL,
        "hreflang_default": settings.SITE_URL + translate_url(path, settings.LANGUAGE_CODE),
        "canonical_url": settings.SITE_URL + path,
        "rubrique": RUBRIQUES.get(getattr(getattr(request, "resolver_match", None), "url_name", None) or "", ""),
        "api_etat": etat,
        "statique": bool(etat.get("statique")),
        "bandeau_degrade": bandeau,
        "copie_le": datetime.fromtimestamp(copie, tz=fuseau_utc.utc).astimezone(timezone.get_current_timezone()) if copie else None,
        "og_image_defaut": settings.SITE_URL + static("img/logo-160.webp"),
    }
