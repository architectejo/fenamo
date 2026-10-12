# Site web FENAMO-RDC (`website/`)

Site public servi sur `fenamordc.cd` (dev : `localhost:8001`). Référence : `docs/cahier-des-charges-site-web.md`. Fonctions numérotées **S-xx**.

## Principe fondamental

Ce projet **n'a pas de base de données métier**. Toute donnée vient de l'API de l'application web (`/api/v1/site/`) et tout dépôt (contact, adhésion, paiement) y repart. SQLite ne sert qu'aux sessions, au cache et aux compteurs.

- L'API est appelée **côté serveur**, jamais depuis le navigateur. La clé du site reste dans `.env`.
- Adresse de l'API : `http://localhost:8000/api/v1/site/` en dev, `https://app.fenamordc.cd/api/v1/site/` en production (variable `API_BASE_URL`).
- Délai maximal d'un appel : 5 s ; au-delà, **mode dégradé (S-12)** : dernier contenu en cache, formulaires et vérification « momentanément indisponibles ».
- Durées de cache par point d'accès : § 6.1 du cahier des charges (réglables dans `.env`). Vérification et dépôts : jamais en cache.
- Une adresse de purge sécurisée permet à l'application web de vider le cache après une publication.

## Structure cible

```text
website/
├── site_fenamo/            # configuration (settings base/dev/prod, urls, wsgi)
├── pages/                  # pages de contenu (accueil, à propos, organisation, actualités…)
├── services/
│   └── api_client.py       # unique point d'appel à l'API (timeouts, cache, erreurs)
├── verification/           # S-03, lien QR /v/<jeton>/
├── adhesion/               # S-04 à S-06
├── locale/                 # fichiers .po (fr, ln, sw, lua, kg)
├── templates/ · static/ · tests/ · docs/
├── manage.py · passenger_wsgi.py · requirements.txt · .env.example
```

Aucun appel HTTP à l'API ailleurs que dans `services/api_client.py`.

## Règles

- **Vérification publique (§ 10.2)** : afficher seulement photo, nom, identifiant MBR, qualité, association membre, coordination, antenne, parking, état, validité ; pour un engin : numéro, type, marque, couleur, plaque, propriétaire, motard, état, validité. Tout autre champ reçu est ignoré. Pages `noindex`. Limite de 20 vérifications par heure et par IP, puis captcha.
- **Langues** : français par défaut ; lingala (`ln`), kiswahili (`sw`), tshiluba (`lua`), kikongo (`kg`) via `i18n_patterns` et fichiers `.po`. Tout texte affiché passe par `{% translate %}` / `gettext`. Repli sur le français si une traduction manque.
- **Paiement en ligne** : visible seulement si la config de l'API l'indique activé (F-65).
- **Formulaires** : CSRF, champ piège invisible, limite par IP ; pièces jointes vérifiées (type réel, taille) puis transmises à l'API et supprimées localement.
- Texte HTML venant de l'API toujours nettoyé (liste blanche de balises).
- **Performance** : accueil < 600 Ko, vérification < 150 Ko ; images WebP chargées à la demande ; aucun CDN.
- **Référencement** : titre et description par page, Open Graph, `sitemap.xml`, `robots.txt`, `hreflang`.
- Anciennes adresses de `virtrine` redirigées (annexe B du cahier des charges).

## Tests

Les tests n'appellent jamais la vraie API : elle est simulée (réponses JSON de référence dans `tests/fixtures/`). Tester systématiquement le mode dégradé et l'absence de champs interdits dans la vérification.

```bash
python manage.py runserver 8001
pytest
python manage.py makemessages -l ln -l sw -l lua -l kg && python manage.py compilemessages
```
