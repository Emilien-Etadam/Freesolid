# Fonctions simples à implémenter

Analyse du 2026-08-11. Critère « simple » : l'API FreeCAD headless existe et
est sûre (pas de dépendance à la couche Gui), et le geste utilisateur tient
dans l'interaction déjà en place (clic de face, prompt, clic dans l'esquisse).
Chaque fonction embarque son icône FreeCAD (`app/icons/`, noms d'origine)
dans le même commit — voir `app/icons/README.md`.

Le nom affiché est **toujours** le terme SolidWorks 2025 français
(`freesolid/vocab.py` fait foi).

## Palier 1 — trivial (client seul, ou un seul op serveur)

| Fonction (nom SolidWorks) | API / geste | Icône | État |
|---|---|---|---|
| Vues standard (Isométrique, Face, Dessus, Droite) | client Three.js, Ctrl+7/1/5/4 | view-*.svg | **fait** |
| Zoom au mieux | client, touche F | zoom-fit-best.svg | **fait** |
| Annuler / Rétablir (Ctrl+Z / Ctrl+Y) | `doc.UndoMode = 1` + `doc.undo()` / `doc.redo()` | edit-undo.svg, edit-redo.svg | à faire |
| Exporter STL / STEP | `shape.exportStl(path)` / `shape.exportStep(path)` — clé pour l'impression 3D | — | à faire |
| Rectangle par le centre | variante du rectangle existant (centre + coin) | Sketcher_CreateRectangle_Center.svg | à faire |
| Géométrie de construction (bascule) | `sketch.toggleConstruction(geo)` | Sketcher_ToggleConstruction.svg | à faire |
| Esquisse sur plan nommé (Face / Dessus / Droite) | `sketch_start` avec plan d'origine au lieu d'une face | Sketcher_NewSketch.svg | à faire |

## Palier 2 — simple (op serveur + prompt, aucune interaction nouvelle)

| Fonction | API FreeCAD | Icône | Notes |
|---|---|---|---|
| Bossage/Base avec révolution | `PartDesign::Revolution` (axe = axe vertical de l'esquisse, angle) | PartDesign_Revolution.svg | même flux que le bossage |
| Enlèv. de matière avec révolution | `PartDesign::Groove` | PartDesign_Groove.svg | idem |
| Symétrie | `PartDesign::Mirrored` (plan de symétrie = plan d'origine) | PartDesign_Mirrored.svg | prompt : Face / Dessus / Droite |
| Répétition linéaire | `PartDesign::LinearPattern` (direction, longueur, occurrences) | PartDesign_LinearPattern.svg | direction = axe X/Y/Z |
| Répétition circulaire | `PartDesign::PolarPattern` (axe, angle, occurrences) | PartDesign_PolarPattern.svg | |
| Coque | `PartDesign::Thickness` sur la face cliquée (face retirée) | PartDesign_Thickness.svg | le picking de face est déjà là |
| Options du bossage : inversé, plan milieu | propriétés `Reversed`, `Midplane` du Pad/Pocket | PartDesign_Pad.svg | cases dans le prompt |

## Palier 3 — simple côté serveur, petit geste client à créer

| Fonction | API FreeCAD | Icône | Geste |
|---|---|---|---|
| Arc par centre | `Part.ArcOfCircle` | Sketcher_CreateArc.svg | 3 clics : centre, départ, fin |
| Arc 3 points | idem | Sketcher_Create3PointArc.svg | 3 clics sur l'arc |
| Congé d'esquisse | `sketch.fillet(geo1, geo2, …)` | Sketcher_CreateFillet.svg | clic sur deux lignes |
| Ajuster les entités (trim) | `sketch.trim(geo, point)` | Sketcher_Trimming.svg | clic sur le tronçon à couper |
| Rainure droite (slot) | 2 arcs + 2 lignes + contraintes | Sketcher_CreateSlot.svg | 2 clics + largeur |
| Polygone | `Sketcher_CreateRegularPolygon` (géométrie + contraintes égales) | Sketcher_CreateRegularPolygon.svg | centre + sommet + nb côtés |
| Contraintes manuelles (coïncidente, tangente, égale, parallèle, perpendiculaire, horizontale, verticale) | `sketch.addConstraint(...)` | constraints/*.svg | sélection 1-2 entités + bouton |
| Cotation intelligente à 2 entités | `DistanceX/Y`, `Distance`, `Angle` selon la paire | Constraint_Dimension.svg | le vrai réflexe SolidWorks |
| Dépouille | `PartDesign::Draft` (faces + angle, plan neutre) | PartDesign_Draft.svg | faces cliquées, angle au prompt |

## Pas simples — plus tard, en connaissance de cause

- **Assistant de perçage** (`PartDesign::Hole`) : l'API existe mais le
  formulaire est riche (normes, taraudage, fraisage…) — gros travail d'UI.
  Icône déjà prête : PartDesign_Hole.svg.
- **Congé / chanfrein sur arêtes** : demande le *picking d'arêtes* dans le
  viewport (aujourd'hui : faces seulement). C'est le prochain gros chantier
  d'interaction — il débloque le vrai flux SolidWorks des habillages.
- **Lissage / balayage** : multi-esquisses + trajectoire.
- **Multi-corps, plans de référence personnalisés, mise en plan, assemblages.**
- **Solveur dans le navigateur** (planegcs-wasm) : pas une fonction mais le
  chantier M3 — drag à 60 fps.
