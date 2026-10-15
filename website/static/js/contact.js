/* Formulaire de contact (S-07) : amélioration progressive. Sans JavaScript, le formulaire s'envoie par un POST classique. */
(function () {
  'use strict';
  /* Après l'échange du fragment par HTMX : le focus va sur le résumé (erreur ou accusé), lu par les lecteurs d'écran. */
  document.body.addEventListener('htmx:afterSwap', function (e) {
    var zone = e.target;
    if (!zone || zone.id !== 'contact-zone') { return; }
    var cible = zone.querySelector('[data-focus-apres]');
    if (cible) { cible.focus(); if (cible.scrollIntoView) { cible.scrollIntoView({ block: 'center' }); } }
    var texte = zone.querySelector('[data-compte-caracteres]');
    if (texte) { texte.dispatchEvent(new Event('input', { bubbles: true })); }
  });
  /* Panne réseau (aucune réponse) : le formulaire n'est pas remplacé, la saisie est conservée ; message clair. */
  document.body.addEventListener('htmx:sendError', function () {
    var f = document.getElementById('contact-formulaire');
    if (f && !f.querySelector('[data-erreur-reseau]')) {
      var p = document.createElement('p');
      p.setAttribute('data-erreur-reseau', ''); p.setAttribute('role', 'alert'); p.className = 'champ-erreur';
      p.textContent = f.getAttribute('data-texte-reseau') || '';
      f.querySelector('.formulaire-pied').prepend(p);
    }
  });
})();
