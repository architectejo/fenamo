"""Carte schématique des coordinations (design § 6.3) : une case par coordination, placée par ce dictionnaire.

Les positions sont des données de présentation du site (pas de l'API). Clé : code de la coordination ;
valeur : (colonne, ligne) sur une grille de 5 colonnes. Une coordination dont le code n'est pas ici
figure dans la liste mais n'a pas de case.
"""
POSITIONS = {
    "NU": (2, 0), "BU": (3, 0), "HU": (4, 0),
    "SU": (1, 1), "MO": (2, 1), "TS": (3, 1), "IT": (4, 1),
    "EQ": (1, 2), "TP": (2, 2), "MN": (3, 2), "NK": (4, 2),
    "MD": (1, 3), "SA": (2, 3), "LO": (3, 3), "SK": (4, 3),
    "KN-O": (0, 4), "KN-E": (1, 4), "KL": (2, 4), "KO": (3, 4), "TG": (4, 4),
    "KOC": (0, 5), "KW": (1, 5), "KA": (2, 5), "KC": (3, 5), "HL": (4, 5),
    "LW": (3, 6), "HK": (4, 6),
}
PAS = 62
COTE = 56

# Seuils de couleur (membres actifs) : à ajuster quand les effectifs réels seront connus (design § 6.3)
SEUIL_1, SEUIL_2 = 1000, 5000


def classe_effectif(membres) -> int:
    """0 : aucun (ou inconnu) ; 1 : moins de 1 000 ; 2 : de 1 000 à 5 000 ; 3 : plus de 5 000."""
    if not membres:
        return 0
    if membres < SEUIL_1:
        return 1
    if membres <= SEUIL_2:
        return 2
    return 3


def tuile(code: str) -> dict | None:
    """Géométrie de la case d'un code, ou None."""
    if code not in POSITIONS:
        return None
    colonne, ligne = POSITIONS[code]
    x, y = colonne * PAS, ligne * PAS
    return {"x": x, "y": y, "cote": COTE, "tx": x + COTE / 2, "ty": y + COTE / 2 + 6}
