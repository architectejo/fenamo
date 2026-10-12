"""Compile locale/*/LC_MESSAGES/django.po en django.mo sans GNU gettext.

Usage : python tools/compile_mo.py
Les .mo sont indispensables : Django n'active un code de langue (ln, lua, kg)
que si un django.mo existe pour lui. Équivalent minimal de `msgfmt`.
"""
import ast
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "locale"


def parse_po(text: str) -> dict:
    messages, ctx, mid, mstr, cur = {}, None, None, None, None
    fuzzy = False

    def flush():
        if mid is not None and mstr and not fuzzy:
            key = mid if ctx is None else f"{ctx}\x04{mid}"
            messages[key] = mstr

    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#,") and "fuzzy" in line:
            fuzzy = True
            continue
        if line.startswith("#") or not line:
            if not line:
                flush()
                ctx = mid = mstr = cur = None
                fuzzy = False
            continue
        if line.startswith("msgctxt"):
            ctx, cur = ast.literal_eval(line[7:].strip()), "ctx"
        elif line.startswith("msgid"):
            mid, cur = ast.literal_eval(line[5:].strip()), "id"
        elif line.startswith("msgstr"):
            mstr, cur = ast.literal_eval(line[6:].strip()), "str"
        elif line.startswith('"'):
            val = ast.literal_eval(line)
            if cur == "id":
                mid += val
            elif cur == "str":
                mstr += val
            elif cur == "ctx":
                ctx += val
    flush()
    return messages


def write_mo(messages: dict, path: Path) -> None:
    keys = sorted(messages)
    ids, strs, offsets = b"", b"", []
    for k in keys:
        kb, vb = k.encode("utf-8"), messages[k].encode("utf-8")
        offsets.append((len(ids), len(kb), len(strs), len(vb)))
        ids += kb + b"\0"
        strs += vb + b"\0"
    n = len(keys)
    keystart = 7 * 4 + 16 * n
    valuestart = keystart + len(ids)
    table = []
    for o1, l1, o2, l2 in offsets:
        table += [l1, o1 + keystart]
    for o1, l1, o2, l2 in offsets:
        table += [l2, o2 + valuestart]
    data = struct.pack("Iiiiiii", 0x950412DE, 0, n, 7 * 4, 7 * 4 + 8 * n, 0, 0)
    data += struct.pack("%di" % len(table), *table) + ids + strs
    path.write_bytes(data)


def main() -> None:
    for po in sorted(ROOT.glob("*/LC_MESSAGES/django.po")):
        messages = parse_po(po.read_text(encoding="utf-8"))
        # L'en-tête (msgid vide) est requis pour déclarer le jeu de caractères.
        messages.setdefault("", "Content-Type: text/plain; charset=UTF-8\n")
        write_mo(messages, po.with_suffix(".mo"))
        print(f"{po.relative_to(ROOT.parent)} : {len(messages) - 1} textes")


if __name__ == "__main__":
    main()
