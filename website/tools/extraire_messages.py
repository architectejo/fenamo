"""Extrait les textes à traduire (templates et code) vers locale/*/LC_MESSAGES/django.po, sans GNU gettext.

Usage : python tools/extraire_messages.py [--langues fr ln sw lua kg]
Équivalent minimal de `makemessages` pour les gabarits Django (`{% translate %}`, `{% blocktranslate %}`,
`_("...")` dans un gabarit) et le code Python (`_()`, `gettext()`, `gettext_lazy()`).
Les traductions déjà saisies sont conservées ; les textes disparus sont retirés.
Un texte sans traduction reste vide : Django affiche alors le texte français (repli).
Ensuite : python tools/compile_mo.py
"""
import ast
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
LANGUES = ["fr", "ln", "sw", "lua", "kg"]
DOSSIERS = ["templates", "pages", "services", "site_fenamo"]

RE_TRANSLATE = re.compile(r"""\{%-?\s*(?:translate|trans)\s+(?P<q>["'])(?P<t>(?:\\.|(?!(?P=q)).)*)(?P=q)[^%]*%\}""", re.S)
RE_UNDERSCORE = re.compile(r"""\b_\(\s*(?P<q>["'])(?P<t>(?:\\.|(?!(?P=q)).)*)(?P=q)\s*\)""", re.S)
RE_BLOC = re.compile(r"\{%-?\s*(?:blocktranslate|blocktrans)(?P<opts>[^%]*)%\}(?P<corps>.*?)\{%-?\s*endblocktrans(?:late)?\s*-?%\}", re.S)
RE_VAR = re.compile(r"\{\{\s*([\w.]+)\s*(?:\|[^}]*)?\}\}")
RE_PLURAL = re.compile(r"\{%-?\s*plural\s*-?%\}")


def delit(texte: str, q: str) -> str:
    return texte.replace("\\" + q, q).replace("\\n", "\n").replace("\\\\", "\\")


def variable(opts: str, nom: str) -> str:
    return nom.split(".")[-1]


def bloc(corps: str, opts: str):
    """(msgid, plural|None) d'un blocktranslate : {{ x.y }} -> %(y)s ; `trimmed` replie les blancs."""
    noms = {}
    for m in re.finditer(r"(\w+)=([\w.\"']+)", opts):
        noms[m.group(2)] = m.group(1)

    def convertir(t):
        if "trimmed" in opts:
            t = " ".join(t.split())
        return RE_VAR.sub(lambda m: "%(" + (noms.get(m.group(1)) or m.group(1).split(".")[-1]) + ")s", t.replace("%", "%%"))

    morceaux = RE_PLURAL.split(corps)
    if len(morceaux) == 2:
        return convertir(morceaux[0]), convertir(morceaux[1])
    return convertir(corps), None


def extraire():
    """{(msgid, plural): [références]} dans l'ordre d'apparition."""
    trouves: dict[tuple, list] = {}

    def ajouter(msgid, plural, ref):
        if msgid.strip():
            trouves.setdefault((msgid, plural), []).append(ref)

    for dossier in DOSSIERS:
        for chemin in sorted((RACINE / dossier).rglob("*")):
            if chemin.suffix not in (".html", ".py") or "migrations" in chemin.parts or "tests" in chemin.parts:
                continue
            ref = chemin.relative_to(RACINE).as_posix()
            texte = chemin.read_text(encoding="utf-8")
            if chemin.suffix == ".html":
                for m in RE_BLOC.finditer(texte):
                    ajouter(*bloc(m.group("corps"), m.group("opts")), ref)
                for m in RE_TRANSLATE.finditer(texte):
                    ajouter(delit(m.group("t"), m.group("q")), None, ref)
                for m in RE_UNDERSCORE.finditer(texte):
                    ajouter(delit(m.group("t"), m.group("q")), None, ref)
            else:
                for noeud in ast.walk(ast.parse(texte)):
                    if isinstance(noeud, ast.Call) and noeud.args and isinstance(noeud.args[0], ast.Constant) and isinstance(noeud.args[0].value, str):
                        f = noeud.func
                        nom = f.id if isinstance(f, ast.Name) else getattr(f, "attr", "")
                        if nom in ("_", "gettext", "gettext_lazy"):
                            ajouter(noeud.args[0].value, None, f"{ref}:{noeud.lineno}")
    return trouves


def echapper(t: str) -> str:
    return t.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def ligne(mot: str, t: str) -> list[str]:
    return [f'{mot} "{echapper(t)}"']


def lire_existant(chemin: Path) -> dict:
    """{msgid: [msgstr...]} déjà saisis (pluriels : une valeur par forme)."""
    if not chemin.exists():
        return {}
    resultat, mid, vals, cur = {}, None, [], None

    def clore():
        if mid and any(vals):
            resultat[mid] = vals[:]

    for l in chemin.read_text(encoding="utf-8").splitlines():
        l = l.strip()
        if not l:
            clore(); mid, vals, cur = None, [], None
        elif l.startswith("msgid_plural"):
            cur = "p"
        elif l.startswith("msgid"):
            mid, cur = ast.literal_eval(l[5:].strip()), "id"
        elif l.startswith("msgstr["):
            vals.append(ast.literal_eval(l.split("]", 1)[1].strip())); cur = "s"
        elif l.startswith("msgstr"):
            vals = [ast.literal_eval(l[6:].strip())]; cur = "s"
        elif l.startswith('"'):
            v = ast.literal_eval(l)
            if cur == "id":
                mid += v
            elif cur == "s":
                vals[-1] += v
    clore()
    return resultat


NOMS = {"fr": "French", "ln": "Lingala", "sw": "Swahili", "lua": "Luba-Lulua (Tshiluba)", "kg": "Kongo (Kikongo)"}


def ecrire(code: str, trouves: dict):
    chemin = RACINE / "locale" / code / "LC_MESSAGES" / "django.po"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    anciens = lire_existant(chemin)
    sortie = [
        f"# Traductions FENAMO-RDC - {NOMS[code]}.",
        "# Textes sources en français : une chaîne sans traduction s'affiche en français (repli).",
        "# Lingala : les lettres ɛ et ɔ demandent un sous-ensemble de police « latin étendu » (voir docs/design).",
        'msgid ""', 'msgstr ""', '"Project-Id-Version: site-fenamo\\n"', f'"Language: {code}\\n"', '"MIME-Version: 1.0\\n"',
        '"Content-Type: text/plain; charset=UTF-8\\n"', '"Content-Transfer-Encoding: 8bit\\n"', '"Plural-Forms: nplurals=2; plural=(n > 1);\\n"', "",
    ]
    for (msgid, plural), refs in trouves.items():
        sortie.append("#: " + " ".join(dict.fromkeys(refs)))
        if "%(" in msgid or "%(" in (plural or ""):
            sortie.append("#, python-format")
        sortie += ligne("msgid", msgid)
        deja = anciens.get(msgid, [])
        if plural is not None:
            sortie += ligne("msgid_plural", plural)
            for i in range(2):
                sortie.append(f'msgstr[{i}] "{echapper(deja[i] if i < len(deja) else "")}"')
        else:
            sortie += ligne("msgstr", deja[0] if deja else "")
        sortie.append("")
    chemin.write_text("\n".join(sortie), encoding="utf-8")
    return len(trouves)


def main():
    langues = sys.argv[sys.argv.index("--langues") + 1:] if "--langues" in sys.argv else LANGUES
    trouves = extraire()
    for code in langues:
        print(f"locale/{code} : {ecrire(code, trouves)} textes")


if __name__ == "__main__":
    main()
