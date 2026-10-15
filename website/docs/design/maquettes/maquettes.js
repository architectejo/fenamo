/* Maquettes seulement (à ne pas intégrer) : simule les réponses du serveur selon l'adresse.
   [data-demo-param="x"][data-demo-valeur="v"] : visible si ?x=v ; [data-demo-defaut="x"] : visible si ?x est absent.
   ?menu=ouvert, ?langue=ouverte, ?visionneuse=N, ?etat=erreur (contact : champs en erreur). */
(function () {
  var p = new URLSearchParams(location.search);
  document.querySelectorAll('[data-demo-param]').forEach(function (el) {
    el.hidden = p.get(el.getAttribute('data-demo-param')) !== el.getAttribute('data-demo-valeur');
  });
  document.querySelectorAll('[data-demo-defaut]').forEach(function (el) {
    var cle = el.getAttribute('data-demo-defaut');
    if (cle === 'etat-form') { el.hidden = p.get('etat') === 'envoye'; return; }
    el.hidden = p.has(cle);
  });
  if (p.get('etat') === 'erreur') {
    document.querySelectorAll('[data-demo-erreur]').forEach(function (c) { c.classList.add('champ--erreur'); var i = c.querySelector('input, textarea'); if (i) { i.setAttribute('aria-invalid', 'true'); } });
    var n = document.getElementById('c-nom'); if (n) { n.value = 'Kabeya Tshimanga Josué'; }
    var t = document.getElementById('c-tel'); if (t) { t.value = '0812 34'; }
  }
  if (p.get('etat') === 'recherche') { var q = document.getElementById('q'); if (q) { q.value = 'gilet'; } }
  if (p.get('etat') === 'vide') { var q2 = document.getElementById('q'); if (q2) { q2.value = 'moto-ambulance'; } }
  window.addEventListener('load', function () {
    if (p.get('menu') === 'ouvert') { var m = document.querySelector('[data-menu-site]'); if (m) { m.click(); } }
    if (p.get('langue') === 'ouverte') { var l = document.querySelector('.site-tete [data-langue]'); if (l && l.offsetParent) { l.click(); } else { var m2 = document.querySelector('[data-menu-site]'); if (m2) { m2.click(); } } }
    if (p.has('visionneuse')) { var els = document.querySelectorAll('[data-visionneuse]'); var i = parseInt(p.get('visionneuse'), 10) || 0; if (els[i]) { els[i].click(); } }
  });
})();
