# P012 — Esquisse : Décaler les entités (offset)

Retour au produit (`docs/fonctions-manquantes.md`, ligne « Décaler les
entités »). L'outil SolidWorks du quotidien : sélectionner une chaîne
d'entités, donner une distance, obtenir le contour décalé.

Périmètre : `engine/kernel.py`, `engine/protocol.py`,
`app/sketch.js`, `app/index.html`, selftest, tests. Pas de nouveau
fichier app sauf nécessité.

## 1. Op moteur `sketch_offset`

`sketch_offset(sketch, geos, distance, reversed=False)` :

- Construire un `Part.Wire` à partir des `toShape()` des géométries
  sélectionnées (`geos` = ids, ordre libre — `Part.Wire` sait chaîner
  des arêtes connexes ; si elles ne forment pas une chaîne connexe,
  `KernelError` claire : « les entités à décaler doivent former une
  chaîne connexe »).
- `wire.makeOffset2D(distance si non reversed, sinon -distance)` —
  gérer l'exception OCCT (offset impossible → message français).
- Réinjecter le résultat dans l'esquisse : pour chaque arête du fil
  décalé, `Part::GeomLineSegment` pour une droite,
  `Part::GeomArcOfCircle` pour un arc, `Part::GeomCircle` pour un
  cercle complet (cas : offset d'un cercle seul). Toute autre courbe
  (BSpline issue d'un offset de spline…) → `KernelError` « géométrie
  non décalable pour l'instant » — PAS de réinjection partielle : tout
  ou rien.
- Les entités créées restent **non contraintes** (le « Décalage »
  paramétrique de SolidWorks viendra plus tard — le noter en
  commentaire). Retour : `sketch_state`.
- Transactionnel : ajouter `"sketch_offset"` à `_TRANSACTIONAL`
  (un Ctrl+Z annule tout le décalage).

## 2. Protocole

- `OPS["sketch_offset"] = _Req(("sketch", str), ("geos", list),
  ("distance", float))` — `reversed` optionnel non typé.
- **Le snapshot des clés d'OPS dans `tests/test_protocol.py` doit être
  mis à jour** (c'est son travail d'attraper cet ajout) + un assert de
  déclaration comme pour les autres ops.

## 3. UI (mode esquisse)

- Bouton « Décaler » dans la barre d'esquisse (`app/index.html`,
  à côté de sk-mirror/sk-array, même style — texte ou icône existante,
  ne PAS ajouter de nouveau SVG sans provenance).
- Flux, calqué sur sk-array : l'utilisateur sélectionne des entités
  avec l'outil Sélectionner, clique Décaler → panneau PropertyManager
  (« Décaler les entités ») : distance (mm, défaut 5, min 0.01),
  check « Inverser le côté ». OK → `sketch_offset` avec la sélection,
  `applyState` du retour. Sélection vide → message d'aide, pas de
  panneau (comme sk-mirror).
- Raccourci : aucun (la barre suffit pour l'instant).

## 4. Selftest (obligatoire — FreeCAD requis)

Étendre p17 (ou l'étape esquisse avancée la plus adaptée) :

- Rectangle 40×30 en chaîne fermée → `sketch_offset` des 4 lignes,
  distance 5 → `p17_offset_ok` : 4 lignes + 4 congés d'arc OU 4 lignes
  selon le mode OCCT (compter ≥ 4 entités nouvelles ET vérifier
  qu'une des nouvelles lignes est bien à 5 mm de l'originale).
- Cercle seul décalé → `p17_offset_circle_ok` : un cercle de rayon
  r±5.
- Cas d'erreur : deux lignes non connexes → `KernelError` attendue →
  `p17_offset_disjoint_ok`.

## Validation avant push

1. `python3 -m pytest tests/ -q` — tout vert (snapshot OPS mis à jour).
2. `node --check` sur les JS modifiés ; `node --test tests/js/*.test.mjs`
   — 50 verts.
3. Selftest FreeCAD : 48 étapes, 90 indicateurs verts attendus (87+3).
4. Smoke local : parcours vert (il ne touche pas au décalage mais doit
   rester vert).
5. Description de PR : captures ou description du geste UI complet.
6. Commit : `[P012] esquisse — décaler les entités (makeOffset2D, panneau, selftest)`.
