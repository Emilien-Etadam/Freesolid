# P023 — Projection orthographique, solide caché en esquisse, Modifier au clic droit

Trois demandes utilisateur, toutes côté client (`app/`), zéro moteur.

## 1. Projection orthographique par défaut — et partout

Aujourd'hui : `THREE.PerspectiveCamera(40, …)` (main.js ~68), aucune
projection orthographique nulle part. La CAO travaille en ortho.

- Remplacer la caméra par une `THREE.OrthographicCamera` : c'est la
  projection **par défaut et unique** — les boutons de vue (iso, face,
  dessus, droite) ne changent que l'orientation, jamais la projection.
- Points d'attention (les vérifier un à un, ils cassent en silence) :
  - `resize()` : recalculer left/right/top/bottom depuis l'aspect, pas
    seulement `camera.aspect`.
  - **Zoom** : OrbitControls zoome une caméra ortho via `camera.zoom`
    (+ `updateProjectionMatrix`), pas par la distance — vérifier molette
    et « Zoom au mieux » (`view-fit`) : l'ajustement doit calculer un
    `zoom` depuis la boîte englobante, pas une distance.
  - Mode esquisse : `toLocal`/`toScreen` (project/unproject) doivent
    rester justes — rejouer le drag de point ET d'arête du smoke.
  - Le plan de coupe visuel (`btn-clip`) et l'aperçu jaune doivent
    rester corrects.
- Si un rendu perspective est souhaitable un jour, ce sera une entrée du
  menu Réglages — hors périmètre ici, ne pas l'ajouter.

## 2. Cacher les volumes pendant l'édition d'esquisse

En entrant en mode esquisse (`freesolid:sketch-enter`, déjà émis) :
masquer les rendus volumiques — maillage du corps actif, autres corps
estompés, surfaces (`visible = false` sur les groupes, pas de dispose).
Les rétablir à la sortie (`freesolid:sketch-exit`), y compris en cas de
sortie par Quitter/Échap ou par sortie automatique (clic Bossage).

- La grille, le calque image d'esquisse et le tracé de l'esquisse
  restent visibles.
- La géométrie de référence reste disponible pour « Convertir les
  entités » (opération moteur, indépendante de l'affichage).
- Cas à vérifier : esquisse sur face d'un solide → le solide disparaît
  bien à l'entrée et revient à la sortie ; refresh de maillage pendant
  l'esquisse (réconciliation serveur) ne doit pas re-rendre le solide
  visible.

## 3. « Modifier » au clic droit sur fonction ou esquisse

Le menu contextuel (`#ctxmenu`, index.html) gagne une entrée **Modifier**
en première position :

- visible pour : fonctions (`editFeature` — le même chemin que le
  double-clic), esquisses (`onSketchRowDblClick`/`sketch_edit`),
  surfaces paramétriques (`editSurface`) ;
- masquée pour : corps, plans, et surfaces figées (celles qui refusent
  déjà l'édition au double-clic — même garde) ;
- pattern existant des entrées conditionnelles : `ctx-color` (attribut
  `hidden` posé par `openMenu` selon la cible).

## Validation

- `node --check` sur chaque JS modifié ; `python3 -m pytest tests/ -q`
  (doit rester vert, rien côté moteur).
- `scripts/smoke/smoke.js` : le parcours complet doit passer tel quel
  en ortho (drags, aperçu, bossage, barre de reprise). Ajouter deux
  pas : (a) pendant l'esquisse, vérifier qu'aucun maillage volumique
  n'est visible (exposer un compteur simple si besoin, ou vérifier par
  capture du canvas que le pad n'occulte plus le tracé — au minimum un
  pas qui entre en esquisse sur une face du bossage et vérifie l'état
  `visible` des groupes via une propriété de debug) ; (b) clic droit sur
  la fonction Bossage → l'entrée Modifier est visible et ouvre le
  panneau d'édition.
- Commit(s) préfixés `[P023]`. Ne pas toucher `app/vendor/`. Français,
  vocabulaire SolidWorks 2025.
