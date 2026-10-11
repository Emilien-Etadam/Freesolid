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

État : ✅ icône de Nodes déjà branchée · 🟦 brouillon de Claude branché, à redessiner.

Les brouillons sont générés par `scripts/make_icons.py` (une fonction par icône,
`python scripts/make_icons.py app/icons`). Une icône redessinée dans
`D:\Dev\icones` sous le même nom remplace simplement le fichier de
`app/icons/` ; il faut alors retirer sa fonction du script pour qu'il ne
l'écrase pas.

## 1. Onglet Fonctions — priorité 1

| Commande | Fichier | État |
|---|---|---|
| Esquisse | `fs_sketch.svg` | 🟦 |
| Corps | `fs_body.svg` | 🟦 |
| Plan de référence | `fs_plane.svg` | 🟦 |
| Extrusion | `nodes_extrude.svg` | ✅ |
| Révolution | `fs_revolve.svg` | 🟦 |
| Enlèvement extrudé | `fs_pocket.svg` | 🟦 |
| Enlèvement par révolution | `fs_groove.svg` | 🟦 |
| Perçage | `fs_hole.svg` | 🟦 |
| Lissage | `fs_loft.svg` | 🟦 |
| Balayage | `fs_sweep.svg` | 🟦 |
| Hélice | `nodes_helix.svg` | ✅ |
| Texte | `nodes_text.svg` | ✅ |
| Fonction graphe | `fs_graph_feature.svg` | 🟦 (l'icône de Nodes était trop sombre) |
| Combiner (corps) | `fs_boolean.svg` | 🟦 |
| Congé | `fs_fillet.svg` | 🟦 |
| Chanfrein | `fs_chamfer.svg` | 🟦 |
| Coque | `fs_shell.svg` | 🟦 |
| Dépouille | `fs_draft.svg` | 🟦 |
| Répétition linéaire | `fs_linear_pattern.svg` | 🟦 |
| Répétition circulaire | `fs_polar_pattern.svg` | 🟦 |
| Symétrie | `fs_mirror.svg` | 🟦 |
| Répétition variable | `fs_variable_pattern.svg` | 🟦 |

## 2. Accès rapide — priorité 1

| Commande | Fichier | État |
|---|---|---|
| Nouvelle pièce | `fs_new.svg` | 🟦 |
| Ouvrir | `fs_open.svg` | 🟦 |
| Enregistrer | `fs_save.svg` | 🟦 |
| Annuler | `fs_undo.svg` | 🟦 |
| Rétablir | `fs_redo.svg` | 🟦 |
| Reconstruire | `fs_rebuild.svg` | 🟦 |
| Paramètres | `fs_settings.svg` | 🟦 |

## 3. Onglet Esquisse — tracés et outils, priorité 1

| Commande | Fichier | État |
|---|---|---|
| Sélectionner | `fs_select.svg` | 🟦 (texte seul aujourd'hui) |
| Ligne | `nodes_line.svg` | ✅ |
| Rectangle par sommet | `fs_rect.svg` | 🟦 |
| Rectangle par le centre | `fs_rect_center.svg` | 🟦 |
| Cercle | `nodes_circle.svg` | ✅ |
| Spline | `nodes_bspline.svg` | ✅ |
| Ellipse | `fs_ellipse.svg` | 🟦 |
| Arc par centre | `nodes_arc.svg` | ✅ |
| Arc 3 points | `nodes_arc_3_pt.svg` | ✅ |
| Rainure droite | `fs_slot.svg` | 🟦 |
| Polygone | `fs_polygon.svg` | 🟦 |
| Congé d'esquisse | `fs_sketch_fillet.svg` | 🟦 |
| Ajuster | `fs_trim.svg` | 🟦 |
| Géométrie de construction | `fs_construction.svg` | 🟦 |
| Projeter les arêtes | `fs_project.svg` | 🟦 |
| Cotation | `fs_dimension.svg` | 🟦 |
| Symétrie d'esquisse | `fs_sketch_mirror.svg` | 🟦 |
| Réseau d'esquisse | `fs_sketch_array.svg` | 🟦 |
| Décaler | `fs_offset.svg` | 🟦 (texte seul) |
| Image d'esquisse | `fs_sketch_image.svg` | 🟦 (texte seul) |
| Terminer l'esquisse | `fs_sketch_ok.svg` | 🟦 |
| Quitter l'esquisse | `fs_sketch_cancel.svg` | 🟦 |

## 4. Relations d'esquisse — priorité 2

Petites icônes, surtout vues en 16 px : un symbole simple suffit.

| Relation | Fichier | État |
|---|---|---|
| Horizontale | `fs_rel_horizontal.svg` | 🟦 |
| Verticale | `fs_rel_vertical.svg` | 🟦 |
| Coïncidente | `fs_rel_coincident.svg` | 🟦 |
| Parallèle | `fs_rel_parallel.svg` | 🟦 |
| Perpendiculaire | `fs_rel_perpendicular.svg` | 🟦 |
| Tangente | `fs_rel_tangent.svg` | 🟦 |
| Égale | `fs_rel_equal.svg` | 🟦 |
| Concentrique | `fs_rel_concentric.svg` | 🟦 |
| Colinéaire | `fs_rel_collinear.svg` | 🟦 |
| Milieu | `fs_rel_midpoint.svg` | 🟦 |
| Symétrique | `fs_rel_symmetric.svg` | 🟦 |
| Fixe | `fs_rel_fixed.svg` | 🟦 |
| Relations de l'entité | `fs_relations.svg` | 🟦 |

## 5. Arbre de création — priorité 2

L'arbre réutilise les icônes des commandes ; il lui en faut quelques-unes en
plus.

| Élément | Fichier | État |
|---|---|---|
| Esquisse (dans l'arbre) | `fs_sketch.svg` (même que la commande) | 🟦 |
| Plan d'origine | `fs_origin_plane.svg` | 🟦 |
| Origine | `fs_origin.svg` | 🟦 |
| Équations | `fs_equations.svg` | 🟦 |
| Corps surfaciques | `fs_surface_body.svg` | 🟦 |

## 6. Surfaces, Évaluer, Assemblage — priorité 3

| Commande | Fichier | État |
|---|---|---|
| Courbe 3D par points | `nodes_polyline.svg` | ✅ |
| Surface extrudée | `fs_surface_extrude.svg` | 🟦 |
| Surface de révolution | `fs_surface_revolve.svg` | 🟦 |
| Surface lissée | `fs_surface_loft.svg` | 🟦 |
| Coudre | `fs_sew.svg` | 🟦 |
| Épaissir | `fs_thicken.svg` | 🟦 |
| Mesurer | `fs_measure.svg` | 🟦 (texte seul) |
| Évaluer (masse) | `fs_mass.svg` | 🟦 |
| Équations | `fs_equations.svg` | 🟦 |
| Mise en plan | `fs_drawing.svg` | 🟦 |
| Interférences | `fs_interference.svg` | 🟦 (texte seul) |
| Nouvel assemblage | `fs_assembly.svg` | 🟦 |
| Résoudre | `fs_solve.svg` | 🟦 (texte seul) |
| Insérer une pièce | `fs_insert.svg` | 🟦 |
| Répéter le composant | `fs_component_array.svg` | 🟦 |
| Éclater | `fs_explode.svg` | 🟦 (texte seul) |
| Déplacer le composant | `nodes_translate.svg` | ✅ |
| Contrainte d'assemblage | `fs_mate.svg` | 🟦 |

## Bilan

- 10 commandes ont une icône de Nodes.
- **74 brouillons** branchés, à redessiner : 42 en priorité 1, 17 en priorité 2,
  15 en priorité 3, plus la fonction graphe. Copie dans
  `D:\Dev\icones\freesolid-brouillons\` pour les redessiner.
