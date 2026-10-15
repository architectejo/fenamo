# Système de design FENAMO-RDC — site public

Référence de `frontend-htmx` et `site-web` pour le site `fenamordc.cd` : appliquer ce qui est écrit ici, sans réinventer. Le site partage les **jetons** de l'application web (couleurs, polices, espacements, rayons, ombres, durées) ; il a sa propre feuille de style et son propre registre : grand public, plus éditorial et plus chaleureux que le back-office.

| Élément | Emplacement |
| --- | --- |
| Jetons partagés (copie exacte de `web_app/static/css/tokens.css`) | `static/css/tokens.css` |
| Feuille unique du site (base, en-tête, composants, pages, mouvement) | `static/css/site.css` |
| Comportements (menu, langue, thème, chiffres, carte, visionneuse, copie, compteur, carte Google à la demande) | `static/js/site.js` |
| Thème avant affichage (même fichier que l'application, clé `fn-theme`) | `static/js/theme.js` |
| Polices `woff2` + licences OFL (copies de l'application) | `static/fonts/` |
| Logo, favicon (copies de l'application), sprite d'icônes Lucide + licence ISC | `static/img/` |
| Maquettes statiques (chargent les vrais fichiers ci-dessus) | `docs/design/maquettes/` (ouvrir `index.html`) |
| Captures 360 px et 1280 px, clair et sombre | `docs/design/captures/` |
| Contrôle des copies (jetons et polices identiques, pas de couleur en dur, sprite complet) | `tests/test_design_jetons.py` |

Ouvrir les maquettes : depuis `website/`, `python -m http.server 8079`, puis `http://localhost:8079/docs/design/maquettes/`. Paramètres : `?theme=sombre`, `?menu=ouvert`, `?langue=ouverte`, `?langue=ln` (article non traduit), `?etat=recherche|vide` (actualités), `?etat=erreur|envoye` (contact), `?visionneuse=1` (galerie), `?code=500` (erreur), `?cas=panne` (service suspendu), `#coord-HK` (coordinations).

---

## 1. Plan

### 1.1 Couleurs : celles de l'application, autrement dosées

| Nom (jeton) | Hex clair | Usage sur le site |
| --- | --- | --- |
| Encre `--encre` | `#121a26` | Texte ; **aplat de l'accroche et du pied de page** (le registre « nuit, phares, bande réfléchissante ») ; bouton principal. |
| Papier `--papier` / `--fond` | `#f4f2ed` | Fond de toutes les pages, le carton de la carte de membre. Les formulaires et l'encadré d'adhésion sont blancs (`--surface`). |
| Ciel `--ciel` | `#0a62b0` | Liens ; échelle de la carte des coordinations. |
| Jaune `--jaune` | `#f2c200` | La bande du gilet ; le repère sous la rubrique en cours ; le bouton « Vérifier » **sur aplat encre seulement** (10,4:1) ; halo de focus. Jamais du texte sur fond clair. |
| Rouge `--rouge` | `#bf1230` | Erreurs de formulaire. |
| Vert `--vert` | `#0f6e3d` | Coches des conditions, message envoyé. |

Les couleurs exactes du drapeau (`--drapeau-*`) restent réservées aux objets officiels : sur le site, seulement le liseré du **code de coordination en plaque** (`.plaque-code`), qui est le même objet que l'autocollant de l'engin.

**Jetons ajoutés pour le site** (dans le fichier partagé, sans effet sur l'application) :

| Jeton | Valeur | Rôle |
| --- | --- | --- |
| `--t-8` | 42 → 80 px (fluide) | Accroche de l'accueil, titres des pages d'erreur (Barlow) |
| `--interligne-lecture`, `--mesure` | 1,6 ; 66 caractères | Articles et pages institutionnelles |
| `--sur-encre-fort`, `--sur-encre-doux`, `--sur-encre-trait` | `#f4f2ed` (15,6:1), `#b4bfcc` (9,4:1), filet à 18 % | Texte et filets posés sur l'aplat encre |
| `--bande-gilet` | dégradé à bords nets jaune / argent `--gilet-reflet` / jaune (30 / 40 / 30 %) | La bande réfléchissante |
| `--gilet-une`, `--gilet-pied` | 28 px, 12 px | Hauteurs de la bande (accroche, pied) |
| `--echelle-1` à `--echelle-3` | `#e3eef8`, `#9cc8ee`, `#0a62b0` (sombre : `#14324f`, `#2b6299`, `#7cbcf5`) | Carte des coordinations par effectif |

### 1.2 Typographie

Mêmes fichiers que l'application (47 Ko) : **Atkinson Hyperlegible Next** 400 et 700 pour tout le texte (lisible en plein soleil, I/l/1 et 0/O distincts), **Barlow Condensed** 600 pour les titres de page, les chiffres, les codes et les identifiants. Sur le site, Barlow prend plus de place : accroche (`--t-8`), titres de page et d'article (`--t-7`), devise du pied, nom des rubriques dans le menu du téléphone.

Échelle : `--t-1` 13 · `--t-2` 14 · `--t-3` **16** (texte, champs) · `--t-4` 18 (texte des articles dès 768 px, intertitres courts) · `--t-5` 22 · `--t-6` 28→36 · `--t-7` 38→52 · `--t-8` 42→80.

### 1.3 Espacements, rayons, ombres

Jetons de l'application, sans ajout : espacements `--e-1` (4 px) à `--e-9` (64 px) ; sections du site séparées par `--e-8` (48 px) et un filet. Rayons : `--r-plaque` (types d'article, codes, portraits, vignettes de galerie), `--r-champ` (boutons, champs, puces), `--r-panneau` (photos, formulaire, encadré). **Aucune ombre sur les blocs de page** : seuls le sélecteur de langue (`--o-2`) flotte.

### 1.4 Mise en page

Téléphone (360 px) d'abord : une colonne, l'action de la page pleine largeur, menu plein écran.

```
┌──────────────────────────────┐
│ (logo) FENAMO-RDC [Vérifier] ☰│ en-tête collant 56 px, sur papier
├──────────────────────────────┤
│▓▓▓▓▓▓▓▓▓▓ aplat encre ▓▓▓▓▓▓▓│
│ Chaque motard identifié,     │ accroche Barlow 42 px
│ chaque engin numéroté.       │
│ [ MBR0004127 ou 00147 KN-E ] │ vérification immédiate
│ [        Vérifier (jaune)  ] │
│══════════════════════════════│ bande du gilet, bord à bord
│ 54 182 │ 39 267              │ tableau d'affichage (2 × 2)
│ 412    │ 27                  │
│ Actualités : une, puis lignes│ vignette 104 px à gauche
│ ┌ Adhésion (cadre encre) ┐   │
│ Application (téléphone)      │
│══════════════════════════════│ bande du gilet (12 px)
│▓ Unité, Discipline et Progrès│ pied encre
└──────────────────────────────┘
```

Ordinateur (dès 1 100 px pour le menu complet, contenu limité à 1 120 px) :

```
┌──────────────────────────────────────────────────────────────┐
│ (logo) FENAMO-RDC   La FENAMO-RDC  Associations…  Actualités  │
│                     Application mobile  Contact  ◍FR▾ [Vérifier]
├──────────────────────────────────────────────────────────────┤
│▓ Accroche (7/12) + vérification     │ photo 4:5 (5/12)      ▓│
│══════════════════════════════════════════════════════════════│
│ chiffres sur 4 colonnes, filets                                │
│ une : photo 7/12 + titre Barlow 5/12 ; 3 articles en dessous   │
└──────────────────────────────────────────────────────────────┘
Pages intérieures : fil d'Ariane, titre Barlow (--t-7), chapô, sous-navigation
de la rubrique ; lecture en 1 colonne de 66 caractères + colonne de 300 px.
```

Rubriques (5) : **La FENAMO-RDC** (présentation, comité exécutif, coordinations, documents), **Associations membres** (annuaire, adhésion, suivi — lot 3), **Actualités** (actualités et communiqués, galerie), **Application mobile**, **Contact**. Le regroupement suit le § 4.1 du cahier des charges ; le schéma « plan du site » du cahier (contenu intégré non lisible dans le Markdown) est à confirmer.

---

## 2. Contre-relecture : ce qui faisait « site institutionnel modèle »

| Réflexe générique | Remplacé par | Pourquoi |
| --- | --- | --- |
| Grande photo plein écran sous un voile sombre, titre centré, deux boutons | Aplat encre, titre aligné à gauche, **la vérification comme action de l'accroche**, photo à côté (ordinateur) et absente sur téléphone | La police et les clients viennent d'abord vérifier ; une photo plein écran coûte 200 Ko en 3G et nuit à la lecture. |
| Trois « cartes de services » avec icône dans un cercle | Supprimées ; l'adhésion est un encadré avec la liste concrète des pièces (art. 9) | Les cartes de services disent des généralités ; la liste dit quoi préparer. |
| Chiffres avec icônes et compteurs dans des cartes | Tableau d'affichage en Barlow, filets, date de mise à jour | Repris de l'application : le chiffre est l'image. |
| Actualités en cartes ombrées identiques | Une à la une, puis une liste ; sur téléphone, vignette carrée à gauche sans résumé | Moins de hauteur et d'octets ; hiérarchie visible. |
| Badges de catégorie en pilules colorées | Plaque (rayon 4 px) : « Actualité » au trait, « Communiqué » en négatif avec un porte-voix | Un communiqué engage la fédération : il se distingue sans couleur. |
| Carrousel de logos de partenaires | Liste de noms dans le pied | Aucun logo fourni ; un carrousel bouge sans raison. |
| Carte de la RDC décorative, dessinée approximativement | **Carte schématique en cases** (une par coordination, son code en Barlow, couleur selon l'effectif) | Exacte par construction, lisible à 360 px, 3 Ko ; elle reprend l'autocollant (code de coordination). |
| Pied de page sombre à quatre colonnes avec rayures tricolores | Pied encre, **devise en grand**, bande du gilet en bordure haute | La devise est demandée dans le pied par le cahier (§ 2) ; le drapeau reste aux objets officiels. |
| Logos de réseaux sociaux | Libellés en clair (« Facebook », « WhatsApp ») | Lucide n'a plus d'icônes de marques ; un libellé est plus lisible et plus léger. |
| Apparition des blocs au défilement, bouton « retour en haut » | Aucun | Tic d'interface ; gêne sur un téléphone lent. |
| Sous-titre long à côté du logo (« Fédération nationale des… ») | **Retiré** à la vérification visuelle | Il passait sur trois lignes et serrait le menu. Le nom complet est dans l'accroche et le pied. |

**L'élément audacieux, un seul : la bande réfléchissante du gilet.** Jaune, argent, jaune, à bords nets, elle traverse l'écran d'un bord à l'autre sous l'accroche (et se déroule une fois), borde le haut du pied de page sur toutes les pages, et ouvre les pages d'erreur. C'est ce qu'on voit d'un motard FENAMO-RDC la nuit, dans les phares. Tout le reste est sobre.

---

## 3. Jetons partagés : règle de maintenance

- **Une seule source** : `web_app/static/css/tokens.css`. Le site en a une copie octet pour octet ; les polices aussi.
- Procédure : modifier le fichier de l'application, puis `cp web_app/static/css/tokens.css website/static/css/tokens.css` (et `cp web_app/static/fonts/*.woff2 website/static/fonts/` si les polices changent). `pytest website/tests/test_design_jetons.py` échoue tant que les copies diffèrent (test sauté si `web_app/` est absent, par exemple sur le serveur du site).
- Un jeton propre au site va **quand même** dans le fichier partagé (section « Site public ») : il n'a pas d'effet sur l'application.
- Aucune couleur, taille de texte, durée ou ombre en dur dans `site.css` (le test refuse tout `#hex`, `rgb()` ou nom de couleur). Les attributs `style="…"` des maquettes n'utilisent que des jetons ; dans les gabarits, les remplacer par une classe (`.pile`, `.rangee`, `.meta` ou une classe ajoutée à `site.css`).
- Thème sombre : `data-theme="sombre"` sur `<html>`, posé par `theme.js` avant l'affichage (choix dans `localStorage`, clé `fn-theme`, commune aux deux sites ; sinon préférence du système). Bascule : tout élément `[data-theme-basculer]` (bouton du pied, entrée du menu du téléphone). L'accroche et le pied restent sur encre dans les deux thèmes.

---

## 4. Composants (classes de `site.css`)

| Composant | Classes | Variantes, règles |
| --- | --- | --- |
| En-tête | `.site-tete`, `.site-tete-rangee`, `.site-marque`, `.site-marque-nom`, `.site-nav` | Collant. Menu complet dès 1 100 px, rubrique en cours : `aria-current="page"` (bande jaune de 4 px dessous). En dessous : bouton `[data-menu-site]` (`.masque-large`). Le bouton **« Vérifier »** est toujours visible (`.bouton--principal.bouton--verifier`). |
| Menu du téléphone | `.menu-site`, `.menu-rubrique`, `.menu-site-titre`, `.menu-site-pied` | Plein écran sous l'en-tête ; rubriques en Barlow, sous-pages en dessous ; langues à plat ; « Espace des utilisateurs » ; thème. Focus gardé, Échap ferme, focus rendu au bouton. Sans JavaScript, le pied de page sert de plan du site. |
| Sélecteur de langue (S-11) | `.langue`, `.langue-bouton`, `.langue-liste`, `.langue-choix`, `.langue-code`, `.langue-nom`, `.langue-fr`, `.langue--plat` | Visible seulement si au moins deux langues sont actives (F-64). Chaque langue **dans sa propre langue** (`lang`, `hreflang`) : Français, Lingála, Kiswahili, Cilubà (tshiluba), Kikongo ; nom français en petit dessous ; code en plaque ; langue courante : plaque en négatif + coche + `aria-current`. Flottant dans l'en-tête (ordinateur), à plat dans le menu (téléphone). |
| Boutons | `.bouton`, `--principal`, `--jaune`, `--sur-encre`, `--discret`, `--grand`, `--bloc`, `--bloc-mobile`, `.boutons`, `.roue` | Une action principale par zone. `--jaune` et `--sur-encre` **seulement sur aplat encre**. Pas de flèche ajoutée. Chargement : `aria-busy="true"` ou `.htmx-request` affiche `.roue`. |
| Champs | `.champ`, `.champ-libelle`, `.facultatif`, `.champ-aide`, `.champ-saisie`, `.champ--erreur`, `.champ-erreur`, `.champ-piege`, `.compte-caracteres` | 48 px de haut, 16 px. Erreur : bordure rouge de 2 px + message sous le champ (`aria-describedby`, `aria-invalid`). « (facultatif) » plutôt qu'un astérisque. Champ piège anti-robots : `.champ-piege` + `aria-hidden` + `tabindex="-1"`. |
| Accroche | `.une`, `.une-grille`, `.une-sur`, `.une-titre`, `.une-chapo`, `.une-photo`, `.verif-rapide`, `.verif-rapide-ligne`, `.verif-rapide-aide` | Accueil seulement. Le formulaire envoie vers la vérification (S-03, lot 3) en GET. Saisie en Barlow (comme le numéro imprimé). |
| Bande du gilet | `.gilet`, `--deroule`, `--pied`, `--fin` | Toujours décorative (`aria-hidden="true"`). Trois emplois seulement : sous l'accroche, en haut du pied, en haut des pages d'erreur. Jamais dans le contenu. |
| Chiffres clés (S-09) | `.affichage`, `.chiffre`, `.chiffre-valeur[data-compteur]`, `.chiffre-libelle`, `.affichage-source` | 4 chiffres au plus ; toujours la date (« Chiffres au JJ/MM/AAAA »). La valeur finale est écrite dans le HTML (lue sans JavaScript) ; `data-compteur` la fait monter une fois à l'apparition. |
| En-tête de page | `.page-tete`, `.fil`, `.page-titre`, `.chapo`, `.sous-nav` | Fil d'Ariane en `<ol>` ; sous-navigation de la rubrique avec `aria-current="page"`. |
| Sections | `.section`, `--calme`, `.section-tete`, `.section-titre`, `.section-lien`, `.grille-2`, `.grille-lecture`, `.enveloppe` | `.grille-lecture` : texte 66 caractères + colonne de 300 px (ordinateur). |
| Articles (S-01, S-02) | `.une-article`, `.articles`, `.articles--3`, `.article`, `.article-titre`, `.article-resume`, `.article-meta`, `.type`, `.type--communique`, `.liste-articles` | Sous 576 px, `.articles` passe en lignes (vignette carrée, sans résumé). |
| Recherche et filtres | `.outils-liste`, `.recherche`, `.puces`, `.puce` (+ `.nombre`), `.resultat-resume`, `.zone-rafraichie` | Recherche pendant la frappe : `hx-get` + `hx-trigger="input changed delay:300ms, search"` + `hx-target="#resultats"` + `hx-push-url="true"`. Puces = liens (`aria-current`). Mots trouvés en `<mark>`. |
| Article | `.article-tete`, `.article-figure`, `.texte-long`, `.mention-langue`, `.partage` | Corps nettoyé côté serveur (liste blanche). `.mention-langue` si l'article n'existe pas dans la langue choisie. Partage (S-08) : WhatsApp, Facebook, X en liens de partage, « Copier le lien » (`[data-copier-lien]`, libellé `[data-libelle]` → « Lien copié »). |
| Photos | `.photo`, `--4x5`, `--1x1`, `--3x2`, `--carre`, `.photo-vide`, `.photo-initiales`, `.legende`, `.duree` | Image réelle : `<img loading="lazy" decoding="async" width height alt>` WebP dans `.photo`. Sans image : `.photo-vide` (icône + ce qu'il faut photographier) ; portrait sans photo : `.photo-initiales`. Jamais d'image de démonstration. |
| Adhésion, application | `.appel`, `.coches`, `.etapes-liste`, `.appli`, `.telephone` (+ `-ecran`, `-haut`, `-corps`, `-carte`), `.fiche-technique`, `.qr-telecharger` | `.etapes-liste` seulement pour une vraie suite d'étapes. Le téléphone est dessiné en HTML (aucune capture d'écran à fournir). Le QR de téléchargement n'apparaît que sur ordinateur. |
| Organisation, comité | `.echelons`, `.echelon`, `.dirigeants`, `.dirigeant`, `.dirigeant--tete`, `.mandat`, `.jalons`, `.encart`, `.devise-grande`, `.encart-faits` | Le président en tête sur toute la largeur ; les autres dans l'ordre fixé par les éditeurs (F-63). |
| Coordinations | `.coord-grille`, `.coord-carte`, `.carte-tuiles`, `.tuile`, `.tuile--0..3`, `.legende-carte`, `.coords-tete`, `.coords`, `.coord`, `.coord-nom`, `.coord-effectif`, `.coord-detail`, `.antennes`, `.plaque-code` | Voir § 6. |
| Documents (S-10) | `.documents`, `.document`, `.document-icone`, `.document-titre`, `.groupe-titre` | Type, taille, pages, date, nombre de téléchargements. Bouton « Télécharger » avec `aria-label` complet (« Télécharger la charte (PDF, 3,4 Mo) »). |
| Galerie | `.galerie`, `.galerie-element`, `--video`, `.album-tete`, `.visionneuse` (+ `-haut`, `-image`, `-bas`) | Vignettes `<button data-visionneuse data-legende>` ; la visionneuse (dialogue, focus gardé, Échap, flèches) est incluse une fois dans la page. Vidéo : lien YouTube ou Facebook transformé en lecteur seulement au clic. |
| Contact (S-07) | `.coordonnees`, `.coordonnee`, `.carte-lieu` (+ `[data-carte-charger]`), `.formulaire`, `.formulaire-pied`, `.accuse` | La carte Google Maps ne se charge qu'au clic (« Afficher la carte ») : 3G et vie privée ; l'adresse de l'iframe (clé restreinte) est posée par le gabarit dans `data-carte-charger`. Après envoi : `.accuse` avec la référence en `.ident`. |
| Alertes, vide, pages | `.alerte--info/alerte/danger/succes`, `.alerte-titre`, `.vide`, `.pages`, `.pages-numeros`, `.pages-position` | Numéros de page dès 768 px ; « Page 1 sur 8 » en dessous. |
| Mode dégradé (S-12) | `.bandeau-degrade`, `.message-su`, `.message-su-auteur`, `.verif-suspendue` | Voir § 6. |
| Erreurs | `.erreur`, `.erreur-code`, `.erreur-aide` | 404, 500 ; 400 et 403 sur le même modèle. |
| Pied | `.site-pied`, `.pied-devise`, `.pied-colonnes`, `.pied-titre`, `.pied-liste`, `.pied-adresse`, `.partenaires`, `.pied-bas`, `.pied-theme` | Devise (art. 5), siège (art. 3), liens, réseaux, partenaires (saisis par les éditeurs, F-61), mentions, confidentialité, « Espace des utilisateurs » (`app.fenamordc.cd`), thème. |

---

## 5. Mouvement (sobre)

Durées des jetons ; `prefers-reduced-motion: reduce` met tout à zéro (jetons + règle générale de `site.css`). Rien n'apparaît bloc par bloc au défilement.

| Interaction | Comportement | Déclencheur |
| --- | --- | --- |
| Bande du gilet | Se déroule de gauche à droite, une fois (700 ms, après 150 ms) | `.gilet--deroule` |
| Chiffres clés | Montent de 0 à la valeur à leur apparition, une fois (700 ms) | `[data-compteur]` |
| Menu du téléphone | Glisse de 8 px et apparaît (200 ms) ; se retire plus vite (120 ms) | `[data-menu-site]` |
| Sélecteur de langue | Se déroule depuis le bouton (200 ms) | `[data-langue]` |
| Carte des coordinations | La case passe en encre ; la ligne s'ouvre et défile jusqu'à elle | clic sur `.tuile`, ou `#coord-XX` dans l'adresse |
| Erreur de champ | Le message tremble une fois (3 px) | `.champ-erreur` |
| Recherche | Les anciens résultats pâlissent pendant la requête | `.zone-rafraichie` + `.htmx-request` |
| Appui | Bouton enfoncé de 1 px | `:active` |

---

## 6. Écrans clés : ce qu'il faut intégrer

### 6.1 Socle (`templates/base.html`)

1. Dans `<head>` : `theme.js` (sans `defer`), préchargement de `atkinson-hyperlegible-next-400.woff2` et `barlow-condensed-600.woff2`, puis `tokens.css`, puis `site.css` ; `<meta name="theme-color" content="#f4f2ed">`, `<meta name="color-scheme" content="light dark">`. Garder les balises SEO actuelles (titre, description, canonical, hreflang, Open Graph, `noindex`).
2. En fin de `<body>` : `site.js` en `defer` ; HTMX seulement sur les pages qui en ont besoin (actualités, annuaire, formulaires) ; Alpine.js n'est pas nécessaire aux pages de ce lot.
3. Structure : `a.aller-contenu` → `header.site-tete` → `div.menu-site#menu-site[hidden]` → (`div.bandeau-degrade` si mode dégradé) → `main#contenu[tabindex=-1]` → `footer.site-pied`. Copier l'en-tête, le menu et le pied de n'importe quelle maquette (identiques partout).
4. `base.html` actuel : remplacer les classes `.entete` / `.pied` provisoires par cette structure. **Attention, test du lot 1** : `test_lot1_selecteur_visible_seulement_si_plusieurs_langues` vérifie qu'aucun `<nav` n'est présent avec une seule langue ; or la navigation principale est un `<nav class="site-nav">`. Le test doit cibler le sélecteur (par exemple `data-langue` ou `aria-label="Langue"`) : à faire adapter par `testeur`, sans retirer le `<nav>` principal. Les autres attentes du lot 1 (devise dans la page, `<html lang>`, hreflang) sont respectées par les maquettes.
5. Langues : les liens du sélecteur viennent de `language_links` (déjà fourni par le processeur de contexte) ; ajouter le nom de chaque langue dans sa langue et son code.
6. Ne pas intégrer `maquettes.js` ni `maquettes-theme.js` (simulation des états).

### 6.2 Pages

| Page (adresse) | Maquette | Données (API) | Points d'intégration |
| --- | --- | --- | --- |
| Accueil `/` | `accueil.html` | statistiques, articles (4 derniers), config | Formulaire de l'accroche en GET vers `/verifier/`. Chiffres : valeur réelle dans le HTML + `data-compteur` ; date des statistiques. Photo de l'accroche : WebP 4:5, `fetchpriority="high"`, seulement dès 992 px (`<picture>` ou `.une-photo`). Bloc adhésion : montant lu dans la config (F-66). |
| La FENAMO-RDC `/a-propos/` | `a-propos.html` | aucune (texte fixe traduit) | **Objectifs (art. 7), catégories de membres (art. 8) et historique : reprendre le texte exact de la charte** ; ceux des maquettes sont des résumés indicatifs. |
| Comité `/organisation/comite/` | `comite.html` | comité, statistiques | Échelons avec les nombres réels (coordinations, antennes, parkings). Dirigeants dans l'ordre des éditeurs ; fonctions de la liste de l'art. 19 (celles des maquettes sont à vérifier). |
| Coordinations `/organisation/coordinations/` | `coordinations.html` | coordinations, statistiques | Voir § 6.3. |
| Documents `/documents/` | `documents.html` | config (fichiers) | Compteur de téléchargements (S-10) : le lien passe par une vue du site qui compte puis redirige. |
| Application `/application/` | `application.html` | config (version, taille, date, APK) | Mode d'emploi en `.etapes-liste` ; QR de l'adresse de téléchargement généré côté serveur (SVG). |
| Actualités `/actualites/` | `actualites.html` | articles | Fragment `#resultats` (liste + pagination) pour HTMX ; état vide ; puces = `?type=`. |
| Article `/actualites/<slug>/` | `actualite.html` | articles | Open Graph avec l'image de l'article (S-08) ; `.mention-langue` quand la traduction manque (S-01). |
| Galerie `/galerie/` | `galerie.html` | galerie | Albums par activité ; vignettes 1:1 WebP 320 px en `loading="lazy"` ; image agrandie 1 280 px chargée seulement à l'ouverture (`data-src`). |
| Contact `/contact/` | `contact.html` | config ; dépôt contact | POST + CSRF + champ piège ; erreurs à côté des champs ; accusé avec la référence ; carte Google à la demande. |
| Mentions `/mentions-legales/`, `/confidentialite/` | `mentions-legales.html` | aucune | Deux adresses, même gabarit (ancre `#confidentialite`) ou deux pages ; texte à valider par la FENAMO (§ 10.3). |
| Erreurs 404, 500 | `erreur.html` | **aucune** | La 500 est autonome : pas d'appel à l'API, pas de processeur de contexte qui l'appelle (en-tête et pied avec des valeurs fixes). |

### 6.3 Coordinations

- Carte : SVG `viewBox="-4 -4 312 436"`, une case de 56 × 56 par coordination à la position (colonne × 62, ligne × 62) donnée dans le tableau ci-dessous ; chaque case est un `<a class="tuile tuile--N" href="#coord-CODE" aria-label="Nom, n membres actifs">` contenant `<rect rx="4">` et `<text>` (code). Classe selon les membres actifs : `0` aucun (bordure tiretée), `1` moins de 1 000, `2` de 1 000 à 5 000, `3` plus de 5 000 (seuils à ajuster quand les effectifs réels seront connus).
- Liste : une ligne `<details class="coord" id="coord-CODE">` par coordination, dans l'ordre de l'annexe C ; `summary` = code en `.plaque-code`, nom, nombre d'antennes, membres actifs ; détail = membres actifs, engins, antennes et effectif par antenne. Sans JavaScript, `:target` met la ligne en évidence.
- Positions (colonne, ligne) : NU (2,0) BU (3,0) HU (4,0) · SU (1,1) MO (2,1) TS (3,1) IT (4,1) · EQ (1,2) TP (2,2) MN (3,2) NK (4,2) · MD (1,3) SA (2,3) LO (3,3) SK (4,3) · KN-O (0,4) KN-E (1,4) KL (2,4) KO (3,4) TG (4,4) · KOC (0,5) KW (1,5) KA (2,5) KC (3,5) HL (4,5) · LW (3,6) HK (4,6). Ces positions sont des données de présentation : les garder dans un dictionnaire du site (pas dans l'API).

### 6.4 Mode dégradé et service suspendu (S-12)

Maquette `service-suspendu.html` (vérification), deux cas :

- **Application verrouillée (F-07)** : alerte `.alerte--alerte` « Vérification suspendue » + message du super-utilisateur reçu dans le corps de la réponse 503 de l'API, affiché en `.message-su` (texte échappé, retours à la ligne gardés, jamais `|safe`) avec « Message de la FENAMO-RDC · date » ; champ et bouton désactivés ; conseil pour le contrôle en attendant. Le reste du site reste en ligne. Même traitement pour les formulaires de contact et d'adhésion (alerte à la place du bouton d'envoi).
- **API injoignable (délai de 5 s dépassé)** : `.bandeau-degrade` sous l'en-tête sur toutes les pages servies depuis le cache (« Service ralenti. Les pages affichent les informations du JJ/MM/AAAA à HH h MM. ») ; vérification et formulaires : « Service momentanément indisponible » + bouton « Réessayer ».

---

## 7. Écriture

- Phrases courtes, verbes actifs, casse de phrase, pas de point d'exclamation, pas de tutoiement. Un bouton dit ce qu'il fait ; l'accusé reprend le verbe : « Envoyer le message » → « Message envoyé » ; « Copier le lien » → « Lien copié ».
- Une erreur dit quoi faire : « Saisissez un téléphone (+243 et 9 chiffres) ou une adresse e-mail. »
- Vocabulaire de la charte : association membre, engin (moto ou tricycle), coordination provinciale, antenne, parking. Jamais « structure », jamais « ville », jamais l'ancien nom du projet.
- **Typographie française** : espace insécable avant `: ; ? !` et à l'intérieur des guillemets « » ; heures « 14 h 00 » avec insécables. Dans les gabarits, écrire `&nbsp;` dans les chaînes à traduire, ou appliquer un filtre aux textes venant de l'API. Sans cela, un deux-points passe en début de ligne dans les titres (constaté sur les maquettes, corrigé).
- **« FENAMO-RDC » ne se coupe jamais** au trait d'union : éviter les libellés courts où le sigle tombe en fin de ligne (pied, boutons), ou l'entourer de `<span class="insecable">`.
- Formats : `+243 812 345 678`, `JJ/MM/AAAA`, milliers avec espace fine insécable (`54 182`), montants « 50 000 FC ».

---

## 8. Accessibilité et performance (mesurées sur les maquettes)

- Contrastes : texte 15,6:1 sur papier ; texte secondaire 6,4:1 ; liens 5,5:1 ; texte sur aplat encre 15,6:1 et 9,4:1 (doux) ; bouton jaune sur encre 10,4:1 ; légendes des emplacements de photo 5,9:1 ; codes de la carte : encre sur `--echelle-1` 14,9:1, sur `--echelle-2` 9,9:1, blanc sur `--echelle-3` 6,2:1 (sombre : 11,4:1, 5,5:1, 8,6:1) ; alerte 6,6:1.
- Focus : anneau de 2 px + halo jaune de 5 px ; sur aplat encre, l'anneau passe en papier. Lien « Aller au contenu ». Focus gardé dans le menu du téléphone et la visionneuse, rendu au déclencheur.
- Cibles : 44 px minimum (liens du pied, de l'aide d'erreur, du sommaire et des pages compris), 48 px pour les champs et boutons principaux.
- 360 px : aucun débordement horizontal sur les 14 maquettes capturées, aucun libellé coupé (contrôle automatique à chaque capture).
- Poids de l'accueil (maquette) : HTML 21 Ko (5 Ko compressé) + `tokens.css` 9 Ko + `site.css` 56 Ko (10 Ko compressé) + `site.js` 13 Ko + sprite 11 Ko + logo 10 Ko + favicon 9 Ko + polices 47 Ko ≈ **176 Ko** sans photos. Budget photos pour rester sous 600 Ko : accroche 4:5 ≤ 80 Ko (ordinateur seulement), une ≤ 60 Ko, vignettes ≤ 25 Ko. Avec ces photos et HTMX (51 Ko) : ≈ 450 Ko.
- Lingala : les lettres ɛ et ɔ ne sont pas dans le sous-ensemble latin des polices ; elles s'affichent avec la police du système. Prévoir un sous-ensemble « latin étendu » d'Atkinson Hyperlegible Next le jour où le lingala est activé.

---

## 9. Autocritique après captures

- Corrigé à la vérification visuelle : quatre grands emplacements de photo empilés sur téléphone (passés en lignes avec vignette) ; initiales qui débordaient dans le téléphone dessiné ; pied de page très long sur téléphone (deux colonnes de liens) ; sous-titre du logo sur trois lignes (retiré) ; deux classes bleues de la carte presque identiques (échelle `--echelle-*` ajoutée) ; ligne ouverte collée au repère jaune ; « membres actifs » répété qui serrait les noms longs (en-tête de colonne) ; deux-points en début de ligne dans un titre (insécables) ; « FENAMO-RDC » coupé au trait d'union dans le pied ; légende répétée sous chaque vignette de galerie ; photo d'article de 630 px de haut sur ordinateur (limitée à 52 rem) ; portraits du comité trop grands (6 colonnes) ; champ de vérification invisible en thème sombre ; icône de panneau absente du sprite.
- Ornement retiré : sous-titre long à côté du logo. Envisagé puis écarté : rayures « chantier » pour le service suspendu, carte de la RDC en contours.
- Ce qui peut encore faire « modèle » : la succession de sections séparées par un filet, de même rythme, sur l'accueil. Acceptable tant que chaque section a un objet différent (chiffres, actualités, adhésion, application) ; ne pas en ajouter une cinquième.

## 10. Points à trancher avec la FENAMO-RDC

- Textes exacts de la charte : objectifs (art. 7), catégories de membres (art. 8), organes (art. 13), fonctions du comité (art. 19).
- Regroupement des cinq rubriques (schéma « plan du site » du cahier non lisible dans le Markdown).
- Seuils de couleur de la carte des coordinations ; carte schématique en cases acceptée à la place d'une carte en contours (le cahier dit « carte de la RDC avec les 27 coordinations ») ?
- Photos réelles (accroche, actualités, dirigeants), avec accord de publication ; nom de l'hébergeur pour les mentions ; durées de conservation.
- Toutes les données des maquettes sont fictives (noms, effectifs, articles, téléphones, frais de 50 000 FC).
