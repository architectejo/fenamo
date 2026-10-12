/* FENAMO-RDC : comportements communs HTMX + Alpine (aucune autre dépendance).
   Chargé avant Alpine (les deux en defer) pour que alpine:init soit entendu.
   Les textes viennent de window.FENAMO_TEXTES (défini dans base.html, traduit). */
(function () {
  'use strict';

  var T = function () { return window.FENAMO_TEXTES || {}; };

  document.addEventListener('alpine:init', function () {
    var grand = window.matchMedia('(min-width: 992px)');

    // Coque : menu latéral repliable (téléphone : tiroir ; ordinateur : replié / déplié)
    Alpine.data('coque', function () {
      return {
        ouvert: false,
        ferme: false,
        basculer: function () { if (grand.matches) { this.ferme = !this.ferme; } else { this.ouvert = !this.ouvert; } },
        fermerTiroir: function () { this.ouvert = false; },
        estOuvert: function () { return grand.matches ? !this.ferme : this.ouvert; }
      };
    });

    // Toasts alimentés par HX-Trigger (événement « toast ») ou par les messages Django d'un rendu complet
    Alpine.data('toasts', function () {
      return {
        items: [],
        suivant: 1,
        init: function () {
          var self = this;
          document.querySelectorAll('#messages-django [data-niveau]').forEach(function (el) {
            self.ajouter({ message: el.textContent.trim(), niveau: el.dataset.niveau });
          });
        },
        ajouter: function (detail) {
          var liste = Array.isArray(detail) ? detail : [detail];
          var self = this;
          liste.forEach(function (d) {
            if (!d || !d.message) { return; }
            var niveau = d.niveau === 'error' ? 'danger' : (d.niveau || 'info');
            var toast = { id: self.suivant++, message: d.message, niveau: niveau };
            self.items.push(toast);
            setTimeout(function () { self.retirer(toast.id); }, niveau === 'danger' ? 9000 : 5000);
          });
        },
        retirer: function (id) { this.items = this.items.filter(function (t) { return t.id !== id; }); }
      };
    });

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
  });

  // Modale commune (Bootstrap) chargée par HTMX dans #modale-contenu
  function modale() {
    var el = document.getElementById('modale');
    return el ? bootstrap.Modal.getOrCreateInstance(el) : null;
  }
  document.addEventListener('htmx:afterSwap', function (e) {
    var cible = e.detail.target;
    if (cible && cible.id === 'modale-contenu' && cible.children.length) {
      var m = modale();
      if (m) { m.show(); }
    }
  });
  document.addEventListener('modaleFermer', function () {
    var m = modale();
    if (m) { m.hide(); }
  });
  document.addEventListener('hidden.bs.modal', function (e) {
    if (e.target.id === 'modale') { document.getElementById('modale-contenu').replaceChildren(); }
  });
  document.addEventListener('shown.bs.modal', function (e) {
    var champ = e.target.querySelector('[autofocus], input:not([type=hidden]), select, textarea');
    if (champ) { champ.focus(); }
  });

  // Indicateur de chargement global (barre en haut de page)
  var enCours = 0;
  document.addEventListener('htmx:beforeRequest', function () {
    enCours++;
    document.body.classList.add('chargement-actif');
  });
  document.addEventListener('htmx:afterRequest', function () {
    enCours = Math.max(0, enCours - 1);
    if (!enCours) { document.body.classList.remove('chargement-actif'); }
  });
  document.addEventListener('htmx:afterOnLoad', function () {
    if (window.Alpine && Alpine.store('reseau').visible) { Alpine.store('reseau').cacher(); }
  });

  // Erreurs réseau ou serveur : message clair, bouton « Réessayer », saisie conservée (le DOM n'est pas remplacé)
  function requete(e) {
    var cfg = e.detail.requestConfig || {};
    var evt = cfg.triggeringEvent && cfg.triggeringEvent.type;
    return { elt: e.detail.elt, evenement: evt || 'click' };
  }
  function perdue(e) { Alpine.store('reseau').montrer(T().connexionPerdue, requete(e)); }
  document.addEventListener('htmx:sendError', perdue);
  document.addEventListener('htmx:timeout', perdue);
  document.addEventListener('htmx:responseError', function (e) {
    var statut = e.detail.xhr.status;
    var texte = statut >= 500 ? T().erreurServeur : (statut === 403 ? T().refuse : T().introuvable);
    Alpine.store('reseau').montrer(texte, requete(e));
  });

  // Menu : page courante (aria-current) après une navigation boostée
  function majMenu() {
    var chemin = location.pathname;
    document.querySelectorAll('#menu-principal a[href]').forEach(function (a) {
      if (a.getAttribute('href') === chemin) { a.setAttribute('aria-current', 'page'); }
      else { a.removeAttribute('aria-current'); }
    });
    if (window.Alpine) {
      var coque = document.getElementById('app');
      if (coque && coque._x_dataStack) { coque._x_dataStack[0].fermerTiroir(); }
    }
  }
  document.addEventListener('htmx:pushedIntoHistory', majMenu);
  document.addEventListener('htmx:historyRestore', majMenu);
})();
