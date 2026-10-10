# Fonctions manquantes par rapport à SolidWorks — et leur codabilité

Inventaire au 2026-08-11, après les phases A-E. Hors périmètre par
décision (2026-08-11) : tôlerie, moules, soudures, PDM/Toolbox,
simulation FEM. Verdicts :
✅ codable (l'API headless existe, effort raisonnable) ·
🟧 codable avec effort ou limites assumées ·
❌ non codable raisonnablement (FreeCAD ne l'a pas, ou c'est soudé à sa GUI).

## Esquisse

| Fonction SW | Verdict | Comment / pourquoi |
|---|---|---|
| Splines (B-splines) | ✅ | `Sketcher` les a (`Part.GeomBSplineCurve`) ; geste client à créer |
| Ellipses, arcs elliptiques | ✅ | idem |
| Convertir les entités (projeter des arêtes) | ✅ **fait** | contour de la face porteuse → géométrie bloquée (lignes/cercles/arcs) |
| Symétrie / répétition d'entités d'esquisse | ✅ | `addSymmetric`, `addCopy`, `addRectangularArray` |
| Décaler les entités | 🟧 | offset de fil (`Part.Wire.makeOffset2D`) puis réinjection ; la version contrainte de SW est plus riche |
| Texte d'esquisse | 🟧 | `Draft.make_shapestring` headless → gravure/embossage possible (marquage de pièces — utile impression 3D) ; gestion des polices à régler |
| Image d'esquisse (calque de fond) | 🟧 | trivial CÔTÉ CLIENT (image posée sur le plan dans Three.js) — reprendre un scan/logo |
| Blocs d'esquisse | ❌ | aucun équivalent FreeCAD |
| Splines de style, courbure peignée | ❌ | outillage GUI profond |

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

| Fonction SW | Verdict | Comment / pourquoi |
|---|---|---|
| Remplir (surface de remplissage) | ✅ **fait** | `Surface::Filling` sur des bords cliqués (surfaces, courbes, arêtes du solide, esquisses), option « tangent aux faces voisines » (G1 sur la face que borde chaque arête). Limite OCCT : un contour fait d'une seule arête fermée (bout de tube) échoue même sans tangence |
| Surface frontière, surface réglée | ✅ **fait** | `Surface::GeomFillSurface` sur 2 à 4 courbes ; `Part::RuledSurface` entre deux courbes — paramétriques |
| Congé de surface | ✅ **fait** | `Part::Fillet` sur une peau cousue (arêtes entre deux faces), rayon rééditable |
| Supprimer des faces, ligne de séparation, désajuster | ✅ **fait** | lieur de forme qui garde les autres faces ; découpe `BOPTools` (mode standard) par une courbe posée sur la surface ; `Surface::Extend` à 0 (bords naturels, trous bouchés) |
| Courbes : composite, projetée, intersection | ✅ **fait** | lieur de forme d'arêtes bout à bout ; `Part::ProjectOnSurface` selon la normale de l'esquisse ; `Part::Section` (deux surfaces, ou surface et solide) |
| Surface radiée, surface médiane, forme libre, aplatir | ❌ | pas de moteur FreeCAD / OCCT exposé pour ces gestes |
| Remplacer la face | ✅ **fait** | la face est prolongée en prisme puis la surface coupe ce qui la dépasse ; forme recalculée à chaque reconstruction ; un booléen d'ajout, d'intersection, ou les deux quand la matière croît et décroît ; clic à travers les surfaces pour viser la face recouverte |
| Couper avec une surface | ✅ **fait** | la surface balaie un demi-espace (extrusion paramétrique) combiné en soustraction dans l'historique ; aperçu, « inverser le côté » en réédition ; refus clair si la surface ne traverse pas le solide |
| Surface plane, balayée, décalée | ✅ **fait** | `Part::Face`, `Part::Sweep` (profil ouvert, trajectoire esquisse ou spline 3D), `Part::Offset` sans remplissage — paramétriques |
| Esquisse 3D | 🟧 **spline 3D faite** | points cliqués sur la pièce (sommets et centres aimantés) ou sur un plan de clic passant par le dernier point (Tab), coordonnées corrigeables, réédition, aperçu exact du moteur ; pas de lignes ni de relations 3D |
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
