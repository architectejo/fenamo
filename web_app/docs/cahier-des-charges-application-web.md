# Cahier des charges — Application web FENAMO

Oct 12, 2026 · @Anicet

## 1. Présentation

Ce cahier des charges couvre la refonte de l'application web de gestion de la FENAMO, qui sera servie sur `app.fenamordc.cd`. Il fixe trois objectifs : une interface sans rechargement de page, un projet renommé « fenamo », et une application sûre pour des données personnelles de membres.

### 1.1 Contexte

La FENAMO-RDC asbl (Fédération Nationale des Associations des Motocyclistes Taximen de la RDC) est une plateforme associative créée le 30 mars 2024 à Kinshasa, partenaire de l'État à travers le ministère des Transports. Sa charte (juin 2024, acte authentifié par le ministère de la Justice le 12 août 2024) lui confie d'enregistrer et valider les associations du secteur, et d'identifier chaque année les engins (motos à deux roues et tricycles) et les motocyclistes, avec « un tableau actualisé des effectifs sur un logiciel internet avec application mobile » (art. 7). L'application web est ce logiciel.

L'application actuelle, développée en Django sous le nom de projet « coptam », gère déjà les associations membres, les motocyclistes, leurs motos et la communication interne. Elle fonctionne en local sur `localhost:8000` avec une base SQLite.

### 1.2 Objectifs de la refonte

1. **Interface asynchrone** : chaque action courante (valider, ajouter, modifier, supprimer, rechercher) met à jour la page sans la recharger, avec HTMX et Alpine.js.
2. **Renommage** : le projet Django s'appelle `fenamo` ; toute mention « COPTAM » disparaît de l'interface.
3. **Sécurité** : contrôle d'accès sur chaque écran, mots de passe hachés, secrets hors du code.
4. **Mise en production** sur cPanel mutualisé, accessible partout en RDC, y compris sur une connexion mobile lente.
5. **Préparation de l'API** `/api/v1/` qui servira plus tard l'application mobile et le site.

### 1.3 Utilisateurs

L'application est utilisée à tous les échelons de la charte : agents de terrain dans les antennes et les parkings, validateurs d'antenne, de coordination provinciale et national, président de la FENAMO-RDC, éditeurs du contenu, visiteurs en lecture seule (par exemple le ministère des Transports) et super-utilisateurs du prestataire technique. Les membres de base n'y accèdent pas : ils passent par l'application mobile. Les rôles sont détaillés au § 4.

### 1.4 Périmètre

| Inclus dans ce document | Hors périmètre (cahiers des charges séparés) |
| --- | --- |
| Back-office : apps `compte` et `coptapp` | Site public `fenamordc.cd`, nouveau projet séparé qui ne passe que par l'API |
| Gestion du contenu du site (articles multilingues, galerie, comité exécutif, configuration, messages de contact) | Application mobile Android et app `mobapp` |
| API `/api/v1/` : points d'accès publics pour le site, cadre pour le mobile (authentification, versionnement) | Écrans mobiles qui consommeront l'API |
| Renommage, sécurité, déploiement de l'application web | Temps réel (WebSockets), non supporté par l'hébergement |

### 1.5 Glossaire

| Terme | Définition |
| --- | --- |
| Charte | Statuts de la FENAMO-RDC asbl (juin 2024), référence des règles métier de ce document |
| Province / coordination provinciale | Une des 27 coordinations de la charte (art. 43), chacune avec un code officiel ; Kinshasa compte deux coordinations (Kinshasa-Est, Kinshasa-Ouest) |
| Ville | Niveau de l'application actuelle, absent de la charte : retiré au profit des antennes (§ 2.3) |
| Antenne | Correspond à une commune ou à un territoire administratif (art. 66) |
| Parking | Lieu de stationnement des motos-taxis, codifié par la FENAMO (art. 7.4) ; rattaché à une antenne |
| Association membre | Association membre de la FENAMO, enregistrée avec ses documents légaux (F92 ou arrêté ministériel, agrément du ministère des Transports) |
| F92 | Récépissé du ministère de la Justice attestant le dépôt des statuts d'une asbl |
| Membre | Motocycliste (motard) ou propriétaire d'engin inscrit via une association membre. Identifiant au format `MBR0000001` |
| Engin | Moto (deux roues) ou tricycle (trois roues), enregistré au nom d'un propriétaire, avec un numéro FENAMO |
| Motard | Membre qui conduit un engin ; il peut être rattaché à l'engin d'un autre propriétaire |
| Jeton de résidence | Attestation de résidence signée par le chef d'avenue et de quartier, exigée pour l'identification (art. 7.2) |
| Identification annuelle | Renouvellement chaque année de l'identification d'un membre et d'un engin (carte, gilet numéroté, autocollant vinyle) |
| Communiqué | Message diffusé aux utilisateurs, auquel on peut réagir |
| Fragment HTMX | Morceau de HTML renvoyé par le serveur pour remplacer une zone de la page |
| cPanel | Panneau de gestion de l'hébergement mutualisé qui héberge l'application |

## 2. Interfaces avec le site web et l'application mobile

L'application web est la seule propriétaire des données : elle seule écrit dans la base, et le site comme l'application mobile y accèdent par l'API `/api/v1/`. Le site public devient un projet Django séparé, sans accès à la base ; seule l'app mobile actuelle (mobapp) lit encore la base directement pendant la transition.

### 2.1 Données partagées

| Donnée | Maître | Lue par le site | Lue ou créée par le mobile |
| --- | --- | --- | --- |
| Coordinations, antennes, parkings | Application web | Non | Lecture (choix à l'inscription) |
| Associations membres, antennes | Application web | Lecture (liste publique, partenaires) | Lecture |
| Membres | Application web | Non | Création (inscription), lecture de sa propre fiche |
| Motos | Application web | Non | Création et lecture des siennes |
| Articles, galerie, configuration du site | Application web | Lecture | Non |
| Messages de contact | Application web | Création (formulaire) | Non |

Une inscription faite depuis le mobile arrive dans l'application web comme un membre à valider. Elle suit le même circuit de validation qu'un membre saisi par un responsable.

### 2.2 Deux types d'endpoints

| Type | Format | Préfixe | Consommateur | Authentification |
| --- | --- | --- | --- | --- |
| Pages et fragments HTMX | HTML | Racine : `/membres/`, `/motos/`… | Navigateur de l'application web uniquement | Session Django + CSRF |
| API | JSON | `/api/v1/` | Application mobile, site public | Jeton (token), pas de cookie de session |

Un fragment HTMX n'est jamais appelé par un autre produit. Une route `/api/v1/` ne renvoie jamais de HTML.

### 2.3 Règles de compatibilité pendant la refonte

- Aucun champ utilisé par `mobapp` ou `virtrine` n'est renommé ni supprimé sans mise à jour coordonnée de ces apps.
- Les migrations restent additives tant que le site et le mobile lisent directement la base.
- Les anciennes URL de `mobapp` (`/mob/…`) continuent de fonctionner jusqu'à la sortie de la nouvelle application mobile.
- La règle de numérotation des motos (numéro + sigle de province) est centralisée dans une seule fonction, utilisée par l'application web, `mobapp` et la future API.
- L'API `/api/v1/` est conçue dans ce document ; son contenu exact est fixé avec les cahiers des charges du site et du mobile.

Le modèle `Ville` est retiré progressivement : les villes existantes (8 enregistrements) sont converties en antennes, et `mobapp`, qui choisit encore une ville à l'inscription, garde une correspondance ville → antenne jusqu'à la nouvelle application mobile.

### 2.4 Points d'accès publics de l'API pour le site

Le site `fenamordc.cd` n'utilise que ces points d'accès. Ils sont en lecture seule, sauf les dépôts (contact, adhésion, paiement), protégés par une clé propre au site, une limite de débit et un anti-spam.

| Point d'accès | Méthode | Contenu |
| --- | --- | --- |
| `/api/v1/site/config/` | GET | Nom, devise, logo, contacts, réseaux sociaux, partenaires, langues activées, paiement en ligne activé ou non |
| `/api/v1/site/articles/` et `/<id>/` | GET | Articles et communiqués publics, dans la langue demandée (repli sur le français) |
| `/api/v1/site/galerie/` | GET | Images publiées |
| `/api/v1/site/comite/` | GET | Comité exécutif national : nom, fonction, photo, ordre d'affichage |
| `/api/v1/site/coordinations/` | GET | 27 coordinations, codes, antennes |
| `/api/v1/site/associations/` | GET | Annuaire public : nom, sigle, n° F92, qualité (art. 8), coordination, état |
| `/api/v1/site/statistiques/` | GET | Effectifs agrégés (membres et engins actifs par coordination et par type) |
| `/api/v1/site/verifier/membre/<identifiant ou jeton QR>/` | GET | Photo, nom, identifiant, qualité, association membre, coordination, antenne, parking, état, validité de la carte |
| `/api/v1/site/verifier/engin/<numéro ou jeton QR>/` | GET | Numéro FENAMO, type, marque, couleur, plaque, propriétaire, motard rattaché, état, validité |
| `/api/v1/site/contact/` | POST | Message de contact |
| `/api/v1/site/adhesion/` | POST | Demande d'adhésion d'une association avec ses pièces (art. 9) et l'antenne choisie |
| `/api/v1/site/paiement/` | POST | Paiement en ligne des frais d'adhésion (FlexPaie ou équivalent), seulement si activé par un SU |

La vérification publique n'expose jamais : adresses, téléphones, date et lieu de naissance, filiation, numéros de carte d'électeur et de permis, pièces jointes, famille, historique, paiements. Ces informations restent visibles aux utilisateurs connectés, dont la police avec un compte visiteur. Chaque vérification est comptée (sans donnée personnelle du demandeur) pour détecter les abus.

Quand un éditeur publie ou modifie un contenu (F-60 à F-63), l'application web appelle l'adresse de purge du cache du site, protégée par un secret partagé, pour que la modification apparaisse immédiatement sur `fenamordc.cd`. Le jeton QR des cartes et des engins est un code aléatoire distinct de l'identifiant interne.

## 3. Existant

L'application actuelle couvre l'essentiel du besoin métier, mais toutes ses actions rechargent la page et plusieurs failles de sécurité bloquent une mise en ligne en l'état.

### 3.1 Architecture actuelle

| Élément | État constaté |
| --- | --- |
| Framework | Django 5.0.6 (projet généré en 4.1.3), Python 3.12 |
| Projet | Paquet `coptam` (settings, urls, wsgi, asgi) |
| Apps | `compte` (comptes), `coptapp` (métier, `views.py` de 1 198 lignes), `virtrine` (site), `mobapp` (mobile) |
| Base | SQLite (`db.sqlite3`) ; configuration MySQL présente mais commentée |
| Interface | Templates Django, Bootstrap 5, jQuery 3.5.1, template NiceAdmin, Chart.js / ApexCharts / ECharts |
| Formulaires | django-crispy-forms 2.1 |
| Fichiers | Uploads sur disque dans `media/` (photos, logos, pièces d'identité, preuves de paiement) |
| Déploiement prévu | Passenger (`passenger_wsgi.py`) |

### 3.2 Modèle de données

Le modèle `Compte` étend l'utilisateur Django avec cinq booléens `privilege1` à `privilege5`, un champ `editor` et un lien `membreId` vers un membre. Les modèles métier sont `Province`, `Ville`, `Structure`, `Antenne`, `Membre`, `Moto`, `Famille`, `Communique`, `Reaction`, `Notification` et `Error`. Le schéma est détaillé en annexe.

Volume au 12 octobre 2026 : 9 associations membres, 15 membres, 12 motos, 5 provinces, 8 villes, 1 antenne, 5 comptes.

### 3.3 Fonctionnalités existantes

| Domaine | Fonctionnalités |
| --- | --- |
| Comptes | Connexion, déconnexion, ajout d'utilisateur, création d'un compte à partir d'un membre, changement de pseudo et de mot de passe, suppression de son compte |
| Géographie | Ajout de provinces, de villes et d'antennes ; fiches province, ville et antenne |
| Associations membres | Ajout, modification, liste, attribution d'une ville, tableau de bord par association membre |
| Membres | Ajout (deux formulaires), fiche, attribution à une association membre, ville ou antenne, validation, demande de suppression, liste globale |
| Famille | Ajout, modification et suppression des ayants droit d'un membre |
| Motos | Ajout, modification, suppression, attribution à un propriétaire, fiche |
| Communication | Communiqués, réactions, notifications |
| Statistiques | Membres et motos par mois et par association membre |
| Recherche | Recherche par nom ou numéro |
| Contenu du site | Articles et galerie, configuration du site, consultation des messages de contact |

### 3.4 Problèmes constatés

| # | Problème | Conséquence | Gravité |
| --- | --- | --- | --- |
| P1 | Aucune vue n'exige d'être connecté (`@login_required` absent) | Une URL connue suffit pour lire ou modifier des données | Critique |
| P2 | Actions de modification en GET (validation, attributions, suppressions) | Une simple visite de lien modifie les données ; pas de protection CSRF | Critique |
| P3 | Comptes créés avec un mot de passe égal à l'adresse e-mail | Mot de passe devinable | Critique |
| P4 | `SECRET_KEY` et mot de passe MySQL écrits dans `settings.py`, `DEBUG=True`, `ALLOWED_HOSTS=['*']` | Fuite de secrets si le code circule | Critique |
| P5 | Droits codés en cinq booléens sans signification documentée | Droits difficiles à vérifier et à faire évoluer | Élevée |
| P6 | Suppression de son propre compte sans confirmation par mot de passe | Perte de compte accidentelle | Élevée |
| P7 | Numérotation des motos par « dernier numéro + 1 » | Doublons possibles lors de saisies simultanées | Moyenne |
| P8 | Statistiques calculées par 12 requêtes par série et `len()` sur des listes | Pages lentes quand le volume grandit | Moyenne |
| P9 | Erreurs ignorées (`except: pass`) | Pannes silencieuses | Moyenne |
| P10 | Dépôt encombré : `venv/`, `__pycache__`, `stderr.log`, templates de démonstration, images de test dans `media/` | Archive lourde (344 Mo), confusion | Faible |

Le mot de passe MySQL visible dans `settings.py` doit être changé sur le serveur, car il a circulé avec l'archive.

## 4. Acteurs et droits

Les droits suivent la hiérarchie de la charte : national, coordination provinciale, antenne (commune ou territoire), parking. Huit rôles, chacun limité à un périmètre, remplacent les booléens `privilege1` à `privilege5` et `editor` ; ils sont gérés avec les groupes et permissions de Django. Le niveau « ville » de l'application actuelle disparaît.

### 4.1 Rôles

| Rôle | Périmètre | Nommé par | Mission |
| --- | --- | --- | --- |
| Super-utilisateur (SU) | Tout | Comptes réservés au prestataire technique | Tout voir et tout faire ; seul à consulter le journal d'activités ; seul à nommer les éditeurs ; peut verrouiller l'application (F-07) |
| Président (PR) | National | SU | Tout voir ; reçoit toutes les notifications (filtrables) ; peut valider à tous les niveaux et agir sur toutes les données |
| Validateur national (VN) | National | PR, SU | 3e validation des membres et des engins ; 2e validation des associations membres ; gestion des antennes |
| Validateur provincial (VP) | Une coordination provinciale | VN, PR, SU | 2e validation des membres et des engins ; 1re validation des associations membres ; rapport hebdomadaire |
| Validateur d'antenne (VA) | Une antenne | VP et au-dessus | 1re validation des membres et des engins ; enregistrement des associations membres ; codification des parkings ; affectation et déplacement des agents |
| Agent de terrain (AT) | Une antenne, éventuellement un parking | VA et au-dessus | Enregistrement des membres, engins, familles ; rattachement des motards aux engins |
| Visiteur (VI) | Antenne, coordination ou national, fixé à la création | PR, SU | Lecture seule : effectifs et listes nominatives filtrables (ex. ministère des Transports) |
| Éditeur (ED) | Contenu du site, communiqués | SU uniquement | Articles, galerie, configuration du site, messages de contact, communiqués |

Correspondance indicative avec les fonctions de la charte : le VA répond au comité d'antenne (superviseur principal, inspecteurs des parkings chargés de l'identification, art. 69) ; le VP à la coordination provinciale (inspecteurs provinciaux chargés de l'identification et de l'enregistrement des engins, art. 44) ; le VN aux inspecteurs nationaux chargés de l'identification (art. 19 et 42).

### 4.2 Nomination des utilisateurs

- Un utilisateur nomme uniquement des rôles situés **en dessous** du sien, et dans son propre périmètre (un VP nomme des VA et des AT de sa coordination).
- Nommer = choisir un membre, lui attribuer un rôle et un périmètre ; le compte est créé avec un mot de passe temporaire à changer à la première connexion.
- Le membre nommé doit être **actif** (validé au niveau 3). Le président et le SU peuvent valider plusieurs niveaux d'un coup pour le rendre actif.
- Celui qui a nommé un utilisateur reçoit les notifications de ses activités, et peut le désactiver, comme tout rôle au-dessus de lui dans le même périmètre.
- Les visiteurs et les éditeurs ne sont pas forcément membres de la FENAMO : leur compte est créé sans fiche membre. Chaque nomination porte aussi une date de début et une date de fin de mandat (charte, art. 72 à 75 : 3 ans pour les comités d'antenne, 4 ans pour les coordinations provinciales, 5 ans pour le comité national) ; une alerte prévient celui qui a nommé avant l'échéance, et les affectations expirées sont listées.

### 4.3 Matrice des droits

Légende : **G** = gérer (créer, modifier, supprimer), **C** = créer, **V1/V2/V3** = valider à ce niveau, **L** = lire, **–** = aucun accès. Chaque droit s'exerce dans le périmètre du rôle.

| Objet | SU | PR | VN | VP | VA | AT | VI | ED |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Nommer des utilisateurs | Tous | VN, VP, VA, AT, VI | VP, VA, AT | VA, AT | AT | – | – | – |
| Verrouiller l'application | Oui | – | – | – | – | – | – | – |
| Coordinations provinciales | G | G | G | L | L | L | L | – |
| Antennes | G | G | G | L | L | L | L | – |
| Parkings | G | G | G | G | G | L | L | – |
| Associations membres | G, toutes validations | G, toutes validations | V2 (finale), modifier | V1, modifier | C | L | L | – |
| Membres | G, V1 à V3 | G, V1 à V3 | V3, modifier | V2, modifier | V1, modifier | C, modifier avant V1 | L | – |
| Engins, familles | G, V1 à V3 | G, V1 à V3 | V3, modifier | V2, modifier | V1, modifier | C, modifier avant V1 | L | – |
| Rattacher / détacher un motard | Oui | Oui | Oui | Oui | Oui | Oui | – | – |
| Affecter, déplacer un agent | Oui | Oui | Oui | Oui | Oui | Demander | – | – |
| Paiements statutaires | G | G | L, C | L, C | C | – | – | – |
| Effectifs et listes nominatives | L | L | L | L | L | L | L, filtres | – |
| Notifications | Toutes | Toutes, filtrables | Son périmètre + ses nommés | Son périmètre + ses nommés | Son périmètre + ses nommés | Ses dossiers | – | – |
| Communiqués | G | L, réagir | L, réagir | L, réagir | L, réagir | L, réagir | L | G |
| Contenu du site | G | – | – | – | – | – | – | G |
| Journal d'activités | L, filtres | – | – | – | – | – | – | – |

### 4.4 Circuit de validation

Membres et motos suivent le même circuit en quatre étapes, de façon indépendante : une moto avance sans attendre la validation de son propriétaire. Seul un membre ou une moto **actif** compte dans les effectifs officiels.

&#91;embedded content: circuit de validation · membres et motos\]

Règles :

- **États** : saisi → validé antenne → validé province → actif ; plus « renvoyé » (avec motif), « à renouveler » (identification annuelle échue) et « supprimé ».
- **Modification** : l'agent corrige sa saisie tant que la 1re validation n'a pas eu lieu ; ensuite, seuls les rôles supérieurs modifient la fiche.

* **Renvoi** : un validateur qui refuse renvoie le dossier au niveau **juste en dessous** (national → coordination provinciale, coordination → antenne, antenne → agent), avec un motif obligatoire.
* **Correction** : un validateur peut corriger lui-même la fiche puis valider, au lieu de la renvoyer. Toute correction après la saisie est journalisée (avant / après).
* **Validation groupée** : le président et le SU peuvent valider plusieurs niveaux d'un coup ; chaque niveau reste tracé séparément.
* **Associations membres** : enregistrées par un validateur d'antenne, validées par la coordination provinciale puis par le national avant d'être actives.
* **Motards** : rattacher un motard à un engin, l'en détacher ou laisser l'engin sans motard est libre, pour tout membre, sans validation ; l'action est journalisée.
* **Déplacement d'un agent** : l'agent peut demander à changer d'antenne ou de parking ; le validateur d'antenne décide.

Les booléens `is_validate1/2/3` sont remplacés par un champ d'état unique ; chaque changement d'état enregistre l'auteur, la date et le motif.

## 5. Besoins fonctionnels

La refonte reprend toutes les fonctionnalités existantes et les complète sur cinq points : validation avec motif, carte de membre, identification annuelle des engins, parkings, paiements statutaires, journal des actions et export des listes. Chaque fonction porte un identifiant (F-xx) utilisé dans les tests et la recette.

### 5.1 Authentification et comptes

| ID | Fonction | Acteur | Règles de gestion |
| --- | --- | --- | --- |
| F-01 | Se connecter / se déconnecter | Tous | Identifiant + mot de passe ; blocage temporaire après 5 échecs ; session expirée après inactivité (durée à fixer) |
| F-02 | Nommer un membre utilisateur | Selon § 4.2 | Rôle inférieur au sien, dans son périmètre ; membre actif ; dates de mandat ; mot de passe temporaire aléatoire à changer à la première connexion |
| F-03 | Créer un compte visiteur ou éditeur | Visiteur : PR, SU ; éditeur : SU | Périmètre du visiteur fixé à la création ; pas de fiche membre |
| F-04 | Modifier son profil et son mot de passe | Tous | Ancien mot de passe exigé ; règles de complexité Django |
| F-05 | Réinitialiser un mot de passe | Celui qui a nommé, rôles supérieurs | Génère un mot de passe temporaire ; action journalisée |
| F-06 | Désactiver un compte, changer son rôle ou son périmètre | Celui qui a nommé, rôles supérieurs | Désactivation plutôt que suppression ; un utilisateur ne supprime plus son propre compte |
| F-07 | Verrouiller / déverrouiller l'application | SU uniquement | Interrupteur dans l'interface du SU, avec un message d'information saisi par le SU ; une fois verrouillée, toute connexion est refusée sauf celle des SU, les sessions ouvertes sont fermées à la requête suivante, et l'API `/api/v1/` répond « service suspendu » ; les données restent intactes ; verrouillage et déverrouillage journalisés. Les comptes SU sont réservés au prestataire technique : ni le président ni personne d'autre ne peut en créer |

### 5.2 Organisation géographique

| ID | Fonction | Acteur | Règles de gestion |
| --- | --- | --- | --- |
| F-10 | Gérer les coordinations provinciales | VN, PR, SU | Les 27 coordinations de la charte sont préchargées avec leur code officiel (annexe C) ; Kinshasa compte deux coordinations (Kinshasa-Est, Kinshasa-Ouest) ; le code sert au numéro d'engin et ne change plus une fois un engin enregistré |
| F-11 | Gérer les antennes | VN, PR, SU | Une antenne correspond à une commune ou à un territoire (art. 66) et appartient à une coordination ; type commune / territoire ; code unique |
| F-12 | Enregistrer une association membre | VA (et au-dessus) | Pièces exigées par la charte (art. 9) : statuts notariés avec récépissé F92 ou arrêté ministériel d'autorisation ; certificat d'enregistrement ou agrément du ministère des Transports ; adresse du siège ; preuve de paiement des frais d'enregistrement et d'adhésion. Numéro F92 unique ; responsable, logo, contacts |
| F-13 | Valider une association membre | VP puis VN (PR, SU à tout niveau) | Le validateur coche chaque pièce de l'art. 9 ; une pièce manquante bloque la validation ; renvoi au niveau inférieur avec motif ; correction possible par le validateur |
| F-12b | Recevoir une demande d'adhésion venue du site | VA de l'antenne choisie | La demande arrive à l'état « saisi » chez le validateur d'antenne choisi par l'association, qui est notifié ; elle suit ensuite le circuit normal antenne → coordination → national (F-13) ; l'association est informée par e-mail de chaque décision ; paiement en ligne des frais possible si F-65 est activé |
| F-14 | Codifier les parkings | VA (et au-dessus) | Charte art. 7.4 : code unique, antenne, nom, localisation ; un membre peut être rattaché à son parking habituel (champ `code_parking` existant) |
| F-15 | Affecter, déplacer un agent de terrain | VA (et au-dessus) | L'agent est rattaché à une antenne, éventuellement à un parking ; il peut demander un déplacement, le VA décide ; historique conservé |
| F-16 | Tableau de bord par antenne, coordination, national | Selon périmètre | Effectifs actifs, dossiers en attente à chaque niveau, engins par type, identifications à renouveler |
| F-18 | Qualité de l'association membre au sein de la FENAMO | VN, PR, SU | Fondateur, co-fondateur, effectif, sympathisant ou d'honneur (art. 8) |
| F-19 | Suspendre, exclure ou clôturer une association membre | PR, SU | États issus de l'art. 10 : active, suspendue, démissionnaire (préavis de 45 jours), exclue, dissoute ; motif et procès-verbal joints ; journalisé |

### 5.3 Membres

| ID | Fonction | Acteur | Règles de gestion |
| --- | --- | --- | --- |
| F-20 | Enregistrer un membre | AT (et au-dessus) | Un seul formulaire (fusion des deux actuels) ; identifiant `MBR` + 7 chiffres généré automatiquement ; qualité motard et / ou propriétaire ; association membre, antenne et parking ; contrôle de doublon sur nom + date de naissance + téléphone |
| F-21 | Modifier un membre | AT avant V1 ; ensuite VV, VP, VN, PR, SU | Toute modification après la saisie est journalisée (avant / après) |
| F-22 | Joindre les pièces | AT (et au-dessus) | Photo, pièce d'identité, jeton de résidence signé par le chef d'avenue et de quartier (art. 7.2), permis de conduire pour un motard (numéro + scan) ; formats JPG, PNG, PDF ; images redimensionnées côté serveur |
| F-23 | Valider, corriger ou renvoyer un membre | VV (V1), VP (V2), VN (V3), PR et SU (tous niveaux) | Circuit du § 4.4 ; renvoi au niveau juste en dessous avec motif |
| F-24 | Changer un membre d'association membre, d'antenne ou de parking | Validateurs dans leur périmètre | Historique conservé |
| F-25 | Supprimer un membre | Demande : AT ou validateur ; exécution : VN, PR, SU | Suppression logique (le membre est masqué, pas effacé) ; motif obligatoire |
| F-26 | Gérer la famille d'un membre | AT (et au-dessus) | Facultative : saisie si les données sont disponibles ; même circuit de validation que le membre |
| F-27 | Délivrer la carte de membre et le gilet numéroté | VN, PR, SU | Membre actif, identification de l'année valide et cotisation annuelle payée (art. 11) ; carte PDF imprimable avec photo, identifiant, année de validité et QR code de vérification ; numéro de gilet unique |
| F-28 | Lister, filtrer et exporter les membres | Tous sauf ED, selon périmètre | Filtres par coordination, antenne, parking, association membre, état, qualité ; pagination ; export CSV / Excel journalisé ; les visiteurs voient les listes nominatives |
| F-29 | Renouveler l'identification annuelle | AT (et au-dessus) | Charte art. 7.2 : identification chaque année ; à l'échéance le membre passe « à renouveler » sans perdre sa validation ; liste des identifications expirées par périmètre |

### 5.4 Engins (motos et tricycles)

| ID | Fonction | Acteur | Règles de gestion |
| --- | --- | --- | --- |
| F-30 | Enregistrer un engin | AT (et au-dessus) | Type : moto (deux roues) ou tricycle (trois roues), conformément à l'art. 1 ; rattaché à un membre propriétaire ; numéros de moteur et de châssis uniques ; plaque facultative ; marque, couleur, photo |
| F-31 | Numéroter un engin | Système | Numéro = compteur par coordination + code officiel (annexe C), reporté sur l'autocollant vinyle sécurisé (art. 7.2) ; attribué sans risque de doublon (verrou ou séquence en base) |
| F-32 | Valider, corriger ou renvoyer un engin | VV (V1), VP (V2), VN (V3), PR et SU (tous niveaux) | Circuit du § 4.4, indépendant de celui du propriétaire |
| F-33 | Rattacher, détacher un motard | AT (et au-dessus) | Libre, sans validation ; tout membre peut être rattaché ; un engin peut rester sans motard ; historique et journal conservés |
| F-34 | Renouveler l'identification annuelle de l'engin | VV (et au-dessus) | Remplace l'« abonnement » actuel : échéance annuelle ; liste des identifications expirées ou proches de l'échéance ; renouvellement journalisé |
| F-35 | Modifier, supprimer un engin | AT avant V1 ; ensuite rôles supérieurs | Suppression logique ; modification après saisie journalisée |
| F-36 | Liste des motards reconnus | Tous sauf ED, selon périmètre | Motards actifs et engin auquel chacun est rattaché |

### 5.5 Communication

| ID | Fonction | Acteur | Règles de gestion |
| --- | --- | --- | --- |
| F-40 | Publier un communiqué | ED, SU | Ciblage possible par coordination ou antenne |
| F-41 | Réagir à un communiqué | Tous sauf VI | Réaction texte ; ajoutée sans rechargement |
| F-42 | Recevoir des notifications | Selon § 4.3 | Le président reçoit tout ; un validateur reçoit les dossiers à traiter dans son périmètre et l'activité des utilisateurs qu'il a nommés ; un agent reçoit les renvois de ses dossiers |
| F-43 | Filtrer les notifications | Tous | Par type (saisie, validation, renvoi, association membre, nomination…), lieu, période ; compteur rafraîchi périodiquement ; marquage comme lu |

### 5.6 Recherche et statistiques

| ID | Fonction | Acteur | Règles de gestion |
| --- | --- | --- | --- |
| F-50 | Recherche globale | Selon périmètre | Par nom, identifiant MBR, téléphone, numéro d'engin, plaque ou numéro de gilet ; résultats pendant la frappe |
| F-51 | Statistiques et effectifs | Tous sauf ED, selon périmètre | Membres et engins par mois, par coordination, antenne, parking, association membre et type d'engin ; calculées par agrégation en base |
| F-52 | Rapport hebdomadaire des coordinations | VP (et au-dessus) | Charte art. 56 : rapport chaque lundi vers l'exécutif national ; généré automatiquement (nouveaux membres et engins, validations, renvois, identifications expirées) ; export PDF / Excel |

### 5.7 Contenu du site

| ID | Fonction | Acteur | Règles de gestion |
| --- | --- | --- | --- |
| F-60 | Gérer les articles et la galerie | ED, SU | Titre, texte, image principale, galerie, code d'intégration vidéo ; chaque article peut être saisi dans plusieurs langues (français obligatoire, lingala, kiswahili, tshiluba, kikongo facultatifs) |
| F-61 | Configurer le site | ED, SU | Nom, slogan, logo, image de fond, contacts, réseaux sociaux, partenaires |
| F-62 | Traiter les messages de contact | ED, SU | Liste des messages reçus du site, marquage « traité » |
| F-63 | Gérer le comité exécutif publié | ED, SU | Nom, fonction (liste de la charte, art. 19), photo, ordre d'affichage, dates de mandat ; publié sur le site |
| F-64 | Activer les langues du site | SU | Le français est toujours actif ; chaque langue nationale s'active quand ses textes fixes sont traduits |
| F-65 | Activer / désactiver le paiement en ligne | SU uniquement | Interrupteur unique ; désactivé, le site masque le paiement et l'API le refuse ; changement journalisé |
| F-66 | Fixer les montants des frais | PR, SU | Frais d'enregistrement, d'adhésion, de carte, de numérotation et cotisation annuelle, en francs congolais, avec date d'effet (règlement administratif du comité national, art. 9) |

### 5.8 Journal des actions

| ID | Fonction | Acteur | Règles de gestion |
| --- | --- | --- | --- |
| F-70 | Journaliser les actions | Système | Connexion, saisie, modification, validation, renvoi, suppression, nomination, rattachement de motard, export : auteur, date, objet, avant / après |
| F-71 | Consulter et filtrer le journal | SU | Filtres par date, auteur, rôle, lieu, type d'action |

### 5.9 Paiements statutaires

La charte conditionne l'adhésion des associations membres et la carte de membre à des paiements (art. 9, 11 et 79). L'application les enregistre ; elle n'encaisse rien en ligne dans ce chantier. Un paiement en ligne par mobile money (API FlexPaie ou équivalent) est prévu dans un chantier ultérieur ; le modèle de données le prépare dès maintenant (mode de paiement, référence de transaction, statut).

| ID | Fonction | Acteur | Règles de gestion |
| --- | --- | --- | --- |
| F-80 | Enregistrer un paiement | VA (et au-dessus) | Types : frais d'enregistrement et d'adhésion d'une association membre, cotisation annuelle d'un membre, frais de carte, frais de numérotation d'engin ; montant en francs congolais, date, référence, justificatif ; journalisé |
| F-81 | Situation des paiements | VP (et au-dessus), PR, SU | Payé / impayé par année, par association membre et par périmètre ; utilisée par F-13 (association membre) et F-27 (carte) |

## 6. Spécification de l'interface asynchrone

Toutes les actions courantes se font sans recharger la page, grâce à HTMX pour les échanges avec le serveur et à Alpine.js pour les petits comportements locaux. Le serveur reste Django et renvoie du HTML ; aucun build JavaScript n'est nécessaire.

### 6.1 Principe technique

- **HTMX** (fichier unique d'environ 14 Ko) : des attributs HTML (`hx-get`, `hx-post`, `hx-target`, `hx-swap`) envoient la requête et remplacent une zone de la page par le fragment reçu.
- **Une vue, deux rendus** : la même vue Django renvoie la page complète lors d'un accès direct, ou seulement le fragment quand la requête porte l'en-tête `HX-Request` (bibliothèque `django-htmx`).
- **Fragments** : chaque zone rafraîchissable a son propre template partiel, rangé dans `templates/<app>/partials/`, et inclus dans la page complète avec `{% include %}`.
- **Alpine.js** : modales, onglets, champs conditionnels, confirmation avant suppression, aperçu d'une photo avant envoi.
- **Bibliothèques servies en local** dans `static/` (pas de CDN), versions figées.
- **Navigation** : `hx-boost` sur les liens du menu pour éviter le rechargement complet entre les écrans, avec mise à jour de l'URL dans la barre d'adresse.

### 6.2 Interactions à rendre asynchrones

| Priorité | Écran | Interaction | Zone mise à jour |
| --- | --- | --- | --- |
| 1 | File de validation | Valider, corriger ou renvoyer un membre ou une moto (F-23, F-32) | Ligne du dossier, compteurs de dossiers en attente, notifications |
| 1 | Fiche membre | Valider / renvoyer avec motif dans une modale (F-23) | Badge d'état + boutons + historique de validation |
| 1 | Liste des membres | Recherche pendant la frappe, filtres, pagination (F-28) | Tableau des résultats |
| 1 | Fiche membre | Ajouter, modifier, supprimer une moto (F-30, F-35) | Liste des motos du membre |
| 1 | Fiche moto | Rattacher, détacher un motard (F-33) | Bloc « motard » |
| 1 | Fiche membre | Ajouter, modifier, supprimer un membre de la famille (F-26) | Liste de la famille |
| 1 | Partout | Recherche globale (F-50) | Liste déroulante des résultats |
| 2 | Liste des membres | Enregistrer un membre dans une modale (F-20) | Modale (erreurs) puis nouvelle ligne du tableau |
| 2 | Fiche membre | Changer d'association membre, antenne ou parking (F-24) | Bloc de rattachement |
| 2 | Associations membres | Enregistrer, valider ou renvoyer une association membre (F-12, F-13) | Liste des associations membres, badge d'état |
| 2 | En-tête | Notifications : compteur, liste, filtres, marquer comme lu (F-42, F-43) | Icône et panneau des notifications |
| 2 | Utilisateurs | Nommer un membre, désactiver, réinitialiser (F-02 à F-06) | Liste des utilisateurs nommés |
| 2 | Agents | Demande et décision de déplacement (F-15) | Fiche de l'agent, notification |
| 2 | Communiqués | Publier, réagir (F-40, F-41) | Fil des communiqués / réactions |
| 3 | Fiches coordination / antenne | Ajouter une antenne, un parking (F-11, F-14) | Liste concernée |
| 3 | Tableaux de bord | Changer l'année ou le périmètre des statistiques (F-16, F-51) | Graphiques et effectifs |
| 3 | Journal d'activités | Filtres et pagination (F-71) | Tableau du journal |
| 3 | Contenu du site | Articles, galerie, messages traités (F-60 à F-62) | Listes concernées |

### 6.3 Comportements communs

**Tous les formulaires s'ouvrent dans une boîte modale.** Ajout, modification, validation ou renvoi avec motif, nomination, paiement, confirmation de suppression : aucun formulaire n'est affiché sur une page dédiée. HTMX charge le formulaire dans la modale ; en cas d'erreur, la modale reste ouverte avec les erreurs à côté des champs ; en cas de succès, elle se ferme, un message confirme l'action et la zone concernée se met à jour. Sur téléphone, la modale s'affiche en plein écran.

- **Chargement** : tout bouton qui déclenche une requête affiche un indicateur et se désactive jusqu'à la réponse (`hx-indicator`, `hx-disabled-elt`), ce qui empêche le double envoi.
- **Messages** : succès et erreurs s'affichent dans une zone de notification commune (toast), alimentée par les messages Django renvoyés avec le fragment (en-tête `HX-Trigger`).
- **Erreurs de formulaire** : le formulaire est renvoyé avec les erreurs à côté des champs, sans perdre la saisie.
- **Perte de connexion ou erreur serveur** : un message clair (« Connexion perdue, réessayez ») et un bouton pour relancer ; la saisie en cours n'est pas effacée.
- **Session expirée** : le serveur répond par une redirection HTMX (`HX-Redirect`) vers la page de connexion.
- **Confirmation** : toute suppression demande une confirmation dans une modale.

### 6.4 Règles techniques

- Toute modification passe par **POST** (ou DELETE / PUT via HTMX) avec le **jeton CSRF**, ajouté une fois pour toutes dans la balise `<body>` (`hx-headers`).
- Aucune modification en GET.
- Chaque vue, page ou fragment, contrôle la connexion et les droits du § 4.2 ; un fragment n'est jamais moins protégé que la page.
- **Dégradation** : sans JavaScript, les formulaires et liens restent fonctionnels (rechargement complet).
- Les fragments restent légers : pas de ré-envoi de la page entière pour mettre à jour une ligne.
- Les bibliothèques NiceAdmin non utilisées (ECharts, ApexCharts, éditeurs, pages de démonstration) sont retirées ; une seule bibliothèque de graphiques est conservée (Chart.js).

## 7. Environnements et hébergement

Le développement continue sur `localhost:8000` avec SQLite ; la production sera `app.fenamordc.cd` sur cPanel mutualisé avec MySQL. Le même code tourne dans les deux cas, seul le fichier `.env` change.

### 7.1 Environnements

| Élément | Développement (actuel) | Production (cible) |
| --- | --- | --- |
| Adresse | `http://localhost:8000` | `https://app.fenamordc.cd` |
| Serveur | `python manage.py runserver` | Passenger (application Python cPanel) |
| Base de données | SQLite (`db.sqlite3`) | MySQL (utf8mb4) |
| `DEBUG` | `True` | `False` |
| Fichiers statiques | Servis par `runserver` | `collectstatic` + WhiteNoise |
| Fichiers médias | `media/` local | `media/` hors du dossier public du code, servis par Apache |
| E-mails | Affichés dans la console | SMTP de l'hébergeur |
| HTTPS | Non | Oui (AutoSSL), redirection HTTP → HTTPS |

### 7.2 Configuration par fichier `.env`

Les réglages sensibles ou propres à un environnement sortent de `settings.py` et sont lus dans un fichier `.env` (bibliothèque `python-dotenv`, déjà présente, ou `django-environ`). Un fichier `.env.example` sans valeurs réelles est versionné ; le `.env` ne l'est jamais.

| Variable | Exemple en développement |
| --- | --- |
| `SECRET_KEY` | clé de développement |
| `DEBUG` | `True` |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` |
| `CSRF_TRUSTED_ORIGINS` | `http://localhost:8000` |
| `DATABASE_URL` | `sqlite:///db.sqlite3` |
| `MEDIA_ROOT`, `STATIC_ROOT` | chemins locaux |
| `EMAIL_*` | backend console |

Les réglages sont organisés en `fenamo/settings/base.py`, `dev.py` et `prod.py`. `prod.py` active `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` et HSTS.

### 7.3 Plan d'URL

L'application est servie à la racine de son domaine : `localhost:8000/` en développement, `app.fenamordc.cd/` en production. Les préfixes actuels `/app/` et `/auth/` disparaissent.

| Actuel | Cible |
| --- | --- |
| `/app/` (connexion) | `/connexion/` |
| `/app/deconnexion/` | `/deconnexion/` |
| `/auth/` (accueil admin) | `/` (tableau de bord) |
| `/auth/view-of-membre-from-city-by-selection/<id>` | `/membres/<id>/` |
| `/auth/liste-des-membres-de-coptam/` | `/membres/` |
| `/auth/validate-membre-for-any-user/<id>` (GET) | `/membres/<id>/valider/` (POST) |
| `/auth/add-moto-for-membre-selected/<id>` | `/membres/<id>/motos/ajouter/` (POST) |
| `/auth/view-moto-selected-by-meny-to-one/<id>` | `/motos/<id>/` |
| `/auth/province-views-datails/<id>` | `/provinces/<id>/` |
| `/auth/my-structure-admin/<id>` | `/associations/<id>/` |
| `/auth/site-administration/` | `/contenu-site/` |
| — | `/api/v1/` (réservé, § 2.2) |
| `/admin/` | `/gestion-technique/` (admin Django, nom moins exposé) |

La table complète figure en annexe. Les URL suivent des noms en français, courts et prévisibles : `/<objet>/`, `/<objet>/<id>/`, `/<objet>/<id>/<action>/`.

### 7.4 Base de données : de SQLite à MySQL

- Le code n'utilise que l'ORM Django, sans SQL propre à SQLite, pour rester compatible avec MySQL.
- Une base MySQL locale de test est recommandée avant la mise en production pour vérifier les migrations.
- Reprise des données : `dumpdata` depuis SQLite, `migrate` sur MySQL vide, `loaddata`, puis contrôle des effectifs (associations membres, membres, motos) et copie du dossier `media/`.
- La migration a lieu au lot 5 (§ 11), une seule fois, après gel des saisies.

### 7.5 Contraintes de l'hébergement mutualisé

- Version de Python imposée par l'hébergeur : à vérifier ; le projet doit fonctionner sur Python 3.10 ou plus.
- `mysqlclient` doit pouvoir se compiler sur le serveur ; sinon, `PyMySQL` en remplacement.
- Pas de Node, pas de WebSockets, pas de processus permanent (Celery, Redis) : les tâches périodiques (rappels d'abonnement, purge) passent par les tâches cron de cPanel et des commandes `manage.py`.
- Mémoire et CPU limités : requêtes optimisées, pagination systématique, images compressées à l'envoi.
- Redémarrage de l'application par `tmp/restart.txt` après chaque déploiement.

## 8. Contraintes d'usage en RDC

L'application doit rester utilisable sur un téléphone d'entrée de gamme avec une connexion 3G instable, partout dans le pays.

**L'application est entièrement responsive** : chaque écran fonctionne du téléphone (360 px) à l'ordinateur, avec un menu latéral repliable, des tableaux qui deviennent des cartes sur petit écran et des modales en plein écran sur mobile. La recette (§ 11) vérifie chaque écran sur ces deux formats.

| Contrainte | Exigence |
| --- | --- |
| Connexion lente ou coûteuse | Première page de connexion sous 500 Ko ; fragments HTMX de quelques Ko ; listes paginées (25 lignes par défaut) |
| Images lourdes prises au téléphone | Redimensionnement et compression à l'envoi (largeur maximale à fixer, par exemple 1 200 px) ; vignettes pour les listes |
| Coupures réseau | Saisie conservée en cas d'échec ; bouton « Réessayer » ; pas de double enregistrement (boutons désactivés, contrôle de doublon côté serveur) |
| Usage principal sur téléphone | Interface pensée d'abord pour un écran de 360 px de large ; tableaux transformés en cartes sur mobile ; boutons assez grands pour le doigt |
| Navigateurs | Chrome Android et Opera Mini en mode normal, Firefox, Edge ; deux dernières versions majeures |
| Langue | Interface en français ; textes centralisés pour permettre une traduction plus tard |
| Formats locaux | Téléphones au format +243 suivi de 9 chiffres, contrôlés à la saisie ; dates au format JJ/MM/AAAA ; fuseau horaire Africa/Kinshasa par défaut (l'est du pays est à UTC+2, stockage en UTC) |
| Polices et icônes | Servies en local ; pas de dépendance à Google Fonts ni à un CDN |

## 9. Sécurité et protection des données

L'application traite des données personnelles sensibles (identité, filiation, numéro de carte d'électeur, photos, pièces d'identité) : aucune page ni aucun fichier ne doit être accessible sans connexion et sans droit.

### 9.1 Authentification et accès

- Mots de passe hachés par Django ; suppression de toute création de compte avec un mot de passe prévisible.
- `@login_required` (ou un middleware de connexion obligatoire) sur toutes les vues, sauf la page de connexion.
- Contrôle des droits et du périmètre (§ 4.2) dans chaque vue : un responsable qui change l'identifiant dans l'URL ne voit pas les données d'une autre association membre.
- Mode verrouillé (F-07) appliqué par un middleware à chaque requête, y compris sur l'API. Limitation des tentatives de connexion (par exemple `django-axes`).
- Les mots de passe des membres stockés en clair dans `Membre.password` (utilisés par `mobapp`) sont hachés ; la correction côté mobile relève de son propre cahier des charges, mais le hachage est fait dans ce chantier, avec l'adaptation minimale de la vérification dans \`mobapp\` pour que l'application mobile actuelle continue de fonctionner.

### 9.2 Protection des échanges

- CSRF actif sur toutes les requêtes POST, y compris HTMX.
- HTTPS obligatoire en production, cookies `Secure` et `HttpOnly`, HSTS.
- En-têtes de sécurité : `X-Frame-Options`, `Referrer-Policy`, politique de contenu (CSP) compatible avec HTMX et Alpine.js.
- Validation de tous les fichiers envoyés : type réel, extension, taille.

### 9.3 Secrets et configuration

- `SECRET_KEY`, identifiants de base et de messagerie uniquement dans `.env`.
- Nouvelle `SECRET_KEY` et nouveau mot de passe MySQL en production (les actuels ont circulé).
- `DEBUG=False` et `ALLOWED_HOSTS=app.fenamordc.cd` en production.

### 9.4 Données personnelles et fichiers

- Les pièces d'identité, captures de justice et preuves de paiement ne sont pas servies directement par une URL publique `/media/` : elles passent par une vue qui vérifie les droits.
- Les photos de profil peuvent rester publiques si le site les affiche ; à confirmer.
- Suppression logique des membres ; la purge définitive des données d'un membre supprimé se fait après une durée de conservation à fixer par la FENAMO.
- Les exports (CSV, Excel) sont journalisés.

### 9.5 Sauvegardes et journalisation

- Sauvegarde quotidienne de la base et du dossier `media/` (outil de sauvegarde cPanel + copie hors serveur), avec un test de restauration avant la mise en production.
- Journal des actions sensibles (F-70).
- Journal des erreurs applicatives en production, sans données personnelles dans les messages.

## 10. Renommage et réorganisation du code

Seul le paquet de configuration `coptam` devient `fenamo` ; les apps internes gardent leur nom pour ne toucher ni aux migrations ni aux tables existantes.

### 10.1 Renommage du projet

| Fichier ou réglage | Avant | Après |
| --- | --- | --- |
| Dossier de configuration | `coptam/` | `fenamo/` |
| `manage.py`, `wsgi.py`, `asgi.py` | `DJANGO_SETTINGS_MODULE='coptam.settings'` | `'fenamo.settings.dev'` (local) / `'fenamo.settings.prod'` (serveur) |
| `settings` | `ROOT_URLCONF='coptam.urls'`, `WSGI_APPLICATION='coptam.wsgi.application'` | `fenamo.urls`, `fenamo.wsgi.application` |
| `passenger_wsgi.py` | `from coptam.wsgi import application` | `from fenamo.wsgi import application` |
| Noms d'URL et chemins | `liste-des-membres-de-coptam`, etc. | Plan d'URL du § 7.3 |
| Textes visibles | « COPTAM » dans les titres, menus, pieds de page | « FENAMO-RDC » (nom officiel de la charte), devise « Unité, Discipline et Progrès » |

**Vocabulaire** : le mot « structure » n'apparaît nulle part dans l'interface ; on dit **« association membre »**. Le modèle `Structure` reçoit ce libellé (`verbose_name`) au lot 1, puis est renommé `AssociationMembre` par une migration de renommage, sans perte de données.

Une recherche de « coptam » (sans tenir compte de la casse) dans le code et les templates ne doit plus rien renvoyer, à l'exception des migrations et du nom de l'app `coptapp`.

### 10.2 Apps conservées

| App | Rôle | Dans ce chantier |
| --- | --- | --- |
| `compte` | Comptes, rôles | Refondue |
| `coptapp` | Métier : géographie, membres, motos, communication | Refondue ; `views.py` découpé par domaine |
| `virtrine` | Modèles du contenu du site ; ses pages publiques partent dans le nouveau projet du site | Seuls les écrans de gestion du contenu sont concernés |
| `mobapp` | Pages de l'application mobile | Seulement le hachage des mots de passe et la compatibilité |
| `api` (nouvelle) | API JSON `/api/v1/` | Créée vide avec authentification et versionnement |

### 10.3 Nettoyage du dépôt

- Retirer du dépôt : `venv/`, tous les `__pycache__`, `stderr.log`, `db.sqlite3`, le contenu de `media/`.
- Supprimer les templates de démonstration NiceAdmin non utilisés (composants, icônes, graphiques d'exemple) et la documentation Chart.js copiée dans `static/`.
- Ajouter un `.gitignore`, un `.env.example` et un `README.md` d'installation locale.
- Figer les dépendances réellement utilisées dans `requirements.txt` (retirer Twisted, uvicorn, autobahn, websockets si inutilisés).
- Mettre le projet sous Git dès le lot 1.

### 10.4 Arborescence cible

```text
fenamo/                      # racine du dépôt
├── fenamo/                  # configuration (ex-coptam)
│   ├── settings/
│   │   ├── base.py
│   │   ├── dev.py
│   │   └── prod.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── compte/
├── coptapp/
│   ├── views/               # un module par domaine
│   │   ├── membres.py
│   │   ├── motos.py
│   │   └── ...
│   ├── services/            # règles métier (numérotation, validation)
│   └── templates/coptapp/
│       ├── membres/
│       │   ├── liste.html
│       │   └── partials/    # fragments HTMX
│       └── ...
├── virtrine/
├── mobapp/
├── api/
├── templates/               # gabarits communs (base, menu, toasts)
├── static/                  # htmx, alpine, bootstrap, chart.js en local
├── manage.py
├── passenger_wsgi.py
├── requirements.txt
├── .env.example
└── README.md
```

## 11. Qualité, livraison et recette

Le chantier est livré en cinq lots successifs ; chaque lot est testé en local et validé par la FENAMO avant le suivant. Seul le lot 5 touche au serveur de production.

### 11.1 Lots

| Lot | Contenu | Critère de fin |
| --- | --- | --- |
| 1 — Socle | Git, nettoyage du dépôt, renommage `coptam` → `fenamo`, réglages `base/dev/prod`, `.env`, nouveau plan d'URL, gabarit de base avec HTMX et Alpine.js en local | Le projet démarre sur `localhost:8000` ; aucune occurrence de « coptam » hors exceptions ; toutes les pages existantes s'affichent |
| 2 — Sécurité et droits | Connexion obligatoire, rôles et périmètres (§ 4), POST + CSRF, hachage des mots de passe membres, fichiers sensibles protégés, journal des actions | Tests de droits verts ; aucune modification possible en GET ; accès refusé hors périmètre |
| 3 — Page pilote | Fiche membre entièrement en HTMX : validation, motos, famille, toasts, gestion des erreurs | Recette de la page pilote par la FENAMO, y compris sur téléphone et connexion lente |
| 4 — Migration des écrans | Interactions de priorité 1, puis 2, puis 3 (§ 6.2) ; nouvelles fonctions (carte de membre, abonnements, export) | Toutes les fonctions F-xx recettées |
| 5 — Mise en production | Base MySQL, reprise des données, déploiement sur `app.fenamordc.cd`, HTTPS, sauvegardes, formation | Recette en production signée ; restauration de sauvegarde testée |

Le calendrier de chaque lot sera fixé avec la FENAMO à la validation de ce document.

### 11.2 Tests

- **Tests automatisés** (Django `TestCase` ou `pytest-django`) : modèles et règles métier (numérotation, validation), droits par rôle et par périmètre, réponses des vues en page complète et en fragment.
- **Tests manuels** sur téléphone Android et sur connexion limitée (mode « 3G lente » du navigateur).
- Les tests tournent sur SQLite en local et une fois sur MySQL avant le lot 5.

### 11.3 Recette

- Un jeu d'essai fictif (coordinations, associations membres, membres, engins) sert à la recette ; aucune donnée réelle n'est utilisée en développement sans accord.
- Pour chaque fonction F-xx : scénario, résultat attendu, résultat obtenu, décision (accepté / à corriger).
- Une anomalie bloquante empêche de passer au lot suivant.

### 11.4 Déploiement et retour arrière

1. Sauvegarde de la base et de `media/` sur le serveur.
2. Envoi du code (Git ou archive), installation des dépendances dans l'environnement Python cPanel.
3. `migrate`, `collectstatic`, redémarrage par `tmp/restart.txt`.
4. Contrôles : connexion, une page de chaque domaine, une action HTMX.
5. En cas d'échec : remise de la version précédente du code et restauration de la sauvegarde.

### 11.5 Documentation

- `README.md` : installation locale et lancement.
- Guide de déploiement cPanel.
- Guide utilisateur court par rôle (agent de terrain, validateurs, président, visiteur, éditeur du site).

## 12. Annexes

### A. Schéma des données

&#91;embedded content: modèle de données cible · 9 objets métier\]

La géographie de la charte (coordination, antenne, parking) et l'association membre encadrent le membre ; motos, famille et communication en dépendent. Le compte utilisateur est séparé du membre et porte les rôles du § 4.

### B. URL actuelles et cibles

Méthode : **G** = GET (lecture), **P** = POST (modification). Les URL `/api/v1/` seront définies avec les cahiers des charges du site et du mobile.

| Actuel | Cible | Méthode |
| --- | --- | --- |
| `/app/` | `/connexion/` | G, P |
| `/app/deconnexion/` | `/deconnexion/` | P |
| `/app/admin-manager/<id>` | `/membres/<id>/creer-compte/` | P |
| `/app/add-user/` | `/comptes/ajouter/` | G, P |
| `/app/delete-user/` | `/comptes/<id>/desactiver/` | P |
| `/auth/` | `/` | G |
| `/auth/session` | `/associations/mon-association/` | G |
| `/auth/my-structure-admin/<id>` | `/associations/<id>/` | G |
| `/auth/add-structure/` | `/associations/ajouter/` | G, P |
| `/auth/edit-structure/<id>` | `/associations/<id>/modifier/` | G, P |
| `/auth/structures-liste/` | `/associations/` | G |
| `/auth/ville-attr/<id>/<sid>` | `/associations/<id>/ville/` | P |
| `/auth/add-province-in-app-served-by-admin/` | `/provinces/ajouter/` | G, P |
| `/auth/province-views-datails/<id>` | `/provinces/<id>/` | G |
| `/auth/add-ville-in-province/<id>` | `/provinces/<id>/villes/ajouter/` | G, P |
| `/auth/ville-view-details/<id>` | `/villes/<id>/` | G |
| `/auth/ville-select/<id>` | `/villes/<id>/selectionner/` | P |
| `/auth/add-antenne-in-ville/<id>` | `/associations/<id>/antennes/ajouter/` | G, P |
| `/auth/edit-antenne/<id>` | `/antennes/<id>/modifier/` | G, P |
| `/auth/antenne-list-of-membre-by-group-antenne/<id>` | `/antennes/<id>/` | G |
| `/auth/liste-des-membres-de-coptam/` | `/membres/` | G |
| `/auth/add-membre-from-fenamo/` | `/membres/ajouter/` | G, P |
| `/auth/add-membre-in-ville-by-antenne-no-selected/<id>` | `/membres/ajouter/?ville=<id>` | G, P |
| `/auth/view-of-membre-from-city-by-selection/<id>` | `/membres/<id>/` | G |
| `/auth/validate-membre-for-any-user/<id>` | `/membres/<id>/valider/` et `/membres/<id>/renvoyer/` | P |
| `/auth/sked-to-delete-membre-from-user/<id>` | `/membres/<id>/supprimer/` | P |
| `/auth/structure-attribution/<id>/<idM>` | `/membres/<id>/rattachement/` | P |
| `/auth/ville-attribution/<id>/<idM>/` | `/membres/<id>/rattachement/` | P |
| `/auth/antenne-attribution/<id>/<idM>` | `/membres/<id>/rattachement/` | P |
| `/auth/view-user-from-membre-by-id/<id>` | `/membres/<id>/compte/` | G |
| `/auth/security-of-user-updated/<id>` | `/mon-compte/securite/` | G, P |
| `/auth/add-member-of-family/<id>` | `/membres/<id>/famille/ajouter/` | P |
| `/auth/edit-family-list/<id>` | `/famille/<id>/modifier/` | G, P |
| `/auth/delete-family-member/<id>` | `/famille/<id>/supprimer/` | P |
| `/auth/add-moto-for-membre-selected/<id>` | `/membres/<id>/motos/ajouter/` | P |
| `/auth/view-moto-selected-by-meny-to-one/<id>` | `/motos/<id>/` | G |
| `/auth/edit-moto-for-membre-selected/<id>` | `/motos/<id>/modifier/` | G, P |
| `/auth/delete-moto-for-membre-selected/<id>` | `/motos/<id>/supprimer/` | P |
| `/auth/moto-attribution-for-membre/<id>` | `/motos/<id>/attribuer/` | P |
| `/auth/results-of-seach-on-table/` | `/recherche/` | G |
| `/auth/view-all-notifications-for-user/` | `/notifications/` | G |
| `/auth/post-communique-for-user/` | `/communiques/ajouter/` | P |
| `/auth/list-of-communiques/` | `/communiques/` | G |
| `/auth/view-of-communique-and-reactions-in-page/<id>` | `/communiques/<id>/` (réaction : P) | G, P |
| `/auth/site-administration/` | `/contenu-site/` | G, P |
| `/auth/article-edit/<id>` | `/contenu-site/articles/<id>/modifier/` | G, P |
| `/auth/delete-article/<id>` | `/contenu-site/articles/<id>/supprimer/` | P |
| `/auth/contact-us-from-site/` | `/contenu-site/messages/` | G |
| `/auth/contact-us-from-site-view/<id>` | `/contenu-site/messages/<id>/` | G, P |
| `/auth/error-404-generator/` | Supprimée (pages d'erreur Django standard) | — |
| — | `/journal/` | G |
| — | `/membres/<id>/carte/` | G |
| — | `/motos/abonnements/` | G |

### C. Codes des coordinations provinciales (charte, art. 43)

Ces codes sont préchargés et servent au numéro d'engin (F-31). Les codes de Lualaba et Mai-Ndombe, illisibles sur la copie scannée, ont été confirmés par la FENAMO.

| N° | Coordination | Code |
| --- | --- | --- |
| 1 | Bas-Uele | BU |
| 2 | Équateur | EQ |
| 3 | Haut-Katanga | HK |
| 4 | Haut-Lomami | HL |
| 5 | Haut-Uele | HU |
| 6 | Ituri | IT |
| 7 | Kasaï | KA |
| 8 | Kasaï Central | KC |
| 9 | Kasaï Oriental | KO |
| 10 | Kinshasa-Est | KN-E |
| 11 | Kinshasa-Ouest | KN-O |
| 12 | Kongo-Central | KOC |
| 13 | Kwango | KW |
| 14 | Kwilu | KL |
| 15 | Lomami | LO |
| 16 | Lualaba | LW |
| 17 | Mai-Ndombe | MD |
| 18 | Maniema | MN |
| 19 | Mongala | MO |
| 20 | Nord-Ubangi | NU |
| 21 | Nord-Kivu | NK |
| 22 | Sankuru | SA |
| 23 | Sud-Kivu | SK |
| 24 | Sud-Ubangi | SU |
| 25 | Tanganyika | TG |
| 26 | Tshopo | TS |
| 27 | Tshuapa | TP |

Kinshasa-Est regroupe les districts de la Tshangu et du Mont-Amba ; Kinshasa-Ouest ceux de la Funa et de la Lukunga (art. 14).
