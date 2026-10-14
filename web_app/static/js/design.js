/* FENAMO-RDC : micro-interactions du système de design (sans dépendance, ~10 Ko, ~3 Ko compressé).
   Référence : docs/design/systeme-de-design.md § « Mouvement ».
   Ce fichier ne parle pas au serveur : la plomberie HTMX (requêtes, HX-Trigger, erreurs réseau) reste dans fenamo.js,
   qui appelle l'API exposée ici : FenamoDesign.bulle(), .ouvrirModale(), .fermerModale(), .retirerDossier(), .compter().
   Tout respecte prefers-reduced-motion : les durées CSS tombent à 0 et les compteurs affichent directement la valeur. */
(function () {
  'use strict';
  var reduit = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var sprite = document.documentElement.getAttribute('data-sprite') || '/static/img/icons.svg';

  function icone(nom) {
    var ns = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('class', 'ic'); svg.setAttribute('aria-hidden', 'true'); svg.setAttribute('focusable', 'false');
    var use = document.createElementNS(ns, 'use'); use.setAttribute('href', sprite + '#i-' + nom);
    svg.appendChild(use); return svg;
  }

  /* ---------- Compteurs : [data-compteur="1234"] monte de 0 à la valeur ---------- */
  var format = new Intl.NumberFormat('fr-FR');
  function animerCompteur(el) {
    var cible = parseInt(el.getAttribute('data-compteur'), 10) || 0;
    var duree = cible < 50 ? 500 : 900, debut = null;
    function pas(t) {
      if (debut === null) { debut = t; }
      var p = Math.min(1, (t - debut) / duree);
      var e = 1 - Math.pow(1 - p, 4);
      el.textContent = format.format(Math.round(cible * e));
      if (p < 1) { requestAnimationFrame(pas); } else { el.classList.add('est-compte'); }
    }
    el.textContent = format.format(0);
    requestAnimationFrame(pas);
  }
  /* Le chiffre ne monte que lorsqu'il entre à l'écran (un chiffre hors champ garde sa valeur jusqu'à ce qu'on le voie) */
  var observateur = ('IntersectionObserver' in window) ? new IntersectionObserver(function (entrees) {
    entrees.forEach(function (en) { if (en.isIntersecting) { observateur.unobserve(en.target); animerCompteur(en.target); } });
  }, { threshold: .4 }) : null;
  function compter(racine) {
    (racine || document).querySelectorAll('[data-compteur]:not([data-compte])').forEach(function (el) {
      var cible = parseInt(el.getAttribute('data-compteur'), 10) || 0;
      el.setAttribute('data-compte', '');
      if (reduit || cible < 2) { el.textContent = format.format(cible); return; }
      var r = el.getBoundingClientRect();
      var visible = r.bottom > 0 && r.top < (window.innerHeight || document.documentElement.clientHeight);
      if (observateur && !visible) { observateur.observe(el); } else { animerCompteur(el); }
    });
  }

  /* ---------- Bulles (toasts) ---------- */
  var ICONES = { succes: 'circle-check', danger: 'circle-alert', alerte: 'triangle-alert', info: 'info' };
  var NIVEAUX = { success: 'succes', error: 'danger', danger: 'danger', warning: 'alerte', info: 'info', debug: 'info' };
  function zoneBulles() {
    var z = document.querySelector('.bulles');
    if (!z) { z = document.createElement('div'); z.className = 'bulles'; z.setAttribute('aria-live', 'polite'); document.body.appendChild(z); }
    return z;
  }
  function retirerBulle(b) {
    if (!b.isConnected || b.classList.contains('sort')) { return; }
    b.classList.add('sort');
    var fin = function () { b.remove(); };
    b.addEventListener('animationend', fin, { once: true });
    setTimeout(fin, 400);
  }
  function bulle(d) {
    var niveau = NIVEAUX[d.niveau] || d.niveau || 'info';
    var duree = d.duree || (niveau === 'danger' ? 9000 : 5000);
    var b = document.createElement('div');
    b.className = 'bulle bulle--' + niveau;
    b.setAttribute('role', niveau === 'danger' ? 'alert' : 'status');
    b.style.setProperty('--duree', duree + 'ms');
    b.appendChild(icone(ICONES[niveau] || 'info'));
    var t = document.createElement('div'); t.className = 'bulle-texte'; t.textContent = d.message || '';
    if (d.detail) { var s = document.createElement('small'); s.textContent = d.detail; t.appendChild(s); }
    b.appendChild(t);
    var f = document.createElement('button'); f.type = 'button'; f.className = 'bouton-icone'; f.setAttribute('aria-label', 'Fermer');
    f.appendChild(icone('x')); f.addEventListener('click', function () { retirerBulle(b); });
    b.appendChild(f);
    var barre = document.createElement('span'); barre.className = 'bulle-delai'; barre.setAttribute('aria-hidden', 'true'); b.appendChild(barre);
    barre.addEventListener('animationend', function () { retirerBulle(b); });
    if (reduit) { setTimeout(function () { retirerBulle(b); }, duree); }
    zoneBulles().appendChild(b);
    return b;
  }
  /* HX-Trigger: {"toast": {"message": "Membre validé", "niveau": "success"}} ou une liste */
  document.addEventListener('toast', function (e) { [].concat(e.detail && e.detail.value ? e.detail.value : e.detail).forEach(bulle); });

  /* ---------- Modale ---------- */
  var dernierFocus = null;
  var FOCUSABLES = 'a[href], button:not([disabled]), input:not([disabled]):not([type=hidden]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
  function ouvrirModale(m) {
    m = typeof m === 'string' ? document.querySelector(m) : m;
    if (!m || m.classList.contains('est-ouverte')) { return; }
    dernierFocus = document.activeElement;
    m.hidden = false; m.classList.remove('se-ferme');
    document.documentElement.style.overflow = 'hidden';
    requestAnimationFrame(function () { requestAnimationFrame(function () { m.classList.add('est-ouverte'); }); });
    var corps = m.querySelector('.feuille-corps');
    var premier = m.querySelector('[autofocus]') || (corps && corps.querySelector(FOCUSABLES)) || m.querySelector(FOCUSABLES);
    if (premier) { setTimeout(function () { premier.focus({ preventScroll: true }); }, reduit ? 0 : 60); }
  }
  function fermerModale(m) {
    m = typeof m === 'string' ? document.querySelector(m) : (m || document.querySelector('.modale.est-ouverte'));
    if (!m || m.hidden) { return; }
    m.classList.remove('est-ouverte'); m.classList.add('se-ferme');
    var fin = function () { m.hidden = true; m.classList.remove('se-ferme'); document.documentElement.style.overflow = ''; };
    setTimeout(fin, reduit ? 0 : 220);
    if (dernierFocus && dernierFocus.focus) { dernierFocus.focus({ preventScroll: true }); }
  }
  document.addEventListener('keydown', function (e) {
    var m = document.querySelector('.modale.est-ouverte');
    if (!m) { return; }
    if (e.key === 'Escape') { e.preventDefault(); fermerModale(m); return; }
    if (e.key === 'Tab') {
      var f = [].slice.call(m.querySelectorAll(FOCUSABLES)).filter(function (x) { return x.offsetParent !== null; });
      if (!f.length) { return; }
      var a = f[0], z = f[f.length - 1];
      if (e.shiftKey && document.activeElement === a) { e.preventDefault(); z.focus(); }
      else if (!e.shiftKey && document.activeElement === z) { e.preventDefault(); a.focus(); }
    }
  });

  /* ---------- Menu latéral (tiroir sous 992 px) ---------- */
  function menu(ouvrir) {
    var m = document.querySelector('.menu'), v = document.querySelector('.voile--menu');
    if (!m) { return; }
    m.classList.toggle('est-ouvert', ouvrir);
    if (v) { v.hidden = !ouvrir; }
    document.querySelectorAll('[data-menu-ouvrir]').forEach(function (b) { b.setAttribute('aria-expanded', String(ouvrir)); });
    if (ouvrir) { var l = m.querySelector('a, button'); if (l) { setTimeout(function () { l.focus(); }, reduit ? 0 : 120); } }
  }

  /* ---------- Dossier traité : flash puis retrait de la file ---------- */
  function retirerDossier(el, sens) {
    if (!el) { return; }
    el.classList.add(sens === 'renvoye' ? 'est-renvoye' : 'est-traite');
    var fin = function () {
      var h = el.offsetHeight; el.style.height = h + 'px'; el.style.overflow = 'hidden';
      el.animate ? el.animate([{ height: h + 'px', marginTop: getComputedStyle(el).marginTop }, { height: '0px', paddingTop: 0, paddingBottom: 0, borderWidth: 0 }], { duration: reduit ? 0 : 180, easing: 'ease-in' }).onfinish = function () { el.remove(); } : el.remove();
    };
    setTimeout(fin, reduit ? 0 : 900);
  }

  /* Pastille de compteur qui « bondit » quand sa valeur change */
  function majCompteur(el, valeur) {
    if (!el) { return; }
    el.textContent = valeur; el.hidden = !valeur || valeur === '0';
    el.classList.remove('bondit'); void el.offsetWidth; el.classList.add('bondit');
  }

  /* ---------- Copier dans le presse-papiers : [data-copier="#cible"] (valeur : data-valeur de la cible, sinon son texte) ----------
     Le libellé du bouton (.copier-texte) passe à « Copié » 2 s, l'icône devient une coche ; la cible (et son .mdp-temp) prend .est-copie.
     data-copier-message : bulle de confirmation facultative. Repli execCommand si l'API Clipboard est refusée (HTTP, ancien navigateur). */
  function copierTexte(texte) {
    if (navigator.clipboard && window.isSecureContext) { return navigator.clipboard.writeText(texte); }
    return new Promise(function (ok, ko) {
      var z = document.createElement('textarea'); z.value = texte; z.setAttribute('readonly', ''); z.className = 'lecteur';
      document.body.appendChild(z); z.select();
      try { if (document.execCommand('copy')) { ok(); } else { ko(new Error('copie refusée')); } } catch (err) { ko(err); } finally { z.remove(); }
    });
  }
  function copier(b) {
    var cible = document.querySelector(b.getAttribute('data-copier'));
    if (!cible) { return; }
    var texte = cible.getAttribute('data-valeur') || cible.textContent.replace(/\s+/g, '');
    var libelle = b.querySelector('.copier-texte'), use = b.querySelector('use');
    copierTexte(texte).then(function () {
      var avant = libelle ? libelle.textContent : '', icone = use ? use.getAttribute('href') : '';
      b.classList.add('est-copie'); if (libelle) { libelle.textContent = b.getAttribute('data-copier-fait') || 'Copié'; }
      if (use) { use.setAttribute('href', sprite + '#i-check'); }
      var bloc = cible.closest('.mdp-temp') || cible; bloc.classList.add('est-copie');
      if (b.hasAttribute('data-copier-message')) { bulle({ message: b.getAttribute('data-copier-message'), niveau: 'success', duree: 3000 }); }
      setTimeout(function () { b.classList.remove('est-copie'); if (libelle) { libelle.textContent = avant; } if (use) { use.setAttribute('href', icone); } }, 2000);
    }, function () {
      bulle({ message: 'Copie impossible', detail: 'Sélectionnez le texte et copiez-le à la main.', niveau: 'alerte' });
    });
  }

  /* ---------- Déplier / replier un bloc : [data-deplier="#bloc"] (aria-expanded tenu à jour, classe .est-deplie sur le bloc) ---------- */
  function deplier(b) {
    var bloc = document.querySelector(b.getAttribute('data-deplier'));
    if (!bloc) { return; }
    var ouvert = !bloc.classList.contains('est-deplie');
    bloc.classList.toggle('est-deplie', ouvert); b.setAttribute('aria-expanded', String(ouvert));
    if (ouvert) { var f = bloc.querySelector(FOCUSABLES); if (f) { f.focus({ preventScroll: true }); } }
  }

  /* ---------- Délégation des clics ---------- */
  document.addEventListener('click', function (e) {
    var t = e.target.closest('[data-ouvre-modale], [data-ferme-modale], [data-menu-ouvrir], [data-menu-fermer], [data-theme-basculer], [data-copier], [data-deplier], .modale-voile, .voile--menu');
    if (!t) { return; }
    if (t.hasAttribute('data-copier')) { e.preventDefault(); copier(t); return; }
    if (t.hasAttribute('data-deplier')) { e.preventDefault(); deplier(t); return; }
    if (t.hasAttribute('data-ouvre-modale')) { e.preventDefault(); ouvrirModale(t.getAttribute('data-ouvre-modale')); }
    else if (t.hasAttribute('data-ferme-modale') || t.classList.contains('modale-voile')) { e.preventDefault(); fermerModale(t.closest('.modale')); }
    else if (t.hasAttribute('data-menu-ouvrir')) { menu(true); }
    else if (t.hasAttribute('data-menu-fermer') || t.classList.contains('voile--menu')) { menu(false); }
    else if (t.hasAttribute('data-theme-basculer')) {
      var sombre = document.documentElement.getAttribute('data-theme') !== 'sombre';
      if (sombre) { document.documentElement.setAttribute('data-theme', 'sombre'); } else { document.documentElement.removeAttribute('data-theme'); }
      try { localStorage.setItem('fn-theme', sombre ? 'sombre' : 'clair'); } catch (err) { /* stockage refusé : le choix vaut pour la page */ }
      document.dispatchEvent(new CustomEvent('themechange'));
    }
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') { menu(false); } });

  /* Valeurs absentes (« — ») : la définition s'efface visuellement, la cellule de liste disparaît des cartes mobiles */
  function marquerVides(racine) {
    (racine || document).querySelectorAll('.definitions dd, .liste td[data-libelle]').forEach(function (el) {
      el.classList.toggle('est-vide', el.textContent.trim() === '—');
    });
  }

  /* Contenu inséré par HTMX : compteurs à animer, valeurs vides à marquer */
  document.addEventListener('htmx:afterSettle', function (e) { compter(e.target); marquerVides(e.target); });
  document.addEventListener('DOMContentLoaded', function () { compter(document); marquerVides(document); });

  window.FenamoDesign = { bulle: bulle, ouvrirModale: ouvrirModale, fermerModale: fermerModale, menu: menu, retirerDossier: retirerDossier, compter: compter, marquerVides: marquerVides, majCompteur: majCompteur, icone: icone, copier: copier, deplier: deplier };
})();
