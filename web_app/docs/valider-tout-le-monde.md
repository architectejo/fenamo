# « Valider tout le monde » (F-23)

Fonction **demandée explicitement par l'utilisateur** : valider d'un coup, à son étape, les dossiers de son périmètre.

## Règles

- Service : `coptapp.services.transitions.valider_tous(auteur, filtres=None, plafond=None)` ; décompte pour la modale de confirmation :
  `compter_validables(auteur, filtres=None)`. Vue : `POST /membres/valider-tous/` (nom d'URL `valider-tous`), CSRF obligatoire, 405 en GET.
- Droit : clé `peut_valider_tous` de `droits_membre` (VA, VP, VN, PR et SU ; en droits hérités, SU et privilege5 seulement, jamais
  privilege2 ni privilege3). 403 sinon.
- Étape : chaque rôle valide ce qui est à SON étape (VA : saisi, VP : validé antenne, VN : validé province ; PR et SU enchaînent
  jusqu'à « actif »). Les filtres de la liste (recherche, état, qualité, antenne, association) restreignent la sélection.
- Jamais ses propres saisies ni sa propre fiche (sauf le SU), jamais hors de son périmètre ; compte rendu des « propres saisies ignorées »
  calculé avec les mêmes filtres.
- **Plafond** : 100 membres par appel (réglage `VALIDER_TOUS_PLAFOND`, variable d'environnement du même nom). Le reste est signalé
  (« N restant(s) : relancez la validation ») ; relancer est sans danger (idempotent : un membre déjà validé à cette étape n'est plus candidat).
- Journal : une ligne VALIDATION par membre et par étape franchie (auteur, date, avant / après de l'état), comme une validation unitaire.
- Compte rendu retourné : `valides`, `etapes`, `restants`, `ignores` (par raison), `plafond`.

## Garde-fous

Le bouton n'apparaît que si `peut_valider_tous` et qu'il y a des dossiers validables (`nb_validables`) ; la modale rappelle le nombre de
dossiers et les filtres actifs. Chaque membre est validé dans sa propre transaction avec verrou : un dossier modifié entre-temps est ignoré
(raison `etat_change`), jamais écrasé.
