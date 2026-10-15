---
paths:
  - "**/templates/**"
  - "**/static/**"
---

# Templates et fichiers statiques

- Design : appliquer le système de `ui-designer` (`static/css/tokens.css`, `templates/components/`, `docs/design/`). Aucune couleur ni taille en dur ; rien repris de l'ancien projet (NiceAdmin, template médical, maicons) ni de l'apparence par défaut de Bootstrap.

- Bibliothèques servies depuis `static/` uniquement : jamais de `<script src="https://…">` ni de Google Fonts.
- Application web : tout formulaire passe par la modale commune ; jamais de page dédiée à un formulaire.
- Un fragment HTMX vit dans `partials/_<nom>.html` et est inclus par la page complète (une seule source de HTML).
- Tout texte affiché passe par `{% translate %}` / `{% blocktranslate %}`.
- Jamais `|safe` sur du contenu saisi par un utilisateur.
- Mobile d'abord : vérifier le rendu à 360 px.
- Vocabulaire : « association membre », « engin », « coordination », « antenne », « parking ».
