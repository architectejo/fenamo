# FENAMO-RDC — Instructions communes

Ce dossier contient la refonte des outils numériques de la **FENAMO-RDC asbl** (Fédération Nationale des Associations des Motocyclistes Taximen de la RDC). Deux projets Django distincts :

| Dossier | Produit | Adresse cible | Dev local |
|---|---|---|---|
| `web_app/` | Application web de gestion (back-office + API `/api/v1/`) | `app.fenamordc.cd` | `localhost:8000` |
| `website/` | Site public, qui ne passe **que** par l'API | `fenamordc.cd` | `localhost:8001` |
| `fenamo.zip` | Ancien projet « coptam » | — | **lecture seule** |

## Sources de vérité

1. Les cahiers des charges, en Markdown :
   - `web_app/docs/cahier-des-charges-application-web.md` (fonctions **F-xx**)
   - `website/docs/cahier-des-charges-site-web.md` (fonctions **S-xx**)
2. La charte (statuts) de la FENAMO-RDC, citée dans les cahiers des charges par numéro d'article.

Avant de coder une fonction, lis la section du cahier des charges qui la décrit. Si une demande contredit un cahier des charges ou la charte, **arrête-toi et demande à l'utilisateur** ; ne tranche jamais seul.

## Langue et vocabulaire

- Réponds toujours en **français**. Textes de l'interface, messages, commits et documentation en français.
- Noms métier dans le code en français, sans accents : `Membre`, `Engin`, `AssociationMembre`, `Coordination`, `Antenne`, `Parking`, `Cotisation`.
- Vocabulaire imposé par la charte :
  - **« association membre »**, jamais « structure » (ni dans l'interface, ni dans le nouveau code) ;
  - **« engin »** (moto à deux roues ou tricycle), pas seulement « moto » ;
  - **« coordination provinciale »**, **« antenne »** (commune ou territoire), **« parking »** ; le niveau « ville » n'existe plus.
- Nom officiel affiché : **FENAMO-RDC**. Devise : « Unité, Discipline et Progrès ». Aucune mention « COPTAM » dans l'interface.

## Pile technique et contraintes

- Python 3.10+ et Django ; HTMX + Alpine.js pour l'asynchrone ; Bootstrap 5 limité aux composants utilisés.
- Toutes les bibliothèques front (HTMX, Alpine, Bootstrap, Chart.js, polices) sont servies **en local** : aucun CDN.
- Hébergement final : **cPanel mutualisé** (Passenger). Donc : pas de Node en production, pas de WebSockets, pas de Redis, pas de Celery. Les tâches périodiques passent par des commandes `manage.py` lancées par cron.
- Base : SQLite en développement, MySQL en production. N'utiliser que l'ORM Django (aucun SQL propre à un moteur).
- Usage en RDC : téléphone d'abord (écran 360 px), connexion 3G lente. Pages légères, images compressées, pagination systématique.

## Règles de code

- Toute modification de données passe par **POST** (ou PUT/DELETE via HTMX) avec **CSRF**. Jamais de modification en GET.
- Chaque vue contrôle la connexion **et** le rôle **et** le périmètre (voir le cahier des charges de l'application web, § 4).
- Secrets uniquement dans `.env` (jamais dans le code ni dans un commit). Tenir `.env.example` à jour.
- Pas d'`except: pass` : une erreur est journalisée ou remontée.
- Une fonction métier = un service testable (`services/`), appelé par les vues ; les vues restent minces.
- Chaque fonction F-xx ou S-xx livrée a ses tests.

## Organisation du dépôt

- Un seul dépôt Git à la racine `fenamo/`. Ne jamais pousser (`git push`) sans accord de l'utilisateur.
- Messages de commit en français, préfixés : `feat(web_app):`, `fix(website):`, `test:`, `docs:`, `chore:`… et citant la fonction (`F-23`, `S-03`) quand il y en a une.
- `fenamo.zip` ne se modifie jamais. Pour le consulter, l'extraire dans un dossier temporaire hors du dépôt.

## Équipe d'agents (`.claude/agents/`)

| Agent | Rôle | Écrit du code ? |
|---|---|---|
| `architecte` | Découpe un lot en tâches, fixe le contrat de l'API | Non |
| `backend-django` | Modèles, migrations, services, droits (`web_app/`) | Oui |
| `frontend-htmx` | Templates, fragments, modales, responsive (les deux projets) | Oui |
| `api` | API `/api/v1/` et son contrat avec le site | Oui |
| `site-web` | Projet `website/` | Oui |
| `migration-donnees` | Reprise des données de l'ancien projet, SQLite → MySQL | Oui |
| `testeur` | Tests pytest-django, critères de fin de lot | Oui (tests) |
| `securite` | Audit droits, CSRF, exposition de données, secrets | Non |
| `relecteur` | Relecture indépendante de chaque modification | Non |
| `deploiement-cpanel` | Réglages de production, guides de déploiement | Oui (config, docs) |

Enchaînement d'un lot : `architecte` → agents de réalisation → `testeur` → `securite` et `relecteur` (en parallèle) → `deploiement-cpanel` pour les lots de mise en production. Un agent qui a écrit du code ne valide jamais son propre travail.

## Commandes utiles

```bash
# Application web
cd web_app && python manage.py runserver 8000
cd web_app && pytest

# Site web
cd website && python manage.py runserver 8001
cd website && pytest
```
