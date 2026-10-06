/* Essais des fonctions du navigateur, lancés par outils/essais.py (ou : node essais/app.test.js). */
'use strict';
var assert = require('assert');
var path = require('path');
var app = require(path.join(__dirname, '..', 'site', 'app.js'));
var nombre = 0;
function essai(nom, fn) { fn(); nombre += 1; console.log('  ok    ' + nom); }

essai('recherche sans accents ni majuscules', function () {
  assert.strictEqual(app.norm('Île-de-France'), 'ile-de-france');
  assert.strictEqual(app.norm(null), '');
});
essai('classes de taille', function () {
  assert.strictEqual(app.taille('03'), 'tpe');
  assert.strictEqual(app.taille('12'), 'pme');
  assert.strictEqual(app.taille('21'), 'eti');
  assert.strictEqual(app.taille(''), '');
  assert.strictEqual(app.taille('NN'), 'tpe');
});
essai('jours restants', function () {
  var mardi = new Date(2026, 9, 6, 15, 30);
  assert.strictEqual(app.joursRestants('2026-10-16', mardi), 10);
  assert.strictEqual(app.joursRestants('2026-10-06', mardi), 0);
  assert.strictEqual(app.joursRestants('2026-10-05', mardi), -1);
  assert.strictEqual(app.libelleEcheance(10, false), 'dans 10 jours');
  assert.strictEqual(app.libelleEcheance(10, true), '10 jours');
  assert.strictEqual(app.libelleEcheance(1, false), 'demain');
  assert.strictEqual(app.libelleEcheance(0, false), "aujourd'hui");
  assert.strictEqual(app.libelleEcheance(-3, false), 'date passée');
});
essai('filtres des procédures', function () {
  var liste = [
    { nom: 'ATELIERS', ville: 'Saint-Priest', dept: 'Rhône', region: 'Auvergne-Rhône-Alpes', secteur: 'Industrie', effectif: '12', type: 'rj', aj: true, tribunal: 'TAE de Lyon' },
    { nom: 'BOULANGERIE', ville: 'Annecy', dept: 'Haute-Savoie', region: 'Auvergne-Rhône-Alpes', secteur: 'Commerce', effectif: '01', type: 'lj', aj: false, tribunal: '' },
    { nom: 'TRANSPORTS', ville: 'Arras', dept: 'Pas-de-Calais', region: 'Hauts-de-France', secteur: 'Transport', effectif: '21', type: 'conv', aj: false, tribunal: '' }
  ];
  var vide = { q: '', secteur: '', taille: '', region: '', aj: false };
  function avec(o) { var f = {}; Object.keys(vide).forEach(function (k) { f[k] = vide[k]; }); Object.keys(o).forEach(function (k) { f[k] = o[k]; }); return f; }
  assert.strictEqual(app.filtrerProcedures(liste, vide).length, 3);
  assert.strictEqual(app.filtrerProcedures(liste, avec({ secteur: 'Industrie' })).length, 1);
  assert.strictEqual(app.filtrerProcedures(liste, avec({ taille: 'tpe' }))[0].nom, 'BOULANGERIE');
  assert.strictEqual(app.filtrerProcedures(liste, avec({ region: 'Auvergne-Rhône-Alpes' })).length, 2);
  assert.strictEqual(app.filtrerProcedures(liste, avec({ aj: true })).length, 1);
  assert.strictEqual(app.filtrerProcedures(liste, avec({ q: 'rhone' })).length, 2);
  assert.strictEqual(app.filtrerProcedures(liste, avec({ q: 'liquidation' })).length, 2);
  assert.strictEqual(app.filtrerProcedures(liste, avec({ q: 'introuvable' })).length, 0);
});
essai("critères d'une alerte", function () {
  assert.strictEqual(app.criteres({ secteurs: ['Industrie', 'Commerce'], regions: [], tailles: ['pme'], rythme: 'weekly', aj: true }),
    'secteurs=Industrie|Commerce;regions=;tailles=pme;rythme=weekly;aj=1');
  assert.strictEqual(app.criteres({}), 'secteurs=;regions=;tailles=;rythme=now;aj=0');
});
essai('adresse e-mail', function () {
  assert.ok(app.emailValide('nom@entreprise.fr'));
  assert.ok(!app.emailValide('nom@entreprise'));
  assert.ok(!app.emailValide(''));
});
console.log('  ' + nombre + ' essais du navigateur réussis');
