# Cahier des charges — Site web FENAMO-RDC

Oct 12, 2026 · @Jonathan

## 1. Présentation

Ce cahier des charges couvre le site public `fenamordc.cd` de la FENAMO-RDC asbl : un projet Django séparé, sans base de données métier, qui lit et dépose ses données uniquement via l'API de l'application web `app.fenamordc.cd`.

### 1.1 Contexte

La Fédération Nationale des Associations des Motocyclistes Taximen de la RDC (FENAMO-RDC asbl) a été créée le 30 mars 2024 à Kinshasa, en partenariat avec l'État à travers le ministère des Transports. Sa charte (juin 2024, authentifiée le 12 août 2024) lui confie de réunir les associations de motocyclistes et de propriétaires d'engins, de les enregistrer, et d'identifier chaque année motocyclistes et engins (art. 6 et 7). Le site est sa vitrine publique et la porte d'entrée des nouvelles associations.

### 1.2 Objectifs

1. **Faire connaître** la FENAMO-RDC : mission, organisation, dirigeants, implantation dans les 27 coordinations provinciales.
2. **Recruter** : permettre à une association de déposer sa demande d'adhésion en ligne, pièces jointes et paiement compris.
3. **Rassurer l'État et les partenaires** : annuaire public des associations membres, effectifs, documents officiels.
4. **Vérifier** : permettre à chacun de contrôler une carte de membre ou un engin par numéro ou QR code.
5. **Informer** : actualités, communiqués publics, galerie, application mobile.

### 1.3 Publics

| Public | Ce qu'il vient chercher |
| --- | --- |
| Motocyclistes et propriétaires d'engins | Comprendre la FENAMO-RDC, télécharger l'application mobile, vérifier leur carte |
| Associations candidates | Conditions d'adhésion, dépôt de la demande, paiement des frais |
| Autorités, police, ministère des Transports | Vérification d'un membre ou d'un engin, effectifs, annuaire, documents officiels |
| Partenaires, médias, grand public | Présentation, dirigeants, actualités, contact |

### 1.4 Périmètre

| Inclus | Hors périmètre |
| --- | --- |
| Pages publiques, formulaires de contact et d'adhésion, vérification, paiement en ligne des frais d'adhésion | Saisie et validation des données (application web) |
| Affichage multilingue | Gestion du contenu : articles, galerie, comité, configuration se saisissent dans l'application web (F-60 à F-66) |
| Consommation de l'API publique `/api/v1/site/` | Conception de l'API (cahier des charges de l'application web, § 2.4) |
| Déploiement sur `fenamordc.cd` | Application mobile |

### 1.5 Glossaire

Le glossaire de l'application web s'applique (charte, coordination, antenne, parking, association membre, engin, F92…). Termes propres au site :

| Terme | Définition |
| --- | --- |
| API publique | Points d'accès `/api/v1/site/` de l'application web, réservés au site |
| Clé du site | Secret qui identifie le site auprès de l'API ; jamais visible dans le navigateur |
| Jeton QR | Code unique imprimé en QR sur la carte ou l'autocollant, qui mène à la page de vérification |
| Mise en cache | Conservation temporaire des réponses de l'API par le site pour répondre vite et résister à une panne |

## 2. Identité visuelle

Le site applique l'identité fixée par la charte : nom officiel, devise et logo officiel aux couleurs du drapeau national.

| Élément | Règle |
| --- | --- |
| Nom | « Fédération Nationale des Associations des Motocyclistes Taximen de la République Démocratique du Congo » ; sigle **FENAMO-RDC asbl** ; mention « Plateforme » |
| Devise | **Unité, Discipline et Progrès** (art. 5), visible en pied de page et sur la page de présentation |
| Logo | Logo officiel (art. 4) : motocycliste casqué sur moto à deux roues et tricycle, carte de la RDC, cercle aux trois couleurs du drapeau, fond blanc. Fourni par la FENAMO en SVG ou PNG haute résolution ; jamais déformé ni recoloré |
| Couleurs | Palette tirée du logo et du drapeau : bleu ciel, rouge, jaune, sur fond blanc ; contrastes conformes à l'accessibilité (WCAG AA) |
| Typographie | Une police lisible sur petit écran, servie en local (pas de Google Fonts) |
| Ton éditorial | Institutionnel, clair et direct ; phrases courtes ; tutoiement exclu |
| Images | Photos réelles d'activités de la FENAMO (aucune image de démonstration) ; compressées (WebP) |

Une maquette des pages clés (accueil, adhésion, vérification) est validée par la FENAMO avant l'intégration (lot 1, § 11).

## 3. Existant

Le site actuel est l'app `virtrine` du projet « coptam », servie à la racine de l'application web. Il est entièrement remplacé par le nouveau projet ; seuls ses contenus et ses modèles de données sont réutilisés.

| Élément actuel | Constat | Décision |
| --- | --- | --- |
| Pages : accueil, à propos, activités, détail d'article, portail, politique de confidentialité, configuration | Pages fonctionnelles mais liées directement à la base | Refaites dans le nouveau projet, alimentées par l'API |
| Template d'origine médicale (fichiers `doctors.html`, `Credits.txt`, polices maicons) | Habillage sans rapport avec la FENAMO | Abandonné |
| Modèles `Article`, `Galery`, `Config`, `Contact` | Utiles, mais `Config` multiplie les champs (7 téléphones, 7 partenaires) | Restent dans l'application web, revus (listes de téléphones et de partenaires), exposés par l'API |
| Page `configuration/` publique | Modification du site accessible depuis le site | Supprimée : la configuration se fait dans l'application web (F-61) |
| Clé Google Maps écrite en dur dans un template | Clé exposée et réutilisable par n'importe qui | Nouvelle clé restreinte au domaine `fenamordc.cd`, lue depuis `.env` ; l'ancienne est révoquée |
| APK `fenamo-app.apk` dans les fichiers statiques | Téléchargement direct, sans version ni notice | Page « Application mobile » avec version, taille, date et mode d'emploi |
| Champ `integration_code` des articles (HTML libre) | Risque d'injection de script | Remplacé par un lien vidéo (YouTube, Facebook) transformé en lecteur par le site |

## 4. Arborescence et contenus

Le site compte cinq rubriques sous l'accueil ; chaque page est à un clic du menu, et la vérification est aussi accessible directement par le lien du QR code.

&#91;embedded content: plan du site · 5 rubriques\]

### 4.1 Pages

Les adresses sont en français ; une autre langue ajoute un préfixe (`/ln/`, `/sw/`, `/lua/`, `/kg/`, § 7).

| Page | Adresse | Contenu | Source des données |
| --- | --- | --- | --- |
| Accueil | `/` | Message clé et devise ; chiffres clés (membres et engins actifs, associations membres, coordinations) ; champ « Vérifier une carte » ; dernières actualités ; appel à l'adhésion ; téléchargement de l'application | API : statistiques, articles, config |
| La FENAMO-RDC | `/a-propos/` | Préambule, but et mission (art. 6), 12 objectifs (art. 7), devise, historique de la création du 30 mars 2024, catégories de membres (art. 8) | Texte fixe, traduit |
| Comité exécutif | `/organisation/comite/` | Organigramme (art. 13) et dirigeants : photo, nom, fonction, dans l'ordre fixé par les éditeurs | API : comité |
| Coordinations | `/organisation/coordinations/` | Carte de la RDC avec les 27 coordinations et leurs codes ; pour chacune, antennes et effectifs actifs | API : coordinations, statistiques |
| Documents | `/documents/` | Charte, règlement d'ordre intérieur, formulaires à télécharger (PDF) | API : config (fichiers gérés par les éditeurs) |
| Annuaire | `/associations/` | Liste des associations membres : nom, sigle, n° F92, qualité (art. 8), coordination ; recherche et filtres | API : associations |
| Fiche association | `/associations/<sigle>/` | Logo, nom, sigle, F92, qualité, coordination, siège (ville seulement), nombre de membres actifs | API : associations |
| Adhésion | `/adhesion/` | Conditions de l'art. 9, pièces exigées, frais en vigueur, formulaire de demande (S-04) | API : config, coordinations ; dépôt : adhésion |
| Suivi de demande | `/adhesion/suivi/` | État d'une demande à partir de sa référence et de l'e-mail du demandeur | API : adhésion |
| Paiement des frais | `/adhesion/paiement/` | Paiement mobile money des frais d'adhésion, seulement si activé (F-65) | API : paiement |
| Vérifier | `/verifier/` | Saisie d'un identifiant MBR ou d'un numéro d'engin ; résultat selon le § 10.2 | API : vérification |
| Lien du QR code | `/v/<jeton>/` | Ouvre directement le résultat de la vérification | API : vérification |
| Actualités | `/actualites/` et `/actualites/<slug>/` | Articles et communiqués publics, filtrables par type ; partage sur les réseaux | API : articles |
| Galerie | `/galerie/` | Photos et vidéos d'activités | API : galerie |
| Application mobile | `/application/` | Présentation, version, taille, date, téléchargement de l'APK, mode d'emploi | API : config |
| Contact | `/contact/` | Siège (04, avenue Kasa-Vubu, quartier Mariano, Ngiri-Ngiri, Kinshasa — art. 3), téléphones, e-mail, réseaux sociaux, carte, formulaire (S-07) | API : config ; dépôt : contact |
| Mentions légales, confidentialité | `/mentions-legales/`, `/confidentialite/` | Éditeur du site, hébergeur, traitement des données des formulaires et de la vérification | Texte fixe |
| Erreurs | 404, 500, « service suspendu » | Pages sobres, avec retour à l'accueil et contact | Texte fixe |

### 4.2 Éléments communs à toutes les pages

- En-tête : logo, menu des cinq rubriques, bouton « Vérifier », sélecteur de langue (si plusieurs langues actives).
- Pied de page : devise, coordonnées du siège, réseaux sociaux, partenaires (ministère des Transports et autres partenaires saisis par les éditeurs), liens légaux, lien vers l'espace des utilisateurs `app.fenamordc.cd`.

## 5. Fonctionnalités

Le site n'a pas de comptes utilisateurs : toutes ses fonctions sont ouvertes au public, et toute donnée sensible reste dans l'application web. Chaque fonction porte un identifiant (S-xx) repris dans les tests et la recette.

| ID | Fonction | Règles de gestion |
| --- | --- | --- |
| S-01 | Afficher les contenus | Toutes les pages dynamiques lisent l'API (§ 6) ; un contenu absent dans la langue choisie s'affiche en français |
| S-02 | Rechercher | Recherche dans les actualités et l'annuaire des associations membres ; résultats pendant la frappe (HTMX) |
| S-03 | Vérifier un membre ou un engin | Par identifiant MBR, numéro d'engin ou lien du QR code ; affichage limité aux données du § 10.2 ; états affichés : actif, à renouveler, suspendu, inconnu ; date et heure de la consultation affichées (preuve pour un contrôle) ; limite de 20 vérifications par heure et par adresse IP, puis captcha |
| S-04 | Déposer une demande d'adhésion | Formulaire en 3 étapes : (1) l'association (nom, sigle, n° F92 ou arrêté, siège, coordination et antenne choisies, responsable, téléphone, e-mail) ; (2) les pièces de l'art. 9 (statuts avec F92 ou arrêté, agrément du ministère des Transports, preuve de paiement si payé hors ligne) ; (3) acceptation de la charte et envoi. Le site reçoit une référence de suivi et l'affiche ; un e-mail la confirme. Un numéro F92 déjà enregistré est refusé avec un message clair |
| S-05 | Suivre sa demande | Référence + e-mail ; états : reçue, en vérification (antenne, coordination, national), renvoyée avec motif, acceptée ; aucune donnée interne affichée |
| S-06 | Payer les frais d'adhésion en ligne | Visible seulement si le SU a activé le paiement (F-65) ; montant lu dans l'API (F-66) ; paiement par mobile money via FlexPaie ou équivalent ; la confirmation est reçue par l'application web, pas par le site ; le site affiche le résultat et la référence |
| S-07 | Contacter la FENAMO | Nom, téléphone ou e-mail, objet, message ; transmis à l'application web (F-62) ; accusé de réception à l'écran |
| S-08 | Partager une page | Aperçu soigné sur WhatsApp, Facebook et X (balises Open Graph : titre, résumé, image) ; boutons de partage sur les actualités |
| S-09 | Afficher les statistiques publiques | Membres et engins actifs, associations membres, par coordination ; chiffres agrégés uniquement |
| S-10 | Télécharger l'application et les documents | APK et PDF servis avec version, taille et date ; compteur de téléchargements |
| S-11 | Changer de langue | Sélecteur visible si au moins deux langues sont actives (F-64) ; choix mémorisé |
| S-12 | Fonctionner en mode dégradé | Si l'API ne répond pas, les pages s'affichent avec le dernier contenu en cache ; les formulaires et la vérification affichent « service momentanément indisponible » ; si l'application est verrouillée (F-07), le site reste en ligne mais ces fonctions sont suspendues |

## 6. Utilisation de l'API

Le site appelle l'API depuis son serveur, jamais depuis le navigateur : la clé du site reste secrète, et les réponses sont mises en cache pour que les pages s'affichent vite même quand la connexion entre les deux serveurs est lente.

### 6.1 Points d'accès utilisés et durée de cache

Les points d'accès sont définis au § 2.4 du cahier des charges de l'application web.

| Point d'accès | Pages | Cache côté site |
| --- | --- | --- |
| `/api/v1/site/config/` | Toutes (en-tête, pied de page) | 15 min |
| `/api/v1/site/articles/` | Accueil, actualités | 5 min |
| `/api/v1/site/galerie/` | Galerie | 15 min |
| `/api/v1/site/comite/` | Comité exécutif | 1 h |
| `/api/v1/site/coordinations/` | Coordinations, adhésion | 24 h |
| `/api/v1/site/associations/` | Annuaire, fiches | 1 h |
| `/api/v1/site/statistiques/` | Accueil, coordinations | 1 h |
| `/api/v1/site/verifier/…` | Vérifier, lien QR | Aucun cache (résultat toujours à jour) |
| `/api/v1/site/contact/`, `/adhesion/`, `/paiement/` | Formulaires | Aucun cache (dépôts) |

Les durées sont des valeurs de départ, réglables dans le `.env` du site. Une publication dans l'application web peut vider le cache du site (appel de purge sécurisé), pour qu'un communiqué urgent apparaisse immédiatement.

### 6.2 Règles d'appel

- Chaque appel porte la clé du site dans un en-tête ; la clé est lue dans le `.env` du site et peut être révoquée depuis l'application web.
- Délai maximal d'attente : 5 secondes ; au-delà, le site applique le mode dégradé (S-12).
- Les fichiers (logos, photos, PDF) sont servis par l'application web avec des adresses publiques ; les pièces jointes d'une demande d'adhésion sont transmises par le serveur du site, puis supprimées de celui-ci.
- Les réponses d'erreur de l'API (validation d'un formulaire, doublon F92) sont traduites en messages clairs à côté des champs.
- Le site ne stocke aucune donnée personnelle : il n'a pas de base de données métier, seulement son cache.

## 7. Langues

Le site ouvre en français seul, mais il est construit dès le départ pour les quatre langues nationales : chacune s'active sans développement supplémentaire dès que ses textes sont traduits.

| Langue | Code | Préfixe d'adresse | Au lancement |
| --- | --- | --- | --- |
| Français | fr | aucun | Active, langue de référence |
| Lingala | ln | `/ln/` | Prête, à activer |
| Kiswahili | sw | `/sw/` | Prête, à activer |
| Tshiluba | lua | `/lua/` | Prête, à activer |
| Kikongo | kg | `/kg/` | Prête, à activer |

- **Textes fixes** (menus, boutons, formulaires, messages, pages institutionnelles) : traduits dans les fichiers de traduction Django (`.po`). La FENAMO fournit les traductions ; le prestataire les intègre.
- **Articles et communiqués** : saisis par les éditeurs dans chaque langue souhaitée (F-60) ; le français est obligatoire, les autres facultatifs ; sans traduction, l'article s'affiche en français avec une mention discrète.
- **Activation** : une langue s'active dans l'application web (F-64), seulement quand ses textes fixes sont complets.
- **Référencement** : chaque page déclare ses versions linguistiques (balises `hreflang`).
- **Données** : noms propres, sigles, codes et numéros ne sont jamais traduits.

## 8. Technologie et hébergement

Le site est un projet Django + HTMX distinct de l'application web, hébergé sur le même cPanel mutualisé à l'adresse `fenamordc.cd` ; il reprend les mêmes outils pour qu'une seule compétence suffise à maintenir les deux.

### 8.1 Pile technique

| Élément | Choix |
| --- | --- |
| Langage, framework | Python, Django (même version que l'application web) |
| Interactions | HTMX + Alpine.js servis en local (recherche, formulaire d'adhésion par étapes, sélecteur de langue) |
| Mise en page | CSS léger et responsive (Bootstrap 5 ou équivalent, limité aux composants utilisés) |
| Appels à l'API | Bibliothèque `requests` (ou `httpx`), côté serveur |
| Cache | Cache Django sur fichiers ou base SQLite locale (pas de Redis sur mutualisé) |
| Carte | Carte des coordinations en SVG léger ; carte Google Maps seulement sur la page contact, clé restreinte au domaine |
| Base de données | Aucune base métier ; SQLite seulement pour les sessions, le cache et les compteurs |

### 8.2 Environnements

| Élément | Développement | Production |
| --- | --- | --- |
| Adresse du site | `http://localhost:8001` | `https://fenamordc.cd` (et `www` redirigé) |
| API appelée | `http://localhost:8000/api/v1/site/` | `https://app.fenamordc.cd/api/v1/site/` |
| Serveur | `runserver` | Passenger, application Python cPanel |
| Configuration | `.env` local | `.env` serveur (clé du site, adresse de l'API, clé Google Maps, durées de cache) |
| HTTPS | Non | AutoSSL, redirection HTTP → HTTPS, HSTS |

### 8.3 Référencement et partage

- Titres et descriptions propres à chaque page ; adresses lisibles ; plan du site `sitemap.xml` et `robots.txt`.
- Balises Open Graph pour l'aperçu WhatsApp et Facebook (S-08).
- Les pages de vérification et de suivi ne sont jamais indexées (`noindex`).
- Inscription du site dans Google Search Console.

## 9. Contraintes d'usage en RDC

La plupart des visiteurs arrivent depuis un téléphone d'entrée de gamme, souvent par un lien partagé sur WhatsApp ou un QR code scanné au bord de la route : le site doit s'afficher vite sur une connexion 3G instable.

| Contrainte | Exigence |
| --- | --- |
| Connexion lente ou coûteuse | Page d'accueil sous 600 Ko ; page de vérification sous 150 Ko ; images en WebP, redimensionnées, chargées à la demande |
| Téléphone d'abord | Conçu pour un écran de 360 px, puis adapté à la tablette et à l'ordinateur ; menu repliable ; boutons assez grands pour le doigt |
| Vérification sur le terrain | Lien QR qui ouvre le résultat en une seule page, sans menu à parcourir ; texte lisible en plein soleil (contraste élevé) |
| Coupures | Formulaire d'adhésion qui conserve la saisie entre les étapes ; envoi des pièces avec barre de progression et reprise possible |
| Navigateurs | Chrome Android, Opera Mini en mode normal, Firefox, Edge, Safari ; deux dernières versions majeures |
| Langues et formats | Français par défaut (§ 7) ; téléphones au format +243 ; montants en francs congolais ; dates JJ/MM/AAAA |
| Polices et icônes | Servies en local ; aucune dépendance à un CDN |

## 10. Sécurité et données personnelles

Le site ne détient aucune donnée personnelle et n'affiche que ce qui sert à identifier un membre ou un engin sur le terrain ; tout le reste se consulte dans l'application web avec un compte, y compris pour la police (compte visiteur).

### 10.1 Protection du site

- HTTPS obligatoire, en-têtes de sécurité (HSTS, `X-Frame-Options`, `Referrer-Policy`, politique de contenu compatible avec HTMX et Alpine.js).
- `DEBUG=False` en production ; clé secrète, clé du site et clé Google Maps uniquement dans le `.env`.
- Formulaires : protection CSRF, champ piège invisible contre les robots, limite d'envois par adresse IP, captcha après abus.
- Pièces jointes de l'adhésion : PDF, JPG ou PNG, taille maximale à fixer, type réel vérifié ; transmises à l'API puis effacées du serveur du site.
- Aucun contenu HTML libre venant de l'API n'est injecté tel quel : le texte des articles est nettoyé (liste blanche de balises).

### 10.2 Vérification publique : ce qui est affiché

| Affiché sur le site | Jamais affiché (compte requis dans l'application web) |
| --- | --- |
| **Membre** : photo, nom, identifiant MBR, qualité (motard / propriétaire), association membre, coordination, antenne, parking, état, validité de la carte | Adresse, téléphone, e-mail |
| **Engin** : numéro FENAMO, type, marque, couleur, plaque, nom du propriétaire, motard rattaché, état, validité de l'identification | Date et lieu de naissance, filiation, état civil |
| Date et heure de la consultation | N° de carte d'électeur, n° de permis, pièces jointes, famille, historique, paiements |

- Le jeton QR est un code aléatoire, distinct de l'identifiant interne, pour qu'on ne puisse pas parcourir les fiches en changeant un numéro.
- Une carte signalée perdue ou un membre supprimé s'affiche « non valide », sans autre détail.
- Les vérifications sont comptées (date, résultat) sans enregistrer l'identité du visiteur ; les abus déclenchent la limite de S-03.

### 10.3 Confidentialité

La page `/confidentialite/` explique quelles données les formulaires collectent, à quoi elles servent, qui les traite (la FENAMO-RDC via l'application web), combien de temps elles sont conservées et comment demander leur suppression. Elle précise aussi ce que montre la vérification publique. Le texte est validé par la FENAMO avant la mise en ligne.

## 11. Qualité, livraison et recette

Le site se livre en quatre lots ; il dépend de l'API de l'application web, et sa mise en ligne suit celle de `app.fenamordc.cd` (lot 5 de l'application web).

### 11.1 Lots

| Lot | Contenu | Critère de fin |
| --- | --- | --- |
| 1 — Maquettes et socle | Maquettes validées (accueil, adhésion, vérification), projet Django, `.env`, gabarit commun, fichiers de traduction prêts | Maquettes signées par la FENAMO ; le projet démarre sur `localhost:8001` |
| 2 — Pages de contenu | Accueil, La FENAMO-RDC, organisation, annuaire, actualités, galerie, documents, application mobile, contact, pages légales, branchées sur l'API locale avec cache | Toutes les pages affichent les données du jeu d'essai ; mode dégradé vérifié en coupant l'API |
| 3 — Fonctions publiques | Vérification et lien QR, adhésion en 3 étapes, suivi de demande, contact, paiement en ligne (activable) | Fonctions S-03 à S-07 recettées, y compris sur téléphone et connexion lente |
| 4 — Mise en ligne | Déploiement sur `fenamordc.cd`, HTTPS, référencement, Search Console, anciennes adresses de `virtrine` redirigées | Recette en production signée |

### 11.2 Tests

- **Automatisés** : chaque page répond avec une API simulée ; respect du § 10.2 (aucun champ interdit dans le résultat d'une vérification) ; formulaires (validation, anti-spam) ; repli sur le français.
- **Performance** : poids des pages (§ 9) mesuré avec les outils du navigateur en mode « 3G lente ».
- **Manuels** : téléphone Android d'entrée de gamme ; scan de QR codes réels imprimés.

### 11.3 Recette et documentation

- Scénario par fonction S-xx : résultat attendu, obtenu, décision ; une anomalie bloquante empêche le lot suivant.
- `README.md` d'installation, guide de déploiement cPanel, note pour les éditeurs sur l'effet de leurs saisies (F-60 à F-66) sur le site.

## 12. Annexes

### A. Correspondance entre pages et charte

| Page ou fonction | Articles de la charte |
| --- | --- |
| La FENAMO-RDC | Préambule ; art. 1 et 2 (création, fondateurs) ; art. 5 (devise) ; art. 6 (but) ; art. 7 (objectifs) ; art. 8 (catégories de membres) |
| Identité visuelle | Art. 1 (nom) ; art. 4 (logo) ; art. 5 (devise) |
| Comité exécutif | Art. 13 (organes et organigramme) ; art. 19 (composition du comité exécutif national) ; art. 20 et 72 (mandat de 5 ans) |
| Coordinations | Art. 14 (Kinshasa-Est et Kinshasa-Ouest) ; art. 43 (27 coordinations et codes) ; art. 66 (antennes) |
| Annuaire | Art. 8 (qualité des associations membres) ; art. 9 (F92, agrément) |
| Adhésion et paiement | Art. 9 (conditions et frais) ; art. 79 (ressources) |
| Vérification | Art. 7.2 (identification annuelle, gilets, numérotation, carte de membre) |
| Contact | Art. 3 (siège) |
| Documents | Art. 92 et 93 (règlement d'ordre intérieur) |

### B. Ancien site → nouveau site

| Ancienne adresse (`virtrine`) | Nouvelle adresse | Redirection |
| --- | --- | --- |
| `/` | `/` | — |
| `/a-propos-de-nous/` | `/a-propos/` | 301 |
| `/activites/` | `/actualites/` | 301 |
| `/article-by-coptam-rdc/<id>` | `/actualites/<slug>/` | 301 |
| `/portail/` | `/` | 301 |
| `/confidentiel/` | `/confidentialite/` | 301 |
| `/configuration/` | Supprimée (F-61 dans l'application web) | 410 |

### C. Points à fournir par la FENAMO

- Logo officiel en SVG ou PNG haute résolution.
- Textes validés : présentation, mentions légales, politique de confidentialité.
- Photos des dirigeants et d'activités, avec accord de publication.
- Charte et règlement d'ordre intérieur en PDF.
- Traductions en lingala, kiswahili, tshiluba et kikongo, quand la FENAMO souhaite activer ces langues.
- Compte marchand FlexPaie (ou équivalent) au nom de la FENAMO-RDC, pour le paiement en ligne.
