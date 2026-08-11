# Les grandes lignes — piliers SolidWorks et plan d'implémentation

Analyse du 2026-08-11. Avant de multiplier les fonctions, on pose les
piliers qui font de SolidWorks un outil de conception et pas un modeleur :
le paramétrique, les relations, les références, les assemblages, le
surfacique. Pour chaque pilier : ce que fait SolidWorks, ce que le moteur
FreeCAD **headless** permet vraiment (vérifié ou à vérifier par selftest),
et le verdict de faisabilité.

Légende faisabilité : 🟢 l'API headless existe et est sûre ·
🟠 possible avec des réserves à lever par un spike · 🔴 FreeCAD ne l'a
pas — il faudra le construire ou assumer l'écart.

## L'inventaire par rapport à SolidWorks

| Pilier SolidWorks | Ce que c'est | Moteur FreeCAD headless | Verdict | État FreeSolid |
|---|---|---|---|---|
| **Esquisse 2D + relations** | Relations : coïncidente, tangente, égale, parallèle, perpendiculaire, H/V, **symétrique, concentrique, milieu, colinéaire, fixe** ; visualisation et suppression des relations | Sketcher/planegcs les a toutes (`Symmetric`, `Tangent`, `PointOnObject`, `Block`…) ; `delConstraint` | 🟢 | 7 relations faites ; manquent 5 + l'affichage/suppression des relations |
| **Paramétrique : cotes nommées** | Renommer une cote (`largeur@Esquisse1`) | `constraint.Name` + `renameConstraint` | 🟢 | à faire |
| **Paramétrique : variables globales** | `Largeur = 100` réutilisable partout | `App::VarSet` (FreeCAD 1.x) ou `Spreadsheet::Sheet`, 100 % headless | 🟢 | à faire |
| **Paramétrique : équations** | `D1@Bossage1 = 2*Largeur + 5` | moteur d'**expressions** : `obj.setExpression("Length", "…")`, sur cotes ET propriétés de fonctions | 🟢 | à faire |
| **Références géométriques** | Plans décalés/angulaires, axes, points de référence | `PartDesign::Plane/Line/Point` + moteur d'attachement (`AttachmentSupport`, `MapMode`) | 🟢 | à faire |
| **Lissage / balayage / hélice** | Loft, sweep, hélice (ressorts, filets réels) | `PartDesign::Additive/SubtractiveLoft`, `…Pipe`, `AdditiveHelix` | 🟢 | à faire (le vocab les couvre déjà) |
| **Multi-corps** | Plusieurs corps dans une pièce, booléens entre corps | plusieurs `PartDesign::Body` par document + `PartDesign::Boolean` | 🟢 | l'engine est mono-corps par choix M0 |
| **Assemblages** | .sldasm, contraintes (coïncidente, concentrique, distance), mouvement | FreeCAD 1.x a l'atelier Assembly intégré (`Assembly::AssemblyObject`, joints, solveur Ondsel) — **headless à prouver** ; le repli sûr : placements directs sans solveur | 🟠 | rien |
| **Surfacique** | Surfaces extrudées/lissées/balayées, remplir, coudre, épaissir, solidifier | API `Part` : extrusion/révolution de profils ouverts, `makeLoft`, `sewShape`, `makeThickness`, `Surface::Filling` — hors PartDesign (pas d'historique intégré au corps) | 🟠 | rien |
| **Esquisses 3D** | Esquisse dans l'espace (trajectoires, routing) | **pas d'équivalent natif** — Sketcher est 2D ; repli : courbes 3D par points (`Part.makePolygon`, B-splines) comme trajectoires de balayage | 🔴 | rien |
| **Mise en plan** | .slddrw, vues, cotes, cartouche | TechDraw fonctionne en script (pages, vues, export SVG/PDF) — rendu à valider headless | 🟠 | rien |
| **Configurations** | Familles de pièces, table de configurations | très faible côté FreeCAD (liens variants embryonnaires) ; repli : VarSet + « enregistrer sous » piloté | 🔴 | rien |
| **Évaluer** | Masse, volume, centre de gravité, mesurer | `Shape.Volume`, `.CenterOfMass`, distances via API — trivial | 🟢 | à faire |
| **Import/export** | STEP, IGES, Parasolid, 3MF, DXF | STEP/STL faits ; IGES/3MF/DXF disponibles | 🟢 | STEP/STL faits |

Deux écarts structurels à assumer honnêtement : les **esquisses 3D**
(FreeCAD ne les a pas — on offrira des courbes 3D par points, pas un
sketcher 3D contraint) et les **configurations** (au mieux des variantes
pilotées par variables). Tout le reste est atteignable avec le moteur
actuel.

## Le plan d'implémentation

Ordre choisi par fondation : chaque phase rend la suivante possible, et
les plus incertaines (🟠) sont précédées d'un *spike* selftest qui prouve
ou tue l'approche avant d'y investir l'UI.

### Phase A — Le paramétrique complet — **fait** (2026-08-11)

1. **Cotes nommées** : renommer une cote depuis son étiquette
   (`largeur`, `entraxe`) — `renameConstraint`.
2. **Variables globales** : panneau « Équations » listant les variables
   (`App::VarSet`) ; créer/éditer/supprimer.
3. **Équations** : toute cote et toute propriété de fonction accepte une
   expression (`= 2*largeur + 5`) ; les cotes pilotées s'affichent avec
   le préfixe Σ comme dans SolidWorks, la valeur reste visible.
4. **Relations d'esquisse complètes** : symétrique, concentrique, milieu,
   colinéaire, fixe ; affichage des relations d'une entité sélectionnée
   dans le panneau + suppression individuelle — sans quoi une esquisse
   sur-contrainte est un mur.

### Phase B — Références et fonctions d'ossature — **fait** (2026-08-11)

5. **Plans de référence** (décalé d'un plan/d'une face, angulaire) et
   **axes** — indispensables dès qu'une pièce n'est pas un empilement sur
   les 3 plans. L'arbre les range comme SolidWorks.
6. **Lissage** et **balayage** : sélection de plusieurs profils/d'une
   trajectoire dans l'arbre ou la zone graphique, aperçu jaune.
7. **Hélice** (ressorts, filetages réels simples).

### Phase C — Multi-corps puis assemblages *(dans cet ordre)* — **fait** (spike validé : joints natifs + solveur MbD)

8. **Multi-corps** : lever le choix mono-corps M0 — plusieurs corps par
   pièce, corps actif dans l'arbre, booléens entre corps. Prérequis
   technique de l'assemblage et des pièces moulées/imprimées complexes.
9. **Assemblage v1 — sans solveur** : document assemblage, insérer des
   .FCStd, déplacer/orienter à la souris (gizmo de placement), arbre des
   composants. Déjà très utile pour vérifier des empilements à imprimer.
10. **Spike assemblage v2** : prouver par selftest que les joints de
    l'atelier Assembly 1.x (coïncident, concentrique, distance) se créent
    et se résolvent **headless**. Si oui → contraintes complètes ; si non
    → petit solveur de placements maison limité à ces trois contraintes.

### Phase D — Surfacique et courbes 3D — **fait en v1** (2026-08-11)

11. **Surfacique v1** : surface extrudée / de révolution / lissée,
    **coudre**, **épaissir**, solidifier — via l'API Part, présenté dans
    un onglet « Surfaces » du ruban. Assez pour reprendre un scan ou
    fermer un volume.
12. **Courbes 3D par points** (le repli esquisse 3D) : polyligne/B-spline
    3D éditable comme trajectoire de balayage.

### Phase E — Exploitation — **fait** : Évaluer/Mesurer, mise en plan DXF ; configurations assumées = variables + enregistrer sous

13. **Évaluer** : masse/volume/CG (avec densité matière), outil Mesurer.
14. **Mise en plan** TechDraw : une page, vues projetées, export PDF —
    après spike headless.
15. **Configurations limitées** : variantes pilotées par variables
    globales, en assumant l'écart avec les vraies configurations SW.

### Transversal (continue en fond)

- **M3 — solveur planegcs-wasm côté client** : drag d'esquisse à 60 fps.
- Compléter les petites fonctions au fil de l'eau (elles s'insèrent dans
  les panneaux existants sans toucher l'architecture).

## Pourquoi cet ordre

Le paramétrique d'abord parce qu'il change la **nature** de chaque
fonction déjà faite (un bossage piloté par `2*largeur` vaut dix fonctions
nouvelles), qu'il est 100 % vert côté API, et que tout ce qui suit
(références, assemblages pilotés, configurations) s'appuie dessus. Les
assemblages attendent le multi-corps parce que techniquement l'un contient
l'autre. Le surfacique vient après parce qu'il vit hors de l'historique
PartDesign et mérite son propre onglet sans perturber le flux principal.
