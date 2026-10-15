# Site public FENAMO-RDC

Site public (`fenamordc.cd`) qui ne passe que par l'API de l'application web. Référence : `docs/cahier-des-charges-site-web.md`.

## Installation locale

```bash
cd website
python -m venv .venv && source .venv/bin/activate      # Windows : .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                    # SECRET_KEY peut rester vide en dev
python manage.py migrate                                # crée var/ et la base locale (sessions)
python manage.py runserver 8001
```

Le site est alors sur http://localhost:8001. Le port 8001 peut être occupé par un autre programme : choisir un autre port (`runserver 8002`) et adapter `SITE_URL` dans `.env`.

L'application web (API) doit tourner sur `localhost:8000` pour que les contenus s'affichent ; sinon le site passe en mode dégradé (dernier contenu en cache, messages « service momentanément indisponible »).

## Tests

```bash
pytest
```

L'API est toujours simulée ; aucun appel réseau réel n'est possible en test.

## Langues

Les fichiers `locale/*/LC_MESSAGES/django.po` et leurs `django.mo` compilés sont **versionnés** : Django n'active `ln`, `lua` et `kg` que si un `.mo` existe. Recompiler après modification :

```bash
python manage.py makemessages -l ln -l sw -l lua -l kg
python tools/compile_mo.py          # ou compilemessages si GNU gettext est installé
```

Les langues proposées se règlent avec `ACTIVE_LANGUAGES` (le français est toujours actif). Une langue inactive redirige (302) vers la version française.

## Purge du cache (contrat pour l'application web)

`POST /_purge/` (hors préfixe de langue, sans CSRF). En-têtes : `X-Purge-Timestamp` (secondes Unix) et `X-Purge-Signature` = HMAC-SHA256 hexadécimal de cet horodatage avec `PURGE_SECRET`. Réponses : 204 (copies fraîches vidées, copies de secours conservées), 403 (signature fausse, absente, horodatage à plus de 300 s, signature déjà utilisée), 429 (plus de 10 appels par minute).

## Mode dégradé et verrou F-07

Panne : dernière copie servie avec le bandeau « Service ralenti ». Verrou (503 `statut: suspendu`) : même copie, sans renouvellement, bandeau « Plateforme momentanément fermée », aucun appel de données pendant le verrou (une sonde de `/api/v1/sante/` toutes les `API_SANTE_INTERVALLE` secondes). Détails : `web_app/docs/api/erreurs.md`.

## Traductions

`python tools/extraire_messages.py` met à jour les cinq `django.po` depuis les gabarits (sans GNU gettext), puis `python tools/compile_mo.py`. Une langue n'est proposée que si la configuration de l'API l'active **et** si son `.po` est complet. Lingala : les lettres ɛ et ɔ demandent un sous-ensemble de police « latin étendu » le jour de l'activation.

## Contenus

`docs/contenu/statuts-extraits.md` : extraits de la charte (références d'articles) d'où viennent les textes de la page « La FENAMO-RDC », du comité, de l'adhésion et des mentions. La page Confidentialité est un projet à valider par la FENAMO.

## Production (cPanel, Passenger)

- Réglages : `site_fenamo.settings.prod` (déjà choisi par `passenger_wsgi.py`).
- `.env` : `SECRET_KEY` (50 caractères au moins), `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `API_BASE_URL` en https, `SITE_API_KEY`, `PURGE_SECRET`. Le démarrage échoue si l'un d'eux est absent ou invalide.
- `pip install -r requirements.txt`, puis `python manage.py migrate` et `python manage.py collectstatic --noinput`.
- Fichiers statiques : servis par **WhiteNoise** depuis `staticfiles/` (même choix que `web_app`), sans configuration Apache particulière.
- `var/` (base SQLite des sessions et cache fichiers) est créé au démarrage et n'est pas versionné.

## Logo

`docs/logo/logo.png` : logo officiel de la FENAMO-RDC, à ne jamais déformer ni recolorer.
