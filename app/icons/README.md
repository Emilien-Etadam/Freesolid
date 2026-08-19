# Icônes

SVG repris **tels quels** du projet [FreeCAD](https://github.com/FreeCAD/FreeCAD),
répertoires :

- `src/Gui/Icons/` (document-*, view-*, zoom-*, edit-*)
- `src/Mod/PartDesign/Gui/Resources/icons/` (PartDesign_*)
- `src/Mod/Sketcher/Gui/Resources/icons/` et ses sous-dossiers
  `general/`, `geometry/`, `tools/`, `constraints/` (Sketcher_*, Constraint_*)

Licence : LGPL, héritée de FreeCAD — compatible avec la licence de ce projet
(LGPL-2.1-or-later). Aucune ressource SolidWorks n'est utilisée ni imitée.

Les fichiers `FreeSolid_*.svg` sont des icônes originales du projet (même
licence), là où FreeCAD n'en fournit pas (relation colinéaire, réglages).

Convention : chaque fichier garde son nom FreeCAD d'origine, pour retrouver
sa source d'un simple grep dans le dépôt FreeCAD. Quand une nouvelle fonction
est implémentée, son icône FreeCAD est ajoutée ici dans le même commit
(voir `docs/fonctions-simples.md`, colonne « Icône »).

Les fichiers `nodes_*.svg` viennent de
[j8sr0230/Nodes](https://github.com/j8sr0230/Nodes), répertoire `icons/`,
repris **tels quels**. Licence LGPL-2.1, héritée — la même que ce projet.
Les noms d'origine (`nodes_box.svg`, `nodes_arc.svg`, `nodes_add.svg`…)
sont conservés, pour retrouver la source d'un grep dans leur dépôt. Les
deux PNG de leur interface Qt (`nodes_default.png`, `nodes_status_icon.png`)
ne sont pas repris ; un nœud qui n'avait qu'un PNG s'affiche ici avec
`nodes_wb_icon.svg` ou `nodes_math.svg`.
