/* FENAMO-RDC : plomberie HTMX + Alpine de l'application web (aucune autre dépendance).
   L'affichage (modale, bulles, compteurs, retrait de dossier, menu, thème) est dans design.js (FenamoDesign) ;
   ce fichier relie HTMX à cet affichage : HX-Trigger, squelette de modale, erreurs réseau, verrouillage des envois.
   Chargé après design.js et avant Alpine (tous en defer) pour que alpine:init soit entendu.
   Les textes traduits viennent de l'élément JSON #fenamo-textes (json_script, base.html). */
(function () {
  'use strict';

  var D = window.FenamoDesign;
  var textes = null;
  var T = function () {
    if (textes === null) {
      var noeud = document.getElementById('fenamo-textes');
      textes = noeud ? JSON.parse(noeud.textContent) : {};
    }
    return textes;
  };

  /* ------------------------------------------------------------------ Alpine */
  document.addEventListener('alpine:init', function () {
    var reduit = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // Bandeau « Connexion perdue, réessayez »
    Alpine.store('reseau', {
      visible: false,
      texte: '',
      requete: null,
      montrer: function (texte, requete) { this.texte = texte; this.requete = requete; this.visible = true; },
      cacher: function () { this.visible = false; this.requete = null; },
      reessayer: function () {
        var r = this.requete;
        this.cacher();
        if (r && r.elt && document.body.contains(r.elt)) { htmx.trigger(r.elt, r.evenement); }
      }
    });

    // Onglets accessibles (rôle tablist) ; l'onglet actif peut venir de l'ancre de l'adresse
    Alpine.data('onglets', function (defaut) {
      return {
        actif: (location.hash && location.hash.length > 1 && document.getElementById('panneau-' + location.hash.slice(1))) ? location.hash.slice(1) : defaut,
        choisir: function (nom) { this.actif = nom; },
        cle: function (e) {
          var liste = Array.prototype.slice.call(this.$root.querySelectorAll('[role=tab]'));
          var i = liste.indexOf(document.activeElement);
          if (i < 0) { return; }
          var suivant = e.key === 'ArrowRight' ? i + 1 : (e.key === 'ArrowLeft' ? i - 1 : -1);
          if (suivant < 0 || suivant >= liste.length) { return; }
          e.preventDefault();
          liste[suivant].focus();
          this.actif = liste[suivant].dataset.onglet;
        }
      };
    });

    // Graphique Chart.js (bibliothèque locale, chargée seulement ici : courbe dans le temps, F-51).
    // Les couleurs sont lues dans les jetons (--etat-<code>-fg, --texte, --surface).
    Alpine.data('graphique', function (idDonnees, urlChart) {
      return {
        chart: null,
        init: function () {
          var self = this;
          var dessiner = function () { self.dessiner(idDonnees); };
          document.addEventListener('themechange', dessiner);
          if (window.Chart) { dessiner(); return; }
          var s = document.createElement('script');
          s.src = urlChart;
          s.onload = dessiner;
          document.head.appendChild(s);
        },
        dessiner: function (id) {
          var noeud = document.getElementById(id), canvas = this.$refs.canvas;
          if (!noeud || !canvas || !window.Chart) { return; }
          var d = JSON.parse(noeud.textContent);
          var style = getComputedStyle(document.documentElement);
          var jeton = function (nom) { return style.getPropertyValue(nom).trim(); };
          var couleurs = d.etats.map(function (e) { return jeton('--etat-' + e + '-fg') || jeton('--texte'); });
          if (this.chart) { this.chart.destroy(); }
          this.chart = new Chart(canvas, {
            type: 'doughnut',
            data: { labels: d.libelles, datasets: [{ data: d.valeurs, backgroundColor: couleurs, borderColor: jeton('--surface'), borderWidth: 3, hoverOffset: 6 }] },
            options: { cutout: '66%', maintainAspectRatio: false, animation: reduit ? false : { duration: 700 }, plugins: { legend: { display: false } } }
          });
        }
      };
    });
  });

  /* ------------------------------------------------------------------ Bulles : messages Django du rendu complet */
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('#messages-django [data-niveau]').forEach(function (el) {
      D.bulle({ message: el.textContent.trim(), niveau: el.dataset.niveau });
    });
  });

  /* ------------------------------------------------------------------ Modale commune */
  var modale = null;
  var contenu = null;
  function lierModale() {
    if (!modale) { modale = document.getElementById('modale'); contenu = document.getElementById('modale-contenu'); }
    return !!modale;
  }
  function focaliser() {
    if (!lierModale()) { return; }
    var champ = contenu.querySelector('[autofocus], .feuille-corps input:not([type=hidden]):not([disabled]), .feuille-corps select, .feuille-corps textarea');
    var cible = champ || contenu.querySelector('.feuille-corps button, .feuille-corps a[href], .feuille-pied [type=submit]');
    if (cible) { cible.focus({ preventScroll: true }); }
  }
  function viderApresFermeture() {
    // La feuille fermée est retirée du DOM (identifiants de champs uniques à la prochaine ouverture)
    setTimeout(function () {
      if (lierModale() && modale.hidden) { contenu.replaceChildren(); }
    }, 450);
  }
  function fermerSiSquelette() {
    if (lierModale() && !modale.hidden && contenu.querySelector('[role=status]') && !contenu.querySelector('form')) {
      D.fermerModale('#modale');
      viderApresFermeture();
    }
  }
  document.addEventListener('modaleFermer', function () { D.fermerModale('#modale'); viderApresFermeture(); });
  document.addEventListener('click', function (e) {
    if (e.target.closest('[data-ferme-modale], .modale-voile')) { viderApresFermeture(); }
    if (e.target.closest('[data-retour]')) { history.back(); return; }
    // Modale alimentée par un <template> de la page (confirmation, formulaire existant sans fragment serveur)
    var local = e.target.closest('[data-modale-locale]');
    if (local && lierModale()) {
      var tpl = document.querySelector(local.getAttribute('data-modale-locale'));
      if (!tpl) { return; }
      contenu.replaceChildren(tpl.content.cloneNode(true));
      if (window.htmx) { htmx.process(contenu); }
      D.ouvrirModale('#modale');
      focaliser();
    }
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') { viderApresFermeture(); } });

  // Une requête GET qui cible la modale l'ouvre tout de suite avec un squelette (retour visuel immédiat en 3G)
  document.addEventListener('htmx:beforeRequest', function (e) {
    var cible = e.detail.target;
    var verbe = e.detail.requestConfig && e.detail.requestConfig.verb;
    if (cible && cible.id === 'modale-contenu' && verbe === 'get' && lierModale()) {
      var modele = document.getElementById('modale-squelette');
      if (modele) { contenu.replaceChildren(modele.content.cloneNode(true)); }
      D.ouvrirModale('#modale');
    }
  });
  document.addEventListener('htmx:afterSwap', function (e) {
    var cible = e.detail.target;
    if (cible && cible.id === 'modale-contenu' && cible.children.length) {
      D.ouvrirModale('#modale');
      focaliser();
    }
  });

  // Formulaires ordinaires (sans HTMX) : boutons d'envoi désactivés dès l'envoi, contre le double clic
  document.addEventListener('submit', function (e) {
    var f = e.target;
    if (e.defaultPrevented || f.hasAttribute('hx-post') || f.hasAttribute('hx-get')) { return; }
    var boutons = f.querySelectorAll('button[type=submit], button:not([type])');
    setTimeout(function () { boutons.forEach(function (b) { b.disabled = true; b.setAttribute('aria-busy', 'true'); }); }, 0);
  });
  window.addEventListener('pageshow', function (e) {
    if (e.persisted) { document.querySelectorAll('button[aria-busy=true]').forEach(function (b) { b.disabled = false; b.removeAttribute('aria-busy'); }); }
  });

  /* ------------------------------------------------------------------ File de validation : retrait des dossiers traités */
  // Le bouton porte hx-swap="outerHTML swap:900ms" et la réponse est vide : la ligne flashe puis disparaît.
  document.addEventListener('htmx:beforeSwap', function (e) {
    var cible = e.detail.target;
    if (cible && cible.classList && cible.classList.contains('dossier') && !(e.detail.serverResponse || '').trim()) {
      var declencheur = e.detail.requestConfig && e.detail.requestConfig.elt;
      var renvoye = declencheur && declencheur.dataset && declencheur.dataset.sens === 'renvoye';
      cible.classList.add(renvoye ? 'est-renvoye' : 'est-traite');
    }
  });
  // HX-Trigger {"fileMaj": {"compte": 37}} : compteurs du menu, de la barre basse et des onglets
  document.addEventListener('fileMaj', function (e) {
    var n = e.detail && e.detail.compte;
    if (n === undefined) { return; }
    document.querySelectorAll('[data-compte-file]').forEach(function (el) { D.majCompteur(el, String(n)); });
  });

  /* ------------------------------------------------------------------ HTMX : chargement, erreurs */
  var enCours = 0;
  function barre(actif) {
    var b = document.getElementById('chargement');
    if (b) { b.classList.toggle('htmx-request', actif); }
  }
  document.addEventListener('htmx:beforeRequest', function () { enCours++; barre(true); });
  document.addEventListener('htmx:afterRequest', function () { enCours = Math.max(0, enCours - 1); if (!enCours) { barre(false); } });
  document.addEventListener('htmx:afterOnLoad', function () {
    if (window.Alpine && Alpine.store('reseau').visible) { Alpine.store('reseau').cacher(); }
  });

  // Erreurs réseau ou serveur : message clair, bouton « Réessayer », saisie conservée (le DOM n'est pas remplacé)
  function requete(e) {
    var cfg = e.detail.requestConfig || {};
    var evt = cfg.triggeringEvent && cfg.triggeringEvent.type;
    return { elt: e.detail.elt, evenement: evt || 'click' };
  }
  function perdue(e) { fermerSiSquelette(); Alpine.store('reseau').montrer(T().connexionPerdue, requete(e)); }
  document.addEventListener('htmx:sendError', perdue);
  document.addEventListener('htmx:timeout', perdue);
  document.addEventListener('htmx:responseError', function (e) {
    fermerSiSquelette();
    var statut = e.detail.xhr.status;
    var texte = statut >= 500 ? T().erreurServeur : (statut === 403 ? T().refuse : T().introuvable);
    Alpine.store('reseau').montrer(texte, requete(e));
  });

  /* ------------------------------------------------------------------ Menu : page courante après navigation boostée */
  function majMenu() {
    var chemin = location.pathname;
    document.querySelectorAll('.menu a[href], .bas a[href]').forEach(function (a) {
      var prefixe = a.dataset.prefixe;
      var actif = a.getAttribute('href') === chemin || (prefixe && chemin.indexOf(prefixe) === 0);
      if (actif) { a.setAttribute('aria-current', 'page'); } else { a.removeAttribute('aria-current'); }
    });
    D.menu(false);
  }
  document.addEventListener('htmx:pushedIntoHistory', majMenu);
  document.addEventListener('htmx:historyRestore', majMenu);
})();
