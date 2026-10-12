/* Maquettes uniquement : ?theme=sombre|clair force le thème (captures). Ne pas intégrer. */
(function () {
  var t = new URLSearchParams(location.search).get('theme');
  if (t === 'sombre') { document.documentElement.setAttribute('data-theme', 'sombre'); }
  if (t === 'clair') { document.documentElement.removeAttribute('data-theme'); }
})();
