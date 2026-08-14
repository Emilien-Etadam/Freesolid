# P010 — Tests JS en CI : banc Node du solveur + smoke navigateur

Aujourd'hui le CI ne teste jamais une ligne de JavaScript. Ce prompt
ajoute deux étages (constat **6.3** de l'audit + le harnais smoke déjà
versionné dans `scripts/smoke/` — il est validé, ne pas le réécrire) :

1. des **tests unitaires Node** de `app/solver.js` (rapides, sans
   navigateur ni FreeCAD) ;
2. le câblage **CI** des deux (unitaires à chaque push, smoke complet
   aussi — voir découpage).

Périmètre : `tests/js/` (nouveau), `.github/workflows/ci.yml`,
`scripts/smoke/` (seulement si un ajustement CI l'exige — le scénario
lui-même ne change pas). **Aucune modification de `app/` ni
`engine/`.**

## 1. Banc Node de `app/solver.js` — `tests/js/`

Node ≥ 20 natif : `node --test` (module `node:test`), pas de framework
à installer. Fichiers en `.mjs` (le repo n'a pas de package.json
racine ; en créer un est autorisé si `node --test` l'exige, avec
`"type": "module"` et rien d'autre).

`createLocalSolver(loadModule)` accepte l'injection du module planegcs.
Deux étages de tests :

- **Avec mock** (la majorité) : un faux `make_gcs_wrapper` qui
  enregistre les primitives poussées et rend `solve()` → 0. À tester :
  - la table `translate` : chaque type FreeCAD couvert produit les
    primitives planegcs attendues (types et ids exacts — Coincident,
    Horizontal/Vertical ligne et point-point, Parallel, Perpendicular,
    Tangent (ligne-ligne → deux `point_on_line_pl`, lc, la, cc), Equal
    (longueur / rayons cc, aa, ca), Distance (p2p, p2l, longueur de
    ligne), DistanceX/Y (`difference` et `coordinate_x/y`), Radius
    (cercle/arc), Diameter, Angle, Symmetric, PointOnObject
    (ligne/cercle/arc), Block → `[]`) ;
  - politique de refus : type inconnu → `load` false ; contrainte
    connue mais irrésolue (coïncidence vers un point d'axe) → false ;
    entité `poly`/`other` → false ; `driving: false` ignorée ;
  - le repère : `origin`/`gx`/`gy` présents et `fixed`, mapping
    (-1, 1) → origin, -1/-2 → gx/gy ;
  - `drag` : les deux contraintes temporaires `coordinate_x/y` sur le
    bon point, `solve() > 1` → null sans casser le modèle, exception →
    modèle invalidé (drag suivant → null).
- **Avec le vrai WASM vendu** (`app/vendor/planegcs/`, quelques cas) :
  le rectangle contraint — drag d'un coin, cotes 40/30 et H/V tenues ;
  le rectangle libre — le coin suit la souris ; cercle tangent — rayon
  et tangence tenus. (Reprendre la géométrie du banc décrit dans les
  PR précédentes ; c'est du Node pur, le WASM se charge par
  `file://`.)

## 2. CI — `.github/workflows/ci.yml`

- **Job `js-tests`** (rapide, à chaque push) : setup-node (Node 22),
  `node --test tests/js/`, plus les `node --check` des cinq JS
  first-party (`main.js`, `sketch.js`, `panel.js`, `solver.js`,
  `geom2d.js` si P009 l'a créé — adapter à ce qui existe).
- **Job `smoke`** (le plus lourd — décision assumée : à chaque push
  aussi, tant que ça tient sous ~10 min) :
  - micromamba `python=3.11 freecad=1.0.0` (même recette que le job
    selftest existant, cache activé) ;
  - `npm ci` dans `scripts/smoke` ; Chromium : installer `playwright`
    (paquet complet) en plus et `npx playwright install --with-deps
    chromium`, OU utiliser un Chromium système du runner avec
    `CHROMIUM_PATH` — au choix, le plus simple qui marche ;
  - lancer `freecadcmd scripts/smoke/serve.py &`, attendre le port
    (boucle curl sur `/api` avec `ping`, timeout 60 s — pas de sleep
    aveugle), `node scripts/smoke/smoke.js` ;
  - uploader `scripts/smoke/shots/` en artefact GitHub Actions
    (`actions/upload-artifact`, `if: always()`) — les captures sont le
    diagnostic quand ça casse.
- Ne pas toucher aux jobs existants (pytest, selftest).

## Validation avant push

1. En local : `node --test tests/js/` tout vert ; si FreeCAD dispo,
   rejouer aussi le smoke local pour vérifier qu'il n'a pas régressé.
2. `python3 -m pytest tests/ -q` — 153 verts (rien de Python ne bouge
   à part ci.yml qui n'est pas du Python).
3. La PR doit montrer le run CI vert des nouveaux jobs (ou expliquer
   précisément ce qui manque au runner si un job ne peut pas être
   validé avant merge).
4. Commit : `[P010] tests JS en CI — banc Node du solveur (mock + WASM) et smoke navigateur`.
