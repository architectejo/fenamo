/* FENAMO-RDC : applique le thème sombre avant le premier affichage (évite l'éclair blanc).
   Chargé dans <head>, sans defer. Choix enregistré dans localStorage ; à défaut, préférence du système. */
(function () {
  var theme = null;
  try {
    theme = localStorage.getItem('fn-theme');
  } catch (e) {
    theme = null; // stockage refusé (navigation privée) : on retombe sur la préférence du système
  }
  if (!theme && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) { theme = 'sombre'; }
  if (theme === 'sombre') { document.documentElement.setAttribute('data-theme', 'sombre'); }
})();
