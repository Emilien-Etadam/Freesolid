# Icônes à dessiner (Q7)

Le jeu d'icônes de FreeSolid suit le style des icônes de Nodes dessinées par
l'utilisateur (`D:\Dev\icones`, déjà copiées dans `app/icons/nodes_*.svg`) :
- volumes en dégradé bleu (`#c8e0f9` → `#637dca`) ;
- points de contrôle et sommets en rouge ;
- outils et opérateurs en gris métal ;
- format 32 × 32, fond transparent, lisibles en 16 et 24 px sur fond sombre
  (`#23272d`).

Elles remplaceront les icônes reprises de FreeCAD, au style différent, et
les boutons qui n'ont que du texte.

**Livraison.** Un SVG par commande, nommé comme dans la colonne « Fichier »,
déposé dans `D:\Dev\icones`. Claude les copie dans `app/icons/`, retire les
métadonnées d'Inkscape et les branche.

**Ce qui distingue les familles** (pour s'y retrouver d'un coup d'œil) :
- ajout de matière : volume bleu ;
- enlèvement : volume bleu entamé, ou trou ;
- habillage (congé, chanfrein…) : l'arête concernée en rouge ;
- répétitions : plusieurs exemplaires du même petit volume ;
- esquisse : traits blancs, points rouges ;
- relations d'esquisse : petit symbole sur deux traits.

État : ✅ icône reprise de FreeCAD ou de Nodes (ou d'origine FreeSolid) · 🟦 brouillon de Claude branché, à redessiner.

**Règle (2026-10-14).** On garde les icônes de FreeCAD et de Nodes que FreeSolid avait ; les brouillons `fs_*` ne bouchent que les commandes qui n'en ont pas. Le choix tient en une ligne par commande dans `app/icons.js` (rôle → fichier) : brancher une icône redessinée, c'est changer cette ligne.

Les brouillons sont générés par `scripts/make_icons.py` (une fonction par icône,
`python scripts/make_icons.py app/icons`). Une icône redessinée dans
`D:\Dev\icones` sous le même nom remplace simplement le fichier de
`app/icons/` ; il faut alors retirer sa fonction du script pour qu'il ne
l'écrase pas.

## 1. Onglet Fonctions — priorité 1

| Commande | Fichier | État |
|---|---|---|
| Esquisse | `fs_sketch.svg` | ✅ FreeCAD (`Sketcher_NewSketch.svg`) |
| Corps | `fs_body.svg` | ✅ FreeCAD (`PartDesign_Body.svg`) |
| Plan de référence | `fs_plane.svg` | ✅ FreeCAD (`PartDesign_Plane.svg`) |
| Extrusion | `nodes_extrude.svg` | ✅ Nodes (`nodes_extrude.svg`) |
| Révolution | `fs_revolve.svg` | ✅ FreeCAD (`PartDesign_Revolution.svg`) |
| Enlèvement extrudé | `fs_pocket.svg` | ✅ FreeCAD (`PartDesign_Pocket.svg`) |
| Enlèvement par révolution | `fs_groove.svg` | ✅ FreeCAD (`PartDesign_Groove.svg`) |
| Perçage | `fs_hole.svg` | ✅ FreeCAD (`PartDesign_Hole.svg`) |
| Lissage | `fs_loft.svg` | ✅ FreeCAD (`PartDesign_AdditiveLoft.svg`) |
| Balayage | `fs_sweep.svg` | ✅ FreeCAD (`PartDesign_AdditivePipe.svg`) |
| Hélice | `nodes_helix.svg` | ✅ Nodes (`nodes_helix.svg`) |
| Texte | `nodes_text.svg` | ✅ Nodes (`nodes_text.svg`) |
| Fonction graphe | `fs_graph_feature.svg` | ✅ Nodes (`nodes_wb_icon.svg`) |
| Combiner (corps) | `fs_boolean.svg` | ✅ FreeCAD (`PartDesign_Boolean.svg`) |
| Congé | `fs_fillet.svg` | ✅ FreeCAD (`PartDesign_Fillet.svg`) |
| Chanfrein | `fs_chamfer.svg` | ✅ FreeCAD (`PartDesign_Chamfer.svg`) |
| Coque | `fs_shell.svg` | ✅ FreeCAD (`PartDesign_Thickness.svg`) |
| Dépouille | `fs_draft.svg` | ✅ FreeCAD (`PartDesign_Draft.svg`) |
| Répétition linéaire | `fs_linear_pattern.svg` | ✅ FreeCAD (`PartDesign_LinearPattern.svg`) |
| Répétition circulaire | `fs_polar_pattern.svg` | ✅ FreeCAD (`PartDesign_PolarPattern.svg`) |
| Symétrie | `fs_mirror.svg` | ✅ FreeCAD (`PartDesign_Mirrored.svg`) |
| Répétition variable | `fs_variable_pattern.svg` | 🟦 |

## 2. Accès rapide — priorité 1

| Commande | Fichier | État |
|---|---|---|
| Nouvelle pièce | `fs_new.svg` | ✅ FreeCAD (`document-new.svg`) |
| Ouvrir | `fs_open.svg` | ✅ FreeCAD (`document-open.svg`) |
| Enregistrer | `fs_save.svg` | ✅ FreeCAD (`document-save.svg`) |
| Annuler | `fs_undo.svg` | ✅ FreeCAD (`edit-undo.svg`) |
| Rétablir | `fs_redo.svg` | ✅ FreeCAD (`edit-redo.svg`) |
| Reconstruire | `fs_rebuild.svg` | ✅ FreeCAD (`Std_Refresh.svg`) |
| Paramètres | `fs_settings.svg` | ✅ FreeSolid (`FreeSolid_Settings.svg`) |

## 3. Onglet Esquisse — tracés et outils, priorité 1

| Commande | Fichier | État |
|---|---|---|
| Sélectionner | `fs_select.svg` | 🟦 (texte seul aujourd'hui) |
| Ligne | `nodes_line.svg` | ✅ Nodes (`nodes_line.svg`) |
| Rectangle par sommet | `fs_rect.svg` | ✅ FreeCAD (`Sketcher_CreateRectangle.svg`) |
| Rectangle par le centre | `fs_rect_center.svg` | ✅ FreeCAD (`Sketcher_CreateRectangle_Center.svg`) |
| Cercle | `nodes_circle.svg` | ✅ Nodes (`nodes_circle.svg`) |
| Spline | `nodes_bspline.svg` | ✅ Nodes (`nodes_bspline.svg`) |
| Ellipse | `fs_ellipse.svg` | ✅ FreeCAD (`Sketcher_CreateEllipseByCenter.svg`) |
| Arc par centre | `nodes_arc.svg` | ✅ Nodes (`nodes_arc.svg`) |
| Arc 3 points | `nodes_arc_3_pt.svg` | ✅ Nodes (`nodes_arc_3_pt.svg`) |
| Rainure droite | `fs_slot.svg` | ✅ FreeCAD (`Sketcher_CreateSlot.svg`) |
| Polygone | `fs_polygon.svg` | ✅ FreeCAD (`Sketcher_CreateRegularPolygon.svg`) |
| Congé d'esquisse | `fs_sketch_fillet.svg` | ✅ FreeCAD (`Sketcher_CreateFillet.svg`) |
| Ajuster | `fs_trim.svg` | ✅ FreeCAD (`Sketcher_Trimming.svg`) |
| Géométrie de construction | `fs_construction.svg` | ✅ FreeCAD (`Sketcher_ToggleConstruction.svg`) |
| Projeter les arêtes | `fs_project.svg` | ✅ FreeCAD (`Sketcher_Projection.svg`) |
| Cotation | `fs_dimension.svg` | ✅ FreeCAD (`Constraint_Dimension.svg`) |
| Symétrie d'esquisse | `fs_sketch_mirror.svg` | ✅ FreeCAD (`Sketcher_Symmetry.svg`) |
| Réseau d'esquisse | `fs_sketch_array.svg` | ✅ FreeCAD (`Sketcher_RectangularArray.svg`) |
| Décaler | `fs_offset.svg` | 🟦 (texte seul) |
| Image d'esquisse | `fs_sketch_image.svg` | 🟦 (texte seul) |
| Terminer l'esquisse | `fs_sketch_ok.svg` | ✅ FreeCAD (`Sketcher_LeaveSketch.svg`) |
| Quitter l'esquisse | `fs_sketch_cancel.svg` | ✅ FreeCAD (`Sketcher_CancelSketch.svg`) |

## 4. Relations d'esquisse — priorité 2

Petites icônes, surtout vues en 16 px : un symbole simple suffit.

| Relation | Fichier | État |
|---|---|---|
| Horizontale | `fs_rel_horizontal.svg` | ✅ FreeCAD (`Constraint_Horizontal.svg`) |
| Verticale | `fs_rel_vertical.svg` | ✅ FreeCAD (`Constraint_Vertical.svg`) |
| Coïncidente | `fs_rel_coincident.svg` | ✅ FreeCAD (`Constraint_Coincident.svg`) |
| Parallèle | `fs_rel_parallel.svg` | ✅ FreeCAD (`Constraint_Parallel.svg`) |
| Perpendiculaire | `fs_rel_perpendicular.svg` | ✅ FreeCAD (`Constraint_Perpendicular.svg`) |
| Tangente | `fs_rel_tangent.svg` | ✅ FreeCAD (`Constraint_Tangent.svg`) |
| Égale | `fs_rel_equal.svg` | ✅ FreeCAD (`Constraint_EqualLength.svg`) |
| Concentrique | `fs_rel_concentric.svg` | ✅ FreeCAD (`Constraint_Concentric.svg`) |
| Colinéaire | `fs_rel_collinear.svg` | ✅ FreeSolid (`FreeSolid_Collinear.svg`) |
| Milieu | `fs_rel_midpoint.svg` | ✅ FreeCAD (`Constraint_PointOnMidPoint.svg`) |
| Symétrique | `fs_rel_symmetric.svg` | ✅ FreeCAD (`Constraint_Symmetric.svg`) |
| Fixe | `fs_rel_fixed.svg` | ✅ FreeCAD (`Constraint_Block.svg`) |
| Relations de l'entité | `fs_relations.svg` | ✅ FreeCAD (`Sketcher_ToggleConstraint.svg`) |

## 5. Arbre de création — priorité 2

L'arbre réutilise les icônes des commandes ; il lui en faut quelques-unes en
plus.

| Élément | Fichier | État |
|---|---|---|
| Esquisse (dans l'arbre) | `fs_sketch.svg` | ✅ FreeCAD (`Sketcher_Sketch.svg`) |
| Plan d'origine | `fs_origin_plane.svg` | ✅ FreeCAD (`Std_Plane.svg`) |
| Origine | `fs_origin.svg` | ✅ FreeSolid (`FreeSolid_Origin.svg`) |
| Équations | `fs_equations.svg` | ✅ FreeCAD (`VarSet.svg`) |
| Corps surfaciques | `fs_surface_body.svg` | 🟦 |

## 6. Surfaces, Évaluer, Assemblage — priorité 3

| Commande | Fichier | État |
|---|---|---|
| Courbe 3D par points | `nodes_polyline.svg` | ✅ Nodes (`nodes_polyline.svg`) |
| Surface extrudée | `fs_surface_extrude.svg` | 🟦 |
| Surface de révolution | `fs_surface_revolve.svg` | 🟦 |
| Surface lissée | `fs_surface_loft.svg` | 🟦 |
| Coudre | `fs_sew.svg` | 🟦 |
| Épaissir | `fs_thicken.svg` | 🟦 |
| Mesurer | `fs_measure.svg` | ✅ FreeCAD (`view-measurement.svg`) |
| Évaluer (masse) | `fs_mass.svg` | 🟦 |
| Équations | `fs_equations.svg` | ✅ FreeCAD (`VarSet.svg`) |
| Mise en plan | `fs_drawing.svg` | ✅ FreeCAD (`TechDraw_PageDefault.svg`) |
| Interférences | `fs_interference.svg` | 🟦 (texte seul) |
| Nouvel assemblage | `fs_assembly.svg` | ✅ FreeCAD (`Geoassembly.svg`) |
| Résoudre | `fs_solve.svg` | 🟦 (texte seul) |
| Insérer une pièce | `fs_insert.svg` | ✅ FreeCAD (`Link.svg`) |
| Répéter le composant | `fs_component_array.svg` | ✅ FreeCAD (`LinkArray.svg`) |
| Éclater | `fs_explode.svg` | 🟦 (texte seul) |
| Déplacer le composant | `nodes_translate.svg` | ✅ Nodes (`nodes_translate.svg`) |
| Contrainte d'assemblage | `fs_mate.svg` | 🟦 |

## Bilan

- Les commandes de ce relevé : 57 avec une icône de FreeCAD, 11 de
  Nodes, 3 d'origine FreeSolid, 14 brouillons.
- Dans toute l'interface (y compris les commandes ajoutées depuis :
  esquisse, surfaces, références…), **107 brouillons `fs_*`** restent
  branchés, à redessiner. Copie dans
  `D:\Dev\icones\freesolid-brouillons\` pour les redessiner.
