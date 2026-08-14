# P016 — Export : facteur d'échelle (compensation d'impression 3D)

Produit, orienté atelier impression 3D : compenser le retrait matière
(PLA ~0,2–0,5 %, ABS plus, résines selon cuisson) sans toucher au
modèle. SolidWorks a sa fonction Échelle ; ici on la met **à l'export**,
non destructive — le paramétrique reste la vérité, le fichier exporté
est agrandi/réduit.

Périmètre : `engine/kernel.py`, `engine/protocol.py`, `app/main.js`
(panneau export), `tests/`, selftest.

## 1. Moteur

`export_part(path, scale=None, scale_z=None)` :

- `scale` : facteur global (float), défaut `None` = 1.0. Bornes de
  bon sens : 0.01 à 100, `KernelError` sinon (« échelle entre 0,01 et
  100 »).
- `scale_z` : facteur vertical séparé optionnel (les imprimantes
  compensent parfois différemment en Z). S'il est absent, Z suit
  `scale`.
- Implémentation : copie de la forme, jamais le document —
  `shape.copy()` puis `transformGeometry(Matrix(sx, 0…))` (matrice
  diagonale sx, sy=sx, sz). La copie transformée part dans l'export
  STL/STEP/3MF existant ; le document n'est **pas** modifié, pas de
  recompute, pas de transaction nécessaire (op en lecture).
- Le retour gagne `"scale": [sx, sy, sz]` quand une échelle ≠ 1 est
  appliquée (sinon champ absent, compat conservée).
- Protocole : `scale`/`scale_z` optionnels non typés (règle P008),
  commentaire mis à jour. Pas de nouvelle op → pas de snapshot à
  changer (le vérifier quand même).

## 2. Client

Le bouton Exporter ouvre son flux actuel — l'enrichir en panneau s'il
est encore un `prompt()` (item 5.2 résiduel), sinon ajouter au panneau
existant :

- chemin (texte, comme aujourd'hui),
- format déduit de l'extension (comportement actuel inchangé),
- « Échelle » (number, défaut 1, min 0.01, step 0.001),
- « Échelle Z séparée » (number, vide par défaut — showIf ou
  placeholder « = échelle » ; n'envoyer que si renseigné),
- note : « Compense le retrait d'impression — le modèle n'est pas
  modifié. Ex. : 1,004 pour un PLA qui rétracte de 0,4 %. »

Après export avec échelle ≠ 1, le message de succès la rappelle :
« Exporté ×1,004 — piece.stl ».

## 3. Selftest

Étendre l'étape export (p18 ou celle qui exporte déjà) :

- Export STL avec `scale=2` d'une pièce connue → recharger le STL est
  lourd ; vérifier plutôt via la forme : l'op peut retourner aussi
  `"bbox"` (boîte englobante de la forme exportée) quand `scale` est
  appliqué → `p18_export_scale_ok` : bbox ×2 vs bbox du corps
  (tolérance 1e-6). Ce champ sert aussi au débogage utilisateur.
- `scale=0` → `KernelError` → `p18_export_scale_invalid_ok`.
- L'export sans échelle doit rester byte-identique en comportement
  (pas de transformGeometry sur le chemin `scale=None`).

## Validation avant push

1. `python3 -m pytest tests/ -q` — tout vert.
2. `node --check` + `node --test` — 50 verts.
3. Selftest FreeCAD : 48 étapes, 97 indicateurs verts attendus (95+2).
4. Smoke local vert.
5. Commit : `[P016] export — facteur d'échelle (compensation retrait impression 3D)`.
