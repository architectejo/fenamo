"""Un service par point d'accès de `/api/v1/site/`, au-dessus de `api_client.get` (S-01, S-09, S-10).

Règles :
- le site ne garde que les champs qu'il connaît (liste blanche) et ignore les champs inconnus du contrat ;
- toute adresse de fichier ou de lien est une adresse http(s) ou disparaît ;
- aucune de ces fonctions ne plante quand l'API est absente : elle rend `None` (ou la valeur par défaut de
  la configuration) et le suivi de la requête (`api_client.suivi()`) signale la panne ou le verrou F-07 ;
  la page affiche alors un état vide soigné ;
- le texte HTML d'un article est nettoyé une seconde fois ici (le premier nettoyage est fait par l'API).
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from urllib.parse import urlsplit

from django.utils.dateparse import parse_date, parse_datetime
from django.utils.safestring import mark_safe

from . import api_client
from . import donnees_statiques
from .api_client import ApiErreur, ApiIndisponible, ApiInactif, ApiSuspendu
from .nettoyage import construire_video, nettoyer_html

logger = logging.getLogger(__name__)

NOM_COMPLET = "Fédération Nationale des Associations des Motocyclistes Taximen de la République Démocratique du Congo"
DEVISE = "Unité, Discipline et Progrès"
# Siège administratif et social, article 3 de la charte : valeur de repli quand la configuration est absente.
SIEGE_STATUTAIRE = "04, avenue Kasa-Vubu, quartier Mariano, commune de Ngiri-Ngiri, Kinshasa"

TYPES_ARTICLE = ("article", "communique")
TYPES_GALERIE = ("photo", "video")

CONFIG_DEFAUT = {
    "nom": "FENAMO-RDC",
    "nom_complet": NOM_COMPLET,
    "devise": DEVISE,
    "message_accueil": "",
    "logo": None,
    "image_fond": None,
    "siege": SIEGE_STATUTAIRE,
    "siege_configure": False,
    "email": "",
    "telephones": [],
    "reseaux": {},
    "partenaires": [],
    "langues_actives": None,
    "paiement_en_ligne": False,
    "documents": [],
    "application": None,
    "mise_a_jour": None,
    "disponible": False,
    "statique": False,
}


# ---------- Valeurs de base ----------

def _texte(valeur, maxi: int = 5000) -> str:
    return valeur.strip()[:maxi] if isinstance(valeur, str) else ""


def _entier(valeur) -> int | None:
    return valeur if isinstance(valeur, int) and not isinstance(valeur, bool) else None


def url_http(valeur) -> str | None:
    """Adresse http(s) absolue ou None (jamais javascript:, data:, //hote…)."""
    if not isinstance(valeur, str):
        return None
    nette = "".join(c for c in valeur if c >= " " and c != "\x7f").strip()
    try:
        morceaux = urlsplit(nette)
    except ValueError:
        return None
    if morceaux.scheme.lower() in ("http", "https") and morceaux.netloc and len(nette) <= 2000:
        return nette
    return None


def _image(valeur) -> dict | None:
    if not isinstance(valeur, dict):
        return None
    url = url_http(valeur.get("url"))
    if not url and isinstance(valeur.get("url"), str) and valeur["url"].startswith("/static/"):
        url = valeur["url"]  # placeholder local du jeu d'exemple
    if not url:
        return None
    return {
        "url": url,
        "vignette": url_http(valeur.get("vignette")) or (valeur["vignette"] if str(valeur.get("vignette", "")).startswith("/static/") else url),
        "largeur": _entier(valeur.get("largeur")),
        "hauteur": _entier(valeur.get("hauteur")),
    }


def _instant(valeur) -> datetime | None:
    if not isinstance(valeur, str):
        return None
    try:
        return parse_datetime(valeur)
    except ValueError:
        return None


def _jour(valeur) -> date | None:
    if not isinstance(valeur, str):
        return None
    try:
        return parse_date(valeur)
    except ValueError:
        return None


def _liste(valeur) -> list:
    return valeur if isinstance(valeur, list) else []


def _lire(chemin: str, **kw):
    """Lecture tolérante : les données, ou None si l'API est absente ou suspendue et qu'aucune copie n'existe.

    Fournisseur unique : en mode « exemple » (données réelles désactivées dans web_app, ou 403 « inactif »
    reçu), le jeu statique est servi sans aucun appel aux points d'accès de données.
    Seul un 404 (article inconnu, page hors limite) remonte : la vue en fait une page 404. Toute autre
    erreur applicative est journalisée et traitée comme une absence de données.
    """
    if config()["statique"]:
        return donnees_statiques.repondre(chemin, kw.get("params"), kw.get("langue"))
    try:
        return api_client.get(chemin, **kw).donnees
    except ApiInactif:
        _basculer_statique()
        return donnees_statiques.repondre(chemin, kw.get("params"), kw.get("langue"))
    except (ApiSuspendu, ApiIndisponible):
        return None
    except ApiErreur as exc:
        if exc.status == 404:
            raise
        logger.warning("API : erreur %s inattendue sur %s", exc.status, chemin)
        return None


def _basculer_statique() -> None:
    """403 « inactif » sur un point d'accès : l'état change ; la configuration est relue à la prochaine requête."""
    api_client.purger_cache()
    api_client.retenir_mode("statique")
    api_client.forcer_statique()
    api_client.noter(statique=True)


def signaler_inactif() -> None:
    """Pour les dépôts (S-07…) : un 403 « inactif » reçu fait basculer le site en mode exemple."""
    _basculer_statique()


# ---------- Configuration (en-tête, pied de page, documents, application) ----------

def _document(d) -> dict | None:
    if not isinstance(d, dict):
        return None
    url = url_http(d.get("url"))
    titre = _texte(d.get("titre"), 200)
    if not url or not titre:
        return None
    return {"titre": titre, "type": _texte(d.get("type"), 40), "url": url, "taille": _entier(d.get("taille")), "date": _jour(d.get("date"))}


def _application(d) -> dict | None:
    if not isinstance(d, dict):
        return None
    version = _texte(d.get("version"), 40)
    url = url_http(d.get("url"))
    if not version or not url:
        return None
    return {"version": version, "url": url, "taille": _entier(d.get("taille")), "date": _jour(d.get("date")), "notice": _texte(d.get("notice"), 2000)}


def config() -> dict:
    """Configuration publique normalisée ; `disponible` est faux sans réponse ni copie ; `statique` : jeu d'exemple.

    Le mode vient de `donnees_reelles` (toujours exposé par l'API). Copie de secours ou API absente : on suit
    le dernier état connu, jamais de données réelles servies par erreur quand il était « statique ».
    """
    if api_client.statique_force():
        return _config_statique(None)
    try:
        rep = api_client.get("config/", ttl="config")
    except ApiInactif:
        api_client.retenir_mode("statique")
        return _config_statique(None)
    except (ApiSuspendu, ApiIndisponible):
        if api_client.dernier_mode() == "statique":
            return _config_statique(None)
        return dict(CONFIG_DEFAUT)
    except ApiErreur as exc:
        logger.warning("API : erreur %s inattendue sur config/", exc.status)
        return dict(CONFIG_DEFAUT)
    brut = rep.donnees
    if not isinstance(brut, dict):
        return dict(CONFIG_DEFAUT)
    reel = brut.get("donnees_reelles") is not False
    if rep.degrade:
        reel = reel and api_client.dernier_mode() != "statique"
    else:
        api_client.retenir_mode("reel" if reel else "statique")
    if not reel:
        return _config_statique(brut)
    return _normaliser_config(brut)


def _config_statique(brut: dict | None) -> dict:
    """Configuration d'exemple ; seuls le nom, la devise et les langues viennent de l'API (config minimale)."""
    donnees = donnees_statiques.repondre("config/")
    for cle in ("nom", "devise", "langues_actives"):
        if brut and brut.get(cle):
            donnees[cle] = brut[cle]
    api_client.noter(statique=True)
    return {**_normaliser_config(donnees), "statique": True}


def _normaliser_config(brut: dict) -> dict:
    siege = _texte(brut.get("siege"), 300)
    reseaux = {}
    for nom, adresse in (brut.get("reseaux") or {}).items() if isinstance(brut.get("reseaux"), dict) else []:
        if nom in ("facebook", "x", "youtube", "instagram", "linkedin") and url_http(adresse):
            reseaux[nom] = url_http(adresse)
    telephones = [
        {"libelle": _texte(t.get("libelle"), 80), "numero": _texte(t.get("numero"), 40)}
        for t in _liste(brut.get("telephones"))
        if isinstance(t, dict) and _texte(t.get("numero"), 40)
    ]
    partenaires = [
        {"nom": _texte(p.get("nom"), 120), "lien": url_http(p.get("lien")), "logo": _image(p.get("logo"))}
        for p in _liste(brut.get("partenaires"))
        if isinstance(p, dict) and _texte(p.get("nom"), 120)
    ]
    langues = brut.get("langues_actives")
    return {
        "nom": "FENAMO-RDC",
        "nom_complet": _texte(brut.get("nom_complet"), 300) or NOM_COMPLET,
        "devise": _texte(brut.get("devise"), 200) or DEVISE,
        "message_accueil": _texte(brut.get("message_accueil"), 300),
        "logo": _image(brut.get("logo")),
        "image_fond": _image(brut.get("image_fond")),
        "siege": siege or SIEGE_STATUTAIRE,
        "siege_configure": bool(siege),
        "email": _texte(brut.get("email"), 200),
        "telephones": telephones,
        "reseaux": reseaux,
        "partenaires": partenaires,
        "langues_actives": [c for c in langues if isinstance(c, str)] if isinstance(langues, list) else None,
        "paiement_en_ligne": brut.get("paiement_en_ligne") is True,
        "documents": [d for d in (_document(x) for x in _liste(brut.get("documents"))) if d],
        "application": _application(brut.get("application")),
        "mise_a_jour": _instant(brut.get("mise_a_jour")),
        "disponible": True,
        "statique": False,
    }


# ---------- Articles ----------

def _article(d, detail: bool = False) -> dict | None:
    if not isinstance(d, dict):
        return None
    slug = _texte(d.get("slug"), 200)
    titre = _texte(d.get("titre"), 300)
    if not slug or not titre:
        return None
    type_ = d.get("type") if d.get("type") in TYPES_ARTICLE else "article"
    article = {
        "slug": slug,
        "type": type_,
        "titre": titre,
        "resume": _texte(d.get("resume"), 1000),
        "image": _image(d.get("image")),
        "date_publication": _instant(d.get("date_publication")),
        "langue": _texte(d.get("langue"), 8),
        "traduit": d.get("traduit") is not False,
    }
    if detail:
        # Second nettoyage défensif : seul ce résultat est marqué sûr pour le gabarit
        article["texte"] = mark_safe(nettoyer_html(_texte(d.get("texte"), 200000)))
        article["video"] = construire_video(d.get("video"))
        article["galerie"] = [g for g in (_element_galerie(x) for x in _liste(d.get("galerie"))) if g]
        article["langues_disponibles"] = [c for c in _liste(d.get("langues_disponibles")) if isinstance(c, str)]
        article["mise_a_jour"] = _instant(d.get("mise_a_jour"))
    return article


def articles(langue: str, type_: str | None = None, q: str | None = None, page: int = 1, taille: int = 12) -> dict | None:
    """Liste paginée {total, page, pages, resultats} ; None si l'API est absente sans copie.

    Lève ApiErreur(404) si la page demandée dépasse la dernière. Une recherche n'est pas mise en copie
    (ses mots sont libres) : sans API, elle rend None.
    """
    params = {"page": page, "taille": taille}
    if type_ in TYPES_ARTICLE:
        params["type"] = type_
    q = (q or "").strip()[:100]
    if len(q) >= 2:
        params["q"] = q
    brut = _lire("articles/", params=params, ttl=None if "q" in params else "articles", langue=langue)
    if not isinstance(brut, dict):
        return None
    return {
        "total": _entier(brut.get("total")) or 0,
        "page": _entier(brut.get("page")) or 1,
        "pages": _entier(brut.get("pages")) or 0,
        "resultats": [a for a in (_article(x) for x in _liste(brut.get("resultats"))) if a],
    }


def article(slug: str, langue: str) -> dict | None:
    """Détail d'un article ; None si l'API est absente sans copie. ApiErreur(404) si inconnu."""
    brut = _lire(f"articles/{slug}/", ttl="articles", langue=langue)
    return _article(brut, detail=True) if isinstance(brut, dict) else None


# ---------- Galerie ----------

def _element_galerie(d) -> dict | None:
    if not isinstance(d, dict):
        return None
    type_ = d.get("type")
    if type_ not in TYPES_GALERIE:
        return None
    image = _image(d.get("image")) if type_ == "photo" else None
    video = construire_video(d.get("video")) if type_ == "video" else None
    if type_ == "photo" and not image:
        return None
    if type_ == "video" and not video:
        return None
    return {
        "type": type_,
        "image": image,
        "video": video,
        "legende": _texte(d.get("legende"), 300),
        "date": _jour(d.get("date")),
        "article": _texte(d.get("article"), 200) or None,
    }


def galerie(type_: str | None = None, page: int = 1, taille: int = 24) -> dict | None:
    params = {"page": page, "taille": taille}
    if type_ in TYPES_GALERIE:
        params["type"] = type_
    brut = _lire("galerie/", params=params, ttl="galerie")
    if not isinstance(brut, dict):
        return None
    return {
        "total": _entier(brut.get("total")) or 0,
        "page": _entier(brut.get("page")) or 1,
        "pages": _entier(brut.get("pages")) or 0,
        "resultats": [g for g in (_element_galerie(x) for x in _liste(brut.get("resultats"))) if g],
    }


# ---------- Comité, coordinations, statistiques ----------

def comite() -> dict | None:
    brut = _lire("comite/", ttl="comite")
    if not isinstance(brut, dict):
        return None
    mandat = brut.get("mandat") if isinstance(brut.get("mandat"), dict) else {}
    membres = []
    for m in _liste(brut.get("membres")):
        if not isinstance(m, dict) or not _texte(m.get("nom"), 200):
            continue
        membres.append(
            {
                "nom": _texte(m.get("nom"), 200),
                "fonction": _texte(m.get("fonction"), 200),
                "fonction_code": _texte(m.get("fonction_code"), 40),
                "photo": _image(m.get("photo")),
                "ordre": _entier(m.get("ordre")) or 0,
            }
        )
    membres.sort(key=lambda m: m["ordre"])  # ordre fixé par les éditeurs (F-63)
    return {"mandat": {"debut": _jour(mandat.get("debut")), "fin": _jour(mandat.get("fin"))}, "membres": membres}


def coordinations() -> list | None:
    brut = _lire("coordinations/", ttl="coordinations")
    if not isinstance(brut, list):
        return None
    resultat = []
    for c in brut:
        if not isinstance(c, dict) or not _texte(c.get("code"), 20) or not _texte(c.get("nom"), 120):
            continue
        antennes = [
            {"code": _texte(a.get("code"), 30), "nom": _texte(a.get("nom"), 120), "type": a.get("type") if a.get("type") in ("commune", "territoire") else ""}
            for a in _liste(c.get("antennes"))
            if isinstance(a, dict) and _texte(a.get("nom"), 120)
        ]
        resultat.append({"code": _texte(c.get("code"), 20), "nom": _texte(c.get("nom"), 120), "ordre": _entier(c.get("ordre")) or 0, "antennes": antennes})
    resultat.sort(key=lambda c: c["ordre"])
    return resultat


def statistiques() -> dict | None:
    """Chiffres agrégés. `engins_actifs` reste None tant que l'API ne le fournit pas : aucun chiffre d'engins n'est alors affiché."""
    brut = _lire("statistiques/", ttl="statistiques")
    if not isinstance(brut, dict):
        return None
    par = []
    for c in _liste(brut.get("par_coordination")):
        if isinstance(c, dict) and _texte(c.get("code"), 20):
            par.append(
                {
                    "code": _texte(c.get("code"), 20),
                    "nom": _texte(c.get("nom"), 120),
                    "membres_actifs": _entier(c.get("membres_actifs")),
                    "associations_membres": _entier(c.get("associations_membres")),
                    "antennes": _entier(c.get("antennes")),
                    "engins_actifs": _entier(c.get("engins_actifs")),
                }
            )
    return {
        "date_calcul": _instant(brut.get("date_calcul")),
        "membres_actifs": _entier(brut.get("membres_actifs")),
        "engins_actifs": _entier(brut.get("engins_actifs")),
        "associations_membres": _entier(brut.get("associations_membres")),
        "coordinations": _entier(brut.get("coordinations")),
        "par_coordination": par,
    }


__all__ = [
    "ApiErreur", "config", "articles", "article", "galerie", "comite", "coordinations", "statistiques", "url_http",
    "CONFIG_DEFAUT", "NOM_COMPLET", "DEVISE", "SIEGE_STATUTAIRE",
]
