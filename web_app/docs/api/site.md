# API `/api/v1/site/` : points d'accès en lecture du site public (lot 2a)

Référence : cahier des charges application web § 2.4 et F-60 à F-64 ; cahier des charges du site § 6. Erreurs communes : `erreurs.md`.
Exemples de réponses (conformes, utilisés par les tests du site) : `website/tests/fixtures/api_site_*.json`.
Le dépôt de contact est livré (section « Dépôt » plus bas) ; les dépôts d'adhésion et de paiement et la vérification publique viennent aux lots suivants ; les routes inconnues sous `/api/v1/site/` répondent 404 JSON.

## Règles communes

- **GET seulement** : toute autre méthode répond 405 (`Allow: GET`). Pas de HEAD ni d'OPTIONS.
- **Ordre des contrôles** : verrou F-07 (503, avant tout) puis clé (401) puis limite de débit (429) puis méthode (405) puis **interrupteur « données réelles » (403 `inactif`)** puis paramètres (400) puis introuvable (404).
- **Données réelles ou jeu d'exemple** : `Config.donnees_reelles_actif` (faux par défaut ; seul un super-utilisateur le change, écran « Contenu du site », `POST /contenu-site/donnees-reelles/`, journalisé, purge du cache du site). Faux : le site affiche son jeu d'exemple et **tous** les points d'accès de données (`articles/`, `articles/<slug>/`, `galerie/`, `comite/`, `coordinations/`, `statistiques/`) répondent `403 {"statut": "inactif", "detail": "Données réelles désactivées."}` ; `config/` reste disponible mais minimale. Défense en profondeur : une erreur du site ne peut jamais exposer de donnée réelle.
- **Aucun cookie ni session** ; `Cache-Control: no-cache` sur toutes les réponses (le cache est celui du site, voir S-12).
- **Clé du site** : en-tête `X-Site-Key: fsk_<prefixe>_<jeton>`.
- **Langue** : `?lang=fr|ln|sw|lua|kg`. Une valeur inconnue, ou une langue non activée dans la configuration (F-64), donne le français.
- **Pagination** (articles, galerie) : `?page=1&taille=12` (taille de 1 à 50, 12 par défaut). Réponse `{"total", "page", "pages", "resultats"}`. Une page au-delà de `pages` répond 404 ; la page 1 d'une liste vide est valide (`pages` = 0).
- **Dates** : instants en ISO 8601 avec fuseau (`2026-10-01T09:30:00+01:00`, heure de Kinshasa) ; dates calendaires en `AAAA-MM-JJ`.
- **Fichiers** : adresses absolues bâties sur `PUBLIC_MEDIA_BASE_URL` (stockage public seulement ; jamais le stockage privé). Une image est `{"url", "vignette", "largeur", "hauteur"}` ; sans vignette stockée, `vignette` vaut `url`.
- **Jamais exposés** : identifiants internes, auteur, `is_delete`, brouillons, `integration_code`, chemins disque, données de compte ou de membre, clés.
- **Erreurs de paramètre** (400) : `{"champ": ["message"]}`. Introuvable (404) : `{"detail": "Introuvable."}`, identique pour « n'existe pas » et « non publié ».

## Points d'accès

| Chemin | Paramètres | Contenu |
| --- | --- | --- |
| `config/` | | Configuration publique |
| `articles/` | `lang`, `type` (`article` ou `communique`), `q` (2 à 100 caractères), `page`, `taille` | Articles publiés dont la date de publication est passée, du plus récent au plus ancien |
| `articles/<slug>/` | `lang` | Détail ; recherche par slug uniquement, jamais par clé primaire |
| `galerie/` | `type` (`photo` ou `video`), `page`, `taille` | Éléments publiés (hors supprimés et images principales d'articles) |
| `comite/` | | Comité exécutif national |
| `coordinations/` | | Coordinations avec code, et leurs antennes avec code ; non paginé |
| `statistiques/` | | Agrégats seulement |

### `config/`

Toujours disponible, avec `donnees_reelles` (booléen). **Faux** : réponse minimale `{"nom": "FENAMO-RDC", "devise": "Unité, Discipline et Progrès", "langues_actives": ["fr"], "donnees_reelles": false}` (aucune donnée saisie dans l'application web, sauf les langues activées). **Vrai** : réponse complète ci-dessous, plus `"donnees_reelles": true`. Fixture du site : `website/tests/fixtures/api_site_inactif.json`.

`{nom, nom_complet, devise, message_accueil, logo, image_fond, siege, email, telephones[{libelle, numero}], reseaux{facebook, x, youtube, instagram, linkedin}, partenaires[{nom, lien, logo}], langues_actives, paiement_en_ligne, documents[{titre, type, url, taille, date}], application{version, url, taille, date, notice} | null, mise_a_jour}`

`nom` vaut toujours « FENAMO-RDC ». `reseaux` et `lien` : seulement des adresses http(s), sinon `null`. `application` est `null` sans APK ou sans version. `taille` en octets. `mise_a_jour` : dernière modification d'un article publié (`null` s'il n'y en a pas). Le téléphone et l'e-mail ici sont ceux de l'association, saisis dans la configuration du site.

### `articles/`

Élément : `{slug, type, titre, resume, image | null, date_publication, langue, traduit}`. `langue` est la langue réellement servie ; `traduit` est faux seulement quand la langue demandée (active) n'a pas de traduction et que le français est servi (le site affiche alors la mention discrète).

### `articles/<slug>/`

Élément ci-dessus, plus `texte` (HTML à liste blanche, nettoyé à l'enregistrement et de nouveau à la sortie), `video` (`{fournisseur, identifiant}` ou `null`), `galerie` (éléments comme ci-dessous, `article` à `null`), `langues_disponibles` (français + traductions existantes des langues activées) et `mise_a_jour`. Fournisseurs : `youtube` (identifiant de la vidéo) et `facebook` (identifiant = adresse https complète, Facebook n'ayant pas d'identifiant court). Aucun code d'intégration n'est jamais fourni : le site fabrique le lecteur.

### `galerie/`

Élément : `{type, image | null, video | null, legende, date, article}` ; `image` pour une photo, `video` pour une vidéo, l'autre à `null` ; `article` est le slug d'un article publié qui contient l'élément, sinon `null`.

### `comite/`

`{mandat{debut, fin}, membres[{nom, fonction, fonction_code, photo, ordre}]}`. Aucun identifiant de membre, téléphone ni e-mail. `mandat` vaut `{null, null}` tant que F-63 ne saisit pas de dates de mandat (le modèle n'en a pas encore).

### `coordinations/`

`[{code, nom, ordre, antennes[{code, nom, type}]}]`. Sont listées les coordinations qui ont un code officiel et les antennes qui ont un code (le code sert de valeur au formulaire d'adhésion).

### `statistiques/`

`{date_calcul, membres_actifs, engins_actifs, engins_par_type, associations_membres, coordinations, par_coordination[{code, nom, membres_actifs, associations_membres, antennes, engins_actifs}]}`. `engins_actifs` et `engins_par_type` valent `null` tant que les états des engins ne sont pas faits (F-30, F-32) : le site ne doit afficher aucun chiffre d'engins.

## Dépôt : `POST /api/v1/site/contact/` (S-07, F-62)

Même clé `X-Site-Key`, mêmes contrôles que ci-dessus avec `POST` pour seule méthode permise (405 `Allow: POST` sinon). Ordre : verrou F-07 (503) puis clé (401) puis limite de débit par clé (429, seau `POST`) puis méthode (405) puis **données réelles (403 `inactif`)** puis corps (413, 400) puis limite par expéditeur (429). **Mode exemple : refusé en 403 `inactif`**, le cahier ne disant rien ; sinon le jeu d'exemple alimenterait la boîte réelle des éditeurs. Le site doit alors afficher « formulaire indisponible » sans appeler l'API (il le sait par `config/`).

Corps : JSON (`Content-Type: application/json`, objet) ou formulaire encodé ; au plus 20 000 octets (413 sinon). Champs ignorés s'ils sont inconnus (jamais écrits en base).

| Champ | Règle |
| --- | --- |
| `nom` | obligatoire, 2 à 100 caractères |
| `mail` | e-mail valide, 254 caractères au plus, **ou** `telephone` (au moins l'un des deux) |
| `telephone` | chiffres, espaces, `+ . - ( )`, 8 à 15 chiffres, 20 caractères au plus |
| `objet` | obligatoire, 100 caractères au plus |
| `message` | obligatoire, 10 à 3 000 caractères, deux liens (`http://`, `https://`, `www.`) au plus ; les retours à la ligne sont gardés |
| `ouvert_le` | **obligatoire** : horodatage Unix (secondes) de l'affichage du formulaire, posé par le site côté serveur (dans un champ signé ou la session, pas modifiable par le navigateur) ; envoi moins de 3 s après : 400 `non_field_errors` ; plus de 24 h ou dans le futur : 400 `ouvert_le` |
| `site_web` | **champ piège** : invisible, doit rester vide. Rempli : réponse 201 identique à un succès, rien n'est enregistré (le robot ne sait pas qu'il est détecté) |

Texte brut seulement : toute balise HTML est retirée (contenu de `script` et `style` effacé), les entités sont décodées puis `<` et `>` supprimés, les caractères de contrôle retirés, les espaces normalisés. `nom`, `objet` tiennent sur une ligne. Un champ qui n'est pas un texte (liste, objet) est refusé. Le site échappe quand même à l'affichage.

Réponses :

- **201** `{"statut": "recu", "detail": "<accusé à afficher>"}` : aucun identifiant ni écho des données. Fixture : `api_site_contact_recu.json`.
- **400** `{"champ": ["message"]}` (champs `nom`, `mail`, `telephone`, `objet`, `message`, `ouvert_le`, `non_field_errors`) ; plusieurs champs à la fois. Corps illisible : `non_field_errors`. Fixture : `api_site_contact_invalide.json`.
- **413** `{"detail": "Requête trop volumineuse."}` (`api_site_contact_trop_gros.json`).
- **429** `{"detail": "Trop de requêtes."}` (limite de la clé, `SITE_API_LIMITE_POST`) ou `{"detail": "Trop de messages envoyés : réessayez plus tard."}` (3 messages par heure pour un même e-mail ou téléphone, compteur du cache `limites`, empreinte seulement) ; `Retry-After` en secondes (`api_site_contact_limite.json`).
- 401, 403 `inactif`, 405, 503 : voir `erreurs.md`.

La limite **par adresse IP** (cahier du site § 8) reste au site : l'API ne voit que l'adresse du serveur du site.

Côté application web : le message est stocké (`virtrine.Contact`, colonnes additives `cree_le`, `traite_par`, `traite_le`, migration 0023 réversible), une ligne F-70 `creation` est écrite **sans donnée personnelle** (origine, présence d'un e-mail ou téléphone, taille du message ; auteur vide) et une notification (`Notification`, sans destinataire nominatif, texte sans donnée) est créée : SU et président la voient (matrice § 4.3). Les éditeurs (ED), qui n'ont pas de panneau de notifications selon la matrice, voient le compteur « à traiter » de l'écran des messages.

Consultation (F-62, SU et ED seulement ; 403 pour les autres, redirection vers la connexion pour un anonyme ; les messages sont nationaux, sans périmètre) :

- `contact` : `GET /contenu-site/messages/`. Contexte : `contacts` (= `page_obj`, 20 par page, `?page=`, plus récent d'abord), `page_obj`, `nb_a_traiter`. Éléments : `nom`, `mail`, `phone`, `raison` (objet), `description` (message), `traiter`, `cree_le`, `traite_par`, `traite_le`.
- `contact-view` : `GET /contenu-site/messages/<id>/` (lecture, ne modifie rien) ; `POST` (CSRF) marque « traité » : idempotent, journal F-70 `modification` (`avant` `{traiter: false}`, `après` `{traiter: true}`), auteur et date conservés. Contexte : `contact`.

## Clés du site

- Modèle `api.CleSite` : nom, préfixe (8 caractères hexadécimaux, unique), empreinte SHA-256 de la clé entière, `active`, `cree_le`, `revoquee_le`, `derniere_utilisation` (écrite au plus une fois par heure). La clé en clair n'est jamais stockée ni journalisée ; un refus est journalisé (adresse, chemin, préfixe s'il est bien formé).
- Créer : `python manage.py creer_cle_site --nom "Site public"` (la clé n'est affichée qu'une fois). Révoquer : `python manage.py revoquer_cle_site <prefixe>` (effet immédiat).
- **Deux clés actives au plus.** Rotation sans coupure : (1) créer la nouvelle clé ; (2) la mettre dans `SITE_API_KEY` du `.env` du site et recharger l'application du site ; (3) vérifier que le site répond ; (4) révoquer l'ancienne clé. Une troisième création est refusée tant qu'une clé n'est pas révoquée.
- **`SITE_API_KEY` du `.env` de `web_app`** : repli de développement, accepté **seulement si `DEBUG=True`**. En production il n'ouvre plus rien ; seules les clés `CleSite` comptent.

## Limite de débit

Par clé, fenêtre fixe d'une minute : `SITE_API_LIMITE_GET` (300 par défaut) et `SITE_API_LIMITE_POST` (30 par défaut, pour les dépôts des lots suivants), réglables dans `.env`. Au-delà : 429 `{"detail": "Trop de requêtes."}` avec `Retry-After` en secondes. Une requête sans clé valide (401) n'use aucun compteur. Les compteurs sont dans le cache `limites` (`DatabaseCache`, table `cache_limites`), partagé entre les processus de Passenger : **lancer une fois `python manage.py createcachetable`** à l'installation et après chaque base neuve (les tests la créent seuls). Si la table manque, la limite est inactive et l'erreur est journalisée (`api.limites`).

## Réglages

`PUBLIC_MEDIA_BASE_URL` (production : `https://app.fenamordc.cd/media/`) ; vide, l'adresse est déduite de la requête. Voir `.env.example`.

## Compatibilité

Ajouter un champ est compatible ; retirer ou renommer un champ, ou changer son sens, impose `/api/v2/`. Le site doit ignorer les champs inconnus.
