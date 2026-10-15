"""Téléchargements (S-10) : adresses du site, qui comptent puis redirigent vers le fichier servi par l'application web."""
from django.db.models import F
from django.utils.text import slugify

from .models import Telechargement

SLUG_DOCUMENT = {"charte": "charte", "roi": "reglement-ordre-interieur"}
GROUPES = {"charte": "fondateurs", "roi": "fondateurs"}


def slug_application(application: dict) -> str:
    """fenamo-1-0-0 : stable pour une version donnée."""
    return "fenamo-" + slugify(application["version"].replace(".", "-")) if application else ""


def documents_avec_slug(config: dict) -> list[dict]:
    """Documents de la configuration, chacun avec son `slug` (unique) et son `cle` de compteur."""
    pris: set[str] = set()
    resultat = []
    for doc in config["documents"]:
        base = SLUG_DOCUMENT.get(doc["type"]) or slugify(doc["titre"]) or "document"
        slug, n = base, 2
        while slug in pris:
            slug, n = f"{base}-{n}", n + 1
        pris.add(slug)
        resultat.append({**doc, "slug": slug, "cle": f"document:{slug}", "groupe": GROUPES.get(doc["type"], "formulaires")})
    return resultat


def totaux(cles: list[str]) -> dict[str, int]:
    return dict(Telechargement.objects.filter(cle__in=cles).values_list("cle", "total"))


def compter(cle: str) -> None:
    """+1 atomique sur le compteur du fichier (créé au premier téléchargement)."""
    Telechargement.objects.get_or_create(cle=cle)
    Telechargement.objects.filter(cle=cle).update(total=F("total") + 1)
