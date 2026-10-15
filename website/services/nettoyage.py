"""Nettoyage défensif du HTML venu de l'API et construction des lecteurs vidéo (§ 10.1).

L'API nettoie déjà le texte des articles (liste blanche) ; le site le nettoie une seconde fois avant de
l'afficher : un texte modifié en route ou une API compromise ne doit pas pouvoir injecter de script.
Même liste blanche que l'API : p, br, strong, em, ul, ol, li, h2, h3, a[href http(s)]. Aucune bibliothèque
externe : analyse par `html.parser`, texte ré-échappé, balises refermées.

Vidéo : l'API ne fournit jamais de code d'intégration, seulement {fournisseur, identifiant}. Le site fabrique
l'adresse du lecteur lui-même, pour une liste blanche de fournisseurs et d'identifiants au format attendu.
"""
from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser
from urllib.parse import quote, urlsplit

BALISES = frozenset({"p", "br", "strong", "em", "ul", "ol", "li", "h2", "h3", "a"})
VIDES = frozenset({"br"})
EFFACER_AVEC_CONTENU = frozenset({"script", "style", "iframe", "object", "embed", "template", "noscript", "svg", "math", "head", "title"})
PROFONDEUR_MAX = 30


def lien_autorise(adresse) -> bool:
    """Vrai pour une adresse http(s) absolue ; refuse javascript:, data:, vbscript:, //hote sans schéma."""
    nettoye = "".join(c for c in (adresse or "") if c >= " " and c != "\x7f").strip()
    try:
        morceaux = urlsplit(nettoye)
    except ValueError:
        return False
    return morceaux.scheme.lower() in ("http", "https") and bool(morceaux.netloc) and len(nettoye) <= 2000


class _Nettoyeur(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sortie: list[str] = []
        self.ouvertes: list[str] = []
        self.ignore = 0

    def handle_starttag(self, balise, attributs):
        if balise in EFFACER_AVEC_CONTENU:
            self.ignore += 1
            return
        if self.ignore or balise not in BALISES:
            return
        if balise == "a":
            href = dict(attributs).get("href") or ""
            if not lien_autorise(href) or len(self.ouvertes) >= PROFONDEUR_MAX:
                return  # le lien est retiré, son texte reste
            self.sortie.append(f'<a href="{escape(href.strip(), quote=True)}" rel="noopener noreferrer">')
            self.ouvertes.append("a")
            return
        if balise in VIDES:
            self.sortie.append("<br>")
            return
        if len(self.ouvertes) >= PROFONDEUR_MAX:
            return
        self.sortie.append(f"<{balise}>")
        self.ouvertes.append(balise)

    def handle_startendtag(self, balise, attributs):
        self.handle_starttag(balise, attributs)
        if balise not in VIDES and balise in BALISES and balise != "a":
            self.handle_endtag(balise)

    def handle_endtag(self, balise):
        if balise in EFFACER_AVEC_CONTENU:
            self.ignore = max(self.ignore - 1, 0)
            return
        if self.ignore or balise not in BALISES or balise in VIDES or balise not in self.ouvertes:
            return
        while self.ouvertes:  # imbrication cassée réparée
            haut = self.ouvertes.pop()
            self.sortie.append(f"</{haut}>")
            if haut == balise:
                break

    def handle_data(self, donnees):
        if not self.ignore:
            self.sortie.append(escape(donnees, quote=False))

    def handle_comment(self, donnees):
        return

    def resultat(self) -> str:
        while self.ouvertes:
            self.sortie.append(f"</{self.ouvertes.pop()}>")
        return "".join(self.sortie)


def nettoyer_html(texte) -> str:
    """HTML réduit à la liste blanche ; chaîne vide pour une valeur vide. Le résultat peut être marqué sûr."""
    if not texte:
        return ""
    nettoyeur = _Nettoyeur()
    nettoyeur.feed(str(texte))
    nettoyeur.close()
    return nettoyeur.resultat().strip()


# ---------- Lecteurs vidéo ----------

_YOUTUBE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_HOTES_FACEBOOK = frozenset({"www.facebook.com", "facebook.com", "m.facebook.com", "web.facebook.com", "fb.watch"})


def construire_video(valeur) -> dict | None:
    """{fournisseur, identifiant} -> {fournisseur, identifiant, embed, lien} ou None si hors liste blanche.

    - youtube : identifiant de 11 caractères ; lecteur sur youtube-nocookie.com ;
    - facebook : l'identifiant est l'adresse https complète de la vidéo (hôte Facebook seulement).
    """
    if not isinstance(valeur, dict):
        return None
    fournisseur, identifiant = valeur.get("fournisseur"), valeur.get("identifiant")
    if not isinstance(identifiant, str):
        return None
    identifiant = identifiant.strip()
    if fournisseur == "youtube" and _YOUTUBE.match(identifiant):
        return {
            "fournisseur": "youtube",
            "identifiant": identifiant,
            "embed": f"https://www.youtube-nocookie.com/embed/{identifiant}?rel=0",
            "lien": f"https://www.youtube.com/watch?v={identifiant}",
        }
    if fournisseur == "facebook":
        try:
            morceaux = urlsplit(identifiant)
        except ValueError:
            return None
        if morceaux.scheme == "https" and (morceaux.hostname or "").lower() in _HOTES_FACEBOOK and len(identifiant) <= 500:
            return {
                "fournisseur": "facebook",
                "identifiant": identifiant,
                "embed": "https://www.facebook.com/plugins/video.php?show_text=false&href=" + quote(identifiant, safe=""),
                "lien": identifiant,
            }
    return None
