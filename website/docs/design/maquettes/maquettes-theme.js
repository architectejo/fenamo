/* Maquettes seulement (à ne pas intégrer) : ?theme=sombre ou ?theme=clair force le thème avant l'affichage. */
(function () {
  var t = new URLSearchParams(location.search).get('theme');
  if (t === 'sombre') { document.documentElement.setAttribute('data-theme', 'sombre'); }
  if (t === 'clair') { document.documentElement.removeAttribute('data-theme'); }
})();
