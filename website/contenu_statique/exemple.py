"""Jeu d'exemple FIXE du site (mode « données d'exemple »).

Aucune donnée réelle : ni nom de personne, ni numéro de membre, ni téléphone, ni adresse, ni effectif réel.
Seuls les 27 codes et noms de coordinations viennent de la charte (art. 43, texte public). Les noms sont
« Prénom Nom (exemple) », les effectifs sont inventés (valeurs arrondies), les adresses sont en `.invalid`.
Les données ont la forme exacte des réponses de l'API (`/api/v1/site/`) : le site les traite comme elles.
"""

COORDINATIONS = [
    ("BU", "Bas-Uele"), ("EQ", "Équateur"), ("HK", "Haut-Katanga"), ("HL", "Haut-Lomami"), ("HU", "Haut-Uele"),
    ("IT", "Ituri"), ("KA", "Kasaï"), ("KC", "Kasaï Central"), ("KO", "Kasaï oriental"), ("KN-E", "Kinshasa-Est"),
    ("KN-O", "Kinshasa-Ouest"), ("KOC", "Kongo-Central"), ("KW", "Kwango"), ("KL", "Kwilu"), ("LO", "Lomami"),
    ("LW", "Lualaba"), ("MD", "Mai-Ndombe"), ("MN", "Maniema"), ("MO", "Mongala"), ("NU", "Nord-Ubangi"),
    ("NK", "Nord-Kivu"), ("SA", "Sankuru"), ("SK", "Sud-Kivu"), ("SU", "Sud-Ubangi"), ("TG", "Tanganyika"),
    ("TS", "Tshopo"), ("TP", "Tshuapa"),
]

CONFIG = {
    "nom": "FENAMO-RDC",
    "nom_complet": "Fédération Nationale des Associations des Motocyclistes Taximen de la République Démocratique du Congo",
    "devise": "Unité, Discipline et Progrès",
    "message_accueil": "",
    "logo": None,
    "image_fond": None,
    "siege": "Siège d'exemple, Kinshasa",
    "email": "exemple@exemple.invalid",
    "telephones": [],
    "reseaux": {},
    "partenaires": [],
    "langues_actives": ["fr"],
    "paiement_en_ligne": False,
    "documents": [
        {"titre": "Document d'exemple (charte)", "type": "charte", "url": "https://exemple.invalid/documents/charte-exemple.pdf", "taille": 1048576, "date": "2026-01-01"},
        {"titre": "Formulaire d'exemple", "type": "autre", "url": "https://exemple.invalid/documents/formulaire-exemple.pdf", "taille": 102400, "date": "2026-01-01"},
    ],
    "application": None,
    "mise_a_jour": None,
}

_TEXTE = (
    "<p>Texte d'exemple : ce contenu est fictif et sert seulement à montrer la mise en page du site.</p>"
    "<h2>Intertitre d'exemple</h2><ul><li>Premier point d'exemple</li><li>Deuxième point d'exemple</li></ul>"
)
ARTICLES = [
    {"slug": "communique-d-exemple", "type": "communique", "titre": "Communiqué d'exemple", "resume": "Résumé d'exemple d'un communiqué : contenu fictif.", "date_publication": "2026-01-15T09:00:00+01:00", "texte": _TEXTE},
    {"slug": "actualite-d-exemple-1", "type": "article", "titre": "Actualité d'exemple, premier article", "resume": "Résumé d'exemple d'une actualité : contenu fictif.", "date_publication": "2026-01-10T09:00:00+01:00", "texte": _TEXTE},
    {"slug": "actualite-d-exemple-2", "type": "article", "titre": "Actualité d'exemple, second article", "resume": "Autre résumé d'exemple : contenu fictif.", "date_publication": "2026-01-05T09:00:00+01:00", "texte": _TEXTE},
]

COMITE = [  # fonctions de l'article 19 de la charte ; noms fictifs
    ("Président national", "PRESIDENT"), ("Vice-président chargé d'administration et question juridique", "VP"),
    ("Vice-président chargé des Finances et fiscalité", "VP"), ("Secrétaire général", "SG"),
    ("Secrétaire rapporteur", "SR"), ("Inspecteur général chargé des opérations et activités", "IG"),
    ("Trésorier général chargé des recettes", "TRESORIER"), ("Conseiller communication / médias", "CONSEILLER"),
]

GALERIE_LEGENDES = [f"Photo d'exemple {i}" for i in range(1, 7)]
