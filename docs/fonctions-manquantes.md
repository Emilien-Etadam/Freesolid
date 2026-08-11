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
| Convertir les entités (projeter des arêtes) | ✅ | `sketch.addExternal(obj, sub)` marche headless — gros manque actuel, à faire tôt |
| Symétrie / répétition d'entités d'esquisse | ✅ | `addSymmetric`, `addCopy`, `addRectangularArray` |
| Décaler les entités | 🟧 | offset de fil (`Part.Wire.makeOffset2D`) puis réinjection ; la version contrainte de SW est plus riche |
| Texte d'esquisse | 🟧 | `Draft.make_shapestring` headless → gravure/embossage possible (marquage de pièces — utile impression 3D) ; gestion des polices à régler |
| Image d'esquisse (calque de fond) | 🟧 | trivial CÔTÉ CLIENT (image posée sur le plan dans Three.js) — reprendre un scan/logo |
| Blocs d'esquisse | ❌ | aucun équivalent FreeCAD |
| Splines de style, courbure peignée | ❌ | outillage GUI profond |

## Fonctions volumiques

| Fonction SW | Verdict | Comment / pourquoi |
|---|---|---|
| Gravure / embossage de texte | 🟧 | ShapeString + poche/bossage — combo codable, très demandé en impression |
| Congé à rayon variable | 🟧 | pas dans PartDesign ; `Part.makeFillet` par arête avec rayons R1/R2 existe → possible hors historique, ou contribution amont |
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
| Remplir (surface de remplissage) | ✅ | `Surface::Filling` marche headless |
| Surface frontière | 🟧 | `Surface::GeomFillSurface` / sections — moins riche que SW |
| Supprimer la face (defeaturing) | 🟧 | `Part.defeaturing` existe selon compilation OCCT |
| Prolonger / ajuster la surface | 🟧 | API OCCT présente, gestes à construire |

## Assemblages

| Fonction SW | Verdict | Comment / pourquoi |
|---|---|---|
| Contraintes mécaniques (crémaillère, vis, engrenages, courroie) | ✅ | déjà dans l'énumération JointType du solveur natif (« RackPinion, Screw, Gears, Belt » vus dans le spike) — il ne manque que l'UI |
| Limites de contraintes (angle/distance min-max) | ✅ | propriétés déjà présentes sur le joint (AngleMin/Max, LengthMin/Max vues au spike) |
| Répétition de composants | ✅ | liens + placements calculés |
| Détection d'interférences | ✅ | intersection booléenne par paires de composants — précieuse avant impression d'assemblages |
| Vue éclatée | 🟧 | animation de placements côté client — codable, spectaculaire |
| Composants flexibles, en contexte | ❌ | édition en contexte = chantier majeur, hors v1 |

## Mise en plan

| Fonction SW | Verdict | Comment / pourquoi |
|---|---|---|
| Vues projetées | ✅ | fait (Face/Dessus/Iso → DXF) |
| Cotes de mise en plan | 🟧 | `TechDraw::DrawViewDimension` scriptable ; placement auto à écrire |
| Coupes, sections, détails | 🟧 | `DrawViewSection` scriptable |
| Nomenclature (BOM) | 🟧 | parcours de l'assemblage → tableau ; export CSV trivial |
| Export PDF de la page | ❌ headless | l'export PDF de TechDraw passe par la GUI ; DXF/SVG restent la voie |

## Données et divers

| Fonction SW | Verdict | Comment / pourquoi |
|---|---|---|
| Import STEP/IGES, export 3MF | ✅ | API Import présente ; à câbler sur Ouvrir/Exporter |
| DWG | ❌ | format propriétaire (convertisseur externe requis) |
| Parasolid, .sldprt natif | ❌ | formats propriétaires |
| Configurations (tables de familles) | ❌ | assumé : variables globales + « enregistrer sous » (fait) |
| Apparences / matériaux visuels | 🟧 | couleurs par corps côté client — simple |
| Plan de coupe visuel (affichage) | ✅ | clipping plane Three.js, client pur — très utile, quasi gratuit |

## Lecture d'ensemble

Le socle SolidWorks est couvert : esquisse contrainte + paramétrique
complet, quinze fonctions volumiques, références, multi-corps,
assemblages contraints par le solveur natif, surfacique v1, mise en
plan DXF, évaluation. Les ❌ se concentrent là où FreeCAD lui-même n'a
pas de moteur (blocs, wrap, formats propriétaires, PDF headless) — aucun n'est bloquant pour le flux
conception → impression 3D. Les prochains ✅ au meilleur rapport
valeur/effort : **convertir les entités**, **gravure de texte**,
**détection d'interférences**, **plan de coupe visuel**, **contraintes
mécaniques (UI)**, **vue éclatée**.
