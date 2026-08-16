# P026 — Drag d'arête : étirer les voisines, pas déplacer tout le contour

## Contexte — diagnostic vérifié (ne pas re-diagnostiquer)

Bug utilisateur : tirer UN bord d'un rectangle déplace tout le
rectangle. Mesuré :

- **Chemin serveur** (`sketch_move` point 0, FreeCAD `moveGeometry`) :
  comportement CORRECT — bord gauche tiré de −15 → bord droit immobile,
  les voisines s'étirent (sonde : x droit reste à 40). Rien à changer.
- **Chemin solveur local** (planegcs WASM, `dragWholeCurve` dans
  `app/solver.js`) : le drag d'une ligne pose 4 contraintes pilotantes
  absolues (`coordinate_x/y` sur p1 ET p2). Deux solutions satisfont
  alors les contraintes du rectangle, et le solveur converge vers la
  translation d'ensemble. C'est lui le coupable — c'est le chemin actif
  à 60 fps dans le navigateur.

## Mission — `app/solver.js`, `dragWholeCurve`

Pour une **ligne**, remplacer les 4 contraintes absolues par le modèle
« ligne rigide » :

- `coordinate_x` + `coordinate_y` pilotantes temporaires sur **p1
  seulement** (la cible curseur, comme aujourd'hui) ;
- deux contraintes **`difference`** temporaires pilotantes qui
  préservent le vecteur de la ligne :
  `p2.x − p1.x = dx` et `p2.y − p1.y = dy`, avec (dx, dy) lus sur
  l'entité du modèle au moment de l'appel (la ligne est rigide, le
  vecteur ne dérive pas pendant le drag). Utiliser la même syntaxe
  `difference` que la table de traduction existante (DistanceX/Y) —
  param1/param2 dans le bon ordre pour que valeur = param2 − param1.

Cercles et arcs : inchangés (le drag par centre est déjà le bon geste).
Types non gérés : inchangés (`null` → repli serveur, qui est correct).

## Tests

- `tests/js/solver-mock.test.mjs` : mettre à jour le test « point 0
  (courbe entière) » — il doit maintenant attendre 2 `coordinate_*` sur
  p1 + 2 `difference` avec les bonnes valeurs de vecteur (plus de
  `dragx2`/`dragy2` absolus). Le test cercle reste tel quel.
- `tests/js/solver-wasm.test.mjs` (le vrai WASM) : ajouter un cas
  rectangle complet — 4 lignes, coïncidences des coins, 2 horizontales,
  2 verticales (mêmes contraintes que l'outil rectangle) ; drag du bord
  gauche (point 0) de −15 en x → **assertions** : les deux extrémités du
  bord droit n'ont pas bougé (±0.01) ET le bord gauche a bien bougé.
  C'est l'assertion qui aurait attrapé le bug.
- `scripts/smoke/smoke.js` : durcir le pas « drag arête » existant —
  en plus de « la géométrie a bougé », vérifier que le bord opposé
  (bas du rectangle) n'a PAS bougé (±1 mm) pendant le drag du bord
  haut. Attention : le drag du bord haut dans le smoke actuel a une
  composante verticale — l'étirement attendu change la hauteur, pas la
  position du bord bas.

## Validation

- `node --check app/solver.js` + les deux suites JS (`node --test
  tests/js/*.test.mjs`) ; `python3 -m pytest tests/ -q` (rien côté
  moteur).
- Smoke complet : tous les pas existants doivent rester verts.
- Commit(s) préfixés `[P026]`. Ne pas toucher `app/vendor/`. Français,
  vocabulaire SolidWorks 2025.
