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
          var suivant = -1;
          if (e.key === 'ArrowRight') { suivant = i + 1; }
          else if (e.key === 'ArrowLeft') { suivant = i - 1; }
          else if (e.key === 'Home') { suivant = 0; }
          else if (e.key === 'End') { suivant = liste.length - 1; }
          if (suivant < 0 || suivant >= liste.length) { return; }
          e.preventDefault();
          liste[suivant].focus();
          this.actif = liste[suivant].dataset.onglet;
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
    var local = e.target.closest('[data-modale-locale]');
    if (local) { ouvrirLocale(local.getAttribute('data-modale-locale')); }
  });
  // Modale alimentée par un <template> de la page (confirmation, formulaire existant sans fragment serveur)
  function ouvrirLocale(selecteur) {
    if (!lierModale()) { return; }
    var tpl = document.querySelector(selecteur);
    if (!tpl) { return; }
    contenu.replaceChildren(tpl.content.cloneNode(true));
    if (window.htmx) { htmx.process(contenu); }
    document.dispatchEvent(new CustomEvent('modaleLocale', { detail: selecteur }));
    D.ouvrirModale('#modale');
    focaliser();
  }
  // Un <template data-ouvrir> s'ouvre dès le chargement : formulaire réaffiché avec ses erreurs (fiche en statut 400)
  document.addEventListener('DOMContentLoaded', function () {
    var d = document.querySelector('template[data-ouvrir][id]');
    if (d) { ouvrirLocale('#' + d.id); }
  });
  // Motif obligatoire : un envoi sans motif est bloqué avec un message lisible (le serveur le vérifie aussi)
  document.addEventListener('submit', function (e) {
    var champ = e.target.querySelector && e.target.querySelector('[data-motif-requis] textarea');
    if (!champ) { return; }
    var erreur = document.getElementById(champ.getAttribute('aria-describedby'));
    if (!champ.value.trim()) {
      e.preventDefault();
      if (erreur) { erreur.hidden = false; }
      champ.setAttribute('aria-invalid', 'true');
      champ.focus();
    }
  }, true);
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

  /* ------------------------------------------------------------------ Suppression d'un membre : modale de confirmation avec action et motif */
  // Compteur du motif (500 caractères au plus)
  document.addEventListener('input', function (e) {
    var zone = e.target.closest && e.target.closest('[data-motif-requis]');
    var compteur = zone && zone.querySelector('[data-compteur-motif]');
    if (compteur) { compteur.textContent = e.target.value.length + ' / ' + (e.target.maxLength > 0 ? e.target.maxLength : 500); }
  });
  // Un formulaire de modale qui porte un champ « action » part par fetch : une réponse 409 (état du membre changé entre-temps)
  // devient une bulle claire ; sinon la page est rechargée et affiche le message flash du serveur.
  document.addEventListener('submit', function (e) {
    var f = e.target;
    if (e.defaultPrevented || !f.closest || !f.closest('.modale') || !f.querySelector('input[name=action]')) { return; }
    e.preventDefault();
    var libere = function () { f.querySelectorAll('button[aria-busy=true]').forEach(function (b) { b.disabled = false; b.removeAttribute('aria-busy'); }); };
    fetch(f.getAttribute('action'), { method: 'POST', body: new FormData(f), credentials: 'same-origin', redirect: 'manual', headers: { 'X-Requested-With': 'fetch' } })
      .then(function (r) {
        if (r.status === 409) {
          libere(); D.fermerModale('#modale'); viderApresFermeture();
          D.bulle({ message: f.dataset.texte409 || T().erreurServeur, niveau: 'danger' });
        } else if (r.type === 'opaqueredirect' || r.ok) {
          window.location.reload();
        } else {
          libere(); D.bulle({ message: r.status >= 500 ? T().erreurServeur : T().refuse, niveau: 'danger' });
        }
      })
      .catch(function () { libere(); D.bulle({ message: T().connexionPerdue, niveau: 'danger' }); });
  });

  /* ------------------------------------------------------------------ Liste filtrée : formulaire unique [data-filtres-form] */
  // Le formulaire porte la recherche, les puces (radios) et les filtres avancés (champs cachés) : la modale « Filtres » copie ses
  // valeurs dans ces champs, puis déclenche l'événement « filtres » (un seul envoi HTMX avec toutes les valeurs).
  var CHAMPS_AVANCES = ['qualite', 'antenne', 'association'];
  function formFiltres() { return document.querySelector('[data-filtres-form]'); }
  function majCompteFiltres() {
    var f = formFiltres();
    var pastille = f && f.querySelector('[data-filtres-compte]');
    if (!pastille) { return; }
    var n = CHAMPS_AVANCES.filter(function (nom) { return f.elements[nom] && f.elements[nom].value; }).length;
    pastille.textContent = n ? String(n) : '';
    pastille.hidden = !n;
  }
  function declencherFiltres() { var f = formFiltres(); majCompteFiltres(); if (f && window.htmx) { htmx.trigger(f, 'filtres'); } }
  function effacerFiltres() {
    var f = formFiltres();
    if (!f) { return; }
    CHAMPS_AVANCES.forEach(function (nom) { if (f.elements[nom]) { f.elements[nom].value = ''; } });
    if (f.elements.q) { f.elements.q.value = ''; }
    var tous = f.querySelector('input[name=etat][value=""]');
    if (tous) { tous.checked = true; }
    declencherFiltres();
  }
  document.addEventListener('modaleLocale', function (e) {
    var f = formFiltres();
    if (e.detail !== '#modale-filtres' || !f || !lierModale()) { return; }
    contenu.querySelectorAll('[data-filtre-champ]').forEach(function (s) { s.value = f.elements[s.dataset.filtreChamp].value; });
  });
  document.addEventListener('click', function (e) {
    var f = formFiltres();
    if (e.target.closest('[data-filtres-appliquer]') && f) {
      contenu.querySelectorAll('[data-filtre-champ]').forEach(function (s) { f.elements[s.dataset.filtreChamp].value = s.value; });
      D.fermerModale('#modale'); viderApresFermeture(); declencherFiltres();
    } else if (e.target.closest('[data-filtres-effacer]') && f) {
      D.fermerModale('#modale'); viderApresFermeture(); CHAMPS_AVANCES.forEach(function (nom) { f.elements[nom].value = ''; }); declencherFiltres();
    } else if (e.target.closest('[data-effacer-filtres]')) {
      e.preventDefault(); effacerFiltres();
    }
  });
  document.addEventListener('DOMContentLoaded', majCompteFiltres);
  // Après un changement de page : le focus revient en tête de la zone remplacée (le lien activé a disparu)
  document.addEventListener('htmx:afterSwap', function (e) {
    var cible = e.detail.target;
    var declencheur = e.detail.requestConfig && e.detail.requestConfig.elt;
    if (cible && cible.id === 'liste-zone' && declencheur && declencheur.closest && declencheur.closest('.pages, [data-effacer-filtres]')) {
      cible.focus({ preventScroll: true });
      cible.scrollIntoView({ block: 'start' });
    }
  });

  // Déconnexion : l'historique HTMX gardé dans le stockage local ne doit pas survivre à la session
  document.addEventListener('submit', function (e) {
    var action = e.target && e.target.getAttribute && e.target.getAttribute('action');
    if (action && /\/deconnexion\/?$/.test(action)) {
      try { localStorage.removeItem('htmx-history-cache'); } catch (err) { /* stockage refusé : rien à effacer */ }
    }
  });

  /* ------------------------------------------------------------------ File de validation : compteurs
   Le retrait animé d'un dossier traité (FenamoDesign.retirerDossier) sera branché avec la file de validation (F-23). */
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
