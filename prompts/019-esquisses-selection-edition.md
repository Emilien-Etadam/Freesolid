# P019 — Esquisses : profil visible, sélection mise en valeur, infos, drag des arêtes

Quatre demandes utilisateur liées, toutes côté esquisse.

## 1. Les fonctions utilisent la dernière esquisse dessinée — et le disent

Le moteur fait déjà le bon choix (`_latest_sketch` : la plus récente non
consommée) quand `sketch` est absent des params. Deux manques côté client :

- **Transparence** : les panneaux Bossage extrudé, Enlèvement de matière,
  Révolution, Enlèvement par révolution et Rainure n'affichent pas quelle
  esquisse sera utilisée. Ajouter en tête de panneau une ligne en lecture
  seule « Profil : ‹label de l'esquisse› ». Le label s'obtient côté client :
  dernière esquisse de l'arbre (`tree.features` enfants + esquisses libres)
  non référencée par une fonction — reproduire la règle du moteur à
  l'identique ; si une esquisse est sélectionnée dans l'arbre (voir §2),
  c'est elle qui est affichée ET passée explicitement en param `sketch`.
- **Priorité à la sélection** : esquisse sélectionnée dans l'arbre →
  `params.sketch = name` ; sinon ne pas passer `sketch` (le moteur prend la
  dernière). C'est le geste SolidWorks : présélection = profil.
- S'il n'existe aucune esquisse disponible, le panneau affiche le message
  d'invalidité existant du moteur — ne pas ouvrir un panneau qui ne peut
  qu'échouer : griser via le mécanisme `invalid` du registry.

## 2. Esquisse sélectionnée = mise en valeur visible

Aujourd'hui, cliquer une esquisse dans l'arbre alimente `panel.notifyPick`
mais rien n'est visible. Ajouter :

- **Arbre** : la ligne cliquée prend la classe `sel` (comme les plans) ;
  re-cliquer ou cliquer ailleurs désélectionne.
- **Viewport** : les arêtes de l'esquisse sélectionnée se dessinent en
  surbrillance (couleur accent existante des sélections) par-dessus le
  solide. Les données existent déjà : `sketch_state(sketch)` renvoie les
  entités 2D et le placement — réutiliser la projection existante du mode
  esquisse pour tracer une polyligne THREE.Line par entité, dans un groupe
  dédié retiré à la désélection (même discipline `disposeSubtree` que le
  reste). Un seul appel réseau par sélection, pas de polling.
- La sélection d'esquisse s'invalide comme les autres après chaque
  fonction (ids et labels bougent) : passer par le
  `panel.invalidateSelections()` existant.

## 3. Infos de l'esquisse sélectionnée dans la barre latérale

Quand une esquisse est sélectionnée dans l'arbre, le PropertyManager
affiche (lecture seule, pas un panneau d'édition) :

- titre : label de l'esquisse ;
- support : plan ou face d'appui (le moteur le connaît — si
  `sketch_state` ne le renvoie pas, l'ajouter à `sketch_state` :
  `support` = label du plan/face) ;
- nombre d'entités, nombre de contraintes ;
- état : « totalement contrainte » / « N degré(s) de liberté » (déjà
  calculé par le moteur pour la barre de statut en mode esquisse —
  réutiliser le même champ) ;
- utilisée par : label de la fonction qui la consomme, ou « libre » ;
- boutons : « Modifier » (ouvre le mode esquisse, chemin `sketch_edit`
  existant du double-clic) et « Fermer ».

Le panneau se ferme à la désélection. Aucune modification moteur autre que
l'éventuel champ `support`.

## 4. Tirer les arêtes des esquisses (pas seulement les extrémités)

En mode esquisse, outil Sélectionner, seuls les points s'attrapent
(`overEndpoint`). Ajouter le drag d'arête :

- **Hit-test** : au `pointerdown`, si aucun point n'est sous le curseur,
  chercher l'entité sous le curseur à distance réelle de la courbe
  (segment : distance point-segment ; cercle/arc : |distance au centre −
  rayon|), seuil identique à `nearestEntity`. Remplacer au passage le
  hit-test « milieu de segment » de `nearestEntity` par cette distance
  réelle (le clic de sélection en profite aussi).
- **Drag** : `mode.drag = { geo, point: 0 }` (convention Sketcher : 0 =
  courbe entière). Le moteur et le protocole acceptent déjà `point: 0` —
  vérifié : `sketch_move` documente « 0 whole curve ».
- **Solveur local (M3)** : dans `app/solver.js`, le drag d'une courbe
  entière se traduit par le déplacement relatif des deux extrémités
  (ou du centre pour cercle/arc). Si la traduction n'est pas raisonnable
  en planegcs, retourner false pour ce cas → le fallback serveur existant
  (file sérielle `sketch_move`) prend le relais, c'est le comportement
  accepté. Ne pas casser le chemin points existant.
- **Curseur** : `grab`/`grabbing` au survol/drag d'une arête, comme les
  points.

## Validation

- `python3 -m pytest tests/ -q`, `node --check` sur chaque JS modifié.
- Tests JS : ajouter aux tests solveur existants (tests/js) un cas de
  traduction du drag d'arête (ou l'assertion explicite du fallback si non
  traduit).
- Scénario navigateur : étendre `scripts/smoke/smoke.js` d'un drag
  d'arête (attraper le milieu d'un côté du rectangle, le déplacer,
  vérifier zéro erreur console). Garder le scénario existant intact.
- Commit(s) préfixés `[P019]`. Ne pas toucher `app/vendor/`. Français,
  vocabulaire SolidWorks.
