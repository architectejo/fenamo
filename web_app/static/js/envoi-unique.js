// Gabarits hérités (base-app.html) : désactive les boutons d'envoi d'un formulaire dès qu'il part,
// pour éviter les doubles envois (équivalent de hx-disabled-elt sur les écrans sans HTMX).
document.addEventListener('submit', function (e) {
  var boutons = e.target.querySelectorAll('button[type=submit], button:not([type])');
  // Différé : le navigateur doit d'abord construire la requête (un bouton désactivé n'est pas envoyé).
  setTimeout(function () {
    boutons.forEach(function (b) { b.disabled = true; b.setAttribute('aria-busy', 'true'); });
  }, 0);
});
// Retour par l'historique : réactive les boutons restés désactivés.
window.addEventListener('pageshow', function (e) {
  if (e.persisted) {
    document.querySelectorAll('button[aria-busy=true]').forEach(function (b) {
      b.disabled = false; b.removeAttribute('aria-busy');
    });
  }
});
