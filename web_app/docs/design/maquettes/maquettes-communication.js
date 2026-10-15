/* Maquettes uniquement (communiqués F-40, données réelles F-67, messages de contact F-62) : simule les réponses du serveur.
   Ne pas intégrer : dans l'application, ces comportements viennent des vues Django, de HTMX et d'Alpine.
   Paramètres de capture : communiques.html?etat=vide|aucun|a-jour · ?modale=modale-publier&cible=antenne&remplir=1 · &erreur=1
   donnees-reelles.html?etat=reel · ?modale=modale-activer · message-contact.html?etat=traite · messages-contact.html?etat=vide */
(function () {
  'use strict';
  var D = window.FenamoDesign;
  var params = new URLSearchParams(location.search);
  var reduit = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  function attendre(ms) { return new Promise(function (r) { setTimeout(r, reduit ? Math.min(ms, 300) : ms); }); }
  function occuper(b, ms) { b.setAttribute('aria-busy', 'true'); b.disabled = true; return attendre(ms).then(function () { b.removeAttribute('aria-busy'); b.disabled = false; }); }
  function icHtml(n) { return D.icone(n).outerHTML; }
  function vue(nom) { document.querySelectorAll('[data-vue]').forEach(function (v) { v.hidden = v.dataset.vue !== nom; }); }

  /* ---------- Communiqués : états de la liste ---------- */
  var etat = params.get('etat');
  if (document.querySelector('.communiques')) {
    if (etat === 'vide' || etat === 'aucun' || etat === 'a-jour') {
      vue(etat);
      var resume = document.querySelector('.resume-liste'); if (resume) { resume.hidden = true; }
      if (etat === 'aucun') { document.getElementById('q').value = 'gilets'; document.getElementById('f-coordination').value = 'KOC'; document.querySelector('.filtres-deplier').insertAdjacentHTML('beforeend', '<span class="ident">1</span>'); }
      if (etat === 'a-jour') { document.querySelector('[name=etat][value=non_lus]').checked = true; }
      if (etat === 'vide') { document.querySelector('.filtres-communiques').hidden = true; }
    }
    document.querySelectorAll('[data-demo-etat-lecture] input').forEach(function (r) {
      r.addEventListener('change', function () {
        var nonLus = r.value === 'non_lus';
        document.querySelectorAll('.communique-ligne').forEach(function (li) { li.hidden = nonLus && li.dataset.lu === 'oui'; });
        document.querySelector('.pages').hidden = nonLus;
      });
    });
  }

  /* ---------- Modale de publication ---------- */
  var fp = document.querySelector('[data-demo-publier]');
  if (fp) {
    var RESUMES = {
      national: 'Reçu par tous les comptes actifs : président, validateurs, agents de terrain de toutes les coordinations et super-utilisateurs.',
      coordination: 'Reçu par le validateur provincial, les validateurs et agents de toutes ses antennes, le président, les validateurs nationaux et les super-utilisateurs.',
      antenne: 'Reçu par le validateur et les agents de cette antenne, le validateur de sa coordination, le président, les validateurs nationaux et les super-utilisateurs.'
    };
    var selCoord = document.getElementById('c-coordination'), selAnt = document.getElementById('c-antenne');
    function cible() { return fp.querySelector('[name=cible]:checked').value; }
    function etiquette() {
      var c = cible();
      if (c === 'coordination' && selCoord.value) {
        var nom = selCoord.options[selCoord.selectedIndex].text;
        return '<span class="portee"><span class="portee-texte">Coordination ' + nom + '</span><span class="portee-code" aria-hidden="true">' + selCoord.value + '</span></span>';
      }
      if (c === 'antenne' && selAnt.value) { return '<span class="portee"><span class="portee-texte">Antenne de ' + selAnt.value + '</span></span>'; }
      if (c === 'national') { return '<span class="portee portee--national"><span class="portee-texte">National</span></span>'; }
      return '<span class="portee"><span class="portee-texte">' + (c === 'coordination' ? 'Coordination à choisir' : 'Antenne à choisir') + '</span></span>';
    }
    function maj() {
      var c = cible();
      fp.querySelectorAll('[data-cible-champ]').forEach(function (ch) {
        var actif = ch.dataset.cibleChamp === c; ch.hidden = !actif; ch.querySelector('select').disabled = !actif;
      });
      fp.querySelector('[data-demo-resume-portee]').innerHTML = etiquette();
      fp.querySelector('[data-demo-resume-texte]').textContent = RESUMES[c];
    }
    fp.addEventListener('change', maj);
    function erreur(nom, el, montrer) {
      var p = document.getElementById(el.id + '-erreur'); if (p) { p.hidden = !montrer; }
      if (montrer) { el.setAttribute('aria-invalid', 'true'); } else { el.removeAttribute('aria-invalid'); }
      return montrer;
    }
    fp.addEventListener('submit', function (e) {
      e.preventDefault();
      var t = document.getElementById('c-titre'), m = document.getElementById('c-message'), c = cible();
      var n = 0, premier = null;
      [[t, !t.value.trim()], [m, !m.value.trim()], [selCoord, c === 'coordination' && !selCoord.value], [selAnt, c === 'antenne' && !selAnt.value]].forEach(function (x) {
        if (erreur(null, x[0], x[1])) { n += 1; premier = premier || x[0]; }
      });
      var g = fp.querySelector('[data-demo-erreur-generale]');
      if (n) {
        g.querySelector('div').innerHTML = '<strong class="alerte-titre">Le communiqué n’est pas publié.</strong>' + (n > 1 ? 'Corrigez les ' + n + ' champs signalés.' : 'Corrigez le champ signalé.');
        g.hidden = false; premier.focus(); return;
      }
      g.hidden = true;
      var b = fp.querySelector('[type=submit]');
      occuper(b, 900).then(function () {
        D.fermerModale('#modale-publier');
        var dest = c === 'national' ? 'Envoyé à toute la fédération.' : c === 'coordination' ? 'Envoyé à la coordination ' + selCoord.options[selCoord.selectedIndex].text + '.' : 'Envoyé à l’antenne de ' + selAnt.value + '.';
        D.bulle({ message: 'Communiqué publié', detail: dest, niveau: 'success' });
        var ul = document.querySelector('.communiques');
        if (ul) {
          var li = document.createElement('li'); li.className = 'communique-ligne'; li.dataset.lu = 'oui';
          li.innerHTML = '<div class="communique-tete">' + etiquette() + '<time class="communique-quand">À l’instant</time></div><h2 class="communique-titre"><a class="communique-lien" href="#"></a></h2><p class="communique-apercu"></p>';
          li.querySelector('a').textContent = t.value.trim(); li.querySelector('.communique-apercu').textContent = m.value.trim();
          ul.insertBefore(li, ul.firstChild);
        }
        fp.reset(); maj(); [t, m].forEach(D.compterCaracteres);
      });
    });
    if (params.get('cible')) { var r = fp.querySelector('[name=cible][value=' + params.get('cible') + ']'); if (r) { r.checked = true; } }
    if (params.get('remplir')) {
      document.getElementById('c-titre').value = 'Contrôle conjoint avec la police de circulation routière à Limete';
      document.getElementById('c-message').value = "Du lundi 19 au samedi 24 octobre, la police de circulation routière et la coordination Kinshasa-Est contrôlent ensemble les engins au rond-point Ngaba et sur le boulevard Lumumba, de 6 h à 18 h.\n\nChaque motard porte son gilet numéroté et présente sa carte de membre.";
      if (params.get('cible') === 'antenne') { maj(); selAnt.value = 'Limete'; }
      if (params.get('cible') === 'coordination') { maj(); selCoord.value = 'KN-E'; }
      [document.getElementById('c-titre'), document.getElementById('c-message')].forEach(D.compterCaracteres);
    }
    maj();
    if (params.get('erreur')) { setTimeout(function () { fp.requestSubmit(); }, 450); }
  }

  /* ---------- Données réelles du site (F-67) ---------- */
  function etatDr(reel, anime) {
    var ex = document.querySelector('[data-demo-dr="exemple"]'), re = document.querySelector('[data-demo-dr="reel"]');
    if (!ex) { return; }
    ex.hidden = reel; re.hidden = !reel;
    if (anime) { re.querySelectorAll('[data-demo-sceau], [data-demo-etat-mot]').forEach(function (el) { el.classList.remove('change'); void el.offsetWidth; el.classList.add('change'); }); }
  }
  if (etat === 'reel') { etatDr(true, false); var er = document.querySelector('[data-demo-entree-reel]'); if (er) { er.hidden = false; } }
  document.querySelectorAll('[data-demo-dr-form]').forEach(function (f) {
    f.addEventListener('submit', function (e) {
      e.preventDefault();
      var reel = f.dataset.demoDrForm === 'reel', b = f.querySelector('[type=submit]');
      occuper(b, 900).then(function () {
        D.fermerModale(f.closest('.modale'));
        etatDr(reel, true);
        var h = document.querySelector('[data-demo-historique]');
        h.insertAdjacentHTML('afterbegin', '<li class="apparait"><span class="point' + (reel ? ' point--vert' : '') + '">' + icHtml(reel ? 'globe' : 'circle-dashed') + '</span><div><p><strong>' + (reel ? 'Données réelles' : 'Données d’exemple') + '</strong> par vous</p><p class="meta">à l’instant</p></div></li>');
        D.bulle(reel ? { message: 'Données réelles activées', detail: 'Le site public affiche maintenant les données réelles.', niveau: 'success' }
                     : { message: 'Données d’exemple rétablies', detail: 'Le site public affiche de nouveau son jeu d’exemple.', niveau: 'success' });
        f.reset();
      });
    });
  });

  /* ---------- Messages de contact (F-62) ---------- */
  var fc = document.querySelector('[data-demo-filtre-contact]');
  if (fc) {
    function filtrer(v) {
      var n = 0;
      document.querySelectorAll('tr[data-etat]').forEach(function (tr) { tr.hidden = !!v && tr.dataset.etat !== v; if (!tr.hidden) { n += 1; } });
      document.querySelector('[data-demo-pages-contact]').hidden = v === 'a_traiter';
      document.querySelector('[data-demo-resume-contact]').textContent = v === 'a_traiter' ? '1 à 5 sur 5' : v === 'traite' ? '1 à 25 sur 212' : '1 à 25 sur 217';
    }
    fc.addEventListener('change', function (e) { filtrer(e.target.value); });
    filtrer('a_traiter');
    if (etat === 'vide') { vue('vide'); document.querySelector('.resume-liste').hidden = true; document.querySelector('[data-demo-nb-a-traiter]').textContent = '0'; fc.querySelector('.nombre').textContent = '0'; }
  }
  function traiter(anime) {
    var z = document.querySelector('[data-demo-zone-traiter]'), p = document.querySelector('[data-demo-pied-traiter]');
    z.innerHTML = '<span class="etat etat--actif' + (anime ? ' change' : '') + '">' + icHtml('circle-check') + 'Traité</span>';
    p.innerHTML = '<p class="traite-par">' + icHtml('circle-check') + '<span>Traité le 15/10/2026 à 10&nbsp;h&nbsp;24 par <strong class="texte-plein">Aimé Tshibangu</strong></span></p>';
  }
  var bt = document.querySelector('[data-demo-traiter]');
  if (bt) {
    bt.addEventListener('click', function () {
      occuper(bt, 700).then(function () { traiter(true); D.bulle({ message: 'Message marqué comme traité', detail: 'Il reste 4 messages à traiter.', niveau: 'success' }); });
    });
    if (etat === 'traite') { traiter(false); }
  }
})();
