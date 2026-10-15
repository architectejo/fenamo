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

  /* ---------- Utilisateurs (F-02 à F-06) ---------- */
  var sprite = document.documentElement.dataset.sprite;
  function ic(nom) { return '<svg class="ic" aria-hidden="true" focusable="false"><use href="' + sprite + '#i-' + nom + '"></use></svg>'; }
  var ligneEnCours = null, nomEnCours = '';

  /* Onglets Comptes / Mandats (dans l'application : Alpine « onglets » ou liens ?onglet= servis par HTMX) */
  document.querySelectorAll('[data-demo-onglets]').forEach(function (liste) {
    var onglets = [].slice.call(liste.querySelectorAll('[role=tab]'));
    function choisir(o, focus) {
      onglets.forEach(function (x) {
        var actif = x === o, p = document.getElementById(x.getAttribute('aria-controls'));
        x.setAttribute('aria-selected', String(actif)); x.tabIndex = actif ? 0 : -1;
        if (p) { p.hidden = !actif; if (actif) { p.style.animation = 'none'; void p.offsetWidth; p.style.animation = 'page-entree var(--d-moyen) var(--courbe-sortie)'; } }
      });
      if (focus) { o.focus(); }
    }
    liste.addEventListener('click', function (e) { var o = e.target.closest('[role=tab]'); if (o) { choisir(o); } });
    liste.addEventListener('keydown', function (e) {
      var i = onglets.indexOf(document.activeElement); if (i < 0) { return; }
      if (e.key === 'ArrowRight') { choisir(onglets[(i + 1) % onglets.length], true); e.preventDefault(); }
      if (e.key === 'ArrowLeft') { choisir(onglets[(i - 1 + onglets.length) % onglets.length], true); e.preventDefault(); }
    });
    if (params.get('onglet') === 'mandats') { choisir(onglets[1]); }
  });
  if (params.get('filtres') === 'ouverts') { var fp = document.querySelector('[data-deplier]'); if (fp) { D.deplier(fp); } }

  /* Le bouton d'une ligne transmet le nom du compte à la modale qu'il ouvre */
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-demo-nom][data-ouvre-modale]'); if (!b) { return; }
    var m = document.querySelector(b.getAttribute('data-ouvre-modale'));
    ligneEnCours = b.closest('tr, .dossier'); nomEnCours = b.dataset.demoNom;
    m.querySelectorAll('[data-demo-sous-titre], [data-demo-nom-cible]').forEach(function (el) { el.textContent = nomEnCours; });
    var f = m.querySelector('[data-demo-fin-cible]'); if (f && b.dataset.demoFin) { f.textContent = b.dataset.demoFin; }
  });

  /* Mot de passe temporaire : alphabet sans 0 O 1 l I, trois groupes de quatre, chiffres balisés */
  function motDePasse() {
    var a = 'ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789', s = '';
    var t = new Uint32Array(12); crypto.getRandomValues(t);
    t.forEach(function (n) { s += a[n % a.length]; });
    return s;
  }
  function afficherMdp(titre, sousTitre, ident) {
    var m = document.getElementById('modale-mdp'), v = motDePasse(), p = m.querySelector('[data-demo-mdp]');
    p.dataset.valeur = v;
    p.innerHTML = [0, 4, 8].map(function (k) { return '<span>' + v.slice(k, k + 4).replace(/(\d)/g, '<b>$1</b>') + '</span>'; }).join('');
    m.querySelector('[data-demo-mdp-titre]').textContent = titre;
    m.querySelector('[data-demo-mdp-nom]').textContent = sousTitre;
    m.querySelector('[data-demo-mdp-ident]').textContent = ident;
    m.querySelector('.mdp-temp').classList.remove('est-copie');
    setTimeout(function () { D.ouvrirModale(m); }, reduit ? 0 : 240);
  }

  /* Nommer un membre : deux étapes, puis le mot de passe temporaire */
  document.querySelectorAll('[data-demo-nommer]').forEach(function (m) {
    var etape = 1, noms = ['Membre', 'Rôle, périmètre et mandat'];
    var suiv = m.querySelector('[data-demo-suivant]'), prec = m.querySelector('[data-demo-precedent]');
    var ROLES = {
      VN: { champs: ['national'], ans: 5, aide: 'Comité national : 5 ans (charte, art. 72 à 75).', libelle: 'validateur national' },
      VP: { champs: ['coordination'], ans: 4, aide: 'Coordination provinciale : 4 ans (charte, art. 72 à 75).', libelle: 'validateur provincial, coordination Kinshasa-Est' },
      VA: { champs: ['antenne'], ans: 3, aide: "Comité d'antenne : 3 ans (charte, art. 72 à 75).", libelle: "validateur d'antenne, antenne de Lemba" },
      AT: { champs: ['antenne', 'association'], ans: 3, aide: "Comité d'antenne : 3 ans (charte, art. 72 à 75).", libelle: 'agent de terrain, antenne de Lemba' }
    };
    function role() { var r = m.querySelector('[name=role]:checked'); return r ? r.value : 'AT'; }
    function montrer() {
      m.querySelectorAll('[data-etape]').forEach(function (p) { p.hidden = String(etape) !== p.dataset.etape; });
      m.querySelectorAll('.etapes span').forEach(function (s, k) { s.classList.toggle('fait', k < etape); });
      m.querySelector('[data-demo-etape-libelle]').textContent = 'Étape ' + etape + ' sur 2 · ' + noms[etape - 1];
      suiv.lastChild.textContent = etape === 2 ? 'Nommer le membre' : 'Continuer';
      prec.textContent = etape === 1 ? 'Annuler' : 'Retour';
      m.querySelector('.feuille-corps').scrollTop = 0;
    }
    m.addEventListener('change', function (e) {
      if (e.target.name === 'membre') {
        var n = e.target.dataset.demoMembre;
        m.querySelector('[data-demo-retenu-nom]').textContent = n;
        m.querySelector('[data-demo-retenu-initiales]').textContent = n.split(' ').map(function (x) { return x[0]; }).slice(0, 2).join('');
      }
      if (e.target.name === 'role') {
        var r = ROLES[role()];
        m.querySelectorAll('[data-demo-champ]').forEach(function (c) { c.hidden = r.champs.indexOf(c.dataset.demoChamp) < 0; });
        m.querySelector('[data-demo-fin]').value = '14/10/' + (2026 + r.ans);
        m.querySelector('[data-demo-fin-aide]').textContent = r.aide;
      }
    });
    var cherche = m.querySelector('[data-demo-cherche-membre]');
    cherche.addEventListener('input', function () {
      var q = cherche.value.trim().toLowerCase();
      m.querySelectorAll('[data-demo-resultats] li').forEach(function (li) { li.hidden = q.length > 1 && li.textContent.toLowerCase().indexOf(q) < 0; });
    });
    suiv.addEventListener('click', function () {
      if (etape < 2) { etape++; montrer(); return; }
      occuper(suiv, 800).then(function () {
        var nom = m.querySelector('[data-demo-retenu-nom]').textContent, r = ROLES[role()];
        D.fermerModale(m);
        afficherMdp('Membre nommé', nom + ' · ' + r.libelle, nom.split(' ')[0][0].toLowerCase() + '.' + nom.split(' ')[1].toLowerCase());
        etape = 1; montrer();
      });
    });
    prec.addEventListener('click', function () { if (etape === 1) { D.fermerModale(m); } else { etape--; montrer(); } });
    m.querySelector('[data-demo-precedent-membre]').addEventListener('click', function () { etape = 1; montrer(); });
    if (params.get('etape') === '2') { etape = 2; montrer(); }
  });

  /* Compte externe : le champ du périmètre suit la tuile choisie */
  document.querySelectorAll('[data-demo-portee]').forEach(function (g) {
    g.addEventListener('change', function (e) {
      document.querySelectorAll('[data-demo-portee-champ]').forEach(function (c) { c.hidden = c.dataset.demoPorteeChamp !== e.target.value; });
    });
  });

  /* Envois simulés */
  document.querySelectorAll('[data-demo-mdp-apres] form, [data-demo-simple] form, [data-demo-desactiver] form, [data-demo-renouveler] form').forEach(function (f) {
    var m = f.closest('.modale');
    f.addEventListener('submit', function (e) {
      e.preventDefault();
      var b = f.querySelector('[type=submit]');
      if (m.hasAttribute('data-demo-desactiver')) {
        var champ = f.querySelector('[data-demo-champ-motif]'), t = champ.querySelector('textarea'), err = champ.querySelector('.champ-erreur');
        if (!t.value.trim()) { champ.classList.add('champ--erreur'); t.setAttribute('aria-invalid', 'true'); err.hidden = false; err.style.animation = 'none'; void err.offsetWidth; err.style.animation = ''; t.focus(); return; }
        champ.classList.remove('champ--erreur'); t.removeAttribute('aria-invalid'); err.hidden = true;
      }
      occuper(b, 700).then(function () {
        D.fermerModale(m);
        var nom = nomEnCours || (m.querySelector('[data-demo-nom-cible]') || {}).textContent || '';
        if (m.hasAttribute('data-demo-mdp-apres')) {
          var msg = m.getAttribute('data-demo-mdp-apres');
          var externe = m.id === 'modale-externe';
          if (externe) { nom = document.getElementById('x-prenom').value + ' ' + document.getElementById('x-nom').value; }
          /* Pas de bulle ici : le titre de la modale du mot de passe reprend déjà le verbe (« Membre nommé », « Compte créé »). */
          afficherMdp(msg, externe ? nom + ' · visiteur' : nom, externe ? document.getElementById('x-ident').value : 'vi.kalala');
        } else if (m.hasAttribute('data-demo-desactiver')) {
          D.bulle({ message: 'Compte désactivé', detail: nom + ' ne peut plus se connecter. Le compte reste dans la liste.', niveau: 'success' });
          if (ligneEnCours && ligneEnCours.tagName === 'TR') {
            ligneEnCours.querySelector('[data-demo-etat]').innerHTML = '<span class="etat etat--supprime change">' + ic('ban') + 'Désactivé</span>';
            ligneEnCours.querySelector('[data-demo-actions]').innerHTML = '<div class="actions-ligne actions-ligne--seule"><button type="button" class="bouton action-ligne" data-ouvre-modale="#modale-reactiver" data-demo-nom="' + nom + '" title="Réactiver le compte">' + ic('user-check') + '<span class="action-ligne-texte">Réactiver<span class="lecteur"> le compte de ' + nom + '</span></span></button></div>';
          } else if (ligneEnCours) { D.retirerDossier(ligneEnCours, 'renvoye'); decrementerMandats(); }
          f.querySelector('textarea').value = '';
        } else if (m.hasAttribute('data-demo-renouveler')) {
          D.bulle({ message: 'Mandat renouvelé', detail: nom + ' reste en fonction jusqu\'au ' + document.getElementById('r-fin').value + '.', niveau: 'success' });
          if (ligneEnCours) { D.retirerDossier(ligneEnCours, 'traite'); decrementerMandats(); }
        } else {
          var parts = m.getAttribute('data-demo-simple').split('|');
          D.bulle({ message: parts[0], detail: m.id === 'modale-reactiver' ? nom + ' peut de nouveau se connecter.' : parts[1], niveau: 'success' });
          if (m.id === 'modale-reactiver' && ligneEnCours && ligneEnCours.tagName === 'TR') {
            ligneEnCours.querySelector('[data-demo-etat]').innerHTML = '<span class="etat etat--actif change">' + ic('circle-check') + 'Actif</span>';
          }
        }
      });
    });
  });
  function decrementerMandats() {
    document.querySelectorAll('[data-demo-compte-mandats]').forEach(function (el) { var n = parseInt(el.textContent, 10) - 1; if (n >= 0) { D.majCompteur(el, String(n)); } });
  }

  /* Motif : suggestions et compteur de caractères */
  document.addEventListener('click', function (e) {
    var p = e.target.closest('[data-demo-motif-puce]'); if (!p) { return; }
    var t = p.closest('.champ').querySelector('textarea');
    t.value = (t.value ? t.value + ' ' : '') + p.textContent + '.'; t.dispatchEvent(new Event('input', { bubbles: true })); t.focus();
  });
  /* (Le compteur de caractères est fourni par design.js : [data-compte-caracteres].) */

  /* ---------- Verrouillage de l'application (F-07) ---------- */
  var ouvert = document.querySelector('[data-demo-verrou="ouvert"]'), ferme = document.querySelector('[data-demo-verrou="ferme"]');
  function etatVerrou(estFerme, anime) {
    ouvert.hidden = estFerme; ferme.hidden = !estFerme;
    document.querySelector('[data-demo-bandeau]').hidden = !estFerme;
    document.querySelectorAll('[data-demo-entree-verrou]').forEach(function (li) { li.hidden = !estFerme; if (anime && estFerme) { li.classList.add('apparait'); } });
    var mi = document.querySelector('[data-demo-menu-icone] use'); if (mi) { mi.setAttribute('href', sprite + (estFerme ? '#i-lock' : '#i-lock-open')); }
    if (anime) {
      var panneau = estFerme ? ferme : ouvert;
      panneau.querySelectorAll('.verrou-sceau, .verrou-etat').forEach(function (el) { el.classList.remove('change'); void el.offsetWidth; el.classList.add('change'); });
    }
  }
  if (ouvert && ferme) {
    if (params.get('etat') === 'verrouillee') { etatVerrou(true, false); }
    var fv = document.querySelector('[data-demo-verrouiller]'), fd = document.querySelector('[data-demo-deverrouiller]');
    fv.addEventListener('submit', function (e) {
      e.preventDefault();
      var champ = fv.querySelector('[data-demo-champ-message]'), t = champ.querySelector('textarea'), err = champ.querySelector('.champ-erreur');
      if (!t.value.trim()) { champ.classList.add('champ--erreur'); t.setAttribute('aria-invalid', 'true'); err.hidden = false; err.style.animation = 'none'; void err.offsetWidth; err.style.animation = ''; t.focus(); champ.scrollIntoView({ block: 'center' }); return; }
      champ.classList.remove('champ--erreur'); t.removeAttribute('aria-invalid'); err.hidden = true;
      var b = fv.querySelector('[type=submit]');
      occuper(b, 800).then(function () {
        D.fermerModale('#modale-verrouiller');
        document.querySelector('[data-demo-message-affiche]').textContent = t.value.trim();
        var motif = document.getElementById('v-motif').value.trim();
        document.querySelector('[data-demo-motif-affiche]').textContent = motif || 'Aucun motif saisi.';
        document.querySelectorAll('[data-demo-duree]').forEach(function (d) { d.textContent = 'quelques secondes'; });
        etatVerrou(true, true);
        D.bulle({ message: 'Application verrouillée', detail: '212 sessions fermées. Vous restez connecté.', niveau: 'success' });
      });
    });
    fd.addEventListener('submit', function (e) {
      e.preventDefault();
      var b = fd.querySelector('[type=submit]');
      occuper(b, 700).then(function () {
        D.fermerModale('#modale-deverrouiller');
        etatVerrou(false, true);
        var motif = document.getElementById('d-motif').value.trim();
        document.querySelector('[data-demo-historique]').insertAdjacentHTML('afterbegin', '<li class="apparait"><span class="point point--vert">' + ic('lock-open') + '</span><div><p><strong>Déverrouillée</strong> par vous</p><p class="meta">à l\'instant</p><p class="petit doux texte-saisi"></p></div></li>');
        document.querySelector('[data-demo-historique] li .texte-saisi').textContent = motif ? 'Motif : ' + motif : 'Sans motif';
        D.bulle({ message: 'Application déverrouillée', detail: 'Les comptes peuvent de nouveau se connecter.', niveau: 'success' });
      });
    });
    /* Captures : ?modale=modale-verrouiller&remplir=1 (message saisi), &erreur=1 (message manquant) */
    if (params.get('remplir')) {
      var tm = document.getElementById('v-message');
      tm.value = "Migration des données vers le nouveau serveur.\nL'application rouvre aujourd'hui à 12 h. Vos dossiers sont conservés : reprenez vos saisies à la réouverture.";
      document.getElementById('v-motif').value = 'Bascule SQLite vers MySQL (lot 9). Sauvegarde faite à 07 h 30.';
      [tm, document.getElementById('v-motif')].forEach(D.compterCaracteres);
    }
    if (params.get('erreur')) { setTimeout(function () { fv.requestSubmit(); }, 400); }
  }

  /* Connexion pendant le verrouillage : ?verrou=1 */
  if (params.get('verrou')) { document.querySelectorAll('[data-demo-verrou-connexion]').forEach(function (el) { el.hidden = false; }); }

  /* Ouverture directe d'une modale (captures) : ?modale=modale-renvoi */
  if (params.get('modale')) { D.ouvrirModale('#' + params.get('modale')); }
  if (params.get('menu') === 'ouvert') { D.menu(true); }
  if (params.get('bulle')) { D.bulle({ message: 'Membre validé', detail: 'Trésor Lutete Nsimba passe à « validé province ».', niveau: 'success', duree: 60000 }); }
})();
