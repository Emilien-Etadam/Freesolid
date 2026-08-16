# P024 — Esquisses visibles et sélectionnables dans le viewport

## Contexte

P019 a branché la sélection d'esquisse (surbrillance + panneau infos)
sur les lignes de l'**arbre**. L'utilisateur voulait aussi — surtout —
le geste SolidWorks : cliquer l'esquisse **dans la zone graphique**.
Constat préalable vérifié : les esquisses libres (non consommées) ne
sont pas rendues du tout dans le viewport — il n'y a donc rien à y
cliquer. Ne rien retirer de P019 : les deux chemins (arbre et viewport)
doivent converger vers la même sélection.

## Mission

### 1. Moteur — `engine/kernel.py`, `tessellate`

Ajouter au maillage un champ `sketches` : les esquisses **libres** du
corps actif (mêmes candidates que `_latest_sketch` — non consommées par
une fonction), chacune sous forme de polylignes :

```
"sketches": [{"name", "label", "positions": […], "indices": […]}]
```

- Géométrie déjà placée en 3D : utiliser `sk.Shape.Edges` (le Shape d'un
  Sketcher::SketchObject est posé dans l'espace) et `discretize`, comme
  le fait déjà le bloc `curves` — même packing (`pack_edges`).
- Géométrie de construction exclue (elle n'apparaît pas dans Shape,
  vérifier que c'est bien le cas).
- Une esquisse vide ne produit pas d'entrée.
- Les esquisses consommées ne sont PAS rendues (comme SolidWorks les
  replie dans leur fonction) — le panneau infos reste accessible par
  l'arbre pour elles.

### 2. Client — rendu

- `showMesh` : un objet lignes par esquisse (`THREE.LineSegments`),
  couleur discrète distincte des courbes 3D existantes (`curvesLines`,
  turquoise) et de la couleur de sélection accent — proposer un blanc
  bleuté genre `0x8fa8c8`. Dans `volumesGroup` (masqué en mode
  esquisse, comme le reste).
- Cycle de vie identique aux autres maillages : retirés/reconstruits à
  chaque `showMesh`, dispose propre (conventions `disposeSubtree` /
  `ownedMaterial` du fichier).

### 3. Client — sélection au clic dans le viewport

- Au `pointerup` de sélection (le chemin qui choisit face/arête) :
  raycast sur les lignes d'esquisse avec un seuil en pixels (même
  calcul que le seuil des arêtes en ortho). Priorité : si une ligne
  d'esquisse est dans le seuil, elle gagne sur la face derrière elle
  (le geste vise l'esquisse, pas le solide).
- Le clic sélectionne l'esquisse **exactement comme le clic d'arbre**
  aujourd'hui : factoriser `selectSketchInTree` en un
  `selectSketch(feature)` partagé (surbrillance accent + panneau infos
  + `selectedSketch` qui présélectionne le profil des fonctions +
  `notifyPick("sketch")` absorbé par lissage/balayage). Re-cliquer la
  même esquisse la désélectionne (même toggle).
- Survol : curseur `pointer` quand une ligne d'esquisse est dans le
  seuil (cohérent avec le reste).
- La désélection existante (clic dans le vide, après une fonction,
  fermeture du panneau) doit continuer à couvrir ce nouveau chemin —
  c'est le même état `selectedSketch`, rien à dupliquer.

### 4. Validation

- `python3 -m pytest tests/ -q`, `node --check` sur chaque JS modifié.
- Selftest : dans une étape existante, indicateur
  `p3_free_sketch_in_mesh` — après une esquisse libre (rectangle non
  extrudé), `tessellate()["sketches"]` contient une entrée avec le bon
  nom et des positions non vides ; après le bossage qui la consomme,
  l'entrée disparaît.
- `scripts/smoke/smoke.js` : un pas — dessiner une esquisse libre
  décalée du solide (rectangle, Terminer), cliquer dessus dans le
  viewport, vérifier que le panneau infos s'ouvre (titre = label de
  l'esquisse) et que `#tree` porte une ligne `.sel` ; Échap/Fermer puis
  la suite inchangée.
- Commit(s) préfixés `[P024]`. Ne pas toucher `app/vendor/`. Français,
  vocabulaire SolidWorks 2025.
