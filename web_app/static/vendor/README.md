Bibliothèques front servies en local (aucun CDN). Versions figées :

- htmx.min.js : htmx 2.0.4
- alpine.min.js : Alpine.js 3.14.9
- bootstrap/bootstrap.min.css et bootstrap.bundle.min.js : Bootstrap 5.2.2 (bundle avec Popper ; modale, menus déroulants, repli)
- chartjs/chart.min.js : Chart.js 3.9.1 (seule bibliothèque de graphiques ; à charger uniquement sur les pages qui tracent un graphique)

Les polices d'icônes (bootstrap-icons, boxicons, remixicon) restent dans coptapp/static/vendor pour les écrans hérités (base-app.html) ; elles disparaîtront avec eux (lots 3-4).
Pour mettre à jour : remplacer le fichier à la main et modifier ce fichier.
