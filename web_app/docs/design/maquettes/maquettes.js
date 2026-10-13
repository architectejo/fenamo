/* Maquettes uniquement : simule les réponses du serveur (HTMX) pour montrer les micro-interactions.
   Ne pas intégrer : dans l'application, ces comportements viennent des vues Django + fenamo.js + design.js. */
(function () {
  'use strict';
  var D = window.FenamoDesign;
  var params = new URLSearchParams(location.search);
  var reduit = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  function attendre(ms) { return new Promise(function (r) { setTimeout(r, reduit ? Math.min(ms, 300) : ms); }); }
  function occuper(b, ms) { b.setAttribute('aria-busy', 'true'); b.disabled = true; return attendre(ms).then(function () { b.removeAttribute('aria-busy'); b.disabled = false; }); }
  function decrementer() {
    document.querySelectorAll('[data-demo-compte]').forEach(function (el) {
      var n = parseInt(el.textContent, 10) - 1; if (n >= 0) { D.majCompteur(el, String(n)); }
    });
  }

  /* Barre de chargement pendant une « requête » */
  function requete(ms) { document.body.classList.add('htmx-request'); return attendre(ms).then(function () { document.body.classList.remove('htmx-request'); }); }

  /* File de validation : valider */
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-demo-valider]');
    if (!b) { return; }
    var li = b.closest('.dossier');
    occuper(b, 700).then(function () {
      var badge = li.querySelector('.etat');
      badge.className = 'etat etat--valide_province change';
      badge.innerHTML = '<span class="etat-pastilles" aria-hidden="true"><i class="plein"></i><i class="plein"></i><i></i></span>Validé province';
      D.retirerDossier(li, 'traite');
      decrementer();
      D.bulle({ message: 'Membre validé', detail: b.dataset.nom + ' passe à « validé province ».', niveau: 'success' });
      setTimeout(function () { if (!document.querySelector('[data-demo-file] .dossier')) { var v = document.querySelector('[data-demo-vide]'); if (v) { v.hidden = false; } } }, 1300);
    });
  });

  /* Renvoyer : ouvre la modale avec le nom du dossier */
  var dossierEnCours = null;
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-demo-renvoyer]');
    if (!b) { return; }
    dossierEnCours = b.closest('.dossier');
    var n = document.querySelector('[data-demo-renvoi-nom]');
    if (n) { n.textContent = b.dataset.nom + ' · ' + dossierEnCours.querySelector('.ident').textContent; }
    D.ouvrirModale('#modale-renvoi');
  });
  document.addEventListener('click', function (e) {
    var p = e.target.closest('[data-demo-motif]');
    if (!p) { return; }
    var t = p.closest('.champ').querySelector('textarea');
    t.value = (t.value ? t.value + ' ' : '') + p.textContent + '.'; t.focus();
  });
  document.querySelectorAll('[data-demo-form-renvoi]').forEach(function (f) {
    f.addEventListener('submit', function (e) {
      e.preventDefault();
      var champ = f.querySelector('[data-demo-champ-motif]'), t = champ.querySelector('textarea'), err = champ.querySelector('.champ-erreur');
      if (!t.value.trim()) {
        champ.classList.add('champ--erreur'); t.setAttribute('aria-invalid', 'true'); err.hidden = false;
        err.style.animation = 'none'; void err.offsetWidth; err.style.animation = ''; t.focus(); return;
      }
      var b = f.querySelector('[type=submit]');
      occuper(b, 700).then(function () {
        D.fermerModale('#modale-renvoi');
        champ.classList.remove('champ--erreur'); t.removeAttribute('aria-invalid'); err.hidden = true; t.value = '';
        if (dossierEnCours) { D.retirerDossier(dossierEnCours, 'renvoye'); decrementer(); }
        D.bulle({ message: 'Dossier renvoyé à l\'antenne', detail: 'Le validateur de l\'antenne est notifié.', niveau: 'info' });
      });
    });
  });

  /* Fiche : valider */
  var vf = document.querySelector('[data-demo-valider-fiche]');
  if (vf) {
    vf.addEventListener('click', function () {
      occuper(vf, 700).then(function () {
        var zone = document.querySelector('[data-demo-etat-fiche]');
        zone.innerHTML = '<span class="etat etat--valide_province change"><span class="etat-pastilles" aria-hidden="true"><i class="plein"></i><i class="plein"></i><i></i></span>Validé province</span>';
        var c = document.querySelectorAll('[data-demo-circuit] li');
        c[2].className = 'fait'; c[2].querySelector('.quand').textContent = '12/10 · vous'; c[3].className = 'courant';
        var h = document.querySelector('[data-demo-historique]');
        h.insertAdjacentHTML('afterbegin', '<li class="apparait"><span class="point point--ciel"><svg class="ic" aria-hidden="true"><use href="' + document.documentElement.dataset.sprite + '#i-check"></use></svg></span><div><p><strong>Validé province</strong> par vous</p><p class="meta">à l\'instant</p></div></li>');
        vf.hidden = true;
        D.bulle({ message: 'Membre validé', detail: 'Il attend maintenant la validation nationale.', niveau: 'success' });
      });
    });
  }

  /* Puces de filtre : la zone pâlit, squelettes, puis résultats */
  document.querySelectorAll('[data-demo-puces]').forEach(function (g) {
    g.addEventListener('click', function (e) {
      var p = e.target.closest('.puce'); if (!p) { return; }
      g.querySelectorAll('.puce').forEach(function (x) { x.setAttribute('aria-pressed', String(x === p)); });
      var file = document.querySelector('[data-demo-file]'), sq = document.querySelector('[data-demo-squelette]');
      if (!file || !sq) { return; }
      file.hidden = true; sq.hidden = false;
      requete(650).then(function () { sq.hidden = true; file.hidden = false; file.style.animation = 'page-entree var(--d-moyen) var(--courbe-sortie)'; });
    });
  });

  /* Recherche globale : résultats pendant la frappe */
  document.querySelectorAll('[data-demo-recherche]').forEach(function (r) {
    var i = r.querySelector('input'), res = r.querySelector('.recherche-resultats');
    if (!res) { return; }
    i.addEventListener('input', function () { res.hidden = i.value.trim().length < 2; });
    i.addEventListener('blur', function () { setTimeout(function () { res.hidden = true; }, 150); });
  });

  /* Notifications */
  document.querySelectorAll('[data-demo-notifs]').forEach(function (n) {
    var b = n.querySelector('button'), p = n.querySelector('.flottant');
    b.addEventListener('click', function () { p.hidden = !p.hidden; b.setAttribute('aria-expanded', String(!p.hidden)); });
    document.addEventListener('click', function (e) { if (!n.contains(e.target)) { p.hidden = true; b.setAttribute('aria-expanded', 'false'); } });
  });

  /* Modale à étapes */
  document.querySelectorAll('[data-demo-etapes]').forEach(function (m) {
    var etape = 1, noms = ['Identité', 'Rattachement', 'Pièces'];
    var suiv = m.querySelector('[data-demo-suivant]'), prec = m.querySelector('[data-demo-precedent]');
    function montrer() {
      m.querySelectorAll('[data-etape]').forEach(function (p) { p.hidden = String(etape) !== p.dataset.etape; });
      m.querySelectorAll('.etapes span').forEach(function (s, k) { s.classList.toggle('fait', k < etape); });
      m.querySelector('[data-demo-etape-libelle]').textContent = 'Étape ' + etape + ' sur 3 · ' + noms[etape - 1];
      suiv.lastChild.textContent = etape === 3 ? 'Enregistrer le membre' : 'Continuer';
      prec.textContent = etape === 1 ? 'Annuler' : 'Retour';
      m.querySelector('.feuille-corps').scrollTop = 0;
    }
    suiv.addEventListener('click', function () {
      if (etape < 3) { etape++; montrer(); return; }
      occuper(suiv, 900).then(function () {
        D.fermerModale(m);
        D.bulle({ message: 'Membre enregistré', detail: 'Héritier Mukendi Kasongo · MBR0004127. Le dossier part à l\'antenne de Lemba.', niveau: 'success' });
        etape = 1; montrer();
      });
    });
    prec.addEventListener('click', function () { if (etape === 1) { D.fermerModale(m); } else { etape--; montrer(); } });
    var ph = m.querySelector('[data-demo-photo]');
    if (ph) {
      ph.addEventListener('change', function () {
        var f = ph.files[0]; if (!f) { return; }
        var r = new FileReader(); r.onload = function () { m.querySelector('[data-demo-apercu]').innerHTML = '<img alt="Aperçu de la photo" src="' + r.result + '">'; }; r.readAsDataURL(f);
      });
    }
    if (m.classList.contains('est-ouverte')) { m.hidden = false; document.documentElement.style.overflow = 'hidden'; }
  });

  /* Connexion */
  var fc = document.querySelector('[data-demo-connexion]');
  if (fc) {
    fc.addEventListener('submit', function (e) {
      e.preventDefault();
      var b = fc.querySelector('[type=submit]');
      occuper(b, 900).then(function () { document.querySelector('[data-demo-erreur]').hidden = false; document.getElementById('mdp').focus(); });
    });
    var vm = document.querySelector('[data-demo-voir-mdp]');
    vm.addEventListener('click', function () {
      var i = document.getElementById('mdp'), voir = i.type === 'password';
      i.type = voir ? 'text' : 'password'; vm.setAttribute('aria-pressed', String(voir));
      vm.setAttribute('aria-label', voir ? 'Masquer le mot de passe' : 'Afficher le mot de passe');
      vm.querySelector('use').setAttribute('href', document.documentElement.dataset.sprite + (voir ? '#i-eye-off' : '#i-eye'));
    });
  }

  /* Vérification : bascule valide / non valide */
  var bv = document.querySelector('[data-demo-basculer-verif]');
  if (bv) {
    bv.addEventListener('click', function () {
      var v = document.querySelector('[data-demo-verif="valide"]'), n = document.querySelector('[data-demo-verif="invalide"]');
      v.hidden = !v.hidden; n.hidden = !n.hidden;
      bv.textContent = n.hidden ? 'Voir le cas « carte non valide »' : 'Voir le cas « carte valide »';
    });
    if (params.get('etat') === 'invalide') { bv.click(); }
  }

  /* Catalogue : bulles */
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-demo-bulle]'); if (!b) { return; }
    if (b.dataset.demoBulle === 'succes') { D.bulle({ message: 'Engin enregistré', detail: 'Numéro attribué : 00148 KN-E.', niveau: 'success' }); }
    else { D.bulle({ message: 'Enregistrement impossible', detail: 'Le numéro de châssis existe déjà. Vérifiez la saisie.', niveau: 'danger' }); }
  });

  /* Ouverture directe d'une modale (captures) : ?modale=modale-renvoi */
  if (params.get('modale')) { D.ouvrirModale('#' + params.get('modale')); }
  if (params.get('menu') === 'ouvert') { D.menu(true); }
  if (params.get('bulle')) { D.bulle({ message: 'Membre validé', detail: 'Trésor Lutete Nsimba passe à « validé province ».', niveau: 'success', duree: 60000 }); }
})();
