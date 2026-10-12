---
paths:
  - "web_app/api/**"
  - "website/services/**"
---

# API /api/v1/

- Sérialiseurs en liste blanche explicite de champs ; jamais `fields = "__all__"`.
- Vérification publique : aucun champ d'adresse, téléphone, e-mail, naissance, filiation, n° d'électeur, n° de permis, pièce jointe, famille ou paiement.
- Recherche publique par jeton QR aléatoire ou identifiant public, jamais par clé primaire.
- Changement de contrat : mettre à jour `web_app/docs/api/` et `website/tests/fixtures/` dans le même commit.
- Rupture de compatibilité = nouvelle version (`/api/v2/`).
