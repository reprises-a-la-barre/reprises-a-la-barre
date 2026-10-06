/* Reprises à la barre : comportements du site. Aucun outil extérieur, aucun traceur. */
(function () {
  'use strict';

  var MOIS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
  var TYPES = { rj: 'Redressement judiciaire', lj: 'Liquidation judiciaire', conv: 'Conversion en liquidation' };
  var TRANCHES = {
    NN: 'Sans salarié', '00': 'Sans salarié', '01': '1 à 2 salariés', '02': '3 à 5 salariés',
    '03': '6 à 9 salariés', '11': '10 à 19 salariés', '12': '20 à 49 salariés', '21': '50 à 99 salariés',
    '22': '100 à 199 salariés', '31': '200 à 249 salariés', '32': '250 à 499 salariés',
    '41': '500 à 999 salariés', '42': '1 000 à 1 999 salariés', '51': '2 000 à 4 999 salariés',
    '52': '5 000 à 9 999 salariés', '53': '10 000 salariés et plus'
  };
  var PAR_PAGE = 40;

  /* ---------- Fonctions pures (essayées hors navigateur) ---------- */

  function norm(texte) {
    return String(texte == null ? '' : texte).toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  }

  function taille(code) {
    if (!Object.prototype.hasOwnProperty.call(TRANCHES, code)) { return ''; }
    if (['NN', '00', '01', '02', '03'].indexOf(code) !== -1) { return 'tpe'; }
    if (['11', '12'].indexOf(code) !== -1) { return 'pme'; }
    return 'eti';
  }

  function joursRestants(iso, maintenant) {
    var p = String(iso).split('-');
    var cible = new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]));
    var jour = new Date(maintenant.getFullYear(), maintenant.getMonth(), maintenant.getDate());
    return Math.round((cible.getTime() - jour.getTime()) / 86400000);
  }

  function libelleEcheance(n, court) {
    if (n < 0) { return 'date passée'; }
    if (n === 0) { return "aujourd'hui"; }
    if (n === 1) { return 'demain'; }
    return court ? n + ' jours' : 'dans ' + n + ' jours';
  }

  function filtrerProcedures(liste, f) {
    var aiguille = norm(f.q).trim();
    return liste.filter(function (p) {
      if (f.secteur && p.secteur !== f.secteur) { return false; }
      if (f.taille && taille(p.effectif) !== f.taille) { return false; }
      if (f.region && p.region !== f.region) { return false; }
      if (f.aj && !p.aj) { return false; }
      if (aiguille) {
        var botte = norm([p.nom, p.ville, p.dept, p.region, p.secteur, p.tribunal, TYPES[p.type]].join(' '));
        if (botte.indexOf(aiguille) === -1) { return false; }
      }
      return true;
    });
  }

  function criteres(choix) {
    return [
      'secteurs=' + (choix.secteurs || []).join('|'),
      'regions=' + (choix.regions || []).join('|'),
      'tailles=' + (choix.tailles || []).join('|'),
      'rythme=' + (choix.rythme === 'weekly' ? 'weekly' : 'now'),
      'aj=' + (choix.aj ? '1' : '0')
    ].join(';');
  }

  function emailValide(valeur) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(valeur || '').trim());
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { norm: norm, taille: taille, joursRestants: joursRestants, libelleEcheance: libelleEcheance,
      filtrerProcedures: filtrerProcedures, criteres: criteres, emailValide: emailValide };
  }
  if (typeof document === 'undefined') { return; }

  /* ---------- Outils de page ---------- */

  var racine = document.body.getAttribute('data-racine') || './';

  function el(balise, classe, texte) {
    var noeud = document.createElement(balise);
    if (classe) { noeud.className = classe; }
    if (texte != null) { noeud.textContent = texte; }
    return noeud;
  }

  /* ---------- Échéances : « dans N jours » toujours à jour ---------- */

  Array.prototype.forEach.call(document.querySelectorAll('[data-echeance]'), function (noeud) {
    var n = joursRestants(noeud.getAttribute('data-echeance'), new Date());
    var texte = libelleEcheance(n, noeud.getAttribute('data-format') === 'court');
    noeud.textContent = noeud.getAttribute('data-majuscule') ? texte.charAt(0).toUpperCase() + texte.slice(1) : texte;
    if (n <= 7 && noeud.classList.contains('ligne__echeance')) { noeud.classList.add('ligne__echeance--proche'); }
  });

  /* ---------- Page des dossiers ---------- */

  var pageDossiers = document.getElementById('page-dossiers');
  if (pageDossiers) { dossiers(); }

  function dossiers() {
    var etat = { vue: 'offres', q: '', secteur: '', taille: '', region: '', aj: false, montrees: PAR_PAGE };
    var procedures = null;
    var champ = document.getElementById('q');
    var region = document.getElementById('region');
    var caseAj = document.getElementById('case-aj');
    var aj = document.getElementById('aj');
    var compte = document.getElementById('compte');
    var effacer = document.getElementById('effacer');
    var vueOffres = document.getElementById('vue-offres');
    var vueProcedures = document.getElementById('vue-procedures');
    var liste = document.getElementById('liste-procedures');
    var plus = document.getElementById('plus');
    var explications = { offres: document.getElementById('explication-offres'), procedures: document.getElementById('explication-procedures') };
    var segments = pageDossiers.querySelectorAll('.segment');
    var lignesOffres = vueOffres.querySelectorAll('.ligne');

    function filtre() { return Boolean(norm(etat.q).trim() || etat.secteur || etat.taille || etat.region || etat.aj); }

    function ligneProcedure(p) {
      var d = String(p.date).split('-');
      var item = el('li');
      var bloc = el('details', 'depliable');
      var tete = el('summary', 'ligne ligne--large');
      var vignette = el('span', 'vignette vignette--neutre');
      vignette.appendChild(el('span', 'vignette__jour', String(Number(d[2]))));
      vignette.appendChild(el('span', 'vignette__mois', MOIS[Number(d[1]) - 1]));
      var principal = el('span', 'ligne__principal');
      principal.appendChild(el('span', 'ligne__titre', p.nom));
      var ou = p.ville && p.dept && norm(p.ville) !== norm(p.dept) ? p.ville + ' (' + p.dept + ')' : (p.ville || p.dept);
      principal.appendChild(el('span', 'ligne__lieu', [ou, p.tribunal].filter(Boolean).join(', ')));
      var colonne1 = el('span', 'ligne__colonne');
      colonne1.appendChild(el('span', '', TRANCHES[p.effectif] || 'Effectif non communiqué'));
      colonne1.appendChild(el('span', 'second', p.secteur || 'Activité non communiquée'));
      var colonne2 = el('span', 'ligne__colonne');
      colonne2.appendChild(el('span', '', TYPES[p.type] || ''));
      colonne2.appendChild(el('span', 'second', p.aj ? 'Administrateur désigné' : 'Sans administrateur'));
      tete.appendChild(vignette); tete.appendChild(principal); tete.appendChild(colonne1); tete.appendChild(colonne2);
      var detail = el('div', 'depliable__detail');
      if (p.texte) { detail.appendChild(el('p', '', p.texte)); }
      var actions = el('div', 'actions');
      if (p.url) {
        var bodacc = el('a', 'lien-action', "Voir l'annonce au BODACC");
        bodacc.href = p.url; bodacc.target = '_blank'; bodacc.rel = 'noopener';
        actions.appendChild(bodacc);
      }
      var contact = el('a', 'lien-action', "Contacter l'avocat");
      contact.href = racine + 'avocat/#contact';
      actions.appendChild(contact);
      detail.appendChild(actions);
      bloc.appendChild(tete); bloc.appendChild(detail); item.appendChild(bloc);
      return item;
    }

    function afficher() {
      var filtree = filtre();
      Array.prototype.forEach.call(segments, function (s) { s.setAttribute('aria-pressed', s.getAttribute('data-vue') === etat.vue ? 'true' : 'false'); });
      vueOffres.hidden = etat.vue !== 'offres';
      vueProcedures.hidden = etat.vue !== 'procedures';
      explications.offres.hidden = etat.vue !== 'offres';
      explications.procedures.hidden = etat.vue !== 'procedures';
      caseAj.hidden = etat.vue !== 'procedures';
      effacer.hidden = !filtree;

      if (etat.vue === 'offres') {
        var aiguille = norm(etat.q).trim();
        var visibles = 0;
        Array.prototype.forEach.call(lignesOffres, function (ligne) {
          var garde = (!etat.secteur || ligne.getAttribute('data-secteur') === etat.secteur) &&
            (!etat.taille || ligne.getAttribute('data-taille') === etat.taille) &&
            (!etat.region || ligne.getAttribute('data-region') === etat.region) &&
            (!aiguille || norm(ligne.getAttribute('data-texte')).indexOf(aiguille) !== -1);
          ligne.hidden = !garde;
          ligne.classList.toggle('premiere', garde && visibles === 0);
          if (garde) { visibles += 1; }
        });
        vueOffres.querySelector('.vide').hidden = visibles !== 0;
        if (!filtree) { compte.textContent = visibles + (visibles > 1 ? " appels d'offres ouverts, classés par date limite" : " appel d'offres ouvert"); }
        else if (visibles === 0) { compte.textContent = "Aucun appel d'offres pour ces critères"; }
        else { compte.textContent = visibles + (visibles > 1 ? " appels d'offres correspondent" : " appel d'offres correspond") + ' à vos critères'; }
        return;
      }

      if (procedures === null) { compte.textContent = 'Chargement des procédures…'; return; }
      var retenues = filtrerProcedures(procedures, etat);
      liste.textContent = '';
      retenues.slice(0, etat.montrees).forEach(function (p) { liste.appendChild(ligneProcedure(p)); });
      plus.hidden = retenues.length <= etat.montrees;
      vueProcedures.querySelector('.vide').hidden = retenues.length !== 0;
      if (!filtree) { compte.textContent = retenues.length + ' procédures ouvertes, de la plus récente à la plus ancienne'; }
      else if (retenues.length === 0) { compte.textContent = 'Aucune procédure pour ces critères'; }
      else { compte.textContent = retenues.length + (retenues.length > 1 ? ' procédures correspondent' : ' procédure correspond') + ' à vos critères'; }
    }

    function choisir(groupe, valeur) {
      Array.prototype.forEach.call(groupe.querySelectorAll('.pastille'), function (b) {
        b.setAttribute('aria-pressed', b.getAttribute('data-valeur') === valeur ? 'true' : 'false');
      });
    }

    Array.prototype.forEach.call(segments, function (s) {
      s.addEventListener('click', function () { etat.vue = s.getAttribute('data-vue'); etat.montrees = PAR_PAGE; afficher(); });
    });
    Array.prototype.forEach.call(pageDossiers.querySelectorAll('.pastilles[data-filtre]'), function (groupe) {
      groupe.addEventListener('click', function (e) {
        var bouton = e.target.closest('.pastille');
        if (!bouton) { return; }
        etat[groupe.getAttribute('data-filtre')] = bouton.getAttribute('data-valeur');
        etat.montrees = PAR_PAGE;
        choisir(groupe, bouton.getAttribute('data-valeur'));
        afficher();
      });
    });
    champ.addEventListener('input', function () { etat.q = champ.value; etat.montrees = PAR_PAGE; afficher(); });
    region.addEventListener('change', function () { etat.region = region.value; etat.montrees = PAR_PAGE; afficher(); });
    aj.addEventListener('change', function () { etat.aj = aj.checked; etat.montrees = PAR_PAGE; afficher(); });
    plus.addEventListener('click', function () { etat.montrees += PAR_PAGE; afficher(); });
    effacer.addEventListener('click', function () {
      etat.q = ''; etat.secteur = ''; etat.taille = ''; etat.region = ''; etat.aj = false; etat.montrees = PAR_PAGE;
      champ.value = ''; region.value = ''; aj.checked = false;
      Array.prototype.forEach.call(pageDossiers.querySelectorAll('.pastilles[data-filtre]'), function (g) { choisir(g, ''); });
      afficher();
    });

    if (location.hash === '#procedures' || lignesOffres.length === 0) { etat.vue = 'procedures'; }
    afficher();

    fetch(racine + 'donnees/procedures.json')
      .then(function (r) { if (!r.ok) { throw new Error('indisponible'); } return r.json(); })
      .then(function (donnees) {
        procedures = Array.isArray(donnees) ? donnees : [];
        var nombre = pageDossiers.querySelector('[data-nombre="procedures"]');
        if (nombre) { nombre.textContent = String(procedures.length); }
        afficher();
      })
      .catch(function () {
        procedures = [];
        if (etat.vue === 'procedures') { compte.textContent = 'Les procédures sont momentanément indisponibles. Rechargez la page dans un instant.'; }
      });
  }

  /* ---------- Formulaire d'alerte ---------- */

  var formulaire = document.getElementById('alerte');
  if (formulaire) { alerte(); }

  function alerte() {
    var erreur = document.getElementById('erreur');
    var groupes = formulaire.querySelectorAll('.pastilles[data-choix]');

    Array.prototype.forEach.call(groupes, function (groupe) {
      var unique = groupe.hasAttribute('data-unique');
      groupe.addEventListener('click', function (e) {
        var bouton = e.target.closest('.pastille');
        if (!bouton) { return; }
        var boutons = groupe.querySelectorAll('.pastille');
        var tout = bouton.getAttribute('data-valeur') === '';
        if (unique || tout) {
          Array.prototype.forEach.call(boutons, function (b) { b.setAttribute('aria-pressed', b === bouton ? 'true' : 'false'); });
        } else {
          bouton.setAttribute('aria-pressed', bouton.getAttribute('aria-pressed') === 'true' ? 'false' : 'true');
          var choisis = groupe.querySelectorAll('.pastille[aria-pressed="true"]:not([data-valeur=""])').length;
          var general = groupe.querySelector('.pastille[data-valeur=""]');
          if (general) { general.setAttribute('aria-pressed', choisis === 0 ? 'true' : 'false'); }
        }
        erreur.hidden = true;
      });
    });

    function valeurs(nom) {
      var groupe = formulaire.querySelector('.pastilles[data-choix="' + nom + '"]');
      if (!groupe) { return []; }
      return Array.prototype.map.call(groupe.querySelectorAll('.pastille[aria-pressed="true"]'), function (b) { return b.getAttribute('data-valeur'); })
        .filter(function (v) { return v !== ''; });
    }

    formulaire.addEventListener('submit', function (e) {
      var email = formulaire.querySelector('[name="EMAIL"]');
      var accord = formulaire.querySelector('[name="OPT_IN"]');
      var message = '';
      if (!emailValide(email.value)) { message = 'Indiquez une adresse e-mail valide, par exemple nom@entreprise.fr.'; }
      else if (!accord.checked) { message = 'Cochez la case pour accepter de recevoir les alertes.'; }
      else if (formulaire.getAttribute('data-pret') !== '1') { message = 'Les inscriptions ne sont pas encore ouvertes.'; }
      if (message) {
        e.preventDefault();
        erreur.textContent = message;
        erreur.hidden = false;
        return;
      }
      var rythme = valeurs('rythme')[0] || 'now';
      formulaire.querySelector('[name="CRITERES"]').value = criteres({
        secteurs: valeurs('secteurs'), regions: valeurs('regions'), tailles: valeurs('tailles'),
        rythme: rythme, aj: document.getElementById('alerte-aj').checked
      });
    });
  }
})();
