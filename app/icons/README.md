# Icônes

SVG repris **tels quels** du projet [FreeCAD](https://github.com/FreeCAD/FreeCAD),
répertoires :

- `src/Gui/Icons/` (document-*, view-*, zoom-*, edit-*)
- `src/Mod/PartDesign/Gui/Resources/icons/` (PartDesign_*)
- `src/Mod/Sketcher/Gui/Resources/icons/` et ses sous-dossiers
  `general/`, `geometry/`, `tools/`, `constraints/` (Sketcher_*, Constraint_*)

Licence : LGPL, héritée de FreeCAD — compatible avec la licence de ce projet
(LGPL-2.1-or-later). Aucune ressource SolidWorks n'est utilisée ni imitée.

Convention : chaque fichier garde son nom FreeCAD d'origine, pour retrouver
sa source d'un simple grep dans le dépôt FreeCAD. Quand une nouvelle fonction
est implémentée, son icône FreeCAD est ajoutée ici dans le même commit
(voir `docs/fonctions-simples.md`, colonne « Icône »).
