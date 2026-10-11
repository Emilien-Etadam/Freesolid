# Esquisse — périmètre et état

Ce document fixe **ce que « toutes les fonctions d'esquisse » veut dire**
pour FreeSolid : la liste fermée des outils d'esquisse 2D qu'un modeleur
paramétrique de pièces de la classe de SolidWorks propose, et l'état de
chacun. Les noms sont les nôtres (vocabulaire générique de la CAO) ; rien
n'est repris de l'aide, des icônes ni des textes de l'éditeur.

## Critère « fait »

Un outil est **fait** quand :

1. **Moteur** — une op JSON déclarée dans `engine/protocol.py`,
   annulable, qui refuse proprement une entrée impossible (message
   traduit dans `engine/lang/en.json`) — ou, pour un pur geste
   d'interface, une fonction pure testée.
2. **Interface** — un bouton de la barre Esquisse (icône originale,
   infobulle traduite), une consigne dans la barre d'état à chaque clic,
   un aperçu qui suit le curseur pour les tracés.
3. **Relations** — la géométrie créée porte les relations qui la tiennent
   (coïncidences, tangences, parallélismes…), sans redondance.
4. **Tests** — un indicateur du selftest (FreeCAD réel) et/ou des tests
   JS / Python des fonctions pures.
5. **Clic** — le geste vérifié à la souris dans le navigateur.

## Entités

| Outil | État | Op moteur | Test |
|---|---|---|---|
| Ligne (en chaîne), saisie de la longueur et de l'angle au clavier | ✅ | `sketch_add_line` | `m0`, `numeric-draw` |
| Ligne d'axe (construction) | ✅ | `sketch_add_line` (`construction`) | `p51_traces` |
| Point | ✅ | `sketch_add_point` | `p51_traces` |
| Rectangle par sommet, par le centre | ✅ | `sketch_add_rectangle` | `m0`, `p40` |
| Rectangle 3 points, rectangle 3 points par le centre | ✅ | `sketch_add_rect3` | `p51_contours`, `sketchtools` |
| Parallélogramme | ✅ | `sketch_add_rect3` (`parallelogram`) | `p51_contours` |
| Polygone régulier (par un sommet ou par le cercle inscrit) | ✅ | `sketch_add_polygon` | `p3`, `sketchtools` |
| Cercle par le centre, par 3 points | ✅ | `sketch_add_circle` | `p3`, `sketchtools` |
| Arc par le centre, arc 3 points, arc tangent | ✅ | `sketch_add_arc`, `sketch_add_tangent_arc` | `p3`, `p51_traces` |
| Ellipse, arc d'ellipse | ✅ | `sketch_add_ellipse`, `sketch_add_ellipse_arc` | `p17`, `p51_traces` |
| Parabole | ✅ | `sketch_add_parabola` | `p51_traces` |
| Conique (galbe rho) | ✅ | `sketch_add_conic` | `p51_traces` |
| Spline par points de passage, spline par pôles | ✅ | `sketch_add_spline`, `sketch_add_spline_poles` | `p17`, `p51_traces` |
| Rainure droite, par le centre, en arc (centre ou 3 points) | ✅ | `sketch_add_slot`, `sketch_add_arc_slot` | `p3`, `p51_contours` |
| Texte d'esquisse | ✅ | `sketch_add_text` | `p51_complements` |
| Courbe par équation x(t), y(t) | ✅ | `sketch_add_equation` | `p51_complements`, `test_sketchmore` |

## Outils

| Outil | État | Op moteur | Test |
|---|---|---|---|
| Congé, chanfrein (une ou deux distances) | ✅ | `sketch_fillet`, `sketch_chamfer` | `p3`, `p51_edition` |
| Ajuster, prolonger, coin, scinder | ✅ | `sketch_trim`, `sketch_extend`, `sketch_corner`, `sketch_split` | `p3`, `p51_edition`, `p51_complements` |
| Décaler (aperçu, côté, originaux en construction) | ✅ | `sketch_offset` | `p17` |
| Symétrie | ✅ | `sketch_mirror` | `p17` |
| Répétition linéaire, répétition circulaire | ✅ | `sketch_array`, `sketch_polar_array` | `p17`, `p51_edition` |
| Déplacer, copier, tourner, mettre à l'échelle | ✅ | `sketch_transform` | `p51_edition` |
| Convertir les entités (figées ou liées à la pièce) | ✅ | `sketch_convert`, `sketch_reference` (`edges`) | `p14`, `p51_references` |
| Courbe d'intersection (plan ∩ solide, liée) | ✅ | `sketch_reference` (`intersection`) | `p51_references` |
| Points de percée des courbes 3D (liés) | ✅ | `sketch_reference` (`pierce`) | `p51_references` |
| Silhouette (arêtes vues de la pièce, projetées) | ✅ | `sketch_silhouette` | `p51_references` |
| Géométrie de construction | ✅ | `sketch_toggle_construction` | `p1` |
| Blocs : créer, insérer (position, angle, échelle) | ✅ | `sketch_block_save`, `sketch_block_insert` | `p51_complements` |
| Image d'esquisse (gardée avec l'esquisse) | ✅ | `sketch_picture` | `p51_complements` |
| Splines : convertir en spline, insérer un nœud, augmenter le degré | ✅ | `sketch_spline` | `p51_complements` |
| Peigne de courbure, accrochage à la grille | ✅ | client (`curvatureComb`, `gridStep`) | `sketchtools` |

## Relations

| Relation | État | Test |
|---|---|---|
| Horizontale, verticale (ligne ou deux points) | ✅ | `p3` |
| Coïncidente, colinéaire, parallèle, perpendiculaire | ✅ | `p3`, `p7` |
| Tangente, concentrique, égale, symétrique, milieu, fixe | ✅ | `p3`, `p7` |
| Sur l'entité (point sur courbe) | ✅ | `p51_relations_cotes` |
| Corradiale | ✅ | `p51_relations_cotes` |
| Intersection (point au croisement de deux courbes) | ✅ | `p51_relations_cotes` |
| Percée (coïncidence avec un point de percée lié) | ✅ | `p51_references` |
| Relations proposées selon la sélection, liste et suppression | ✅ | `relations-applicable`, `p7` |

## Cotes

| Cote | État | Test |
|---|---|---|
| Longueur, horizontale, verticale, point–point, point–ligne, entre parallèles | ✅ | `p3`, `dim-geometry` |
| Angle entre deux lignes, angle à l'axe | ✅ | `p3`, `p51_relations_cotes` |
| Rayon, diamètre (cercle et arc) | ✅ | `p3`, `p51_relations_cotes` |
| Longueur d'arc | ✅ | `p51_relations_cotes`, `dims` |
| Cotes ordonnées horizontales et verticales | ✅ | `p51_relations_cotes` |
| Cote de référence (pilotée), entre parenthèses | ✅ | `p51_relations_cotes`, `dims` |
| Cotes nommées, expressions, équations | ✅ | `p7` |

## État de l'esquisse

| Fonction | État | Test |
|---|---|---|
| Couleur par état (libre, définie, en trop), degrés de liberté, (-)/(+) dans l'arbre | ✅ | `test_sketch_status` |
| Réparer (redondances, conflits, extrémités presque jointes) | ✅ | `p51_complements` |
| Définir entièrement (cotes ajoutées jusqu'à zéro degré de liberté) | ✅ | `p51_complements` |
| Esquisse 3D | ✅ | voir [surfacique.md](surfacique.md) (`p46_esquisse3d_*`) |

## Hors périmètre (assumé)

- **Égalité de courbure (G2) entre splines** : le solveur d'esquisse de
  FreeCAD n'a pas de contrainte de continuité en courbure ; la tangence
  (G1) est là.
- **Calques d'esquisse, esquisses partagées entre fonctions** :
  organisation du document plutôt qu'outil d'esquisse.

## Comportements à connaître

- **Blocs** : un bloc est un modèle ; l'insérer en copie les entités et
  leurs relations internes. Modifier le bloc ensuite ne met pas à jour
  les copies déjà posées.
- **Texte, courbe par équation, silhouette** : les contours sont
  bloqués (forme exacte) ; pour les changer, on les retrace.
- **Tourner, mettre à l'échelle** : les relations internes à la
  sélection suivent ; celles vers le reste de l'esquisse tombent.
- **Image** : enregistrée avec l'esquisse jusqu'à 5 Mo ; au-delà, calque
  de travail pour la séance.
