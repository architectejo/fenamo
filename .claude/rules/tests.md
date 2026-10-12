---
paths:
  - "**/tests/**"
  - "**/conftest.py"
---

# Tests

- Nommer chaque test avec l'identifiant de la fonction : `test_F23_…`, `test_S03_…`.
- Données fictives uniquement (factory_boy ou fixtures) ; rien ne vient de `fenamo.zip`.
- Le site n'appelle jamais la vraie API en test : réponses simulées dans `website/tests/fixtures/`.
- Pour chaque vue : cas nominal, refus de rôle, refus de périmètre, réponse fragment HTMX et page complète.
