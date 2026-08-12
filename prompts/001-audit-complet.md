# P001 — Audit complet du code

## Mission

Audit de l'intégralité du dépôt. **Aucune modification de code** : le
livrable est un rapport, `docs/audit/2026-08-audit.md`. C'est une pause
qualité avant la suite du développement.

## Contexte (à lire avant de commencer)

FreeSolid = une UI web moderne (type SolidWorks) sur un moteur FreeCAD
headless intact. Architecture en trois couches :

- **`app/`** — client navigateur sans build : `index.html` (ruban 4
  onglets, topbar), `main.js` (viewport Three.js, picking faces/arêtes,
  arbre, panneaux de fonctions, assemblage, surfaces), `sketch.js` (mode
  esquisse 2D : outils, accrochages, cotes, drag), `solver.js` (M3 :
  solveur planegcs WASM local pour le drag à 60 fps), `panel.js`
  (PropertyManager piloté par spec), `vendor/planegcs/` (tiers, LGPL —
  **hors périmètre d'audit**, ne pas le commenter).
- **`engine/`** — Python stdlib uniquement : `server.py` (HTTP
  localhost:8787, statique + POST /api, verrou global car FreeCAD n'est
  pas thread-safe), `kernel.py` (~3500 lignes, toutes les opérations
  FreeCAD : PartDesign, Sketcher, assemblage, surfacique, import/export,
  selftest), `protocol.py` (registre OPS, validation, pack maillages —
  pur, testable sans FreeCAD).
- **`tests/`** — pytest sur la partie pure (107 tests). Le selftest
  end-to-end (`scripts/run-selftest.py`, 47 étapes / 73 indicateurs)
  nécessite FreeCAD ≥ 1.0 (CI : job micromamba).

Invariants à connaître pour auditer juste :

- Le serveur est **la vérité** ; le client est optimiste (drag local,
  aperçus jaunes) mais se réconcilie toujours sur l'état serveur.
- Les ids de géométrie/faces/arêtes sont **invalidés à chaque rebuild** ;
  toute conservation d'id côté client à travers un rebuild est un bug.
- Une action UI = une transaction FreeCAD (ensembles `_TRANSACTIONAL` /
  `_PREVIEWABLE` dans `kernel.py`) = un seul Ctrl+Z.
- `sketch_move` est volontairement hors transaction (fréquence du drag).
- Textes UI : français, vocabulaire SolidWorks 2025.

`docs/optimisation.md` liste les dettes de performance déjà connues :
les recouper (confirmer/infirmer), ne pas les recopier.

## Axes d'audit (tous, dans cet ordre dans le rapport)

1. **Correction / bugs** — chemins d'erreur avalés, promesses non
   attendues, courses async (double-clic, drag pendant un refresh,
   réponse serveur obsolète qui écrase un état plus récent), ids
   périmés, `parseFloat`/unités, conversions degrés/radians, cas
   limites géométriques (arcs traversant ±π, géométrie de construction,
   esquisses vides).
2. **Robustesse moteur** — `kernel.py` : exceptions FreeCAD non
   rattrapées qui laisseraient une transaction ouverte ou un document
   incohérent ; nettoyage des objets temporaires (SubShapeBinder, pages
   TechDraw, fichiers temp) ; comportements si le document actif change
   sous une op ; le verrou global couvre-t-il bien tout accès FreeCAD.
3. **Sécurité** — surface localhost : traversal statique, validation
   des params (`protocol.py`), chemins de fichiers passés par le client
   (open/save/export/import : écriture arbitraire ?), expressions
   FreeCAD (`setExpression`) comme vecteur d'injection, absence de CORS/
   origine sur POST /api (un site tiers peut-il piloter le kernel ?).
4. **Fuites et performance client** — cycle de vie Three.js :
   `geometry.dispose()`/`material.dispose()` aux endroits où meshes,
   lignes, sprites de cotes et ghosts sont reconstruits ; écouteurs
   ajoutés/retirés symétriquement ; canvas de sprites ; taille des
   payloads JSON.
5. **Qualité / architecture** — duplication entre panneaux de fonctions
   dans `main.js`, taille et découpage des fichiers, code mort, noms
   incohérents, spec `panel.js` contournée quelque part, cohérence des
   réponses d'API (`ok/error`, formats d'état).
6. **Couverture de tests** — ce qui est pur mais non testé dans
   `protocol.py`/logique extraite ; ce que `solver.js` mérite comme
   tests Node ; trous du selftest (ops jamais exercées — en dresser la
   liste exacte en comparant le registre OPS au selftest).
7. **Cohérence UI/FR** — textes anglais restants, incohérences de
   vocabulaire vs SolidWorks, raccourcis clavier en conflit.
8. **Licences / provenance** — en-têtes, `app/icons/README.md`,
   `app/vendor/planegcs/README.md` : rien à auditer dans le code tiers,
   seulement vérifier que la provenance est complète.

## Format du rapport (`docs/audit/2026-08-audit.md`)

- En tête : résumé exécutif (10 lignes max) + décompte par sévérité.
- Ensuite une section par axe. Chaque constat :
  - **Sévérité** : `bloquant` (perte de données / crash / sécurité),
    `majeur` (bug réel atteignable), `mineur` (bug théorique, dette),
    `suggestion`.
  - **Localisation** : `fichier:ligne` précis.
  - **Constat** : le problème, avec le scénario qui le déclenche.
  - **Remède proposé** : une phrase, sans le coder.
  - **Effort** : S / M / L.
- Terminer par un **top 10 priorisé** (rapport gain/effort) qui servira
  de base aux prompts suivants.

## Contraintes

- Ne modifier **aucun** fichier hors `docs/audit/`.
- Lire réellement les fichiers en entier (`main.js` et `kernel.py` sont
  longs — c'est là que se cachent les constats intéressants).
- Vérifications permises : `python3 -m pytest tests/ -q`,
  `node --check app/*.js`, lecture. Ne pas lancer le serveur ni le
  selftest.
- Chaque constat doit être **vérifié sur le code** (pas de généralité du
  genre « il faudrait plus de tests » sans liste précise).
- Commit : `[P001] audit complet du code — rapport` puis push sur `main`.
