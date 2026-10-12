# Système de design FENAMO-RDC — application web

Ce document est la référence de `frontend-htmx` : il applique ce qui est écrit ici, sans réinventer. Les deux projets (application web, puis site public) partagent les mêmes jetons. Cette phase couvre l'application web.

| Élément | Emplacement |
| --- | --- |
| Jetons (couleurs, typo, espacements, rayons, ombres, durées) | `static/css/tokens.css` |
| Feuille unique de l'application (base, coque, composants, mouvement) | `static/css/app.css` |
| Micro-interactions (bulles, modale, tiroir, compteurs, retrait de dossier) | `static/js/design.js` |
| Thème avant affichage (évite l'éclair blanc) | `static/js/theme.js` (repris du brouillon) |
| Polices `woff2` + licences OFL | `static/fonts/` |
| Icônes (sprite) + licence ISC | `static/img/icons.svg`, `static/img/LICENCE-ICONES.txt` |
| Gabarits de composants documentés | `templates/components/` |
| Maquettes statiques (utilisent les vrais fichiers ci-dessus) | `docs/design/maquettes/` (ouvrir `index.html`) |
| Captures 360 px et 1280 px, clair et sombre | `docs/design/captures/` |

Pour ouvrir les maquettes avec les polices : depuis `web_app/`, `python -m http.server 8078`, puis `http://localhost:8078/docs/design/maquettes/`. Paramètres utiles : `?theme=sombre`, `?modale=modale-renvoi`, `?menu=ouvert`, `?bulle=1`, `?etat=invalide` (vérification).

---

## 1. Plan

### 1.1 Palette : six couleurs nommées

| Nom | Hex (clair) | Hex (sombre) | Usage |
| --- | --- | --- | --- |
| Encre | `#121a26` | `#eceff3` (texte) | Texte, bouton principal, icônes, chiffres. Le bouton principal est **encre**, pas bleu. |
| Papier | `#f4f2ed` | `#0e141d` (fond) | Fond de l'application. Blanc cassé chaud, celui du carton d'une carte de membre. Les panneaux sont blancs (`#ffffff`). |
| Ciel | `#0a62b0` | `#7cbcf5` | Liens, information, état « validé antenne / province ». Dérivé du bleu ciel du drapeau, assombri pour 6,2:1 sur blanc. |
| Jaune | `#f2c200` | idem | Le repère « gilet » : élément actif du menu, halo de focus, étape en cours, bouton du bloc « À traiter ». **Jamais du texte sur fond clair** (variante texte : `#6b4f00`). |
| Rouge | `#bf1230` | `#ff8f9e` | Renvoi, suppression, erreur, pastille de compteur. |
| Vert | `#0f6e3d` | `#74d6a0` | Actif, succès, bouton « Valider ». |

Les trois couleurs exactes du drapeau (`--drapeau-ciel`, `--drapeau-jaune`, `--drapeau-rouge`) sont **réservées aux objets officiels** : carte de membre et plaque d'engin. Nulle part ailleurs (pas de bandeau, pas de liseré décoratif).

### 1.2 Couleurs d'état du circuit

| État | Texte / fond (clair) | Marque non colorée |
| --- | --- | --- |
| Saisi | `#3e4756` / `#e9e6df` | 3 pastilles vides |
| Validé antenne | `#0a4f8f` / `#e3eef8` | 1 pastille pleine sur 3 |
| Validé province | `#0a4f8f` / `#cfe2f5` | 2 pastilles pleines sur 3 |
| Actif | `#0b5e33` / `#ddf2e5` | 3 pastilles pleines |
| Renvoyé | `#a3102a` / `#fbe3e6` | icône retour |
| À renouveler | `#6b4f00` / `#ffedb0` | icône horloge |
| Supprimé | `#4f5868` / transparent, bordure tiretée | icône corbeille |

L'état se lit sans la couleur : libellé + pastilles (qui comptent les validations obtenues) ou icône. Contrastes du texte de badge : 6,3:1 à 7,5:1 (clair), 6,6:1 à 9,3:1 (sombre).

### 1.3 Typographie : deux familles, trois fichiers (47 Ko)

| Famille | Fichiers | Rôle |
| --- | --- | --- |
| **Atkinson Hyperlegible Next** (OFL) | 400 et 700, sous-ensemble latin (12 + 13 Ko) | Tout le texte. Dessinée pour la lisibilité (I/l/1 et 0/O distincts) : agent en plein soleil, policier qui lit une carte. Le zéro barré est voulu. |
| **Barlow Condensed** (OFL) | 600 (22 Ko) | Chiffres clés, identifiants (`MBR0004127`), numéros d'engin et de gilet, titres de page. Esprit des numéros de gilet et des autocollants ; condensée, elle loge les mots longs du français. |

Échelle (`--t-1` à `--t-7`) : 13, 14, **16** (texte et champs, jamais moins sur mobile), 18, 22, 28→36 (titre de page, fluide), 38→52 (chiffre clé, fluide). Interlignage 1,5 ; 1,15 pour les titres.

### 1.4 Espacements, rayons, ombres

- Espacements (base 4 px) : `--e-1` 4 · `--e-2` 8 · `--e-3` 12 · `--e-4` 16 · `--e-5` 20 · `--e-6` 24 · `--e-7` 32 · `--e-8` 48 · `--e-9` 64.
- Rayons, du plus officiel au plus doux : `--r-plaque` 4 px (badges, plaques, identifiants), `--r-champ` 8 px (champs, boutons), `--r-panneau` 12 px, `--r-feuille` 20 px (réservé), `--r-rond` (avatars, puces).
- Ombres, **seulement pour ce qui flotte** : `--o-0` aucune (les panneaux ont une bordure, pas d'ombre) ; `--o-1` survol d'un bouton ; `--o-2` menus, bulles, carte de membre ; `--o-3` modale et tiroir.
- Cibles tactiles : `--cible` 44 px minimum ; `--cible-confort` 48 px pour les champs et les boutons principaux sur téléphone.

### 1.5 Mise en page

Téléphone (360 px) d'abord : une colonne, l'action principale pleine largeur sous le titre, navigation au pouce en bas.

```
┌──────────────────────────────┐
│ (logo) [ Rechercher     ] 🔔 GT│ barre haute 56 px, sur papier
├──────────────────────────────┤
│ Titre de page (Barlow)       │
│ ⌖ Antenne de Lemba · parking │ périmètre de l'utilisateur
│ [ Action principale        ] │ pleine largeur, 48-64 px
│ ...une colonne...            │
├──────────────────────────────┤
│ Accueil  Membres  À valider³  Menu │ barre basse 64 px
└──────────────────────────────┘
```

Ordinateur (dès 992 px) : menu latéral clair fixe de 264 px, contenu limité à 1 120 px, colonne de contexte à droite sur les fiches.

```
┌──────────┬───────────────────────────────────────────┐
│ logo     │ [ Rechercher            ]      🔔  CM ▾    │
│ FENAMO   ├───────────────────────────────────────────┤
│▌Tableau  │ Titre (Barlow)           [Exporter][Action]│
│ File  24 │ ┌──────────────────────────┐ ┌───────────┐ │
│ Membres  │ │ contenu principal (2/3)  │ │ contexte  │ │
│ Engins   │ │                          │ │ (1/3)     │ │
│ ...      │ └──────────────────────────┘ └───────────┘ │
│┄périmètre┄│                                           │
└──────────┴───────────────────────────────────────────┘
```

Le bas du menu rappelle toujours **le rôle et le périmètre** (« Validateur provincial · Coordination Kinshasa-Est ») : chaque droit s'exerce dans un périmètre, l'utilisateur doit le voir.

---

## 2. Contre-relecture : ce qui faisait « modèle » et ce qui a changé

Comparaison du premier jet (et du brouillon trouvé dans le dépôt) avec ce qu'on produirait pour n'importe quel tableau de bord :

| Réflexe générique | Remplacé par | Pourquoi |
| --- | --- | --- |
| Menu latéral bleu nuit en dégradé | Menu clair, repère jaune de 4 px sur l'élément actif | Le menu sombre est la signature des gabarits d'administration ; un fond clair se lit mieux en plein soleil. Le jaune vient du gilet. |
| Bouton principal bleu | Bouton principal **encre** ; vert réservé à « Valider », rouge à « Renvoyer / Supprimer » | Le bleu primaire est celui de Bootstrap ; ici la couleur porte un sens métier. |
| Bandeau « Bienvenue » en dégradé avec rayures tricolores | Bloc **« À traiter »** : le nombre de dossiers en attente à mon niveau + un bouton | Un tableau de bord sert à agir. Le seul bloc sombre de l'écran est celui de l'action. |
| Quatre cartes de chiffres avec icône dans un carré coloré et cercle décoratif | **Tableau d'affichage** : chiffres en Barlow, séparés par des filets, sous un trait d'encre | Le chiffre est l'image. Pas d'icône, pas de cadre. |
| Grille de « raccourcis » (cartes identiques) | Supprimée | Elle doublait le menu. |
| Toutes les cartes avec la même ombre grise | Bordures fines ; ombre seulement pour ce qui flotte | Hiérarchie lisible : ce qui a une ombre est au-dessus. |
| Plus Jakarta Sans (police « SaaS » à la mode) | Atkinson Hyperlegible Next + Barlow Condensed | Choix fonctionnels : lisibilité des identifiants, place pour le français. |
| Étiquettes de groupe en MAJUSCULES espacées dans le menu | Petits titres en casse normale | Tic d'interface générée. |
| Badges d'état « pilule colorée » | Badge rectangulaire (rayon 4 px) + pastilles de progression | Lisible sans la couleur ; montre où en est le circuit. |
| Avatars d'initiales multicolores | Avatars neutres | La couleur est réservée aux états. |
| Liseré tricolore en bas de la page de connexion | **Retiré** à la vérification visuelle | Ornement : le drapeau reste sur les objets officiels. |

**L'élément audacieux, un seul** : la typographie des numéros. Chiffres clés, identifiants, numéros d'engin et de gilet en Barlow Condensed, et la **plaque d'engin** qui reprend l'autocollant vinyle (cadre encre, code de coordination en négatif, liseré du drapeau). Tout le reste est sobre.

---

## 3. Jetons (`static/css/tokens.css`)

- Toute couleur, taille, durée, ombre, rayon ou plan (`z-index`) vient d'une variable. Aucune valeur en dur dans les gabarits ni dans une autre feuille.
- Thème sombre : attribut `data-theme="sombre"` sur `<html>`, posé par `theme.js` (choix enregistré dans `localStorage` sous la clé `fn-theme`, sinon préférence du système). Bascule : tout élément portant `data-theme-basculer` (géré par `design.js`, qui émet l'événement `themechange` pour Chart.js).
- `prefers-reduced-motion: reduce` met toutes les durées à 0 (jetons `--d-*`) et `app.css` neutralise les animations restantes.
- **Pont temporaire** en fin de fichier : il redirige les anciennes variables `--fn-*` du brouillon vers les nouveaux jetons pour que les écrans du brouillon restent utilisables. **À supprimer** dès que `base.html` charge `app.css` (voir § 8).

Variables les plus utilisées :

| Rôle | Variable |
| --- | --- |
| Fond, panneau, panneau calme, creux | `--fond`, `--surface`, `--surface-2`, `--surface-creuse` |
| Séparateur, bordure de champ (3,4:1) | `--trait`, `--trait-fort` |
| Texte, texte secondaire (6,4:1), lien | `--texte`, `--texte-doux`, `--lien` |
| Bouton principal | `--action`, `--action-survol`, `--action-texte` |
| Retours | `--succes-fg/bg`, `--danger-fg/bg`, `--alerte-fg/bg`, `--info-fg/bg` |
| États | `--etat-<code>-fg`, `--etat-<code>-bg` (codes du § 1.2) |

---

## 4. Composants

Chaque gabarit de `templates/components/` documente ses paramètres en tête de fichier. Les classes CSS correspondantes sont dans `app.css` ; la page `maquettes/composants.html` les montre toutes.

| Gabarit | Classes | Variantes / notes |
| --- | --- | --- |
| `_icone.html` | `.ic`, `.ic--petite`, `.ic--grande` | Sprite Lucide (`i-<nom>`). Équivaut à `{% icone %}` de `fenamo/balises.py`. |
| `_bouton.html` | `.bouton` | `--principal` (encre, une fois par zone), `--valider` (vert, circuit uniquement), `--danger` (contour rouge), `--danger-plein` (confirmation de suppression), `--discret`, `--petit`, `--bloc`. Roue de chargement intégrée (`.roue`, visible avec `.htmx-request` ou `aria-busy="true"`). `.bouton-icone` pour les boutons sans texte (avec `aria-label`). |
| `_champ.html` | `.champ`, `.champ-libelle`, `.champ-aide`, `.champ-erreur`, `.champ-prefixe` | Rend `{{ champ }}` tel quel ; `app.css` style les widgets Django dans `.champ`. « (facultatif) » plutôt que des astérisques. Tuiles de choix : `.choix` (radio ou case, 56 px). Dépôt de photo avec aperçu : `.depot`. Cases : `.case`. |
| `modale_base.html` | `.feuille`, `.feuille-tete`, `.feuille-corps`, `.feuille-pied`, `.etapes` | Gabarit à étendre pour chaque formulaire. `large=True` : 840 px. Pied : Annuler puis l'action. Formulaire long : `.etapes` (3 barres) et un bloc par étape. |
| `_modale_conteneur.html` | `.modale`, `.modale-voile`, `.modale-contenu` | Inclus une fois dans `base.html`. |
| `_bulles.html` | `.bulles`, `.bulle--succes/danger/alerte/info` | Zone des toasts + conversion des messages Django. |
| `_badge_etat.html` | `.etat`, `.etat--<code>` | 7 états ; `change=True` : animation « tampon » après une validation. |
| `_circuit.html` | `.circuit` | 4 étapes : `fait`, `courant`, `renvoi`, à venir. |
| `_plaque.html` | `.plaque`, `.plaque--grande` | Numéro + code de coordination (format fixé par F-31). |
| `_carte_membre.html` | `.carte-membre` | Seulement si la carte est délivrable ; sinon alerte info qui dit ce qui manque. `qr_svg` marqué sûr côté Python. |
| `_dossier.html` | `.file`, `.dossier` | Ligne de file de validation : boutons Valider / Renvoyer (ou « Corriger le dossier » pour l'agent), motif du renvoi, ancienneté (rouge si trop longue). |
| `tableau_base.html` | `.liste-enveloppe`, `.liste` | Tableau → cartes sous 576 px. Chaque `<td>` porte `data-libelle` et **une seule enveloppe** de contenu ; `data-role="titre"` et `data-role="actions"`. |
| `_pagination.html` | `.pages` | Garde les filtres (`{% querystring %}`), HTMX si `cible`. Numéros dès 768 px. |
| `_etat_vide.html` | `.vide` | Raison + action suivante. |
| `_erreur.html` | `.alerte--danger/alerte/info/succes`, `.alerte-titre` | Bouton « Réessayer » intégré (connexion perdue). |
| `_squelette.html` | `.squelette`, `--ligne`, `--chiffre`, `--titre`, `--champ` | `lignes`, `chiffres`, `modale`. |
| `_chiffre.html` | `.affichage`, `.chiffre-valeur`, `.chiffre-libelle`, `.chiffre-ecart` | Compteur animé (`data-compteur`). 4 chiffres au plus par rangée. |

Autres motifs CSS prêts, montrés dans les maquettes : `.page-tete` (titre + contexte + actions), `.fil` (fil d'Ariane), `.panneau`, `.grille--principale` (2/3 + 1/3), `.grille--2`, `.definitions` (liste clé/valeur), `.a-traiter`, `.barres` (répartition sans Chart.js), `.onglets`, `.puce` (filtres), `.defile-horizontal`, `.historique`, `.journal` (+ `.journal-diff` avant/après), `.flottant` + `.notif` (notifications), `.recherche` + `.recherche-resultats`, `.porte` (connexion), `.verif` (vérification), `.chargement` (barre de requête), `.bandeau-reseau`, `.zone-rafraichie`.

---

## 5. Mouvement

Durées : `--d-court` 120 ms (survol, appui), `--d-moyen` 200 ms (bulles, tiroir, changement de page), `--d-long` 320 ms (modale), `--d-compteur` 700 ms. Courbes : `--courbe-sortie` pour ce qui arrive, `--courbe-entree` pour ce qui part (plus court). Rien n'apparaît en cascade bloc par bloc.

| Interaction | Comportement | Déclencheur | Mouvement réduit |
| --- | --- | --- | --- |
| Changement d'écran (`hx-boost`) | Le contenu glisse de 6 px et apparaît (200 ms) | `[data-page]` dans `.contenu`, animation CSS à l'insertion | Instantané |
| Requête en cours | Barre de 3 px en haut ; la zone rafraîchie pâlit à 45 % | `.chargement`, `.zone-rafraichie` + `.htmx-request` | Barre fixe, sans glissement |
| Chargement lent (> 300 ms) | Squelettes avec reflet | `_squelette.html` comme `hx-indicator` | Reflet figé |
| Modale | Téléphone : feuille qui monte du bas (320 ms) ; ordinateur : boîte qui grandit de 98 % à 100 % ; fermeture plus rapide (200 ms) ; focus sur le premier champ, piégé, rendu au déclencheur ; Échap ferme | `FenamoDesign.ouvrirModale('#modale')` / `fermerModale()` | Instantané |
| Bulle (toast) | Glisse depuis le haut (téléphone) ou en bas à droite ; barre de délai (5 s, 9 s pour une erreur), en pause au survol | `FenamoDesign.bulle({message, detail, niveau})`, événement `toast` | Pas de barre ; retrait après le délai |
| Validation dans la file | Le bouton tourne ; le badge passe à l'état suivant (« tampon ») ; la ligne flashe en vert puis glisse à droite et se replie ; les compteurs du menu et de l'onglet diminuent avec un rebond | `FenamoDesign.retirerDossier(ligne, 'traite')`, `majCompteur(el, n)` | Retrait immédiat |
| Renvoi | Idem en rouge, glissement à gauche | `retirerDossier(ligne, 'renvoye')` | Retrait immédiat |
| Erreur de champ | Le message tremble une fois (3 px) | `.champ-erreur` à l'insertion | Aucun |
| Chiffres clés | Montent de 0 à la valeur (700 ms, une seule fois) | `[data-compteur]` au chargement et après `htmx:afterSettle` | Valeur affichée directement |
| Barres de répartition | Se remplissent depuis la gauche | `.barres .barre span` | Instantané |
| Menu latéral (téléphone) | Tiroir depuis la gauche + voile ; focus dans le menu ; Échap ou voile ferment | `data-menu-ouvrir`, `data-menu-fermer` | Instantané |
| Notifications | Le panneau se déroule ; la pastille rebondit quand le nombre change | `.flottant`, `majCompteur()` | Instantané |
| Appui | Bouton enfoncé de 1 px | `:active` | Aucun |

---

## 6. Règles d'usage

- **Une action principale par zone.** Sur téléphone, elle est pleine largeur et au moins à 48 px.
- **Le vert ne sert qu'à valider, le rouge qu'à renvoyer ou supprimer, le jaune qu'à signaler « ici ».** Pas de couleur pour décorer.
- **Le drapeau n'apparaît que sur la carte de membre et la plaque d'engin.**
- **Panneaux sans ombre** ; une ombre signifie « au-dessus de la page ».
- **Identifiants toujours en `.ident`** (Barlow) : `MBR0004127`, codes de parking, numéros de gilet ; numéros d'engin toujours en `_plaque.html`.
- **Tableaux** : jamais de défilement horizontal sur téléphone ; ils deviennent des cartes.
- **Pas de Bootstrap sur les nouveaux écrans.** `app.css` couvre la grille, les utilitaires et les composants. Bootstrap ne reste chargé que par `base-app.html` (écrans hérités) jusqu'à leur migration.
- **Graphiques** : préférer `.barres` (CSS) ; Chart.js seulement pour une courbe dans le temps (F-51), chargé uniquement sur cette page, couleurs lues dans les jetons.

### Écriture

- Phrases courtes, verbes actifs, casse de phrase. Pas de point d'exclamation.
- Un bouton dit ce qu'il fait, la bulle reprend le même verbe : « Valider le membre » → « Membre validé » ; « Renvoyer à l'antenne » → « Dossier renvoyé à l'antenne » ; « Enregistrer l'engin » → « Engin enregistré ».
- Le détail d'une bulle dit la suite : « Il attend maintenant la validation nationale. »
- Une erreur dit quoi faire, sans s'excuser : « Saisissez 9 chiffres après +243, par exemple 812 345 678. »
- Vocabulaire de la charte : association membre, engin (moto ou tricycle), coordination provinciale, antenne, parking. Jamais « structure », jamais « ville », jamais « COPTAM ».
- Formats : téléphone `+243 812 345 678`, dates `JJ/MM/AAAA`, milliers avec espace fine (`48 216`).

---

## 7. Accessibilité et performance (vérifiées)

- Contrastes : texte principal 15,6:1 sur papier ; texte secondaire 6,4:1 ; liens 5,5:1 ; textes de badge ≥ 6,3:1 ; bordures de champ 3,4:1. Page de vérification : verdict blanc sur vert 7,9:1 et sur rouge 7,9:1, aucun texte atténué (AAA).
- Focus clavier : anneau encre de 2 px + halo jaune de 5 px, visible en clair comme en sombre. Lien « Aller au contenu ». Focus piégé dans la modale, rendu au déclencheur.
- Cibles : 44 px minimum, 48 px pour champs et boutons principaux sur téléphone ; tuiles de choix de 56 px.
- 360 px : aucun débordement horizontal sur les 10 maquettes (vérifié automatiquement) ; aucun libellé coupé.
- Poids de la page de connexion : HTML 4 Ko + `tokens.css` 10 Ko + `app.css` 61 Ko (12 Ko compressé) + `design.js` 10 Ko + polices 47 Ko + logo 10 Ko ≈ **145 Ko** ; avec HTMX, Alpine et `fenamo.js` ≈ **290 Ko** (< 500 Ko). Le gain principal vient du retrait de Bootstrap (≈ 190 Ko) sur les nouveaux écrans.

---

## 8. Intégration par `frontend-htmx`

### 8.1 Socle (à faire en premier)

1. **`templates/base.html`** : charger `tokens.css` puis `app.css` (et plus `bootstrap.min.css`, `base.css`, `layout.css`, `components.css`, `pages.css`, `animations.css`) ; précharger `atkinson-hyperlegible-next-400.woff2` et `barlow-condensed-600.woff2` ; `theme.js` dans `<head>` sans `defer` ; puis `htmx.min.js`, `design.js`, `fenamo.js`, `alpine.min.js` en `defer`. Poser `data-sprite="{% static 'img/icons.svg' %}"` sur `<html>`. Structure de la coque : copier celle des maquettes (`.coque` > `nav.menu` + `.voile--menu` + `.corps` > `header.haut` + `main.contenu#contenu` > `div[data-page]` + `footer.pied`, puis `nav.bas`). Inclure `components/_modale_conteneur.html` et `components/_bulles.html` une fois. `<meta name="theme-color" content="#f4f2ed">`.
2. **Menus** : réécrire `partials/_menu.html`, `_haut.html`, `_menu_bas.html` sur le modèle de la coque des maquettes (liens par rôle, compteur de la file dans le menu et la barre basse, bloc « périmètre » en bas du menu, bouton de thème dans la barre haute sur ordinateur et dans le menu sur téléphone). `aria-current="page"` sur le lien actif.
3. **`fenamo.js`** : garder la plomberie HTMX (HX-Trigger, bandeau réseau et « Réessayer », verrouillage des envois, `HX-Redirect`) et brancher l'affichage sur `design.js` :
   - modale : après un échange dont la cible est `#modale-contenu`, appeler `FenamoDesign.ouvrirModale('#modale')` ; sur l'événement `modaleFermer`, `FenamoDesign.fermerModale('#modale')` ; pendant le chargement, insérer `_squelette.html` variante `modale` ;
   - bulles : l'événement `toast` est déjà écouté par `design.js` ; convertir `#messages-django` avec `FenamoDesign.bulle()` ;
   - file : sur `htmx:beforeSwap` dont la cible est un `.dossier` et la réponse vide, ajouter la classe `est-traite` (ou `est-renvoye`) ; le bouton porte `hx-swap="outerHTML swap:900ms"` ; mettre à jour les compteurs avec `FenamoDesign.majCompteur()` à partir d'un HX-Trigger `fileMaj` ;
   - supprimer les composants Alpine `coque`, `toasts` et `compteur` (remplacés par `design.js`) ; garder `onglets` ; adapter `graphique` (couleurs lues dans `--etat-*` et `--encre`) ; **retirer `listeFiltrable`** (filtrage côté navigateur : la recherche et la pagination passent par le serveur, F-28).
   - bandeau réseau : classes `.bandeau-reseau` + `.bouton`.
4. **Supprimer le pont `--fn-*`** à la fin de `tokens.css` une fois les étapes 1 à 3 faites.
5. Les maquettes contiennent quelques attributs `style="…"` qui n'utilisent que des jetons (`var(--e-6)`…) : ce sont des raccourcis de maquette. Dans les gabarits, les remplacer par les classes existantes (`.pile`, `.rangee`, `.meta`…) ou par une classe utilitaire ajoutée à `app.css` ; jamais de valeur en dur. Largeur des barres `.barres` : classes de palier `.part-0` à `.part-100` (pas de 5), avec le filtre `palier_5` de `balises.py` ; aucun `style="--part:…"`.
6. `maquettes.js` et `maquettes-theme.js` simulent le serveur : **ne pas les intégrer**.

### 8.2 Écran par écran

| Écran | Maquette | À intégrer |
| --- | --- | --- |
| Connexion (`compte/pages-login.html`) | `connexion.html` | Page hors coque `.porte` : panneau devise (ordinateur seulement), formulaire `.porte-cadre` ; erreur en `_erreur.html` au-dessus du formulaire ; bouton afficher/masquer le mot de passe (`aria-pressed`) ; le bouton « Auto-identification » du brouillon ne correspond à aucune fonction du cahier des charges : ne pas le reprendre sans accord de l'utilisateur. Mêmes gabarits pour `verrou.html` (message du SU dans une `.alerte--alerte`) et pour les pages 400/403/404/500 (`.porte` + `.vide`). |
| Tableau de bord du président / des validateurs (F-16) | `tableau-de-bord-president.html` | `.page-tete` avec périmètre et année ; bloc `.a-traiter` (dossiers en attente à mon niveau, détail, bouton vers la file) ; `.affichage` de 4 `_chiffre.html` ; panneaux « Dossiers en attente par niveau » et « Membres actifs par coordination » en `.barres` ; colonne « Activité récente » (`.historique`) et « Mandats bientôt échus ». Changement d'année : `hx-get` sur la zone, squelette `chiffres`. |
| Tableau de bord de l'agent | `tableau-de-bord-agent.html` | Salutation + antenne/parking ; deux grandes actions (enregistrer un membre, un engin) ouvrant la modale ; alerte des renvois ; 4 chiffres de la semaine ; « Mes derniers dossiers » en `_dossier.html` (bouton « Corriger le dossier » pour un renvoi). |
| File de validation (F-23, F-32, F-13) | `file-de-validation.html` | Onglets Membres / Engins / Associations membres avec compteurs ; puces par antenne (HTMX, squelette) ; `_dossier.html` ; modale de renvoi : motif obligatoire, suggestions en `.puce` qui complètent le texte, bouton « Renvoyer à l'antenne » (le libellé nomme le niveau inférieur réel : agent, antenne ou coordination) ; état vide « File à jour » ; `_pagination.html`. |
| Fiche membre (page pilote) | `fiche-membre.html` | `.fil`, en-tête (photo, nom, identifiant, qualité, gilet, badge) et actions selon le droit ; `_circuit.html` ; onglets Identité / Engins / Famille / Pièces / Paiements ; panneaux `.definitions` avec « Modifier » / « Changer » ouvrant la modale ; engins en `tableau_base.html` + `_plaque.html` ; colonne droite : carte de membre (ou alerte de ce qui manque) et historique (nouvel événement inséré avec `.apparait`). |
| Liste des membres (F-28) | `liste-membres.html` | Recherche pendant la frappe (`hx-trigger="input changed delay:300ms"`), bouton Filtres (modale), puces d'état avec effectifs, résumé « 1 à 25 sur 12 018 », `tableau_base.html` (cartes sous 576 px), `_pagination.html`, export. |
| Enregistrer un membre (F-20) | `modale-enregistrer-membre.html` | `modale_base.html` avec `large=True` et `.etapes` : 1 Identité (nom, postnom, prénom, naissance, sexe en tuiles, téléphone avec préfixe +243, qualité en tuiles), 2 Rattachement (antenne, parking facultatif, association membre ; alerte de doublon possible), 3 Pièces (photo avec aperçu, cases des pièces). Bouton « Continuer » puis « Enregistrer le membre ». Même gabarit pour la nomination (F-02) : membre actif, rôle en tuiles, périmètre, dates de mandat. |
| Journal d'activités (F-70, F-71) | `journal.html` | Filtres en puces + recherche ; jours en intertitres collants ; entrées `.journal` (heure, auteur, rôle, type d'action, objet, lieu) et `.journal-diff` pour l'avant/après ; pagination « Plus récent / Plus ancien ». |
| Vérification d'une carte (aperçu, futur site) | `verification.html` | `.verif` : verdict plein (valide / non valide) en titre, photo, nom, identifiant, gilet, validité, coordination, engin en plaque ; **aucune donnée personnelle** au-delà (§ API) ; contraste AAA. |

### 8.3 État du brouillon trouvé dans le dépôt

| Élément | Décision | Détail |
| --- | --- | --- |
| `static/js/theme.js` | **Garder** | Inchangé. |
| `static/img/icons.svg`, `LICENCE-ICONES.txt` | **Gardé, régénéré** | Mêmes identifiants `i-<nom>` + nouvelles icônes (motorbike, square-parking, list-checks, tricycle…). Licence mise à jour (Lucide 1.55, ISC). |
| `static/img/logo-*.webp`, `favicon.png` | **Garder** | |
| `fenamo/balises.py` | **Garder `icone`** ; adapter le reste | `badge_etat` doit rendre `components/_badge_etat.html` ; `avatar` : classes `.avatar` neutres, **supprimer `teinte_avatar`** ; `etat_membre` : vérifier la correspondance (il saute « validé province » : `is_validate2` y est lu comme « validé antenne ») avec `backend-django` ; `indicateurs_tableau_bord` et `historique_objet` sont de la logique métier dans une balise : à déplacer dans un service (`backend-django`). |
| `static/js/fenamo.js` | **Adapter** | Voir § 8.1, point 3. |
| `static/js/envoi-unique.js` | **Garder** | Sert les écrans hérités (`base-app.html`). |
| `templates/base.html`, `partials/_menu.html`, `_haut.html`, `_menu_bas.html` | **Refaire** | Sur la coque des maquettes. |
| `partials/_modale.html`, `_modale_confirmation.html`, `_bouton_post.html`, `_bouton_confirmer.html` | **Remplacer** | Par `components/modale_base.html` (la confirmation de suppression est une modale avec un bouton `danger-plein`) et `components/_bouton.html`. |
| `partials/composants/*` (`_stat`, `_raccourci`, `_avatar`, `_badge_etat`, `_etat_vide`, `_squelette`, `_entete_page`, `_confirmer`) | **Jeter** | Remplacés par `templates/components/`. La grille de raccourcis disparaît. |
| `static/css/base.css`, `layout.css`, `components.css`, `pages.css`, `animations.css` | **Jeter** | Remplacés par `app.css` (après le § 8.1). |
| `static/fonts/plus-jakarta-sans-latin.woff2`, `LICENCE-POLICE.txt` | **Jeter** | Remplacés par Atkinson Hyperlegible Next et Barlow Condensed. |
| `tableau_bord/tableau_bord.html`, `partials/_corps.html`, `_raccourcis.html` | **Refaire / jeter `_raccourcis`** | Selon les maquettes de tableau de bord. |
| `coptapp/membres/partials/*`, `app/membre.html`, `app/membre-list.html` | **Adapter** | Le découpage en fragments est bon ; le balisage suit les maquettes fiche et liste. |
| `compte/pages-login.html`, `securite.html`, `verrou.html`, `partials/_compte_cree.html` | **Adapter** | Connexion et verrou : `.porte` ; sécurité : panneau + modale ; compte créé : modale avec le mot de passe temporaire en `.ident` et un bouton « Copier ». |
| `templates/400.html` … `500.html`, `erreur_base.html` | **Adapter** | `.porte` + `.vide` + bouton « Revenir au tableau de bord ». |

À signaler à `backend-django` (constaté pendant les captures sur une copie de la base) : `/membres/` répond 500 (`Compte.MultipleObjectsReturned`, un `get()` trouve deux comptes) pour un super-utilisateur sans fiche membre.

---

## 9. Autocritique après captures

- Corrigé à la vérification visuelle : fond du menu interrompu sur les pages longues ; marque coupée en deux lignes dans la barre haute à 360 px ; icône de contexte isolée sur sa ligne ; pagination repliée à 360 px ; formulaire de modale étiré sur toute la hauteur ; focus initial de la modale sur « Fermer » au lieu du premier champ ; en-tête de tableau collant qui masquait la première ligne ; QR code qui chevauchait le texte de la carte ; cellules à deux valeurs mal alignées en mode carte.
- Ornement retiré : le liseré tricolore de la page de connexion.
- Ce qui peut encore faire « modèle » : la succession de panneaux blancs de même rayon sur la fiche membre. Acceptable parce qu'ils portent des titres d'action différents et pas d'ombre ; à surveiller quand la fiche engin et la fiche association membre s'ajouteront.
- Points ouverts : format exact du numéro d'engin (F-31) ; délai à partir duquel une attente passe en rouge (5 jours dans les maquettes). La photo sur la page de vérification est conforme au cahier des charges du site (données affichées : photo, nom, identifiant, qualité, association membre, coordination, antenne, parking, état, validité).
