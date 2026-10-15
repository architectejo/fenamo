"""Lot 2a : fichiers de traduction à jour, repli sur le français, langue incomplète jamais active."""
import ast
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "tools"))


def test_S11_les_po_contiennent_tous_les_textes_des_gabarits():
    import extraire_messages

    attendus = {msgid for (msgid, _plural) in extraire_messages.extraire()}
    for code in ("fr", "ln", "sw", "lua", "kg"):
        po = (RACINE / "locale" / code / "LC_MESSAGES" / "django.po").read_text(encoding="utf-8")
        presents = set()
        for ligne in po.splitlines():
            if ligne.startswith("msgid ") and ligne != 'msgid ""':
                presents.add(ast.literal_eval(ligne[6:]))
        manquants = attendus - presents
        assert not manquants, f"{code} : relancer python tools/extraire_messages.py ({len(manquants)} textes absents, ex. {sorted(manquants)[:2]})"


def test_S11_repli_francais_pour_un_texte_non_traduit(client, api, langues_completes):
    api.config(langues_actives=["fr", "kg"])
    html = client.get("/kg/a-propos/").content.decode()
    assert '<html lang="kg">' in html and "Nos douze objectifs" in html


def test_S11_une_traduction_saisie_s_affiche(client, api, langues_completes, tmp_path, settings):
    """Un .po compilé avec une traduction l'emporte sur le français (mécanisme du repli)."""
    from django.utils import translation

    with translation.override("ln"):
        assert translation.gettext("Texte jamais traduit") == "Texte jamais traduit"


def test_S11_po_avec_pluriels_analyse_sans_erreur(tmp_path):
    from services.langues import _analyser_po

    po = tmp_path / "django.po"
    po.write_text(
        'msgid ""\nmsgstr ""\n\nmsgid "Un"\nmsgid_plural "Des"\nmsgstr[0] "A"\nmsgstr[1] ""\n\nmsgid "Deux"\nmsgstr "B"\n',
        encoding="utf-8",
    )
    assert _analyser_po(po) == (2, 1)


def test_S11_langue_complete_seulement_si_tout_est_traduit(tmp_path, settings):
    from services import langues

    (tmp_path / "ln" / "LC_MESSAGES").mkdir(parents=True)
    (tmp_path / "ln" / "LC_MESSAGES" / "django.po").write_text('msgid ""\nmsgstr ""\n\nmsgid "Un"\nmsgstr "A"\n', encoding="utf-8")
    settings.LOCALE_PATHS = [tmp_path]
    assert "ln" in langues.po_complets() and "sw" not in langues.po_complets()
