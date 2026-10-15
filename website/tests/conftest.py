"""Outils de test du site : aucun appel réseau réel, API simulée avec les réponses de `tests/fixtures/`."""
import copy
import json
import socket
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import requests

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def charger(nom):
    """Fixture JSON de référence {status, headers, body}."""
    return json.loads((FIXTURES / nom).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def aucun_reseau(monkeypatch):
    """Les tests n'appellent jamais la vraie API : toute connexion sortante échoue."""
    tentatives = []

    def interdit(self, *args, **kwargs):
        tentatives.append(args)
        raise AssertionError("Appel réseau réel interdit en test")

    monkeypatch.setattr(socket.socket, "connect", interdit)
    monkeypatch.setattr(socket.socket, "connect_ex", interdit)
    yield tentatives


@pytest.fixture(autouse=True)
def cache_isole(settings, tmp_path):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "tests",
        }
    }
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _base_de_test(db):
    """Le compteur de téléchargements (S-10) est en base : la base de test est disponible partout."""


class _Reponse:
    def __init__(self, status, corps, entetes=None):
        self.status_code = status
        self._corps = corps
        self.headers = entetes or {}

    def json(self):
        if self._corps is None:
            raise ValueError("corps illisible")
        return copy.deepcopy(self._corps)


class ApiSimulee:
    """Fausse API `/api/v1/` : sert les fixtures, mémorise les appels, sait tomber en panne ou se verrouiller (F-07)."""

    def __init__(self, monkeypatch):
        self.appels = []  # (methode, chemin, params)
        self.sondes = 0
        self.mode = "ok"  # ok | coupee | verrou | lente
        self.message = "Maintenance : retour demain."
        self.sante_ok = True  # la santé répond « ok » quand le mode n'est pas « verrou »
        self.surcharges = {}  # chemin -> (status, corps[, en-têtes])
        self.envois = []  # corps (data) et en-têtes des POST reçus : [{"data": {...}, "headers": {...}}]
        self.config_corps = charger("api_site_config.json")["body"]
        self._articles = charger("api_site_articles.json")["body"]
        self._articles_ln = charger("api_site_articles_ln.json")["body"]
        self._detail = charger("api_site_article_detail.json")["body"]
        self._galerie = charger("api_site_galerie.json")["body"]
        self._comite = charger("api_site_comite.json")["body"]
        self._coordinations = charger("api_site_coordinations.json")["body"]
        self._statistiques = charger("api_site_statistiques.json")["body"]
        monkeypatch.setattr(requests, "request", self._request)
        monkeypatch.setattr(requests, "get", lambda url, **kw: self._request("GET", url, **kw))

    # --- pilotage ---
    def coupee(self):
        self.mode = "coupee"

    def rallumee(self):
        self.mode = "ok"

    def verrouillee(self, message=None):
        self.mode = "verrou"
        if message is not None:
            self.message = message

    def inactive(self):
        """Données réelles désactivées dans web_app (fixture api_site_inactif.json)."""
        self.mode = "inactif"

    def deverrouillee(self):
        self.mode = "ok"

    def repondre(self, chemin, status, corps, entetes=None):
        self.surcharges[chemin] = (status, corps, entetes or {})

    def repondre_fixture(self, chemin, nom):
        """Sert une fixture {status, headers, body} pour ce chemin."""
        f = charger(nom)
        self.repondre(chemin, f["status"], f["body"], f.get("headers"))

    def config(self, **champs):
        self.config_corps.update(champs)

    def appels_donnees(self):
        return [a for a in self.appels if not a[1].startswith("sante")]

    # --- réponses ---
    def _request(self, methode, url, params=None, **kw):
        chemin = urlsplit(url).path
        params = dict(params or {})
        if "/api/v1/sante/" in chemin:
            self.sondes += 1
            self.appels.append((methode, "sante/", params))
            if self.mode == "coupee":
                raise requests.ConnectionError("API coupée")
            return _Reponse(200, {"statut": "suspendu" if self.mode == "verrou" else "ok", "version": "v1"})
        base = "/api/v1/site/"
        relatif = chemin.split(base, 1)[1] if base in chemin else chemin
        self.appels.append((methode, relatif, params))
        if methode == "POST":
            self.envois.append({"data": dict(kw.get("data") or {}), "headers": dict(kw.get("headers") or {})})
        if self.mode == "coupee":
            raise requests.ConnectionError("API coupée")
        if self.mode == "lente":
            raise requests.Timeout("délai dépassé")
        if self.mode == "verrou":
            return _Reponse(503, {"statut": "suspendu", "detail": "Service suspendu.", "message": self.message})
        if self.mode == "inactif":
            inactif = charger("api_site_inactif.json")
            sortie = inactif["config"] if relatif == "config/" else inactif["autres"]
            return _Reponse(sortie["status"], sortie["body"])
        if relatif in self.surcharges:
            return _Reponse(*self.surcharges[relatif])
        return self._route(relatif, params)

    def _route(self, relatif, params):
        if relatif == "contact/":
            f = charger("api_site_contact_recu.json")
            return _Reponse(f["status"], f["body"], f["headers"])
        introuvable = _Reponse(404, {"detail": "Introuvable."})
        if relatif == "config/":
            return _Reponse(200, self.config_corps)
        if relatif == "statistiques/":
            return _Reponse(200, self._statistiques)
        if relatif == "comite/":
            return _Reponse(200, self._comite)
        if relatif == "coordinations/":
            return _Reponse(200, self._coordinations)
        if relatif == "galerie/":
            return self._paginer(self._galerie, params, filtre=lambda e: params.get("type") in (None, e["type"]))
        if relatif == "articles/":
            source = self._articles_ln if params.get("lang") == "ln" else self._articles
            q = (params.get("q") or "").lower()
            if params.get("q") is not None and not 2 <= len(q) <= 100:
                return _Reponse(400, {"q": ["La recherche doit contenir de 2 à 100 caractères."]})

            def filtre(a):
                return params.get("type") in (None, a["type"]) and (not q or q in (a["titre"] + " " + a["resume"]).lower())

            return self._paginer(source, params, filtre=filtre)
        if relatif.startswith("articles/") and relatif.count("/") == 2:
            slug = relatif.split("/")[1]
            if slug == self._detail["slug"]:
                return _Reponse(200, self._detail)
            return introuvable
        return introuvable

    @staticmethod
    def _paginer(source, params, filtre):
        elements = [e for e in source["resultats"] if filtre(e)]
        taille = int(params.get("taille", 12))
        page = int(params.get("page", 1))
        pages = -(-len(elements) // taille)
        if page > max(pages, 1):
            return _Reponse(404, {"detail": "Introuvable."})
        debut = (page - 1) * taille
        return _Reponse(200, {"total": len(elements), "page": page, "pages": pages, "resultats": elements[debut : debut + taille]})


@pytest.fixture(autouse=True)
def api(monkeypatch):
    """API simulée par défaut pour tous les tests (aucun appel réseau réel)."""
    return ApiSimulee(monkeypatch)


@pytest.fixture
def langues_completes(monkeypatch):
    """Toutes les traductions sont considérées complètes : l'activation dépend alors de la seule configuration."""
    from services import langues

    monkeypatch.setattr(langues, "po_complets", lambda: {c for c, _n in __import__("django.conf").conf.settings.LANGUAGES})
