/* FENAMO-RDC : comportements du site public (sobres, sans dépendance).
   Menu du téléphone, sélecteur de langue, thème, chiffres clés, carte des coordinations, visionneuse de la galerie,
   copie du lien, compteur de caractères, carte Google Maps chargée à la demande.
   Tout fonctionne sans ce fichier (liens et ancres) ; il ne fait qu'améliorer. Mouvement réduit respecté. */
(function () {
  'use strict';
  var reduit = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var ESPACE_FINE = ' ';

  function $(sel, racine) { return (racine || document).querySelector(sel); }
  function $$(sel, racine) { return Array.prototype.slice.call((racine || document).querySelectorAll(sel)); }
  function focalisables(racine) {
    return $$('a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select, textarea, [tabindex]:not([tabindex="-1"])', racine)
      .filter(function (el) { return el.offsetParent !== null; });
  }

  /* ---------- Thème (même clé que l'application : fn-theme) ---------- */
  function basculerTheme() {
    var sombre = document.documentElement.getAttribute('data-theme') !== 'sombre';
    if (sombre) { document.documentElement.setAttribute('data-theme', 'sombre'); } else { document.documentElement.removeAttribute('data-theme'); }
    try { localStorage.setItem('fn-theme', sombre ? 'sombre' : 'clair'); } catch (e) { /* stockage refusé : le choix vaut pour la page */ }
    $$('[data-theme-basculer]').forEach(function (b) { b.setAttribute('aria-pressed', sombre ? 'true' : 'false'); });
  }

  /* ---------- Menu du téléphone ---------- */
  var menuDeclencheur = null;
  function ouvrirMenu(bouton) {
    var menu = document.getElementById(bouton.getAttribute('aria-controls'));
    if (!menu) { return; }
    menuDeclencheur = bouton;
    menu.hidden = false; menu.classList.remove('se-ferme');
    bouton.setAttribute('aria-expanded', 'true');
    bouton.setAttribute('aria-label', bouton.getAttribute('data-libelle-fermer') || 'Fermer le menu');
    var use = bouton.querySelector('use'); if (use) { use.setAttribute('href', use.getAttribute('href').replace('#i-menu', '#i-x')); }
    document.body.classList.add('menu-ouvert');
    var premier = focalisables(menu)[0]; if (premier) { premier.focus(); }
  }
  function fermerMenu(rendreFocus) {
    var bouton = menuDeclencheur || $('[data-menu-site][aria-expanded="true"]');
    if (!bouton) { return; }
    var menu = document.getElementById(bouton.getAttribute('aria-controls'));
    bouton.setAttribute('aria-expanded', 'false');
    bouton.setAttribute('aria-label', bouton.getAttribute('data-libelle-ouvrir') || 'Ouvrir le menu');
    var use = bouton.querySelector('use'); if (use) { use.setAttribute('href', use.getAttribute('href').replace('#i-x', '#i-menu')); }
    document.body.classList.remove('menu-ouvert');
    if (menu) {
      if (reduit) { menu.hidden = true; } else {
        menu.classList.add('se-ferme');
        setTimeout(function () { menu.hidden = true; menu.classList.remove('se-ferme'); }, 130);
      }
    }
    if (rendreFocus !== false) { bouton.focus(); }
    menuDeclencheur = null;
  }

  /* ---------- Sélecteur de langue ---------- */
  function fermerLangues(sauf) {
    $$('[data-langue][aria-expanded="true"]').forEach(function (b) {
      if (b === sauf) { return; }
      b.setAttribute('aria-expanded', 'false');
      var l = document.getElementById(b.getAttribute('aria-controls')); if (l) { l.hidden = true; }
    });
  }
  function basculerLangues(bouton) {
    var liste = document.getElementById(bouton.getAttribute('aria-controls'));
    var ouvrir = bouton.getAttribute('aria-expanded') !== 'true';
    fermerLangues(bouton);
    bouton.setAttribute('aria-expanded', ouvrir ? 'true' : 'false');
    liste.hidden = !ouvrir;
    if (ouvrir) { var cur = liste.querySelector('[aria-current]') || liste.querySelector('a'); if (cur) { cur.focus(); } }
  }

  /* ---------- Chiffres clés : montent de 0 à la valeur, une seule fois, quand ils deviennent visibles ---------- */
  function formater(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ESPACE_FINE); }
  function animerCompteur(el) {
    var cible = parseInt(el.getAttribute('data-compteur'), 10);
    if (isNaN(cible) || reduit) { el.textContent = formater(cible); return; }
    var debut = null, duree = 700;
    function pas(t) {
      if (!debut) { debut = t; }
      var p = Math.min(1, (t - debut) / duree), e = 1 - Math.pow(1 - p, 3);
      el.textContent = formater(Math.round(cible * e));
      if (p < 1) { requestAnimationFrame(pas); }
    }
    requestAnimationFrame(pas);
  }
  function initCompteurs() {
    var els = $$('[data-compteur]');
    if (!els.length) { return; }
    if (!('IntersectionObserver' in window)) { els.forEach(function (el) { el.textContent = formater(el.getAttribute('data-compteur')); }); return; }
    var io = new IntersectionObserver(function (entrees) {
      entrees.forEach(function (en) { if (en.isIntersecting) { animerCompteur(en.target); io.unobserve(en.target); } });
    }, { threshold: .4 });
    els.forEach(function (el) { io.observe(el); });
  }

  /* ---------- Coordinations : la case de la carte ouvre la ligne correspondante ---------- */
  function choisirCoordination(id, defiler) {
    var ligne = document.getElementById(id);
    if (!ligne || !ligne.classList.contains('coord')) { return; }
    $$('.coord.est-choisie, .tuile.est-choisie').forEach(function (el) { el.classList.remove('est-choisie'); });
    ligne.classList.add('est-choisie');
    ligne.open = true;
    $$('.tuile[href="#' + id + '"]').forEach(function (t) { t.classList.add('est-choisie'); });
    if (defiler) { ligne.scrollIntoView({ behavior: reduit ? 'auto' : 'smooth', block: 'start' }); }
    var resume = ligne.querySelector('summary'); if (resume) { resume.focus({ preventScroll: true }); }
  }

  /* ---------- Lecteur vidéo : iframe créée au clic, adresses de lecteur de la liste blanche seulement ---------- */
  var LECTEURS = ['https://www.youtube-nocookie.com/embed/', 'https://www.facebook.com/plugins/video.php'];
  function creerLecteur(adresse, titre) {
    if (!LECTEURS.some(function (debut) { return adresse.indexOf(debut) === 0; })) { return null; }
    var f = document.createElement('iframe');
    f.src = adresse; f.title = titre || 'Vidéo'; f.loading = 'lazy'; f.allowFullscreen = true;
    f.referrerPolicy = 'strict-origin-when-cross-origin';
    f.setAttribute('allow', 'encrypted-media; picture-in-picture; fullscreen');
    return f;
  }
  function chargerVideo(zone) {
    var f = creerLecteur(zone.getAttribute('data-video-embed'), zone.getAttribute('data-video-titre'));
    if (!f) { return false; }
    zone.innerHTML = ''; zone.appendChild(f); return true;
  }

  /* ---------- Visionneuse de la galerie ---------- */
  var vis = { el: null, elements: [], index: 0, declencheur: null };
  function afficherDansVisionneuse(i) {
    var n = vis.elements.length; vis.index = (i + n) % n;
    var src = vis.elements[vis.index];
    var corps = $('[data-visionneuse-image]', vis.el), legende = $('[data-visionneuse-legende]', vis.el), pos = $('[data-visionneuse-position]', vis.el);
    var photo = src.querySelector('.photo');
    corps.innerHTML = '';
    if (photo) {
      var c = photo.cloneNode(true); c.className = 'photo photo--3x2';
      var grande = src.getAttribute('data-src'), lecteur = src.getAttribute('data-video'), img = c.querySelector('img');
      /* Image agrandie chargée seulement à l'ouverture (la vignette sert de repli) */
      if (grande && img && /^https?:\/\//.test(grande)) { img.removeAttribute('loading'); img.removeAttribute('width'); img.removeAttribute('height'); img.src = grande; }
      /* Vidéo : le lecteur n'est construit qu'ici, à l'ouverture, pour une adresse de lecteur connue */
      if (lecteur) { c.innerHTML = ''; var f = creerLecteur(lecteur, src.getAttribute('data-legende')); if (f) { c.appendChild(f); } }
      corps.appendChild(c);
    }
    legende.textContent = src.getAttribute('data-legende') || '';
    pos.textContent = (vis.index + 1) + ' / ' + n;
  }
  function ouvrirVisionneuse(bouton) {
    vis.el = document.getElementById('visionneuse'); if (!vis.el) { return; }
    vis.elements = $$('[data-visionneuse]'); vis.declencheur = bouton;
    afficherDansVisionneuse(vis.elements.indexOf(bouton));
    vis.el.hidden = false; document.body.classList.add('menu-ouvert');
    $('[data-visionneuse-fermer]', vis.el).focus();
  }
  function fermerVisionneuse() {
    if (!vis.el || vis.el.hidden) { return; }
    vis.el.hidden = true; document.body.classList.remove('menu-ouvert');
    if (vis.declencheur) { vis.declencheur.focus(); }
  }

  /* ---------- Copier le lien de la page (partage) ---------- */
  function copierLien(bouton) {
    var url = bouton.getAttribute('data-copier-lien') || window.location.href;
    var libelle = bouton.querySelector('[data-libelle]');
    function fait() {
      if (!libelle) { return; }
      var avant = libelle.textContent; libelle.textContent = bouton.getAttribute('data-copier-fait') || 'Lien copié';
      setTimeout(function () { libelle.textContent = avant; }, 2000);
    }
    if (navigator.clipboard && window.isSecureContext) { navigator.clipboard.writeText(url).then(fait, fait); return; }
    var t = document.createElement('textarea'); t.value = url; t.setAttribute('readonly', ''); t.style.position = 'absolute'; t.style.left = '-9999px';
    document.body.appendChild(t); t.select();
    try { document.execCommand('copy'); } catch (e) { if (window.console) { console.warn('Copie impossible', e); } }
    document.body.removeChild(t); fait();
  }

  /* ---------- Compteur de caractères ---------- */
  function compter(champ) {
    var cible = document.querySelector(champ.getAttribute('data-compte-caracteres'));
    if (!cible) { return; }
    var max = parseInt(champ.getAttribute('maxlength'), 10) || 0;
    var v = cible.querySelector('[data-compte-valeur]'); if (v) { v.textContent = champ.value.length; }
    cible.classList.toggle('est-plein', max && champ.value.length >= max);
  }

  /* ---------- Carte Google Maps : chargée seulement sur demande (3G, vie privée) ---------- */
  function chargerCarte(bouton) {
    var zone = bouton.closest('.carte-lieu'); var src = bouton.getAttribute('data-carte-charger');
    if (!zone || !src) { return; }
    var f = document.createElement('iframe');
    f.src = src; f.title = bouton.getAttribute('data-carte-titre') || 'Carte'; f.loading = 'lazy'; f.referrerPolicy = 'no-referrer-when-downgrade';
    zone.appendChild(f); zone.classList.add('est-chargee');
  }

  /* ---------- Délégation des événements ---------- */
  document.addEventListener('click', function (e) {
    var t = e.target.closest('[data-theme-basculer], [data-menu-site], [data-langue], .tuile, [data-visionneuse], [data-visionneuse-fermer], [data-visionneuse-precedent], [data-visionneuse-suivant], [data-copier-lien], [data-carte-charger], .lecteur-video-lien');
    if (!t) {
      if (!e.target.closest('.langue')) { fermerLangues(); }
      return;
    }
    if (t.hasAttribute('data-theme-basculer')) { basculerTheme(); }
    else if (t.hasAttribute('data-menu-site')) { if (t.getAttribute('aria-expanded') === 'true') { fermerMenu(); } else { ouvrirMenu(t); } }
    else if (t.hasAttribute('data-langue')) { basculerLangues(t); }
    else if (t.classList.contains('tuile')) { e.preventDefault(); var id = t.getAttribute('href').slice(1); history.replaceState(null, '', '#' + id); choisirCoordination(id, true); }
    else if (t.hasAttribute('data-visionneuse')) { ouvrirVisionneuse(t); }
    else if (t.hasAttribute('data-visionneuse-fermer')) { fermerVisionneuse(); }
    else if (t.hasAttribute('data-visionneuse-precedent')) { afficherDansVisionneuse(vis.index - 1); }
    else if (t.hasAttribute('data-visionneuse-suivant')) { afficherDansVisionneuse(vis.index + 1); }
    else if (t.hasAttribute('data-copier-lien')) { copierLien(t); }
    else if (t.hasAttribute('data-carte-charger')) { chargerCarte(t); }
    else if (t.classList.contains('lecteur-video-lien')) { var zone = t.closest('[data-video-embed]'); if (zone && chargerVideo(zone)) { e.preventDefault(); } }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      if (vis.el && !vis.el.hidden) { fermerVisionneuse(); return; }
      var ouverte = $('[data-langue][aria-expanded="true"]'); if (ouverte) { fermerLangues(); ouverte.focus(); return; }
      if (document.body.classList.contains('menu-ouvert')) { fermerMenu(); }
    }
    if (vis.el && !vis.el.hidden) {
      if (e.key === 'ArrowLeft') { afficherDansVisionneuse(vis.index - 1); }
      if (e.key === 'ArrowRight') { afficherDansVisionneuse(vis.index + 1); }
    }
    /* Focus gardé dans le menu ou la visionneuse */
    if (e.key === 'Tab') {
      var piege = (vis.el && !vis.el.hidden) ? vis.el : (document.body.classList.contains('menu-ouvert') ? $('.menu-site:not([hidden])') : null);
      if (!piege) { return; }
      var f = focalisables(piege); var bouton = $('[data-menu-site][aria-expanded="true"]');
      if (bouton && piege.classList.contains('menu-site')) { f.unshift(bouton); }
      if (!f.length) { return; }
      if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
    }
  });

  document.addEventListener('input', function (e) { if (e.target.hasAttribute('data-compte-caracteres')) { compter(e.target); } });

  window.addEventListener('resize', function () { if (window.innerWidth >= 1100 && document.body.classList.contains('menu-ouvert') && !(vis.el && !vis.el.hidden)) { fermerMenu(false); } });
  window.addEventListener('hashchange', function () { if (location.hash.indexOf('#coord-') === 0) { choisirCoordination(location.hash.slice(1), true); } });

  function init() {
    $$('[data-theme-basculer]').forEach(function (b) { b.setAttribute('aria-pressed', document.documentElement.getAttribute('data-theme') === 'sombre' ? 'true' : 'false'); });
    initCompteurs();
    $$('[data-compte-caracteres]').forEach(compter);
    if (location.hash.indexOf('#coord-') === 0) { choisirCoordination(location.hash.slice(1), false); }
  }
  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', init); } else { init(); }

  window.FenamoSite = { ouvrirMenu: ouvrirMenu, fermerMenu: fermerMenu, choisirCoordination: choisirCoordination, ouvrirVisionneuse: ouvrirVisionneuse, fermerVisionneuse: fermerVisionneuse, basculerTheme: basculerTheme, compteur: animerCompteur };
})();
