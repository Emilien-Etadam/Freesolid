# P014 — Image d'esquisse (calque de fond)

Produit (`docs/fonctions-manquantes.md` : « Image d'esquisse (calque de
fond) — trivial CÔTÉ CLIENT »). Le geste SolidWorks « Image
d'esquisse » : poser un scan, un logo ou un plan papier photographié
sous l'esquisse pour le redessiner par-dessus. Très utilisé pour
reprendre une pièce existante en impression 3D.

**Tout est côté client** : l'image ne quitte jamais le navigateur, ne
touche ni le moteur ni le fichier .FCStd. Périmètre : `app/sketch.js`,
`app/index.html` (un bouton + un `<input type="file">` caché). Aucune
modification `engine/`.

## Le geste

1. En mode esquisse, bouton « Image » dans la barre (à côté de
   Décaler ; icône existante `Image-icon.svg` si vendorée, sinon texte).
2. Sélecteur de fichier (PNG/JPEG/SVG — `accept="image/*"`), lu via
   `FileReader`/`createObjectURL`, jamais envoyé au serveur.
3. L'image apparaît sur le plan d'esquisse : `THREE.TextureLoader` (ou
   `CanvasTexture` depuis un `<img>` décodé) sur un `PlaneGeometry`
   dans le `group` d'esquisse, **derrière la géométrie** (renderOrder
   inférieur aux lignes, `depthTest: false`, opacité ~0.5).
4. Panneau PropertyManager « Image d'esquisse » ouvert dans la foulée :
   - Largeur (mm, défaut 100 — la hauteur suit le ratio de l'image),
   - X / Y du centre (mm, défaut 0/0),
   - Rotation (°, défaut 0),
   - Opacité (0.1–1, défaut 0.5),
   - bouton/row « Supprimer l'image » (row `list` avec onDelete, ou
     équivalent existant du contrat panel.js).
   `onChange` ajuste le mesh en direct (pas de serveur, pas de
   debounce nécessaire). OK ferme le panneau, l'image reste.
5. L'image est **par esquisse** (une seule à la fois suffit) : elle
   survit aux redraw() tant que l'esquisse est ouverte, disparaît à la
   sortie (exit) — pas de persistance, c'est un calque de travail.
   Rouvrir l'esquisse = re-importer si besoin (le noter dans la note
   du panneau).

## Garde-fous techniques

- **Dispose** : le mesh d'image respecte la convention P006 —
  `material.userData.own = true`, texture disposée à la suppression et
  à l'exit. Le `redraw()` reconstruit le groupe : l'image doit être
  préservée comme la `previewLine` (retirée avant `disposeSubtree` +
  `clear`, ré-ajoutée après — même mécanique).
- Le picking d'esquisse (snap, sélection, drag) ne doit PAS voir
  l'image : elle est dans le décor, pas dans `endpoints()`/
  `nearestEntity()` (vérifier que rien ne raycaste dessus).
- `createObjectURL` : `revokeObjectURL` après chargement de la
  texture.
- SVG : laisser le navigateur rasteriser via `<img>` — pas de lib.

## Validation avant push

1. `node --check` sur les JS modifiés ; `node --test` — 50 verts.
2. `python3 -m pytest tests/ -q` — 153 verts (rien moteur).
3. Smoke local vert (l'image n'y est pas scriptée — l'upload de
   fichier en headless est possible via `setInputFiles` : si simple,
   ajouter au smoke une étape « poser une image 2×2 px en data-URL,
   vérifier zéro erreur » ; sinon le dire dans la PR).
4. Description de PR : capture du calque sous une esquisse.
5. Commit : `[P014] esquisse — image de fond (calque client, réglages en direct)`.
