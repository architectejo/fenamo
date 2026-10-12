# Application web FENAMO-RDC (`web_app/`)

Back-office de gestion servi sur `app.fenamordc.cd` (dev : `localhost:8000`). Référence : `docs/cahier-des-charges-application-web.md`. Fonctions numérotées **F-xx**.

## Structure cible

```text
web_app/
├── fenamo/                 # configuration (ex-« coptam »)
│   ├── settings/ base.py · dev.py · prod.py
│   ├── urls.py · wsgi.py · asgi.py
├── compte/                 # comptes, rôles, périmètres, nominations, verrouillage
├── coptapp/                # métier : géographie, associations membres, membres, engins, paiements
│   ├── views/              # un module par domaine
│   ├── services/           # règles métier (numérotation, circuit de validation…)
│   └── templates/coptapp/<domaine>/partials/   # fragments HTMX
├── virtrine/               # modèles du contenu du site (plus de pages publiques)
├── mobapp/                 # app mobile actuelle : compatibilité seulement
├── api/                    # /api/v1/ (site public, puis mobile)
├── templates/              # base, menu, modale commune, toasts
├── static/                 # htmx, alpine, bootstrap, chart.js en local
├── tests/
├── docs/
├── manage.py · passenger_wsgi.py · requirements.txt · .env.example
```

Les noms d'apps `compte`, `coptapp`, `virtrine`, `mobapp` sont conservés pour ne pas casser les migrations. Le modèle `Structure` est affiché « Association membre » (`verbose_name`) puis renommé `AssociationMembre` par une migration `RenameModel`.

## Règles métier à ne jamais oublier

- **Hiérarchie** (charte) : national → coordination provinciale (27, codes de l'annexe C) → antenne (commune ou territoire) → parking. Pas de niveau « ville ».
- **Rôles** : SU, PR (président), VN, VP, VA (validateur d'antenne), AT (agent de terrain), VI (visiteur, lecture seule), ED (éditeur). Matrice complète au § 4.3. Un utilisateur nomme seulement des rôles inférieurs, dans son périmètre ; le membre nommé doit être actif.
- **Circuit de validation** (membres, engins, associations membres) : saisi → validé antenne → validé province → actif. Un refus renvoie au niveau juste en dessous, avec motif. PR et SU peuvent valider plusieurs niveaux d'un coup. Chaque étape est journalisée.
- **Engins** : moto ou tricycle ; numéro = compteur par coordination + code officiel, attribué sans doublon possible (verrou ou séquence).
- **Identification annuelle** des membres et des engins ; carte de membre seulement si actif + identification valide + cotisation payée.
- **Verrouillage (F-07)** : interrupteur réservé aux SU ; middleware vérifié à chaque requête, API comprise. Seuls les SU se connectent quand l'application est verrouillée.
- **Paiement en ligne (F-65)** : désactivé par défaut, activable par un SU.

## Interface (HTMX + Alpine.js)

- **Tout formulaire s'ouvre dans une modale** chargée par HTMX (plein écran sur mobile). Erreurs : la modale reste ouverte. Succès : elle se ferme, un toast confirme, la zone concernée se rafraîchit.
- Une vue sert la page complète ou le fragment selon `request.htmx` (`django-htmx`).
- Fragments dans `templates/<app>/<domaine>/partials/_<nom>.html`.
- Jeton CSRF posé une fois via `hx-headers` sur `<body>`. Boutons désactivés pendant la requête (`hx-disabled-elt`).
- Messages Django renvoyés par l'en-tête `HX-Trigger` vers la zone de toasts commune. Session expirée : `HX-Redirect` vers `/connexion/`.
- Responsive obligatoire : tableaux transformés en cartes sous 576 px.

## API (`api/`)

- Préfixe `/api/v1/`. Points d'accès du site sous `/api/v1/site/` (liste au § 2.4 du cahier des charges), protégés par la clé du site.
- La vérification publique n'expose **jamais** : adresse, téléphone, e-mail, naissance, filiation, n° d'électeur, n° de permis, pièces jointes, famille, paiements.
- Jeton QR = code aléatoire distinct de l'identifiant interne.
- Une publication de contenu (F-60 à F-63) appelle la purge du cache du site.

## Migrations et compatibilité

- Migrations additives tant que `mobapp` lit la base ; ne supprimer ni renommer un champ utilisé par `mobapp` sans plan de compatibilité.
- Les 8 villes existantes deviennent des antennes ; `mobapp` garde une correspondance ville → antenne.
- Mots de passe des membres (`Membre.password`) hachés ; la vérification de `mobapp` est adaptée en conséquence.

## Ordre des lots

1. Socle : Git, nettoyage, renommage `coptam` → `fenamo`, réglages par environnement, `.env`, nouveau plan d'URL, gabarit HTMX.
2. Sécurité et droits.
3. Page pilote : fiche membre entièrement en HTMX.
4. Migration des écrans (priorités du § 6.2) et nouvelles fonctions.
5. MySQL, reprise des données, mise en production.

## Commandes

```bash
python manage.py runserver 8000
python manage.py makemigrations && python manage.py migrate
pytest                       # tous les tests
pytest -k F23                # tests d'une fonction
python manage.py check --deploy --settings=fenamo.settings.prod
```
