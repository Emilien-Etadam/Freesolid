# Bijouterie — que reprendre de JewelCraft ?

*Relevé du 2026-08-21, en réponse à la question « peut-on implémenter ces
outils dans FreeSolid ? ».*

[JewelCraft](https://github.com/mrachinskiy/jewelcraft) (Mikhail Rachinskiy,
v3.0.0, Blender ≥ 4.5) est une **boîte à outils de conception de bijoux** :
poser des pierres, générer griffes et sièges, contrôler les écarts, peser le
métal, sortir un rapport de fabrication. Onze ans de métier condensés, et le
seul projet libre qui couvre vraiment ce flux.

Réponse courte : **oui, environ les deux tiers — et ce qui se reprend le
mieux est précisément ce que JewelCraft fait le moins bien**, parce que le
maillage y estime ce que le BRep calcule exactement. Ce qui ne se reprend pas
n'est pas une fonction manquante, c'est un **paradigme** : la déformation de
maillage. Détail ci-dessous.

## 1. La licence, avant tout le reste

**JewelCraft est GPL-3.0-or-later. FreeSolid est LGPL-2.1-or-later.**

C'est exactement la situation de Chili3D relevée dans
[`landscape.md`](landscape.md) — une compatibilité **à sens unique**. Notre
LGPL-2.1-**or-later** peut monter en LGPL-3 puis se combiner à du GPL-3 ;
l'inverse est faux. Reprendre le moindre fichier ferait basculer l'ensemble
distribué en GPL-3, et romprait la promesse affichée au README
(« LGPL-2.1-or-later, comme FreeCAD »).

Ce n'est **pas** le cas de `j8sr0230/Nodes` (N006), qui était sous notre
licence et donc empruntable tel quel.

| Leur dépôt | Reprenable ? |
|---|---|
| `source/**` — tout le code Python | **Non.** GPL-3, et de toute façon écrit contre `bpy`/`bmesh` |
| `assets/gems/gems.blend` — les 17 tailles | **Non.** Asset GPL-3 — et du **maillage**, donc inutilisable dans une chaîne BRep |
| `assets/icons/`, `assets/report/` | **Non.** Même licence |
| Densités des pierres, tables de tailles de bague, facteurs de correction de volume | **Oui** — ce sont des **faits** (gemmologie, métallurgie, normes de taille), pas de l'expression protégeable. À re-sourcer publiquement, pas à copier-coller depuis leur fichier |
| La taxonomie métier — quels outils existent, comment ils s'enchaînent | **Oui**, et c'est la vraie valeur : le travail de conception, pas les lignes |

Donc : **réécrire, jamais importer.** Comme pour `Nodes`, ce n'est pas une
perte — leur code tourne dans `bpy` avec des modificateurs Blender ; notre
moteur est du `freecadcmd` sans GUI. La pile ne se transplante pas.

## 2. L'inventaire complet

Verdicts, même légende que
[`fonctions-manquantes.md`](fonctions-manquantes.md) :
✅ codable (l'API headless existe, effort raisonnable) ·
🟧 codable avec effort ou limites assumées ·
❌ non codable raisonnablement.

### Données pures — presque gratuit

| Outil JewelCraft | Verdict | Comment / pourquoi |
|---|---|---|
| Densités des 18 pierres (diamant 3,53 · corindon 4,1 · zircone 5,9 …) | ✅ | une table dans `engine/vocab.py`, source unique de la terminologie |
| Poids en carats (`ct_calc` : x·y·z × facteur de taille) | ✅ **et mieux** | leur formule *approche* le volume par un facteur de correction (1,025 à 1,888) parce que Blender n'a que du maillage. Nous avons `shape.Volume` **exact** (`kernel.py:1666`). Le facteur reste utile pour une pierre non modélisée ; sinon on le contourne |
| Bibliothèque d'alliages (or 14 k/18 k, argent, platine, palladium…) | ✅ | `mass_properties(density=…)` prend déjà la densité (`kernel.py:1652`) ; il ne manque que la table et son panneau |
| Tailles de bague US/UK/EU/JP → diamètre, circonférence | ✅ | table + `sketch_add_circle` |
| Size Curve (cercle au diamètre d'une taille) | ✅ | esquisse pilotée par une variable globale — le paramétrique de la phase A répond exactement à ça |
| Curve Length Display | ✅ | `wire.Length` |

### Sertissage — le cœur du métier, et FreeCAD y est fort

| Outil JewelCraft | Verdict | Comment / pourquoi |
|---|---|---|
| Cutter (siège sous la pierre) | ✅ **et mieux** | profil révolutionné + `add_boolean` cut (`kernel.py:1752`). Booléen **BRep exact** là où Blender enchaîne des booléens de maillage qui cassent sur les arêtes vives |
| Prongs (griffes) | ✅ | esquisse + `add_revolution` + `add_polar_pattern` (`kernel.py:2393`) — trois fonctions déjà là |
| Auto Prongs (nombre et position calculés) | ✅ | dérivé de la table des tailles ; c'est de la donnée, pas de la géométrie |
| Microprong Cutter (canal entre deux pierres) | 🟧 | `add_curve3d` (`kernel.py:982`) + `add_sweep` (`kernel.py:2211`) ; les positions se dérivent des placements de pierres |
| Gem Add / Edit | 🟧 | **le gros du travail** : les 17 tailles à re-modeler en BRep paramétrique. Chacune = esquisse + révolution ou lissage + répétition polaire. Rien de risqué, mais rien de gratuit — et le `.blend` n'aide pas |
| Gem Recover | ✅ | retrouver l'identité d'une pierre = relire ses métadonnées ; un `App::VarSet` par pierre suffit |
| Asset manager (bibliothèque de composants) | ✅ | `insert_component` (`kernel.py:351`) pose déjà un `.FCStd` en `App::Link`. Manquent l'arborescence de dossiers et les aperçus côté client |

### Distribution et répétition

| Outil JewelCraft | Verdict | Comment / pourquoi |
|---|---|---|
| Radial Instance | ✅ | `add_polar_pattern` |
| Mirror | ✅ | `add_mirror` (`kernel.py:2356`) |
| Distribute / Redistribute on curve | 🟧 | placements par `edge.valueAt` le long d'une courbe. `array_component` (`kernel.py:580`) est aujourd'hui linéaire (dx/dy/dz) — à étendre, ou à confier à la **fonction graphe**, qui sait boucler et lister ([`nodes-macros.md`](nodes-macros.md) §3) |
| Instance Face (semis sur les faces) | 🟧 | même réponse : c'est le cas d'usage canonique de la fonction graphe — « semer 500 perçages sur une surface gauche », mot pour mot le §3 |
| Resize / Incremental Resize | 🟧 | déjà relevé : « matrice sur la forme, hors historique paramétrique » |

### Contrôle et rapport — là où on est presque arrivés

| Outil JewelCraft | Verdict | Comment / pourquoi |
|---|---|---|
| Calculate Weight | ✅ **déjà là à 80 %** | `mass_properties` rend volume, masse, surface, CG, encombrement. Manquent la ventilation par corps et la table d'alliages |
| Select Overlapping (pierres qui se touchent) | ✅ | `check_interference` (`kernel.py:664`) fait déjà les volumes communs par paires. La version JewelCraft est plus fine — un **écart minimal** entre rondistes, pas seulement l'intersection — mais c'est la même mesure, via `measure` (`kernel.py:1683`) |
| Spacing overlay (anneaux d'écart dans la vue) | ✅ **et plus simple** | overlay Three.js côté client. Leur version passe par un shader GPU Blender ; chez nous c'est du dessin dans la scène qu'on a déjà |
| Select by trait (taille / pierre / taille de coupe) | ✅ | filtre sur métadonnées |
| Design Report (HTML) | ✅ | lecture de l'arbre + génération HTML en stdlib pure. Les avertissements (pierres trop proches, siège trop mince) sont des mesures BRep — plus sûres que sur maillage |
| Gem Map (carte colorée annotée) | 🟧 | `make_drawing` (`kernel.py:1124`) sort déjà Face/Dessus/Iso en DXF ; restent le code couleur, les étiquettes et l'export image |

### Le mur : la déformation

| Outil JewelCraft | Verdict | Comment / pourquoi |
|---|---|---|
| Lattice Project | ❌ | déformation de forme libre par cage (FFD). OCCT/PartDesign ne l'a pas, et un modèle BRep n'a pas de sommets à tirer |
| Lattice Profile | ❌ | idem |
| Stretch Along Curve | ❌ | déformer un solide **déjà construit** le long d'une courbe — pas d'équivalent |
| Move Over/Under | 🟧 | poser un objet sur ou sous une courbe est un **placement calculé**, pas une déformation — celui-là passe |

## 3. Pourquoi les ❌ ne sont pas un manque

Le flux JewelCraft est un flux Blender : on modélise un jonc **à plat**, on
le peuple de pierres, puis on **plie** l'ensemble autour du doigt avec une
lattice. C'est la bonne méthode quand la géométrie est du maillage — un
maillage se déforme sans se poser de question.

En CAO BRep paramétrique, on ne plie pas après coup : **on construit courbe
d'emblée**, par révolution ou par balayage le long de la courbe de taille.
Le `add_sweep` et le `add_polar_pattern` que nous avons ne sont pas des
succédanés de la lattice — ce sont les outils du même résultat par l'autre
bout, et ils gardent l'historique rééditable, ce que la lattice perd.

L'écart honnête à assumer est donc étroit : les cas où la déformation est
l'intention elle-même (torsader une bague, écraser un motif sur une forme
gauche). Pour ceux-là, FreeSolid n'a rien et n'aura rien tant qu'OCCT n'a pas
de FFD — même verdict que « enroulement (wrap) » et « forme libre, flex »
déjà consignés dans [`fonctions-manquantes.md`](fonctions-manquantes.md).

## 4. Lecture d'ensemble

Sur les 28 lignes de l'inventaire : **18 ✅, 7 🟧, 3 ❌** — et les ✅ ne
sont pas les faciles par hasard. Le sertissage (siège, griffes) est du
booléen et de la répétition polaire, c'est-à-dire ce que FreeCAD fait mieux
que Blender ; la pesée est déjà écrite et plus exacte que la leur ; le
contrôle d'écarts s'appuie sur `check_interference` et `measure`, qui
existent.

Trois choses seulement coûtent vraiment :

1. **La bibliothèque de pierres** — 17 tailles à modeler en paramétrique.
   Incompressible, sans risque technique, et réutilisable telle quelle
   ensuite. C'est là que part l'essentiel de l'effort.
2. **La distribution sur courbe et sur faces** — à ne pas coder comme une
   fonction de plus, mais comme des **nœuds** de la fonction graphe. Le §3
   de [`nodes-macros.md`](nodes-macros.md) décrit déjà ce besoin ; la
   bijouterie en est le premier client réel.
3. **Le rapport et la carte** — du rendu, pas de la géométrie. Court, mais
   c'est ce qui rend l'outil vendable à un atelier.

Et un préalable non négociable : **rien ne se copie**. GPL-3 contre notre
LGPL-2.1. On reprend l'inventaire, les tables de faits et l'ordre des
gestes ; on écrit le code.

### Ordre proposé, si la piste s'ouvre

Chaque étape se tient seule et rend la suivante possible :

| | Étape | S'appuie sur |
|---|---|---|
| **B1** | Table des matières (pierres, alliages, tailles de bague) + pesée ventilée par corps | `mass_properties`, `vocab.py` |
| **B2** | Siège et griffes paramétriques sur une pierre posée à la main | `add_boolean`, `add_revolution`, `add_polar_pattern` |
| **B3** | Bibliothèque des 17 tailles en `.FCStd`, posées par le gestionnaire d'actifs | `insert_component` |
| **B4** | Distribution sur courbe et semis sur faces, en nœuds | fonction graphe (N004-N006) |
| **B5** | Écarts : contrôle, overlay Three.js, sélection des pierres trop proches | `check_interference`, `measure` |
| **B6** | Rapport HTML et carte des pierres | `make_drawing`, lecture d'arbre |

Une réserve de périmètre, à trancher avant B1 : FreeSolid se présente comme
une **CAO mécanique** face à SolidWorks. La bijouterie est un métier voisin
mais distinct — c'est un **atelier** au sens FreeCAD, pas une extension du
ruban existant. Rien ici ne contredit l'architecture ; la question est celle
du cap, pas de la faisabilité.
