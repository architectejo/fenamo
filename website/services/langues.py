"""Langues actives du site (S-11, § 7).

Règle : langues actives = `config.langues_actives` (API, F-64) ∩ langues dont le fichier `.po` est complet.
Le français est toujours actif. Quand l'API ne donne ni configuration ni copie, repli sur ACTIVE_LANGUAGES
du `.env` (choix explicite de l'exploitant, non filtré).

Un `.po` est complet quand il contient des textes et qu'aucun n'a de traduction vide ou « fuzzy ».
Le français est la langue source : toujours complet.
"""
from __future__ import annotations

import ast
import logging
from functools import lru_cache
from pathlib import Path

from django.conf import settings

from . import site_api

logger = logging.getLogger(__name__)


def _analyser_po(chemin: Path) -> tuple[int, int]:
    """(textes, textes_sans_traduction) d'un .po ; l'en-tête (msgid vide) est ignoré, un pluriel compte une fois."""
    total = vides = 0
    msgid, formes, courant, flou = None, [], None, False

    def clore():
        nonlocal total, vides
        if msgid:  # non vide
            total += 1
            if not formes or not all(formes) or flou:
                vides += 1

    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne:
            clore()
            msgid, formes, courant, flou = None, [], None, False
        elif ligne.startswith("#,") and "fuzzy" in ligne:
            flou = True
        elif ligne.startswith("#") or ligne.startswith("msgctxt"):
            continue
        elif ligne.startswith("msgid_plural"):
            courant = "plural"
        elif ligne.startswith("msgid"):
            msgid, courant = ast.literal_eval(ligne[5:].strip()), "id"
        elif ligne.startswith("msgstr["):
            formes.append(ast.literal_eval(ligne.split("]", 1)[1].strip()))
            courant = "str"
        elif ligne.startswith("msgstr"):
            formes = [ast.literal_eval(ligne[6:].strip())]
            courant = "str"
        elif ligne.startswith('"'):
            valeur = ast.literal_eval(ligne)
            if courant == "id":
                msgid += valeur
            elif courant == "str" and formes:
                formes[-1] += valeur
    clore()
    return total, vides


@lru_cache(maxsize=32)
def _po_complet(chemin: str, horodatage: float) -> bool:
    try:
        total, vides = _analyser_po(Path(chemin))
    except (ValueError, SyntaxError, OSError) as exc:  # fichier abîmé : la langue n'est pas proposée, la page ne casse pas
        logger.warning("Fichier de traduction illisible (%s) : %s", chemin, exc)
        return False
    return total > 0 and vides == 0


def po_complets() -> set[str]:
    """Codes de langue dont le .po est complet (le fichier est relu s'il change)."""
    complets = {settings.LANGUAGE_CODE}
    for code, _nom in settings.LANGUAGES:
        for racine in settings.LOCALE_PATHS:
            po = Path(racine) / code / "LC_MESSAGES" / "django.po"
            if po.exists() and _po_complet(str(po), po.stat().st_mtime):
                complets.add(code)
    return complets


def langues_actives() -> list[str]:
    """Codes actifs, français en tête, dans l'ordre de settings.LANGUAGES."""
    config = site_api.config()
    demandees = config["langues_actives"]
    if demandees is None:
        demandees = list(settings.ACTIVE_LANGUAGES)  # repli .env : pas de filtre sur les .po
        autorisees = set(demandees)
    else:
        autorisees = set(demandees) & po_complets()
    codes = [code for code, _nom in settings.LANGUAGES if code in autorisees or code == settings.LANGUAGE_CODE]
    return codes


# Chaque langue dans sa propre langue, puis son nom français (design § 4, sélecteur de langue)
NOMS = {
    "fr": ("Français", ""),
    "ln": ("Lingála", "lingala"),
    "sw": ("Kiswahili", "kiswahili"),
    "lua": ("Cilubà", "tshiluba"),
    "kg": ("Kikongo", "kikongo"),
}
