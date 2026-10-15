# Contrat des erreurs de l'API `/api/v1/`

Référence : cahier des charges application web § 2.4 et F-07 ; cahier des charges du site S-12 et § 6.2.
Toutes les erreurs sont du JSON (`Content-Type: application/json`). Aucune réponse de l'API ne pose de cookie ni de session.
Statut : le 503 « suspendu » et la santé sont **implémentés et testés** (`tests/test_F07_api_suspendue.py`) ; les points d'accès en lecture de `/api/v1/site/` (401, 404, 405, 429, 400 de paramètres) sont **implémentés et testés** (`tests/test_api_site_lot2a.py`, détail dans `site.md`) ; le dépôt de contact (400, 413, 429, 403 `inactif`) est **implémenté et testé** (`tests/test_S07_contact_api.py`, détail dans `site.md`) ; les autres dépôts (adhésion, paiement) restent le contrat cible. 413 : corps de dépôt trop volumineux, `{"detail": "Requête trop volumineuse."}`.

## Tableau

| Code | Cas | Corps |
| --- | --- | --- |
| 400 | Validation d'un dépôt (contact, adhésion, paiement) | `{"champ": ["message", …]}` ; erreur non liée à un champ : clé `non_field_errors` |
| 401 | Clé du site absente ou invalide, ou révoquée | `{"detail": "Clé du site absente ou invalide."}` |
| 403 | Paiement demandé alors que F-65 est désactivé ; signature de rappel invalide | `{"detail": "…"}` |
| 403 | **Données réelles désactivées** : tout point d'accès de données de `/api/v1/site/` (sauf `config/`) tant que l'interrupteur du super-utilisateur est faux | `{"statut": "inactif", "detail": "Données réelles désactivées."}` |
| 404 | Identifiant, numéro ou jeton QR inconnu (même réponse pour « n'existe pas » et « non public ») | `{"detail": "Introuvable."}` |
| 405 | Méthode non permise | `{"detail": "…"}` |
| 429 | Limite de débit dépassée | `{"detail": "Trop de requêtes."}` + en-tête `Retry-After` (secondes) |
| 503 | **Application verrouillée (F-07)** | voir ci-dessous |

Les messages sont en français, destinés à être affichés tels quels à côté des champs.

## 503 « service suspendu » (F-07)

Pendant le verrouillage, le middleware `compte.middleware.VerrouApplicationMiddleware` répond **avant** la vérification de la clé du site, pour **toute** route sous `/api/` (y compris `/api/v1/`, `/api/v2/`, routes inexistantes) et **toute** méthode (GET, POST, PUT, PATCH, DELETE, OPTIONS), sauf la santé.

```http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
Cache-Control: no-store
```

```json
{"statut": "suspendu", "detail": "Service suspendu.", "message": "Maintenance : retour demain."}
```

- Exactement trois clés : `statut` (toujours `"suspendu"`), `detail` (texte fixe), `message` (texte saisi par le super-utilisateur, 1 à 500 caractères, texte brut : le site l'échappe à l'affichage).
- **Champs interdits** : motif du verrouillage, auteur (identifiant ou nom), date de début, toute donnée métier. Un test vérifie leur absence.
- Pas de `Retry-After` : la durée est inconnue.
- Réponse non cachable : ne jamais la stocker comme contenu valide.

## Santé : `GET /api/v1/sante/`

| État | Code | Corps |
| --- | --- | --- |
| Normal | 200 | `{"statut": "ok", "version": "v1"}` |
| Verrouillée | **200** | `{"statut": "suspendu", "version": "v1"}` |

La santé répond 200 même verrouillée, pour distinguer un verrou d'une panne (une panne = pas de réponse, timeout ou 5xx autre que le 503 ci-dessus). Elle n'expose pas le message. Attention : `/api/v1/` (racine, sonde historique) n'est pas la santé du contrat et répond 503 pendant le verrou.

## Ce que le site doit faire (S-12) — à réaliser par `site-web`, lot séparé

Le client API du site n'est pas modifié par ce lot.

1. Reconnaître le verrou : statut 503 **et** corps JSON avec `statut == "suspendu"`. Ne pas le traiter comme une panne (pas de nouvelle tentative en boucle, pas de journal d'erreur).
2. Pages de lecture (accueil, actualités, comité, coordinations, annuaire, statistiques) : servir le **dernier contenu en cache** valide (cache de repli), sans le renouveler ni prolonger sa durée à cause du 503 ; la purge du cache (F-60 à F-63) est elle aussi suspendue.
3. Fonctions suspendues : vérification (S-03), contact, adhésion, suivi, paiement (S-06) n'appellent plus l'API et affichent la page « service suspendu » avec le `message` reçu (échappé). Aucune valeur de repli pour la vérification : jamais de résultat périmé servi depuis le cache.
4. Ne jamais mettre en cache une réponse 503 ni le `message` comme contenu de page ; ne pas répercuter `Cache-Control` du 503 sur les pages de repli.
5. Détection de fin de verrou : interroger `/api/v1/sante/` (200) ; dès `statut == "ok"`, reprendre les appels normaux. Pendant le verrou, limiter à une sonde de santé par intervalle court (par ex. 30 s) plutôt qu'un appel par visiteur.
6. Panne (timeout de 5 s, erreur réseau, 5xx autre) : mode dégradé S-12 avec « service momentanément indisponible », distinct du message de verrou.
7. Fixtures de test : `website/tests/fixtures/api_suspendu.json` et `api_sante_suspendue.json`.
