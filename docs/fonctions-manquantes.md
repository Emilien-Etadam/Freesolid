# Fonctions manquantes par rapport à SolidWorks — et leur codabilité

Inventaire au 2026-08-11, après les phases A-E. Hors périmètre par
décision (2026-08-11) : tôlerie, moules, soudures, PDM/Toolbox,
simulation FEM. Verdicts :
✅ codable (l'API headless existe, effort raisonnable) ·
🟧 codable avec effort ou limites assumées ·
❌ non codable raisonnablement (FreeCAD ne l'a pas, ou c'est soudé à sa GUI).

## Esquisse

Périmètre complet et critère « fait » : [esquisse.md](esquisse.md).

| Fonction SW | Verdict | Comment / pourquoi |
|---|---|---|
| Splines (par points, par pôles), ellipses, arcs d'ellipse, paraboles, coniques | ✅ **fait** | tracés au clic avec aperçu ; conique en B-spline rationnelle (galbe rho) |
| Convertir les entités | ✅ **fait** | figées (bloquées) ou liées à la pièce (géométrie externe qui suit les cotes) ; courbe d'intersection, points de percée, silhouette |
| Symétrie / répétition d'entités | ✅ **fait** | symétrie, répétition linéaire et circulaire, déplacer / copier / tourner / échelle |
| Décaler les entités | ✅ **fait** | aperçu, côté, originaux en construction |
| Texte d'esquisse | ✅ **fait** | contours des lettres, bloqués |
| Image d'esquisse (calque de fond) | ✅ **fait** | enregistrée avec l'esquisse (jusqu'à 5 Mo) |
| Blocs d'esquisse | ✅ **fait** | créer depuis une sélection, insérer (position, angle, échelle) ; les copies posées ne suivent pas une redéfinition du bloc |
| Splines de style, courbure peignée | ✅ **fait** | convertir en spline, insérer un nœud, augmenter le degré, peigne de courbure, égaliser la courbure (G2) au raccord de deux splines |

## Fonctions volumiques

| Fonction SW | Verdict | Comment / pourquoi |
|---|---|---|
| Gravure / embossage de texte | ✅ **fait** | makeWireString + corps outil combiné dans l'historique ; police système auto-détectée |
| Congé à rayon variable | ❌ | décision 2026-08 : refusé tant que PartDesign ne le porte pas nativement — la voie `Part::Fillet` (validée par sonde : paramétrique, rayons R1/R2, suit le corps) vivrait hors de la chaîne PartDesign (finition terminale, arêtes par indice) ; pas de fonction bricolée |
| Congé de face, congé plein | ❌ | OCCT fragile là-dessus (cf. segfault déjà rencontré) |
| Nervure | 🟧 | pas de PartDesign::Rib ; se construit en esquisse ouverte + pad — un assistant est codable |
| Échelle (scale) | 🟧 | matrice sur la forme, hors historique paramétrique |
| Enroulement (wrap) | ❌ | pas d'équivalent |
| Dôme, forme libre, flex | ❌ | pas d'équivalent |
| Filetage réel | ✅ | fait (hélice) ; assistant filetages normalisés = données + UI |
| Répétition pilotée par esquisse / table | 🟧 | positions lues d'une esquisse de points → MultiTransform ; codable |

## Surfacique avancé

Périmètre complet et critère « fait » : [surfacique.md](surfacique.md).

| Fonction SW | Verdict | Comment / pourquoi |
|---|---|---|
| Remplir (surface de remplissage) | ✅ **fait** | `Surface::Filling` sur des bords cliqués (surfaces, courbes, arêtes du solide, esquisses), option « tangent aux faces voisines » (G1 sur la face que borde chaque arête). Une arête fermée seule (bout de tube) est coupée en deux moitiés par un objet auxiliaire recalculé. Quand le solveur ne tient pas la tangence (faces voisines perpendiculaires : bout de tube), un bouchon B-spline tangent par construction prend le relais (écart < 0,1° au bord), recalculé avec ses sources |
| Surface frontière, surface réglée | ✅ **fait** | `Surface::GeomFillSurface` sur 2 à 4 courbes ; `Part::RuledSurface` entre deux courbes — paramétriques |
| Congé de surface | ✅ **fait** | `Part::Fillet` sur une peau cousue (arêtes entre deux faces), rayon rééditable |
| Supprimer des faces, ligne de séparation, désajuster | ✅ **fait** | lieur de forme qui garde les autres faces ; découpe `BOPTools` (mode standard) par une courbe posée sur la surface ; `Surface::Extend` à 0 (bords naturels, trous bouchés) |
| Courbes : composite, projetée, intersection, hélice | ✅ **fait** | lieur de forme d'arêtes bout à bout ; `Part::ProjectOnSurface` selon la normale de l'esquisse ; `Part::Section` (deux surfaces, ou surface et solide) ; `Part::Helix` (pas, hauteur, rayon, conicité, sens, axe) — paramétriques |
| Surface radiée | ✅ **fait** | `Part::Offset2D` rempli sur un contour plan (arêtes du solide, d'une surface, esquisse), coins vifs |
| Ajustement mutuel | ✅ **fait** | option d'« Ajuster » : l'outil est aussi coupé par la surface, la partie cliquée sur chacune est gardée |
| Surface médiane | ✅ **fait** | deux faces cliquées (plans parallèles et cylindres concentriques exacts, faces inclinées ou courbes par une B-spline passant par les milieux) ou toutes les parois de la pièce sous une épaisseur donnée ; recalculée à chaque reconstruction |
| Forme libre | ✅ **fait** | la surface est convertie en B-spline affinée ; plusieurs points poussés, chacun avec sa hauteur (bosses et creux), rayon d'influence, bords fixes en option ; ou, commande « Pôles », la grille de points de contrôle affichée dans la vue, chaque pôle cliqué déplacé de (dx, dy, dz) ; tout se réédite et suit la surface d'origine |
| Aplatir une surface | ✅ **fait** | `flatmesh` (déroulé conforme par moindres carrés) : patron à plat posé à côté de la surface, exact pour une face développable ; suit la surface d'origine |
| Remplacer la face | ✅ **fait** | la face est prolongée en prisme puis la surface coupe ce qui la dépasse ; forme recalculée à chaque reconstruction ; un booléen d'ajout, d'intersection, ou les deux quand la matière croît et décroît ; clic à travers les surfaces pour viser la face recouverte |
| Couper avec une surface | ✅ **fait** | la surface balaie un demi-espace (extrusion paramétrique) combiné en soustraction dans l'historique ; aperçu, « inverser le côté » en réédition ; refus clair si la surface ne traverse pas le solide |
| Épaissir en enlevant | ✅ **fait** | option « bande épaisse » de la coupe par surface : la surface épaissie (`Part::Offset` rempli) est soustraite ; côté et épaisseur rééditables |
| Surface plane, balayée, décalée | ✅ **fait** | `Part::Face`, `Part::Sweep` (profil ouvert, trajectoire esquisse ou spline 3D), `Part::Offset` sans remplissage — paramétriques |
| Esquisse 3D | ✅ **fait** (spline / polyligne 3D) | points cliqués sur la pièce (sommets et centres aimantés) ou sur un plan de clic passant par le dernier point (Tab) ; segments droits ou lisses ; règles par segment gardées dans la courbe — axe imposé X/Y/Z (Maj+clic le pose), angle avec le segment d'avant, longueur cotée — appliquées par un solveur en chaîne puis une relaxation globale (moteur et aperçu) qui fait tenir ensemble toutes les règles et les points liés, et refuse des règles incompatibles ; points liés (⛓) à un sommet ou un centre de la pièce par un clic aimanté, qui suivent quand la pièce change ; coordonnées corrigeables, réédition, aperçu exact |
| Supprimer la face (defeaturing) | ✅ **fait** | `Shape.defeaturing` sur la fonction courante : forme figée recalculée à chaque reconstruction (elle suit les fonctions d'avant), combinée par un booléen (ajout si le trou se referme, intersection si un bossage part) ; aperçu ; pas d'objet `Part::Defeaturing` headless en 1.1.3 |
| Prolonger / ajuster la surface | ✅ **fait** | prolonger : `Surface::Extend` au-delà du bord cliqué (distance en mm → fractions de l'isocourbe) ; ajuster : découpe `BOPTools` + pièce gardée `CompoundTools`, choisie au clic, « garder l'autre partie » en réédition. La surface remplacée sort de la vue, reste dans l'arbre |

## Assemblages

| Fonction SW | Verdict | Comment / pourquoi |
|---|---|---|
| Contraintes mécaniques (crémaillère, vis, engrenages, courroie) | ✅ **fait** | UI branchée sur les joints natifs (rayons/pas via Distance/Distance2) |
| Limites de contraintes (angle/distance min-max) | ✅ | propriétés déjà présentes sur le joint (AngleMin/Max, LengthMin/Max vues au spike) |
| Répétition de composants | ✅ | liens + placements calculés |
| Détection d'interférences | ✅ **fait** | volumes communs par paires, listés en cm³ |
| Vue éclatée | ✅ **fait** (visuelle) | animation client depuis le centroïde, bouton bascule |
| Composants flexibles, en contexte | ❌ | édition en contexte = chantier majeur, hors v1 |

## Mise en plan

| Fonction SW | Verdict | Comment / pourquoi |
|---|---|---|
| Vues projetées | ✅ | fait (Face/Dessus/Iso → DXF) |
| Cotes de mise en plan | 🟧 | `TechDraw::DrawViewDimension` scriptable ; placement auto à écrire |
| Coupes, sections, détails | 🟧 | `DrawViewSection` scriptable |
| Export PDF de la page | ❌ headless | l'export PDF de TechDraw passe par la GUI ; DXF/SVG restent la voie |

## Données et divers

| Fonction SW | Verdict | Comment / pourquoi |
|---|---|---|
| Import STEP/IGES, export 3MF | ✅ | API Import présente ; à câbler sur Ouvrir/Exporter |
| DWG | ❌ | format propriétaire (convertisseur externe requis) |
| Parasolid, .sldprt natif | ❌ | formats propriétaires |
| Configurations (tables de familles) | ❌ | assumé : variables globales + « enregistrer sous » (fait) |
| Apparences / matériaux visuels | 🟧 | couleurs par corps côté client — simple |
| Plan de coupe visuel (affichage) | ✅ **fait** | clipping Three.js, axe + position + inversion |

## Lecture d'ensemble

Le socle SolidWorks est couvert : esquisse contrainte + paramétrique
complet, quinze fonctions volumiques, références, multi-corps,
assemblages contraints par le solveur natif, surfacique v1, mise en
plan DXF, évaluation. Les ❌ se concentrent là où FreeCAD lui-même n'a
pas de moteur (blocs, wrap, formats propriétaires, PDF headless) — aucun n'est bloquant pour le flux
conception → impression 3D. Les six cibles ✅ prioritaires (convertir
les entités, gravure de texte, interférences, plan de coupe, contraintes
mécaniques, vue éclatée) sont **faites et validées par selftest complet
sur FreeCAD 1.1.3** (2026-08-12). Restent les ✅ secondaires (splines
d'esquisse, ellipses, symétrie/répétition d'entités, remplir,
répétition de composants, limites de contraintes, import STEP/IGES) et
les 🟧.
