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

---

# 5. Le geste qui compte — poser une pierre, la déplacer

*Ajouté le 2026-08-21. C'est la fonction retenue comme prioritaire : des
pierres **aimantées sur la surface** et **déplaçables à la volée**.*

## 5.1 Les deux tiers sont déjà écrits

| Le maillon | État |
|---|---|
| Savoir **quelle face** est sous le curseur | **fait, par construction.** `pack_mesh` groupe la tessellation par face OCCT ; un raycast Three.js retombe sur exactement un groupe, donc un `faceId` (`engine/protocol.py:546`, `app/main.js:656`) |
| Savoir **où** sur cette face | **fait.** `hit.point` du raycast (`app/main.js:689`) |
| La **normale exacte** en un point | **fait, headless.** `face.normalAt(u, v)` tourne déjà dans ce dépôt (`engine/kernel.py:4419`) |
| L'**inverse** : point du monde → (u, v) | **manque.** `face.Surface.parameter(point)` — une ligne, mais jamais exercée ici |
| Le **placement** de la pierre | manque : rotation qui amène +Z sur la normale, puis translation |

Autrement dit, le clic *sait déjà* ce qu'il faut ; il ne sait pas encore le
dire au moteur.

## 5.2 Ce qu'on stocke — et c'est tout le sujet

Un placement figé (une matrice 4 × 4) suffit à *poser* la pierre. Il ne
suffit pas à l'y **garder** : à la première cote qui change, elle décolle.
C'est le comportement Blender, et il est normal là-bas — un maillage n'a
rien à quoi se raccrocher.

En BRep, la surface **existe encore** après la reconstruction. On peut donc
stocker non pas la position, mais **de quoi la recalculer** :
`(face, u, v, spin, lift)`.

| | Placement figé | Ancrage (u, v) |
|---|---|---|
| Poser la pierre | identique | identique |
| Passer d'une taille 52 à 54 | elle décolle de ~0,32 mm | elle suit le jonc |
| Épaissir le jonc | elle s'enfonce | elle suit |
| Rééditer une fonction en amont | tout à repositionner | rien à faire |
| Fichier `.FCStd` relu dans FreeCAD | des solides posés là | des solides posés là |

**C'est la seule différence, et c'est toute la justification du projet sur
ce point.** Si on stocke une matrice, autant rester sous Blender ; c'est
`(u, v)` qui rend la chose supérieure, pas le format de fichier.

## 5.3 Le drag à 60 fps — le motif planegcs, resservi tel quel

Le dépôt a déjà tranché ce problème une fois, pour l'esquisse : **le client
va vite et approximativement, le serveur dit la vérité au relâchement.** Le
même partage s'applique mot pour mot :

- **`pointermove`** → raycast sur la tessellation déjà en mémoire, la pierre
  suit immédiatement. Aucun aller-retour, donc aucun plafond de fréquence.
- **`pointerup`** → une seule op `move_gem` → projection exacte sur le BRep
  → `(u, v)` exacts → recompute → la pierre se recale sur la surface vraie.

Deux manques côté client, tous deux courts :

1. **Les normales sont approximées.** `geometry.computeVertexNormals()`
   (`app/main.js:323`) moyenne les normales de triangles : la pierre
   facetterait visiblement en glissant sur un jonc. Le correctif est
   d'accepter un tableau `normals` optionnel dans `pack_mesh`, rempli par
   `face.normalAt(u, v)` à chaque sommet de la tessellation. **Bénéfice
   collatéral : tout l'ombrage de l'app y gagne**, pas seulement les pierres.
2. **Pas d'instanciation.** Aucun `InstancedMesh` dans `main.js` : 200
   pierres feraient 200 objets Three.js. Une géométrie, N matrices — c'est
   la forme naturelle, et elle épouse le `PlacementList` d'un `App::Link`
   côté moteur (Q7 de la sonde).

## 5.4 Les trois risques, dont un sérieux

### Le toponaming — celui qui peut coûter cher

`faceId` est un **index entier**. Toute édition en amont renumérote les
faces d'OCCT. C'est déjà le cas pour `add_fillet`, `add_text`, `add_draft` —
tolérable pour trois congés, **intenable pour deux cents pierres** : une
retouche du jonc et le semis entier se disperse.

Trois parades, de la plus sûre à la plus fragile :

| Ancrage | Toponaming | Le geste demandé |
|---|---|---|
| **Sur une courbe** — abscisse le long de la courbe de taille | immunisé : une courbe est un objet de premier rang, pas un index | glisser **le long** du jonc. C'est le `Distribute on curve` de JewelCraft |
| **Sur une esquisse de points** — points projetés sur la surface selon la normale | immunisé : l'esquisse est un objet nommé | glisser les points **dans l'esquisse** — et ce drag-là est **déjà écrit**, c'est planegcs à 60 fps. Déjà relevé 🟧 (« répétition pilotée par esquisse ») dans [`fonctions-manquantes.md`](fonctions-manquantes.md) |
| **Sur la face, en (u, v)** | exposé — à câbler sur l'element map de FreeCAD 1.0, que le dépôt n'utilise nulle part aujourd'hui | glisser **librement sur la surface**. C'est exactement le geste demandé |

Le geste voulu pointe vers la troisième ligne, qui est la moins solide. La
deuxième donne **le même résultat visuel** avec un modèle sûr et un drag
déjà codé, au prix d'un intermédiaire (une esquisse porteuse). Arbitrage à
faire les yeux ouverts, pas à découvrir à la deux-centième pierre.

### La couture

Sur un jonc cylindrique, `u` boucle à 2π. Un drag qui franchit la couture
téléporte la pierre à l'autre bout si `(u, v)` n'est pas normalisé. Sans
gravité — mais à traiter, sinon c'est le bug que l'utilisateur rencontre
dans les dix premières secondes. Q4 de la sonde le mesure.

### Le coût des sièges

N pierres = N booléens, et OCCT s'écroule bien avant 200. La parade
standard : **un compound des N outils, une seule coupe**. Q6 chiffre le gain
réel sur la machine cible.

## 5.5 La surface d'op minimale

Cinq ops, dans le style de `engine/protocol.py` :

| Op | Params | Rend |
|---|---|---|
| `place_gem` | `face`, `x`, `y`, `z`, `gem`, `size` | projette, stocke `(u, v)`, rend le placement |
| `move_gem` | `gem`, `face`, `x`, `y`, `z` | reprojette, met à jour `(u, v)` |
| `spin_gem` | `gem`, `angle` ou `lift` | rotation autour de la normale, enfoncement |
| `remove_gem` | `gem` | — |
| `list_gems` | — | pour le rapport, l'overlay d'écarts et les sièges |

Tout le reste du sertissage est **déjà couvert** : `add_boolean` pour les
sièges, `add_revolution` + `add_polar_pattern` pour les griffes.

## 5.6 Verdict de la sonde — exécutée le 2026-08-21

`scripts/spike-pierres.py` sur **FreeCAD 1.1.3**. Verdict : **vert sur la
chaîne, deux réserves chiffrées.**

### Ce qui est acquis

| | Résultat |
|---|---|
| **Q0** les méthodes existent | 7 sur 7 : `valueAt`, `normalAt`, `tangentAt`, `isPartOfDomain`, `curvatureAt`, `Surface.value`, `Surface.parameter` |
| **Q1** l'inverse point → (u, v) | marche sur les quatre surfaces (plan, cylindre, tore, B-spline). **Les trois voies rendent des (u, v) identiques au millionième** — `Surface.parameter` suffit, les replis sont inutiles |
| **Q1** l'aimantation | **0,00007 à 0,008 mm** entre le point cliqué et le point exact reprojeté. Invisible |
| **Q2** **l'ancrage tient** | jonc de rayon 10 → 12 : la pierre reste **collée**, à la **même hauteur**, au **même angle**, normale toujours radiale. Témoin négatif : un placement figé aurait décollé de **2,0 mm** |
| **Q3** le domaine trimmé | `isPartOfDomain` accepte le plein, **refuse le trou**. Un dépôt hors matière se refuse avant d'exister |
| **Q4** la couture | pas de repli : `u` revient à 6,282 et non à 0. Le drag cartésien traverse la couture sans téléporter |
| **Q7** 200 pierres | `App::Link` + `PlacementList` : **0,002 s**. L'affichage n'est pas un sujet |

**Q2 était le verdict, et il est vert.** L'ancrage `(u, v)` survit au
changement de cote : c'est exactement ce qu'un placement figé ne sait pas
faire, et c'est toute la raison de mener ça en BRep plutôt qu'en maillage.

### Les deux réserves

**Sur surface libre, l'ancrage glisse de 0,13 mm** (Q2b). En bombant un
chaton B-spline de 2,0 à 3,5, la pierre reste *sur* la surface et se
réoriente correctement (10,5° de bascule), mais elle **dérive de 0,13 mm en
plan**. Ce n'est pas un défaut d'implémentation : une B-spline interpolée se
**re-paramétrise** quand ses pôles bougent, donc `(u, v)` ne désigne plus
tout à fait le même endroit.

Portée réelle : nulle sur les surfaces **analytiques** — révolution,
balayage, cylindre, tore, c'est-à-dire **le cas du jonc**, où la
paramétrisation est une formule et ne dérive pas (Q2 le montre à zéro). La
dérive ne concerne que les surfaces libres, et croît avec l'ampleur de la
retouche. À dire à l'utilisateur, pas à masquer.

**Le coût des sièges reste à chiffrer.** À 40 sièges, le compound ne gagne
que **1,6×** sur la coupe une par une (0,98 s → 0,62 s) — utile, pas
décisif. 0,62 s pour 40 pierres ne dit rien de 200 : c'est la **courbe** qui
manque, pas le point.

### Une sonde qui ne mesurait rien

**Q5 était invalide au premier passage.** `Part.Face.tessellate()` met sa
triangulation **en cache sur la forme** : les trois déviations demandées
(0,5 · 0,1 · 0,02) ont rendu trois fois le même maillage — 31 752 triangles,
même écart de 0,0039 mm. La sonde mesurait une seule déviation en croyant en
mesurer trois.

Corrigé (face neuve à chaque tour), en même temps que Q6 qui ne testait
qu'une seule taille. **À relancer** :

```bash
~/squashfs-root/usr/bin/freecadcmd scripts/spike-pierres.py
```

Ce que le second passage doit dire : l'enfoncement réel à la déviation que
l'app utilise (0,1), et si `ms_par_pierre` reste plat entre 40, 100 et 200
sièges — plat, le semis passe d'un bloc ; croissant, il faudra le découper
en paquets.

### Les deux règles que la sonde impose au code

1. **Ne jamais interpoler `u`, ni comparer des écarts de `u`** pour juger
   qu'une pierre en touche une autre. Sur une surface périodique `u` boucle
   à 2π : deux pierres voisines peuvent être à 2π l'une de l'autre en
   paramètre. Les écarts se mesurent **en 3D**, toujours.
2. **Ne jamais stocker une matrice.** Ni comme cache, ni « en attendant ».
   Dès qu'une matrice figée existe quelque part, elle finit par faire
   autorité un jour de reconstruction, et le bénéfice entier disparaît.

### Verdict

🟢 sur le mécanisme — **c'est le bon premier chantier de la piste
bijouterie**. Il réutilise le picking par face (fait), la tessellation
groupée (faite), `normalAt` (fait), et le partage client/serveur de
l'esquisse (fait). Ce qui manque tient en une projection inverse et cinq
ops : voir
[`prompts/P034-pierres-sur-surface.md`](../prompts/P034-pierres-sur-surface.md).
