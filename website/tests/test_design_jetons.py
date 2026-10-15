"""Système de design partagé : les jetons et les polices du site sont des copies exactes de ceux de l'application web.

Source unique : web_app/static/css/tokens.css. Après toute modification, copier le fichier dans website/static/css/
(et les polices dans website/static/fonts/). Ces tests échouent tant que les deux copies diffèrent.
Hors du dépôt complet (site déployé seul), la comparaison est sautée ; les autres contrôles restent.
"""
import hashlib
import re
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parents[1]
APP = SITE.parent / "web_app"
POLICES = ["atkinson-hyperlegible-next-400.woff2", "atkinson-hyperlegible-next-700.woff2", "barlow-condensed-600.woff2"]


def empreinte(chemin):
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


@pytest.mark.skipif(not (APP / "static" / "css" / "tokens.css").exists(), reason="application web absente (site déployé seul)")
def test_design_jetons_identiques_dans_les_deux_projets():
    site, app = SITE / "static" / "css" / "tokens.css", APP / "static" / "css" / "tokens.css"
    assert empreinte(site) == empreinte(app), (
        "website/static/css/tokens.css diffère de web_app/static/css/tokens.css : copier le fichier de l'application sur celui du site."
    )


@pytest.mark.skipif(not (APP / "static" / "fonts").exists(), reason="application web absente (site déployé seul)")
@pytest.mark.parametrize("police", POLICES)
def test_design_polices_identiques_dans_les_deux_projets(police):
    assert empreinte(SITE / "static" / "fonts" / police) == empreinte(APP / "static" / "fonts" / police)


def test_design_polices_locales_et_presentes():
    jetons = (SITE / "static" / "css" / "tokens.css").read_text(encoding="utf-8")
    site = (SITE / "static" / "css" / "site.css").read_text(encoding="utf-8")
    for texte in (jetons, site):
        assert "fonts.googleapis" not in texte and "@import" not in texte and "http" not in re.sub(r"/\*.*?\*/", "", texte, flags=re.S)
    for url in re.findall(r'url\("\.\./fonts/([^"]+)"\)', jetons):
        assert (SITE / "static" / "fonts" / url).exists(), url


def test_design_site_css_sans_couleur_en_dur():
    """Toute couleur de site.css vient d'un jeton (aucun #hex, rgb() ni nom de couleur en dur)."""
    css = re.sub(r"/\*.*?\*/", "", (SITE / "static" / "css" / "site.css").read_text(encoding="utf-8"), flags=re.S)
    assert re.findall(r"#[0-9a-fA-F]{3,8}\b", css) == []
    assert re.findall(r"\brgba?\(", css) == []
    assert re.findall(r":\s*(?:black|white|red|blue|yellow|green|gray|grey)\b", css) == []


def test_design_icones_utilisees_par_les_maquettes_dans_le_sprite():
    sprite = (SITE / "static" / "img" / "icons.svg").read_text(encoding="utf-8")
    presentes = set(re.findall(r'<symbol id="i-([\w-]+)"', sprite))
    utilisees = set()
    for f in (SITE / "docs" / "design" / "maquettes").glob("*.html"):
        utilisees |= set(re.findall(r"icons\.svg#i-([\w-]+)", f.read_text(encoding="utf-8")))
    assert utilisees - presentes == set()
