# Écarts entre les maquettes et l'intégration : communiqués, données réelles, messages reçus

Comparaison du 15/10/2026 entre les maquettes de `docs/design/maquettes/` et ce qui est intégré :

- communiqués (F-40) : `coptapp/templates/app/list-message.html`, `app/message-view.html`, `coptapp/communiques/partials/_liste.html`, `_modale_publier.html`, `_compteur.html`, `templates/partials/_haut.html`, captures `docs/captures/communiques-*.png` ;
- données réelles (F-67, DR-01) : `virtrine/partials/_donnees_reelles.html`, `_modale_donnees_reelles.html`, `app/site.html` ;
- messages reçus (F-62) : `app/contact.html`, `app/contact-view.html`, vues `contact` et `contactView`.

Maquettes de référence : `communiques.html`, `communique.html`, `donnees-reelles.html`, `messages-contact.html`, `message-contact.html` ; règles CSS nouvelles dans `maquettes/communication.css` ; captures `docs/design/captures/{communiques,communique-lecture,donnees-reelles,messages-contact,message-contact}-*.png`.

Priorité : **P1** = défaut de fonctionnement ou d'accessibilité, à corriger d'abord ; **P2** = écart visible avec la maquette ; **P3** = amélioration. Colonne « Qui » : agent qui corrige.

## 1. Défauts à corriger d'abord (P1)

| # | Écart constaté | Correction attendue | Qui |
| --- | --- | --- | --- |
| 1 | **Ciblage élargi sans le dire.** La vue `addCommunique` ne lit pas `cible`. Si l'auteur coche « Une antenne » (ou « Une coordination ») sans choisir dans la liste, `antenne` et `coordination` arrivent vides et le communiqué part **au niveau national**, vers tous les comptes. | La vue (ou le service) lit `cible` ; `cible=antenne` sans antenne, ou `cible=coordination` sans coordination : erreur 422, modale gardée ouverte, message sous le champ : « Choisissez l'antenne qui reçoit le communiqué. » / « Choisissez la coordination qui reçoit le communiqué. ». Ajouter le test. | backend-django, testeur |
| 2 | **Nombre de non-lus non annoncé.** Dans `_haut.html`, le lien mégaphone porte `aria-label="Communiqués"` : ce libellé remplace tout le contenu du lien, donc le texte `.lecteur` « 3 communiqués non lus » du fragment n'est jamais lu. | Retirer `aria-label` du lien ; mettre `<span class="lecteur">Communiqués</span>` avant le fragment du compteur (qui garde son texte `.lecteur`). Résultat lu : « Communiqués, 3 communiqués non lus ». À 0 : « Communiqués » seul. | frontend-htmx |
| 3 | **Compteur et liste en désaccord.** `nombre_non_lus` ignore les communiqués publiés avant la création du compte (`date_joined`), mais `lister_communiques` les marque `lu = False` et le filtre « Non lus » les montre. Capture `communiques-liste-1280.png` : « 0 communiqués non lus » au-dessus d'une ligne « Non lu ». | Une seule règle dans le service : un communiqué antérieur au compte est considéré comme lu partout (liste, filtre, compteur), ou nulle part. | backend-django |
| 4 | **Animation d'apparition sur chaque ligne** (`app.css`, `.file--communiques .dossier { animation: page-entree … }` et délais en cascade). Interdit par le système de design ; rejoue à chaque rafraîchissement HTMX (toutes les 2 min). | Supprimer ces deux règles. | frontend-htmx |
| 5 | **« Rechercher » coupé à 360 px** dans la barre haute depuis l'ajout du mégaphone (capture `communiques-liste-360.png` : « Recherche »). | Reporter la règle `@media (max-width: 399.98px)` de `communication.css` (espacement `0` entre les icônes, `padding-right: var(--e-2)` dans le champ). | frontend-htmx |
| 6 | **« Reçu le » faux après traitement.** Les deux écrans de contact affichent `mise_a_jour` (`auto_now`) : marquer un message « traité » change sa date de réception. | **En cours** (modifications non commitées au 15/10, migration `virtrine/0023`) : champ `cree_le` ajouté et repris dans les deux gabarits. Reste : l'afficher avec l'heure (« 15/10/2026 à 09 h 12 », « Aujourd'hui, 09:12 » dans la liste). | backend-django, frontend-htmx |
| 7 | **Traitement non tracé.** Marquer un message « traité » n'enregistre ni qui ni quand, et n'est pas journalisé. | **En cours** (mêmes modifications non commitées) : champs `traite_le`, `traite_par` ajoutés. Reste : les remplir au POST, journaliser (F-70) et afficher « Traité le 15/10/2026 à 10 h 24 par Aimé Tshibangu » (`.traite-par`). | backend-django, frontend-htmx |

## 2. Communiqués : barre haute et menu

| # | Écart | Attendu (maquette `communiques.html`) | Prio. |
| --- | --- | --- | --- |
| 8 | Le lien « Communiqués » du menu n'a pas de nombre. | `.nombre` avec les non-lus, comme « File de validation », rafraîchi par le même événement `communiquesMaj`. | P3 |
| 9 | Groupe du menu. | Groupe « Communication » : Communiqués, Notifications. Groupe « Site public » : Contenu du site, Messages reçus (avec le nombre à traiter). | P3 |

## 3. Communiqués : liste (`list-message.html`, `_liste.html`)

| # | Écart | Attendu | Prio. |
| --- | --- | --- | --- |
| 10 | Filtres coordination et antenne absents de l'écran : la vue fournit `choix`, mais le gabarit n'a que deux champs cachés. | Bouton « Filtres » (avec le nombre de filtres actifs) qui déplie `.filtres-plus` sous 768 px ; deux listes : « Coordination » (27, ordre officiel) et « Antenne » (une seule liste, `<optgroup>` par coordination). Montrées seulement si l'utilisateur voit plusieurs coordinations (SU, PR, VN, ED). | P2 |
| 11 | Pas de résumé des filtres ni de position. | `.resume-liste` : « Coordination : toutes · Antenne : toutes » et « 1 à 20 sur 46 ». | P2 |
| 12 | Puces sans nombres. | « Tous 46 », « Non lus 3 » (`.nombre`). | P3 |
| 13 | Ligne bâtie sur `.dossier` avec avatar mégaphone répété et trois métadonnées à icône (date, lieu, auteur). | `.communique-ligne` (voir `communication.css`) : en tête l'étiquette de portée `.portee` et la date à droite ; titre ; aperçu sur deux lignes ; toute la carte cliquable (lien étiré). Pas d'avatar, pas d'auteur dans la liste. | P2 |
| 14 | Lieu écrit « Antenne Antenne A », « Coordination Province fictive ». | `.portee` : « National » (bande du drapeau, `.portee--national`), « Coordination Kinshasa-Est » + code en `.portee-code` (`province.code`), « Antenne de Lemba ». Tag ou inclusion `components/_portee.html` (paramètres : coordination, antenne). | P2 |
| 15 | Lu et non lu se ressemblent (tous sur surface blanche). | Non lu : `.non-lu` (surface, bande jaune, titre gras, pastille « Non lu »). Lu : fond transparent, titre en graisse normale. | P2 |
| 16 | Date « 15/10/2026 · 18:15 » pour tout. | « Aujourd'hui, 09:30 », « Hier, 16:40 », puis « 12/10/2026 » ; dans `<time datetime>`. | P3 |
| 17 | Contexte « 0 communiqués non lus ». | « 3 non lus · vous recevez ceux de toute la fédération » (périmètre réel) ; à 0 : « Tout est lu ». | P3 |
| 18 | Deux états vides, sans action. | Trois cas : aucun communiqué (« Aucun communiqué pour l'instant » + « Publier un communiqué » si autorisé) ; aucun résultat (« Aucun communiqué ne correspond », rappel de la recherche, « Effacer les filtres ») ; filtre « Non lus » vide (« Tout est lu », icône `check-check`, « Voir tous les communiqués »). | P3 |
| 19 | Bouton « Publier un communiqué » non pleine largeur à 360 px. | `bouton--bloc-mobile`. | P3 |

## 4. Communiqués : lecture (`message-view.html`)

| # | Écart | Attendu (maquette `communique.html`) | Prio. |
| --- | --- | --- | --- |
| 20 | Panneau `panneau--etroit` (520 px) : lignes courtes à 1 280 px. | `.panneau.lecture` (mesure de 66 caractères), texte `.lecture-texte` (interligne 1,6 ; 18 px dès 768 px ; `white-space: pre-line`, garder `linebreaksbr` ou le texte brut). | P2 |
| 21 | Pas de portée ; métadonnées à icônes ; auteur affiché par son identifiant (« admin-test »). | En tête : `.portee`, titre, « Publié le 15/10/2026 à 07 h 15 » (espaces insécables). En pied : `.lecture-signature` (initiales, nom complet, rôle ; jamais l'identifiant de connexion). | P2 |
| 22 | Titre de repli « Communiqué » quand il n'y a pas de titre. | Le titre est obligatoire à la publication ; pour les anciens communiqués sans titre, reprendre les 80 premiers caractères du message. | P3 |
| 23 | Aucune suite de lecture. | Pied `.lecture-pied` : « Tous les communiqués » et, s'il en reste, « Lire le suivant non lu » (`bouton--principal`), tous deux `bouton--bloc-mobile`. Requête du service : le plus récent non lu visible. | P3 |

## 5. Communiqués : modale de publication (`_modale_publier.html`)

| # | Écart | Attendu (maquette `communiques.html?modale=modale-publier`) | Prio. |
| --- | --- | --- | --- |
| 24 | Ordre titre, message, destinataires. | Ordre d'une enveloppe : **Destinataires**, puis la liste de coordination ou d'antenne, puis le résumé, puis Titre, puis Message. | P2 |
| 25 | Ciblage en `.puce`. | `.choix.choix--cibles` (une colonne), comme le périmètre du compte externe : « National · Toute la fédération », « Une coordination · Ses antennes comprises », « Une antenne · Son équipe seulement », avec `.coche`. | P2 |
| 26 | Antenne en deux listes (coordination de l'antenne, puis antenne). | Une seule liste « Antenne », `<optgroup label="Kinshasa-Est">` par coordination. Moins de gestes au pouce ; le filtre Alpine devient inutile. Libellé de l'autre liste : « Coordination provinciale ». | P2 |
| 27 | Aucun retour sur qui reçoit. | Bloc `.destinataires` (`aria-live="polite"`) : `.portee` du choix courant + phrase tirée de `destinataires_ids` (national : « Reçu par tous les comptes actifs… » ; coordination ; antenne ; voir les trois textes de `maquettes-communication.js`). Le nombre de comptes est un plus (P3). | P2 |
| 28 | Pas de compteur sur le titre. | Compteur `0 / 120` (même composant que le message). | P3 |
| 29 | Erreur seulement globale. | Erreur sous chaque champ (`.champ-erreur`, `aria-invalid`) + alerte en tête « Le communiqué n'est pas publié. Corrigez les N champs signalés. » ; focus sur le premier champ en erreur. Textes : « Écrivez un titre : c'est lui qui s'affiche dans la notification. », « Écrivez le message du communiqué. », plus ceux du point 1. | P2 |
| 30 | Pas d'aide d'écriture. | Sous le message : « Dites quoi, où, quand, et ce que chacun doit faire. Les retours à la ligne sont conservés. » ; sous-titre de la modale : « Il arrive dans les notifications des destinataires ». | P3 |
| 31 | Icône `send` dans le bouton du pied. | Pas d'icône dans les boutons de pied de modale (règle du § 9) : « Annuler », « Publier ». | P3 |
| 32 | Bulle « Communiqué publié. » seule. | « Communiqué publié » + détail « Envoyé à la coordination Kinshasa-Est. » (ou « à toute la fédération », « à l'antenne de Lemba »). | P3 |
| 33 | Focus initial sur la première tuile même si une autre est cochée. | Dans un groupe radio, focus sur l'option cochée (`design.js`, `ouvrirModale`). | P3 |

## 6. Données réelles du site (`_donnees_reelles.html`, `_modale_donnees_reelles.html`)

| # | Écart | Attendu (maquette `donnees-reelles.html`) | Prio. |
| --- | --- | --- | --- |
| 34 | Commentaires des deux gabarits : « F-60 ». | « F-67 (DR-01) ». | P3 |
| 35 | Mot d'état « Activées » / « Désactivées » sous le titre « Données réelles du site ». | Intertitre « Données du site public » ; mot d'état lisible seul : « Données d'exemple » (sceau `circle-dashed`, pas `file-text`) ou « Données réelles » (`.verrou--ferme`, sceau `globe`). | P2 |
| 36 | Conséquences en un paragraphe. | `.verrou-effets` à quatre lignes : Articles et galerie, Comité exécutif, Chiffres de l'accueil, Vérification des cartes. Exemple : `etat--saisi` « Exemple » (`circle-dashed`) et `etat--a_renouveler` « Suspendue » (`unplug`) pour la vérification. Réelles : `etat--actif` « Réels », « Réel », « En service ». En état réel, phrase : « **Visibles par tout le monde** sur fenamordc.cd. » | P2 |
| 37 | Pas d'historique. | `.grille--principale` : carte d'état à gauche, « Changements récents » à droite (`.historique`, 5 dernières bascules lues dans le journal F-70 : état, auteur, date, motif ou « Sans motif ») + « Voir le journal d'activités ». Le service `etat_donnees_reelles` donne déjà la dernière ; l'étendre à une liste. | P2 |
| 38 | Auteur affiché par `get_username()` si le compte n'a pas de nom complet. | Passer par `identifiant_affiche` comme ailleurs (identifiant initial masqué). | P2 |
| 39 | Modale d'activation : conséquences incomplètes. | Ajouter « le bandeau « Données d'exemple » disparaît ; » et « le changement est visible tout de suite et inscrit au journal d'activités. » ; phrase finale : « Activez seulement quand le contenu publié a été relu. » ; sous-titre « Site public fenamordc.cd ». | P3 |
| 40 | Modale « Revenir aux données d'exemple » : simple paragraphe. | `.alerte--alerte` titrée « La vérification des cartes sera suspendue. » + « Le site affichera de nouveau le jeu d'exemple fixe… Aucune donnée de l'application n'est modifiée. » | P3 |
| 41 | Bulles « Le site affiche maintenant… » sans titre court. | Message « Données réelles activées » / « Données d'exemple rétablies », la phrase actuelle en détail. | P3 |
| 42 | `Motif :` et heures sans espaces insécables. | `Motif&nbsp;:`, `10&nbsp;h&nbsp;05` (déjà fait pour l'heure). | P3 |

## 7. Messages reçus du site (`contact.html`, `contact-view.html`)

| # | Écart | Attendu (maquettes `messages-contact.html`, `message-contact.html`) | Prio. |
| --- | --- | --- | --- |
| 43 | Liste complète sans pagination, ni recherche, ni filtre. | Pagination de 25 (`_pagination.html`) ; recherche « Nom, téléphone, e-mail ou objet » pendant la frappe ; puces « À traiter » (par défaut), « Traités », « Tous » avec nombres ; `.resume-liste`. Vue migrée sur le modèle de `listMessage` (service + fragment `_liste.html`). | P2 |
| 44 | Colonnes Nom, Raison, Reçu le, État. | **Objet** (lien `lien-ligne`, gras si à traiter, + `.apercu-ligne` du message), **Expéditeur** (nom + téléphone · e-mail, enveloppés dans `.valeur` pour couper les longues adresses), **Reçu le** (`<time>`, sans retour à la ligne), **État** en `data-role="etat"` (en haut à droite de la carte sous 576 px). « Raison » devient « Objet » (vocabulaire du formulaire S-07). | P2 |
| 45 | Détail titré par le nom de l'expéditeur. | Titre = objet ; contexte « Reçu le 15/10/2026 à 09 h 12 » ; état à droite. | P2 |
| 46 | Message en paragraphe simple ; coordonnées en `.definitions`. | Message en `.message-su` + `.texte-saisi` (texte venu de l'extérieur) ; mention « Répondez par téléphone ou par e-mail : l'application n'envoie pas de réponse. » ; panneau « Expéditeur » avec boutons `tel:` « Appeler » et `mailto:` « Écrire un e-mail » (`.coordonnees`), ou « Pas d'adresse e-mail donnée. ». | P2 |
| 47 | « Marquer comme traité » en tête de page, rechargement complet, aucune bulle. | Bouton `bouton--valider bouton--bloc-mobile` dans le pied du panneau « Expéditeur » (on répond, puis on marque) ; POST HTMX, fragment du panneau, bulle « Message marqué comme traité » + « Il reste 4 messages à traiter. » ; ensuite `.traite-par` (voir point 7). | P2 |
| 48 | Pas de passage au message suivant. | Pied : « Messages reçus » et « Message suivant à traiter ». | P3 |
| 49 | Pas d'accès depuis le menu. | Lien « Messages reçus » (groupe « Site public ») avec le nombre à traiter ; bouton « Messages reçus » + nombre sur l'écran Contenu du site. | P3 |

## 8. CSS à reporter dans `app.css`

Copier `maquettes/communication.css` dans une section « 13 bis. Communication et site public » : `.portee*`, `.communiques`, `.communique-ligne` et ses parties, `.communique-nouveau` (remplace la règle actuelle), `.lecture*`, `.destinataires`, `.choix--cibles`, `.ligne--a-traiter`, `.ligne--traitee`, `.liste td time`, `.liste td > .valeur`, `.apercu-ligne`, `.coordonnees`, `.traite-par`, et la règle de la barre haute sous 400 px. Supprimer en même temps `.dossier.communique.non-lu`, `.communique-icone`, `.file--communiques .dossier` (animation) et `.communique-cibles`. Ne pas utiliser `.a-traiter` pour les lignes : la classe est prise par le bandeau du tableau de bord.

Les gabarits n'ont pas été modifiés par le design ; `maquettes-communication.js` ne s'intègre pas (simulation des réponses du serveur).
