"""Jeu d'exemple servi à la place de l'API quand les données réelles sont désactivées dans web_app.

`repondre(chemin, params, langue)` rend le JSON brut qu'aurait rendu l'API (mêmes champs), à partir de
`contenu_statique/exemple.py`. Aucun appel réseau. Un chemin ou un article inconnu lève ApiErreur(404).
"""
from __future__ import annotations

import copy

from django.templatetags.static import static

from contenu_statique import exemple

from .api_client import ApiErreur


def _page(elements: list, params: dict) -> dict:
    taille = max(1, min(50, int(params.get("taille", 12))))
    page = max(1, int(params.get("page", 1)))
    pages = -(-len(elements) // taille)
    if page > max(pages, 1):
        raise ApiErreur(404)
    debut = (page - 1) * taille
    return {"total": len(elements), "page": page, "pages": pages, "resultats": elements[debut : debut + taille]}


def _article(a: dict, langue: str | None, detail: bool = False) -> dict:
    d = {
        "slug": a["slug"], "type": a["type"], "titre": a["titre"], "resume": a["resume"], "image": None,
        "date_publication": a["date_publication"], "langue": "fr", "traduit": langue in (None, "", "fr"),
    }
    if detail:
        d.update({"texte": a["texte"], "video": None, "galerie": [], "langues_disponibles": ["fr"], "mise_a_jour": a["date_publication"]})
    return d


def repondre(chemin: str, params: dict | None = None, langue: str | None = None):
    params = dict(params or {})
    if chemin == "config/":
        return copy.deepcopy(exemple.CONFIG)
    if chemin == "articles/":
        q = (params.get("q") or "").lower()
        liste = [
            _article(a, langue) for a in exemple.ARTICLES
            if params.get("type") in (None, a["type"]) and (not q or q in (a["titre"] + " " + a["resume"]).lower())
        ]
        return _page(liste, params)
    if chemin.startswith("articles/") and chemin.count("/") == 2:
        slug = chemin.split("/")[1]
        for a in exemple.ARTICLES:
            if a["slug"] == slug:
                return _article(a, langue, detail=True)
        raise ApiErreur(404)
    if chemin == "galerie/":
        image = {"url": static("img/exemple.svg"), "vignette": static("img/exemple.svg"), "largeur": 640, "hauteur": 640}
        elements = [
            {"type": "photo", "image": image, "video": None, "legende": legende, "date": "2026-01-01", "article": None}
            for legende in exemple.GALERIE_LEGENDES
        ]
        return _page([e for e in elements if params.get("type") in (None, e["type"])], params)
    if chemin == "comite/":
        return {
            "mandat": {"debut": None, "fin": None},
            "membres": [
                {"nom": f"Prénom Nom {i} (exemple)", "fonction": f, "fonction_code": c, "photo": None, "ordre": i}
                for i, (f, c) in enumerate(exemple.COMITE, start=1)
            ],
        }
    if chemin == "coordinations/":
        antennes = [
            {"nom": "Antenne d'exemple 1", "type": "commune"},
            {"nom": "Antenne d'exemple 2", "type": "territoire"},
        ]
        return [
            {"code": c, "nom": n, "ordre": i,
             "antennes": [{**a, "code": f"{c}-EX{k}"} for k, a in enumerate(antennes[: 1 + i % 2], start=1)]}
            for i, (c, n) in enumerate(exemple.COORDINATIONS, start=1)
        ]
    if chemin == "statistiques/":
        par = [
            {"code": c, "nom": n, "membres_actifs": (i % 5 + 1) * 250, "associations_membres": i % 3 + 1,
             "antennes": 1 + i % 2, "engins_actifs": None}
            for i, (c, n) in enumerate(exemple.COORDINATIONS, start=1)
        ]
        return {
            "date_calcul": "2026-01-01T00:00:00+01:00", "membres_actifs": sum(p["membres_actifs"] for p in par),
            "engins_actifs": None, "engins_par_type": None, "associations_membres": sum(p["associations_membres"] for p in par),
            "coordinations": len(par), "par_coordination": par,
        }
    raise ApiErreur(404)
