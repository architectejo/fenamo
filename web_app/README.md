# FENAMO-RDC : application web de gestion (`web_app/`)

Back-office de la FENAMO-RDC asbl (association membre, membres, engins, coordinations provinciales, antennes, parkings), plus l'API `/api/v1/` qui alimente le site public. Adresse cible : `app.fenamordc.cd`. En local : `http://localhost:8000`.

Référence fonctionnelle : `docs/cahier-des-charges-application-web.md`. Règles de travail : `CLAUDE.md`.

## Prérequis

- Python 3.10 ou plus récent.
- Git.
- Aucune autre installation : SQLite sert en développement, et les bibliothèques front (HTMX, Alpine.js, Bootstrap) sont fournies dans `static/`. Pas de Node.
- `mysqlclient` (MySQL, production) exige un compilateur et les en-têtes MySQL ; sous Windows, il peut échouer à s'installer. Pour le développement, installez les dépendances sans lui (voir ci-dessous).

## Installation locale

Depuis la racine du dépôt :

```bash
cd web_app
python -m venv ../../venv-fenamo          # environnement hors du dépôt (ou un dossier venv/ ignoré par Git)
source ../../venv-fenamo/bin/activate     # Windows : ..\..\venv-fenamo\Scripts\activate
pip install -r requirements-dev.txt       # production : requirements.txt seul
```

Si `mysqlclient` ne s'installe pas en local, installez les autres dépendances à partir d'une copie du fichier dont vous avez retiré la ligne `mysqlclient` (il ne sert qu'avec MySQL).

### Configuration

```bash
cp .env.example .env
```

En développement, `.env` peut rester tel quel : `SECRET_KEY` vide utilise une valeur de développement, `DEBUG=True`, base SQLite `db.sqlite3`. Ne jamais commiter `.env`. Les variables sont décrites dans `.env.example` (production : `SECRET_KEY` de 50 caractères au moins, `ALLOWED_HOSTS`, `DATABASE_URL`, `STATIC_ROOT`, `MEDIA_ROOT`, `EMAIL_*`).

### Base de données et premier compte

```bash
python manage.py migrate
python manage.py createsuperuser          # compte SU de développement
python manage.py runserver 8000
```

Ouvrir `http://localhost:8000/` : la racine est le tableau de bord, qui renvoie vers `/connexion/` si vous n'êtes pas connecté. Administration technique : `/gestion-technique/`.

Ne jamais utiliser de données réelles de membres en développement : créez des données fictives.

## Tests et contrôles

```bash
pytest                                    # tous les tests
pytest -k F23                             # tests d'une fonction
python manage.py check
python manage.py makemigrations --check   # aucune migration manquante
python manage.py check --deploy --settings=fenamo.settings.prod   # nécessite les variables de production
```

Les tests créent leur propre base de test ; ils durent quelques minutes, car certains lancent `manage.py` dans un sous-processus.

## Réglages par environnement

| Fichier | Usage |
|---|---|
| `fenamo/settings/base.py` | commun, lit `.env` |
| `fenamo/settings/dev.py` | développement (défaut de `manage.py` et `pytest.ini`) |
| `fenamo/settings/prod.py` | production cPanel, HTTPS, MySQL ; `SECRET_KEY`, `ALLOWED_HOSTS` obligatoires |

En production : `DJANGO_SETTINGS_MODULE=fenamo.settings.prod` ; les tâches périodiques passent par des commandes `manage.py` lancées par cron (ni Celery, ni Redis). Le guide de déploiement cPanel sera fourni à part (§ 11.5).

## Où se trouve quoi

- `compte/` : comptes, rôles, périmètres. `coptapp/` : métier. `virtrine/` : contenu du site. `mobapp/` : application mobile actuelle (compatibilité). `api/` : `/api/v1/`.
- `templates/` : gabarit commun (base, menu, modale, toasts). `static/` : bibliothèques front locales.
- Plan d'URL : `coptapp/urls.py`, `compte/urls.py`, `fenamo/urls.py` (cahier des charges § 7.3 et annexe B).

## Limites connues (lot 1)

Plusieurs adresses modifient encore des données en GET (valider, supprimer, rattacher…), et les droits par rôle ne sont pas appliqués : ces points sont traités au lot 2 (repérés par `TODO lot 2` dans `coptapp/urls.py`). Ne pas exposer cette version.
