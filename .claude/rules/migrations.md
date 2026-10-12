---
paths:
  - "**/migrations/**"
---

# Migrations

- Ne jamais modifier une migration déjà appliquée ; en créer une nouvelle.
- Migrations additives tant que `mobapp` lit la base : vérifier qu'un champ n'est pas utilisé dans `mobapp/` avant de le renommer ou le supprimer.
- Migrations de données avec fonction inverse quand c'est possible, et sans aucune donnée personnelle réelle en dur.
- Compatibles SQLite et MySQL (utf8mb4) : pas de SQL brut propre à un moteur.
