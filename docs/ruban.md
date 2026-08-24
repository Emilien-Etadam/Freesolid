# Le ruban : disposition et référence d'organisation

La disposition du ruban vit dans `app/ribbon.json` ; `app/ribbon.js` la
rend, pour le noyau comme pour les onglets de plugins. Ce document dit
d'où vient l'*organisation* de cette disposition, et ce qui a été décidé
pour les commandes qui n'ont pas d'équivalent ailleurs.

## La référence : FreeCAD-Ribbon, transposé, pas copié

[APEbbers/FreeCAD-Ribbon](https://github.com/APEbbers/FreeCAD-Ribbon) est
la référence d'organisation retenue par `landscape.md` : il range les
vraies commandes de FreeCAD, celles que nous ré-exposons une à une. Son
code est GPL-3.0 — inutilisable chez nous (LGPL-2.1-or-later) — et son
fichier de disposition fait partie de la distribution GPL. On n'a donc
**rien copié** : on a lu sa curation par défaut (`CreateStructure.txt`,
qui engendre `RibbonStructure_default.json` ; relevé sur le commit
`ef4f4737` du 2026-08-11) et transposé les **faits d'organisation** dans
notre format, avec nos libellés.

Les faits transposés :

- **L'outil de profil ouvre l'onglet.** Chez lui, « Create sketch » est
  la première commande (et la plus grosse) du premier panneau PartDesign ;
  `Sketcher_NewSketch` ouvre aussi le panneau outils du Part Workbench.
  Chez nous : *Préparation* (esquisse, corps, plan de référence) ouvre
  Fonctions, et *Courbes* (la courbe 3D, trajectoire des balayages) ouvre
  Surfaces.
- **Un seul panneau Modélisation**, ordonné : bloc additif (Pad,
  Revolution, Loft, Pipe, Helix), séparateur, bloc soustractif (Pocket,
  Hole, Groove), séparateur, Boolean en fin de panneau. Chez nous :
  bossage, révolution, lissage, balayage, hélice ‖ enlèvement, perçage,
  enlèv. révolution ‖ combiner. Le booléen quitte donc l'ancien groupe
  « Corps » ; les additifs et soustractifs ne sont plus mélangés.
- **Habillage** dans l'ordre des barres FreeCAD : Fillet, Chamfer, Draft,
  Thickness — congé, chanfrein, dépouille, coque (la dépouille remonte
  avant la coque).
- **Transformations** (son « Transformation Features », notre ancien
  « Répétitions ») : Linear, Polar, Mirrored, MultiTransform — rép.
  linéaire, rép. circulaire, symétrie, rép. variable. L'ordre était déjà
  le bon ; le libellé du groupe suit.
- **Assemblage** : son panneau Assembly ordonne Create, Solve, Insert,
  Create view (la vue éclatée) — Résoudre remonte en deuxième, Éclater
  rejoint ce groupe. Les liaisons ont leur panneau à part (son « Assembly
  Joints ») : Déplacer puis Contrainte.
- **La hiérarchie visuelle.** Ses commandes de tête sont « large » :
  Create sketch, Pad, Pocket, Fillet, Chamfer, Linear Pattern, Create
  Assembly. Chez nous : `"taille": "large"` dans `ribbon.json` — bouton
  en colonne, icône 24 px, libellé dessous. La Courbe 3D l'est aussi,
  par l'analogie déjà posée « l'outil de profil ouvre l'onglet » (chez
  lui, `Sketcher_NewSketch` est le large de tête du panneau Part).

## La correspondance, bouton par bouton

| FreeSolid | Commande FreeCAD | Panneau APEbbers |
|---|---|---|
| Esquisse, Corps, Plan de référence | `PartDesign_CompSketches`, `_Body`, `_CompDatums` | Part Design Helper Features |
| Bossage, Révolution, Lissage, Balayage, Hélice | `PartDesign_Pad`, `_Revolution`, `_AdditiveLoft`, `_AdditivePipe`, `_AdditiveHelix` | Modeling Features (bloc additif) |
| Enlèvement, Perçage, Enlèv. révolution | `PartDesign_Pocket`, `_Hole`, `_Groove` | Modeling Features (bloc soustractif) |
| Combiner | `PartDesign_Boolean` | Modeling Features (fin de panneau) |
| Congé, Chanfrein, Dépouille, Coque | `PartDesign_Fillet`, `_Chamfer`, `_Draft`, `_Thickness` | Dress-Up Features |
| Rép. linéaire, Rép. circulaire, Symétrie, Rép. variable | `PartDesign_LinearPattern`, `_PolarPattern`, `_Mirrored`, `_MultiTransform` | Transformation Features |
| Surface extrudée, de révolution, lissée | `Part_Extrude`, `_Revolve`, `_Loft` | Part Tools (bloc création) |
| Coudre, Épaissir | `Part_MakeSolid`/couture, `Part_Thickness` | Part Tools (bloc modification) |
| Nouvel assemblage, Résoudre, Insérer, Éclater | `Assembly_CreateAssembly`, `_SolveAssembly`, `_Insert`, `_CreateView` | Assembly |
| Déplacer, Contrainte | (drag amont), `Assembly_CreateJoint*` | Assembly Joints |

Sans équivalent chez lui, placés par analogie :

- **Texte** et **Fonction graphe** : des générateurs de forme — la place
  des `CompPrimitive*` chez lui, en fin de bloc additif.
- **Répéter** (composant) : de l'insertion multiple — après Insérer.
- **Interférences** : garde son panneau *Évaluer* ; l'analyse vit chez lui
  dans un panneau outils global, hors des panneaux d'atelier.

## Ce qui n'est pas transposé, et pourquoi

- **La barre d'accès rapide.** Ses `quickAccessCommands` (New, Open, Save,
  Undo, Redo, Refresh…) sont notre topbar, qui les a déjà — mais la topbar
  n'est pas dans `ribbon.json` à ce jour.
- **Son panneau Structure** (Part, Group, VarSet…) : notre équivalent de
  `Std_VarSet` est le bouton Équations, dans la topbar.
- **Ce que nous n'avons pas** : validate/check geometry, shape binder,
  clone, primitives, joints typés, simulation. La table ci-dessus dit où
  chaque chose ira le jour où elle existera.
