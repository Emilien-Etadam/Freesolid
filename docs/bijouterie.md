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
| Gem Add / Edit | ✅ | **révisé deux fois le 2026-08-21 — voir §7.** Un `.FCStd` par famille de taille, **coté par une esquisse** : le diamètre est une cote, les proportions des expressions. Aucune mise à l'échelle, donc aucune conversion de surface ni cote faussée |
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

1. **La bibliothèque de pierres** — 17 familles de taille, chacune un
   `.FCStd` **coté par une esquisse** (§7). Modelées une fois, redimensionnées
   ensuite par une cote, jamais par une matrice. Le poste reste le plus long
   de la piste : c'est du modelage à la main, et un ovale n'est pas un rond
   étiré — chaque famille se dessine pour ce qu'elle est.
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
| **B3** | Bibliothèque des 17 tailles en `.FCStd` cotés, posés par le gestionnaire d'actifs | §7, `insert_component` |
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

`scripts/spike-pierres.py` sur **FreeCAD 1.1.3**, deux passages. Verdict :
**vert sur toute la chaîne — une seule réserve subsiste, et elle est
bornée.**

### Ce qui est acquis

| | Résultat |
|---|---|
| **Q0** les méthodes existent | 7 sur 7 : `valueAt`, `normalAt`, `tangentAt`, `isPartOfDomain`, `curvatureAt`, `Surface.value`, `Surface.parameter` |
| **Q1** l'inverse point → (u, v) | marche sur les quatre surfaces (plan, cylindre, tore, B-spline). **Les trois voies rendent des (u, v) identiques au millionième** — `Surface.parameter` suffit, les replis sont inutiles |
| **Q1** l'aimantation | **0,00007 à 0,008 mm** entre le point cliqué et le point exact reprojeté. Invisible |
| **Q2** **l'ancrage tient** | jonc de rayon 10 → 12 : la pierre reste **collée**, à la **même hauteur**, au **même angle**, normale toujours radiale. Témoin négatif : un placement figé aurait décollé de **2,0 mm** |
| **Q3** le domaine trimmé | `isPartOfDomain` accepte le plein, **refuse le trou**. Un dépôt hors matière se refuse avant d'exister |
| **Q4** la couture | pas de repli : `u` revient à 6,282 et non à 0. Le drag cartésien traverse la couture sans téléporter |
| **Q6** 200 sièges | **3,4 s** par compound, et le coût par pierre est **plat** (≈ 17 ms). Le semis passe d'un bloc |
| **Q7** 200 pierres | `App::Link` + `PlacementList` : **0,002 s**. L'affichage n'est pas un sujet |

**Q2 était le verdict, et il est vert.** L'ancrage `(u, v)` survit au
changement de cote : c'est exactement ce qu'un placement figé ne sait pas
faire, et c'est toute la raison de mener ça en BRep plutôt qu'en maillage.

### Le coût des sièges — réserve levée

Chiffré au second passage, et proprement.

| Sièges | Une coupe par pierre | Compound, une seule coupe | Gain | Par pierre |
|---|---|---|---|---|
| 40 | 0,97 s | **0,63 s** | 1,5× | 15,6 ms |
| 100 | 3,59 s | **1,67 s** | 2,2× | 16,7 ms |
| 200 | 11,06 s | **3,36 s** | 3,3× | 16,8 ms |

Deux lectures, et la seconde est la bonne nouvelle :

- **Le compound est linéaire** — 15,6 → 16,7 → 16,8 ms par pierre, plat.
  200 sièges coûtent **3,4 s**, et 400 en coûteraient 6,7. Pas
  interactif, mais c'est une reconstruction, pas un drag : parfaitement
  tenable. **Le semis passe d'un bloc, pas besoin de le découper en
  paquets.**
- **La coupe une par une est superlinéaire** — 5× plus de pierres coûtent
  11,4× plus de temps. D'où un gain qui *grandit* avec le semis : 1,5× à
  40, 3,3× à 200, et l'écart continue de se creuser. À 200 pierres le
  compound économise près de huit secondes.

Les deux voies rendent le **même volume** et un **solide valide** : le
raccourci ne coûte aucune exactitude.

### La réserve qui reste

Une seule, et elle ne concerne pas le jonc.

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

### Une sonde qui ne mesure toujours rien — et une hypothèse fausse

**Q5 est cassée aux deux passages.** `Part.Face.tessellate()` a rendu le
même maillage — 31 752 triangles, 0,0039 mm — pour les trois déviations
demandées (0,5 · 0,1 · 0,02).

J'ai supposé un **cache de triangulation sur la forme** et corrigé en
construisant une face neuve à chaque tour. **L'hypothèse était fausse** :
au second passage, face neuve, les chiffres n'ont pas bougé d'un iota.

Hypothèse restante, à départager au prochain passage : sur une face
**analytique** (un tore), le mailleur OCCT subdivise par l'**angle** et la
flèche linéaire ne mord pas. La sonde compare désormais tore et B-spline sur
une plage large (5,0 → 0,01) et rend un drapeau `deviation_agit` : si la
surface libre répond et l'analytique non, la question est close.

**Mais Q5 n'est plus sur le chemin critique**, et c'est ce qui compte. La
question de conception qu'elle portait — *le drag client-side sur la
tessellation est-il assez fidèle ?* — **est déjà tranchée par Q1**, mesurée
sur de vraies tessellations : **0,0025 mm** sur le tore, **0,0028** sur le
cylindre, **0,0076** sur la sphère. Un ordre de grandeur sous le centième de
millimètre. Et rien ne pousse à dégrossir le maillage, puisque Q7 pose 200
pierres en 0,002 s.

La sonde mesure maintenant en plus, directement, l'enfoncement **du maillage
que l'app produit réellement** (déviation 0,1, défaut de
`Kernel.tessellate`) — le seul chiffre dont la conception dépende, et il ne
dépend pas de la réponse ci-dessus.

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

## 5.7 P034 livré — relu le 2026-08-21

Livré sur `cursor/p034-pierres-sur-surface-3d1a`. Relecture faite ; ce que
j'ai pu vérifier ici l'est, le reste est relayé.

**Vérifié dans cette session** — `pytest` 226 passed / 16 skipped, tests JS
114 passed, `node --check` sur les deux fichiers touchés, et la relecture du
code contre chaque exigence du prompt :

| Exigence | Livré |
|---|---|
| Cinq ops, pas une de plus | `place_gem`, `move_gem`, `spin_gem`, `remove_gem`, `list_gems` — exactement |
| Aucun booléen | aucun `cut`/`fuse` dans le chemin de pose |
| Corps paramétrique copié, jamais figé | `doc.copyObject(src, True)` (`kernel.py:1545`) |
| Recalcul depuis `(u, v)` | `_refresh_gem_placements` branché **dans `_recompute`** (`kernel.py:285`) — le point de passage unique de toutes les ops, pas un appel dispersé |
| Le piège du renommage de VarSet | `_gem_varset` (`kernel.py:1465`) — et **mieux que demandé** : préfère la VarSet qui porte `diametre`, ce qui la distingue aussi de l'Équations de la pièce, subtilité que le prompt n'avait pas vue |
| Toponaming signalé, pas subi | `FreeSolidGemError` ; le semis **garde sa dernière pose** au lieu de se disperser |
| Avertir sur surface libre | le libellé de l'arbre porte « (surface libre) » quand la face d'ancrage est une B-spline |
| `normals` optionnel dans `pack_mesh` | présent **ssi** au moins une face en fournit — contrat préservé |
| `InstancedMesh` | un par semis |

**Relayé, non vérifiable ici** (ni FreeCAD ni navigateur dans cette session) :
selftest 68 étapes / 179 verts dont `p034_ancrage`, et smoke Playwright sans
erreur. À noter que le selftest a repris le **témoin négatif** de la sonde
(`p034_temoin_fige`) : il ne vérifie pas seulement que la pierre suit, mais
qu'un placement figé, lui, aurait décroché.

**Une réserve de traçabilité, pas de code.** `docs/bijouterie.md`, les trois
sondes et `prompts/P034` vivent sur `claude/freesolid-tools-1em7o1` et ne
sont **pas encore sur `main`**. La mise en œuvre y arrivera par sa propre
branche, mais son raisonnement — pourquoi coté et non mis à l'échelle, les
chiffres qui l'ont tranché — resterait orphelin, et la section « validation »
de P034 renverrait à des sondes absentes. À fusionner avec.


## 5.8 P036 livré — relu le 2026-08-21

Livré sur `cursor/p036-glisser-coter-reconstruire-b595`, **empilé sur P034**
(qui n'était pas fusionné). CI verte sur `d9e31da`, 6 checks sur 6.

**Vérifié ici** — `pytest` 244/16 (contre 226 après P034), tests JS 121
(contre 114), `node --check` sur les quatre fichiers touchés, et lecture du
code contre chaque point du prompt.

| Point du prompt | Livré |
|---|---|
| Migration d'une face à l'autre | `move_gem` (`kernel.py:2078`) : entrée retirée du semis de départ, semis d'arrivée trouvé ou **créé**, puis `_drop_empty_semis` |
| Pas de semis fantôme | `_drop_empty_semis` (`kernel.py:1875`) — et **au-delà du demandé** : il retire aussi le corps de gemme quand plus aucun lien ne le référence |
| Cote hors esquisse | `app/dims.js`, module neuf **partagé** entre le mode esquisse et le viewport — extrait plutôt que dupliqué, avec ses propres tests |
| Bouton Reconstruire | op `rebuild` (`kernel.py:325`) : recalcul forcé, replacement des semis, **erreurs remontées** et non avalées |

### Le point 0 a répondu, et c'était la mauvaise nouvelle

Des trois issues que le prompt listait, c'est **la deuxième** qui s'est
présentée : *la cote change, rien ne bouge à l'écran*. Un vrai défaut de
rafraîchissement, pas de l'ergonomie.

Le commentaire du correctif le nomme sans détour (`kernel.py:5525`) :

> `_recompute` applique aussi `PlacementList` des semis : sans le second
> passage, la cote change et l'écran ne suit pas.

`sketch_set_dim` appelait `doc.recompute()` seul au lieu du `_recompute()`
du noyau — donc sans la passe qui recale les semis. La consigne tenait :
**le bouton Reconstruire n'a pas servi de cache-misère**, la cause a été
corrigée d'abord.

C'est aussi la confirmation du diagnostic posé dans le prompt : le selftest
prouvait l'ancrage côté moteur, donc le défaut était **entre le moteur et le
client**. Il l'était.

### Où en sont les branches

`main` porte le relevé, les sondes et les prompts, mais **ni P034 ni P036** —
les deux vivent empilés sur la même branche Cursor, PR en brouillon. `main` a
avancé de son côté (N011, N011b). La fusion apportera donc les deux d'un
coup, et devra se rapprocher de `main` d'abord.


---

# 6. Une gemme est un solide figé, pas une fonction

> **Révisé au §7** : la voie retenue n'est finalement ni la
> chaîne paramétrique lourde du §2, ni le BREP mis à l'échelle
> décrit ici, mais un `.FCStd` **coté par une esquisse**. Ce
> chapitre reste pour ce qu'il a établi et pour ce qu'il a
> écarté ; la conception vivante est au §7.

*Révision du 2026-08-21. Le §2 chiffrait les 17 tailles comme « le gros du
travail : à re-modeler en BRep **paramétrique** ». C'était une erreur
d'analyse, et elle coûtait cher.*

## 6.1 Ce que j'avais mal posé

Une taille de pierre est une **géométrie normalisée et figée**. Un brillant
rond a 57 facettes dans des proportions publiées : table à 57 % du diamètre,
couronne à 16,2 %, rondiste à 3 %, culasse à 43 %. **Personne ne réédite
l'angle de couronne d'un diamant dans un historique de fonctions** — on
choisit une taille et trois dimensions.

L'historique paramétrique est donc de la machinerie **inutile** ici. Ce
qu'il faut d'une gemme :

- une géométrie **exacte** — facettes planes, arêtes vives, rondiste net ;
- une mise à l'échelle en **x, y, z indépendants** (un ovale est un rond
  étiré) ;
- un coût nul à l'instanciation, deux cents fois ;
- un volume exact, pour le carat.

Un **BREP** — le `TopoDS_Shape` d'OCCT lui-même — donne les quatre. Pas de
conversion, pas de tessellation, pas de perte.

*(Contenant : un `.FCStd`, pas un `.brep` nu — 6,3 × plus petit, et déjà lu
par `insert_component`. Mesuré au §6.7.)*

## 6.2 Ce que ça change

| | Ce que j'avais écrit | Ce qu'il faut lire |
|---|---|---|
| La forme d'une taille | 17 chaînes PartDesign à construire et à maintenir | 17 **solides BREP** modelés une fois, jamais retouchés |
| Le dimensionnement | des cotes pilotées par expressions | une matrice d'échelle x/y/z |
| Le verdict | 🟧 « le gros du travail » | ✅ — long à dessiner, nul à entretenir |
| L'origine | à modeler dans FreeSolid | **n'importe quelle source** : FreeCAD, un STEP fournisseur, un scan |

Le poste reste le plus long de la piste bijouterie — dessiner dix-sept
tailles justes prend du temps. Mais c'est du **modelage à la main**, fait une
fois, pas de la mécanique à entretenir à chaque évolution du moteur. La
différence est celle d'un actif et d'une dette.

## 6.3 Le gain caché : le carat devient exact

C'est la conséquence qui vaut le détour.

JewelCraft calcule le poids en carats par `x · y · z × facteur de
correction`, où le facteur est **tabulé** par taille (de 1,025 à 1,888).
C'est une approximation, et elle est là parce que Blender n'a que du maillage
sous la main.

Avec un BREP, `shape.Volume` est **exact**. Et sous une mise à l'échelle
`(sx, sy, sz)`, le volume est multiplié par `sx · sy · sz` — le déterminant
de l'affinité. Donc :

> le rapport `Volume / (x · y · z)` est **invariant par dimension**.

Autrement dit : **le facteur de correction de JewelCraft se dérive de la
géométrie**, une seule fois par taille, au lieu d'être tabulé — et il devient
exact. On calcule le volume du modèle de référence, on multiplie, c'est fini.
Aucun volume à recalculer par pierre, aucune table à recopier — et, incident
utile, aucun risque de licence puisqu'on ne reprend rien.

## 6.4 Le point à surveiller : l'échelle non uniforme

`transformGeometry()` applique une **affinité**. Un plan reste un plan : une
gemme **tout facettes** traverse l'opération intacte.

Une surface **analytique courbe**, non : OCCT convertit cône et cylindre en
B-splines — et **même à l'échelle (1, 1, 1)**, la seule conversion coûte
**1,18 % de volume** (§6.7). Ma formulation initiale — « plus lourd et plus
fragile » — sous-estimait : c'est 1,18 % de **carat**, soit 0,012 ct sur une
pierre d'un carat. Commercialement, ce n'est pas du bruit.

D'où une consigne de modelage, pas de code : **facetter la gemme, rondiste
compris**. C'est d'ailleurs ainsi que les pierres sont taillées, et la sonde
chiffre l'écart entre les deux voies au lieu de le supposer.

## 6.5 La sonde

```bash
freecadcmd scripts/spike-gemmes-brep.py
```

Six questions : l'aller-retour `.brep` est-il exact au bit près (G1) ; ce que
l'échelle non uniforme fait aux surfaces (G2) ; **le volume se multiplie-t-il,
donc le carat devient-il exact (G3, le verdict)** ; une gemme importée
sert-elle d'outil de booléen pour creuser le siège (G4) ; 200 instances (G5) ;
et ce que pèse la bibliothèque sur le disque (G6).

Le banc d'essai construit un brillant rond en deux versions — tout facettes
et rondiste analytique — aux proportions réelles, pour que G2 et G4 portent
sur de la vraie géométrie de pierre et pas sur un cône.

## 6.6 Ce que ça ne change pas

Le mécanisme de placement ([`P034`](../prompts/P034-pierres-sur-surface.md))
est **indifférent** à ce que la pierre contient. Il pose un `Part::Feature`
via un `App::Link` et le déplace par `(u, v)` ; que la forme dedans vienne
d'un cône témoin ou d'un `.brep` de brillant ne modifie aucune de ses
décisions. P034 reste livrable tel quel, et la gemme s'y substituera sans
retouche.

## 6.7 Verdict de la sonde gemmes — exécutée le 2026-08-21

`scripts/spike-gemmes-brep.py` sur **FreeCAD 1.1.3**. La sonde a affiché
**ROUGE**, et elle avait tort : **les deux échecs venaient de mes critères,
pas de la conception.** Les deux corrections valent d'être lues, l'une
parce qu'elle était une erreur de test, l'autre parce qu'elle a révélé un
piège réel.

### Ce qui est acquis

| | Résultat |
|---|---|
| **G1** aller-retour `.brep` | **exact** : faces et arêtes identiques, forme valide. Lecture en **0,2–0,4 ms**. `Shape.importBrep` est le bon lecteur |
| **G4** gemme en outil de booléen | **tient** : solide valide, un seul solide, matière enlevée. 73 ms pour la facettée, 36 ms pour l'analytique. Les facettes vives ne font pas trébucher OCCT |
| **G5** 200 gemmes | **0,001 s**, et le document ne pèse que **113 octets par pierre** — une forme, N placements |
| **G3** l'échelle | **rigoureusement multiplicative** dans les deux cas (écart 1,6e-9) |

### Correction 1 — mon critère de G1 était faux

J'exigeais l'égalité **binaire** des volumes avant et après l'aller-retour.
La gemme analytique tombait à 5,6 × 10⁻¹⁷ mm³ d'écart, soit **2,5 × 10⁻¹⁶ en
relatif : un ULP de `float64`**. Ce n'est pas la forme qui diffère — faces et
arêtes sont identiques — c'est l'intégrale de volume qui ne se rejoue pas bit
pour bit. Critère corrigé en tolérance relative. **G1 est vert.**

### Correction 2 — G3 mélangeait deux effets, et le second est un piège

Le premier passage annonçait « volume non multiplicatif » pour la gemme
analytique, sur un écart de **1,1763 %**. Mais cet écart était **le même aux
quatre échelles**, au chiffre près — signature d'un coût payé **une fois**,
pas d'une dérive.

En imposant l'échelle (1, 1, 1) — l'identité — on isole le coupable :

| | Coût de la seule conversion | Échelle multiplicative ? |
|---|---|---|
| Gemme **facettée** | **0 %** (1 × 10⁻¹⁶) | oui, 1,3 × 10⁻¹⁶ |
| Gemme **analytique** | **1,1763 %** | oui, 1,6 × 10⁻⁹ |

Ce n'est donc pas l'échelle qui trahit, c'est la **conversion** que
`transformGeometry` impose : cône et cylindre → B-spline, et l'approximation
coûte 1,18 % de volume avant même qu'on ait mis à l'échelle quoi que ce soit.

**La conclusion de conception, et elle sauve tout :**

> Le carat se calcule depuis le volume de la forme **de base**, multiplié par
> `sx · sy · sz`. **Jamais depuis la forme mise à l'échelle.**

Alors il est exact **dans les deux cas** — la conversion n'affecte que la
géométrie affichée et découpée, pas le poids. Ma revendication du §6.3 tient
donc entièrement : **le facteur tabulé de JewelCraft se dérive de la
géométrie, une fois par taille, et devient exact.** Il fallait seulement le
calculer du bon côté de la transformation.

### Le piège que la sonde a trouvé sans qu'on le cherche

`BoundBox` d'une gemme analytique mise à l'échelle 4 × 6 rend
**6,0 × 10,392** au lieu de 4,0 × 6,0. Ratios : **1,5 et √3**.

Ce sont exactement les facteurs d'un cercle représenté en **trois arcs
rationnels** : le triangle de contrôle a ses sommets à 2r, l'un d'eux sur
+X — d'où une étendue de 3r en X (1,5 × le diamètre) et 2 × 2r·sin 60° en Y
(√3 fois). **`BoundBox` borne les pôles de la B-spline, pas la surface.**

Conséquence directe : **une pierre dont on lirait les cotes sur `BoundBox`
serait annoncée jusqu'à 70 % trop grosse** dans le rapport de fabrication.
Les cotes se prennent sur les `(sx, sy, sz)` nominaux — qu'on connaît — ou
sur `optimalBoundingBox()`, que la sonde interroge désormais.

### Correction 3 — le format de la bibliothèque s'inverse

| | Une gemme | 17 tailles |
|---|---|---|
| `.brep` | 47,8 ko | **793 ko** |
| `.FCStd` | 7,5 ko | **125 ko** |

**`.FCStd` est 6,3 × plus petit** — c'est une archive zip, et le BREP s'y
comprime bien. Il est de surcroît **déjà lu par `insert_component`**
(`engine/kernel.py:351`) et peut porter les métadonnées de la taille en
propriétés natives.

La remarque qui a lancé cette révision — *« les pierres peuvent être des
BREP »* — reste juste sur le fond, qui était la **nature** de l'objet : une
forme figée, pas une fonction paramétrique. Seul le **contenant** change :
le BREP voyage dans un `.FCStd`, pas dans un `.brep` nu.

### Une réserve à ne pas laisser passer

Le budget des sièges du §5.6 — **3,4 s pour 200** — a été mesuré avec des
**cônes simples**. G4 montre qu'une vraie gemme facettée coûte **73 ms** par
booléen contre 36 pour une forme analytique : deux fois plus. Ce budget est
donc à **re-mesurer avec une vraie gemme** avant d'être cité. Il ne remet pas
en cause la linéarité établie en Q6, mais son ordonnée à l'origine, oui.

---

# 7. La gemme cotée — la conception retenue

*Révision du 2026-08-21, la troisième et la bonne. Elle vient d'une remarque
de l'auteur : « la pierre est un fichier FreeCAD avec une cote dans une
esquisse pour son diamètre, donc pas d'échelle à faire, c'est
paramétrique. »*

## 7.1 Pourquoi les deux premières voies étaient fausses

| Voie | Ce qui clochait |
|---|---|
| **§2 — 17 chaînes PartDesign** | j'y voyais « le gros du travail » et une mécanique à entretenir. Surestimé : une gemme se modèle une fois |
| **§6 — un BREP figé, mis à l'échelle en x/y/z** | la sonde a chiffré le prix : `transformGeometry` **convertit** cône et cylindre en B-splines — **1,18 % de volume perdu avant toute mise à l'échelle** — et `BoundBox` borne alors les pôles au lieu de la surface, d'où des **cotes annoncées jusqu'à 70 % trop grosses** |

La voie cotée supprime les deux **par construction** : on ne transforme plus
rien, donc rien ne se convertit ; les surfaces restent celles que le modèle
décrit, et la boîte englobante redevient serrée.

## 7.2 L'argument qui n'est pas numérique, et qui pèse le plus

Il y a mieux que la précision, et je ne l'avais pas vu :

> **Un ovale n'est pas un rond étiré.**

Un brillant ovale n'a pas l'agencement de facettes d'un brillant rond qu'on
aurait tiré dans un sens — il en a un autre, avec un nombre de facettes et
des proportions qui lui sont propres. `transformGeometry` produisait donc
une pierre **vraisemblable et fausse**. Une gemme cotée modèle chaque famille
de taille **pour ce qu'elle est**, et expose les cotes qui lui appartiennent :

- rond, princesse, asscher, octogone → **un diamètre** ;
- ovale, marquise, poire, émeraude, baguette → **longueur et largeur** ;
- la profondeur suit un ratio normalisé, libérable si le client le veut.

C'est exactement ce que l'esquisse sait faire, et ce qu'une matrice d'échelle
ne saura jamais.

## 7.3 Ce que ça coûte, et où

Le coût se déplace : plus de conversion, mais **un recalcul par taille**.

Et « par taille » n'est pas « par pierre ». Deux cents pierres de 1,5 mm sur
un même jonc, c'est **un** recalcul et deux cents placements — Q7 et H5
montrent que les placements sont gratuits. Ce qui pèse, c'est le nombre de
**diamètres distincts** dans la pièce : rarement plus d'une poignée.

Le moteur a donc besoin d'un **cache de formes**, clé `(taille, cotes)` :
recalculer une fois, instancier N fois. C'est une ligne de conception, pas
une difficulté.

## 7.4 Où vit le fichier — tranché, et par une troisième voie

*Décision du 2026-08-21 : « on ne laisse pas utiliser de formes importées,
on va créer une bibliothèque de fichiers FreeCAD paramétrables. »*

Ce document n'opposait que deux options, et **aucune n'était bonne** :

| | Lien externe | Forme importée |
|---|---|---|
| La pièce reste rééditable en taille | oui | **non — la pierre est figée** |
| Le `.FCStd` est autonome | **non — dépend d'un fichier** | oui |

Il en existe une troisième, et elle a les deux qualités : **copier l'objet
paramétrique lui-même** dans la pièce. `Document.copyObject(corps, True)`
amène la variable, l'esquisse et la révolution avec elle. Alors :

- la pièce est **autonome** — aucun fichier externe à retrouver ;
- la pierre reste **entièrement paramétrable** — son diamètre est toujours
  une cote d'esquisse, éditable sur place, dans la pièce ;
- la bibliothèque devient ce qu'elle aurait toujours dû être : un jeu de
  **gabarits qu'on instancie**, pas une dépendance d'exécution.

Rien n'est « importé » au sens d'une forme morte : c'est le **modèle** qui
voyage, pas son résultat. H9 le vérifie, et vérifie surtout le piège
pratique : deux gemmes copiées dans une même pièce portent le même nom de
variable à l'origine, et FreeCAD renomme en silence. Le moteur doit retrouver
**la** variable de **chaque** pierre, pas la première venue.

## 7.4 bis — On pose, puis on combine. On ne pose pas des trous

*Même décision, et c'est la plus structurante des trois.*

Poser une pierre **n'enlève pas de matière**. La pierre est un solide posé
sur la surface ; le **siège se creuse plus tard**, en une opération séparée
et explicite.

La raison est dans les chiffres déjà mesurés :

| | Coût |
|---|---|
| Poser ou déplacer 200 pierres | **0,001 s** (H5) |
| Creuser 200 sièges | **3,4 s** au mieux, et davantage sur une pierre facettée (Q6, G4) |

Si le siège se creusait au moment du placement, **chaque déplacement de
pierre relancerait le booléen** — et le geste « déplaçable à la volée », qui
est tout l'objet de la demande, deviendrait impraticable. En séparant :

1. **on pose** — instantané, réversible, on déplace tant qu'on veut ;
2. **on combine** — une fois, quand le semis est arrêté, par un compound des
   N outils et **une seule** coupe (Q6 : linéaire, ≈ 17 ms par pierre).

C'est aussi la façon dont un joaillier travaille : on place les pierres, puis
on serti. Et cela rend le budget des sièges **secondaire** : il se paie une
fois, sur commande, comme une reconstruction — pas dans la boucle
d'interaction.

Conséquence pour [`P034`](../prompts/P034-pierres-sur-surface.md) : son
périmètre était déjà le bon — placer, déplacer, tourner, retirer, lister —
et il le reste.

**Correction du 2026-08-21.** J'avais traduit « on combine » par « sertir »,
et écrit un prompt entier là-dessus : gabarits de sièges, jeu de desserrage,
ouverture pour la lumière, garde sur le jonc scindé. C'était une inférence,
pas une consigne — l'auteur combine lui-même, avec la fonction booléenne
qui existe déjà. Prompt retiré.

Reste un vrai manque, et un seul : `add_boolean` (`engine/kernel.py:2912`)
exige un `PartDesign::Body` et **rejette** un semis, qui est un `App::Link`.
Le geste annoncé n'est donc pas réalisable aujourd'hui. C'est l'objet de
[`P035`](../prompts/P035-booleen-semis.md), beaucoup plus court : faire
accepter un semis comme corps outil, et rien d'autre.

## 7.5 Ce que ça change au reste du relevé

- **§6.3, le carat** : l'argument du « facteur dérivé » devient **inutile**.
  On ne dérive plus rien — `shape.Volume` à la taille demandée **est** le
  volume, exact. Plus simple encore que ce que j'avais proposé.
- **§6.4, l'échelle non uniforme** : **disparaît**. Il n'y a plus d'échelle.
- **§6.7, le piège `BoundBox`** : **disparaît** aussi, tant que la forme
  reste analytique. H3 le vérifie plutôt que de le supposer.
- **§6.7, le format** : la conclusion `.FCStd` **tient**, et pour une raison
  de plus — il faut bien un document pour porter une esquisse et une
  variable.
- **[`P034`](../prompts/P034-pierres-sur-surface.md)** : toujours pas touché.
  Le mécanisme de placement ne sait pas ce qu'il y a dans la pierre, et n'a
  pas à le savoir.

## 7.6 La sonde

```bash
freecadcmd scripts/spike-gemme-parametrique.py
```

Elle construit un vrai brillant rond paramétrique — variable `diametre`,
esquisse de profil entièrement contrainte, six cotes pilotées par
expressions, révolution — l'enregistre, puis le rouvre à huit diamètres.

Sept questions. **H2 et H3 sont le verdict** : si la forme reste analytique
et les cotes justes, les deux pièges de la voie BREP s'évanouissent et il ne
reste qu'à juger le coût du recalcul mesuré en H1. H6 tranche le point
d'architecture du §7.4 ; H7 compare le siège aux 73 ms (BREP facetté) et
36 ms (BREP analytique) déjà mesurés.

## 7.7 bis — Les trois décisions, vérifiées

*Second passage, 2026-08-21. H9 tranche l'architecture ; H7 corrigé donne
enfin un vrai chiffre de siège ; H8 casse sur une API et reste ouvert.*

### H9 — la copie paramétrique tient les deux promesses

| Ce qu'il fallait prouver | Mesuré |
|---|---|
| La copie reste **paramétrable** | `toujours_parametrable: true` — rediamétrée après copie, la pierre recalcule |
| Les gemmes **ne se marchent pas dessus** | `varsets: ["Variables", "Variables001"]`, `diametres_independants: true` — FreeCAD renomme, et chaque pierre garde la sienne |
| Les volumes restent **exacts** | 0,730692 et 13,856079 mm³ — soit `0,216501 · d³` à ø 1,5 et ø 4, au millionième |
| La pièce est **autonome** | `autonome_sans_bibliotheque: true` — la sonde **renomme la bibliothèque sur le disque** avant de rouvrir : les solides sont là, valides, et `documents_ouverts: 1` |

**Les trois décisions tiennent ensemble.** La bibliothèque est un jeu de
gabarits : le modèle voyage dans la pièce, son résultat n'est jamais figé, et
plus rien n'est à retrouver sur le disque à l'ouverture.

Prix de l'autonomie, mesuré : **~7,7 ko par taille distincte** (17 280 octets
pour deux gemmes). À comparer aux 1 900 octets d'une pièce liée — qui, elle,
**tire la bibliothèque à chaque ouverture** (`biblio_tiree_automatiquement:
true`, H6). Le lien externe *fonctionne* donc ; il est écarté sur ses mérites,
pas faute de mieux.

### H7 — le siège, enfin mesuré sur un vrai siège

Placement corrigé : **59,5 % de la pierre** est entrée dans la matière (au
lieu de 2,9 % au premier passage), soit toute la culasse. C'est un vrai
sertissage.

**19,43 ms** — contre **35,65 ms** pour la *même forme* convertie en
B-splines par la voie BREP. **Ne pas convertir est 45 % plus rapide**, en
plus d'être exact. Les deux qualités vont dans le même sens, ce qui est rare
assez pour être noté.

Ordre de grandeur pour 200 sièges, coupés un à un : ~4 s. Avec le compound
d'une seule coupe (Q6), moins. Et puisqu'on **pose d'abord et combine
ensuite** (§7.4 bis), ce coût se paie une fois, sur commande — jamais dans la
boucle d'interaction.

### H8 — cassé sur une API, et la réponse était dans le dépôt

`AttributeError: 'PartDesign.Feature' object has no attribute 'Transformed'`.

Sur FreeCAD 1.1.3, une répétition ne se crée pas par `doc.addObject` puis
`body.addObject`, et ne porte pas ses sources dans `Transformed` : elle se
crée par **`body.newObject`** et les porte dans **`Originals`** — avec un
`body.Tip` à poser, sans quoi la répétition existe sans devenir le solide du
corps. C'est exactement ce que fait `Kernel._transform`
(`engine/kernel.py:2336`), éprouvé depuis des mois. J'avais écrit la sonde
sans consulter le code qui savait déjà.

Corrigé. **Le coût d'un recalcul à charge réelle reste donc à mesurer** — les
6,1 ms de H1 restent un plancher, celui d'une révolution à 4 faces.

Cela dit, la conclusion ne dépend pas du chiffre : même à vingt fois le
plancher, on serait à 120 ms pour une taille, et une pièce en compte une
poignée. C'est la marge qui est en jeu, pas la décision.

## 7.7 Verdict de la sonde gemme cotée — exécutée le 2026-08-21

`scripts/spike-gemme-parametrique.py` sur **FreeCAD 1.1.3**. **Verte**, et
sur les points qui décidaient.

### Les deux pièges de la voie BREP ont disparu

| | Voie BREP mise à l'échelle (§6.7) | **Gemme cotée** |
|---|---|---|
| Surfaces après dimensionnement | tout converti en B-splines | `{Plane 1, Cone 2, Cylinder 1}` — **analytiques, et identiques aux trois diamètres testés** |
| Volume | **−1,18 %** avant même l'échelle | exact |
| `BoundBox` à ø 3 mm | 70 % trop grand | **[3,0 · 3,0 · 1,866]** — le diamètre demandé, au millionième |

`aucune_bspline: true`, `types_stables: true`, `diametre_retrouve: true` aux
trois tailles. **Les deux problèmes que la sonde précédente avait trouvés ne
se posent plus.** Ils n'ont pas été contournés : ils n'existent pas dans
cette conception.

### Le carat, sans aucune table

`volume_en_d3: true` — le volume suit exactement `d³`, avec un facteur
constant de **0,216501** aux trois diamètres. L'esquisse tient donc ses
proportions, et :

> `V(d) = 0,216501 · d³`, exact, lu sur la géométrie.

Le §6.3 proposait de **dériver** le facteur de correction de JewelCraft.
C'est encore trop compliqué : ici on ne dérive rien, on **lit
`shape.Volume`** à la taille demandée. Rapporté à la boîte englobante, le
facteur vaut 0,348 — mais on n'en a même plus besoin.

### Le reste

| | |
|---|---|
| L'esquisse | **entièrement contrainte**, solveur à 0, 14 contraintes — le décompte de degrés de liberté tombe juste |
| Le fichier de bibliothèque | **9,5 ko**. Dix-sept familles ≈ 160 ko |
| 200 pierres d'une taille | **0,001 s**, et **82 octets par pierre** dans le document — plus léger encore que la voie BREP (113) |
| Le siège | **valide**, un seul solide (voir la réserve ci-dessous) |

### Trois mesures qui ne valaient pas ce qu'elles prétendaient

**H1 — 5,5 ms par taille est un plancher, pas la réponse.** La gemme d'essai
est une simple révolution : **4 faces**. Un brillant en a 57. Le chiffre
mesure le coût d'un cône et on le citerait pour celui d'une pierre. La sonde
a donc désormais un **H8** qui remesure avec une répétition polaire de seize
coupes par-dessus — pas les vraies facettes, mais la même charge de calcul —
et rapporte le multiple du plancher.

Cela dit, même à vingt fois le plancher on serait à 110 ms par taille, pour
une poignée de tailles distinctes par pièce. **La conclusion tient quel que
soit le chiffre ; seule sa marge est en jeu.**

**H7 — le siège n'effleurait la pierre que de 2,9 %.** Posée à 9,5 mm, la
gemme ne croisait le jonc que par la pointe du culet : le chronomètre
mesurait un frôlement. Le vrai geste met le **rondiste au ras de la surface**
et enfonce toute la culasse. Placement corrigé, et la sonde rapporte
maintenant quelle part de la pierre le siège a réellement prise.

Les 23 ms mesurés restent instructifs par comparaison avec la voie BREP sur
une forme équivalente — 36 ms pour la version analytique **convertie**. Ne
pas convertir n'est donc pas seulement plus exact : c'est **un tiers plus
rapide**. Mais le budget d'un vrai siège reste à établir.

**H6 — mon test était faux.** `RuntimeError: Owner document not saved` :
FreeCAD refuse un lien inter-documents depuis un document **jamais écrit** —
il lui faut un chemin pour poser la référence. Rien à voir avec la
conception. Le test enregistre désormais avant de lier, et le point
d'architecture du §7.4 reste **ouvert** jusqu'au prochain passage.

### Verdict

**La gemme cotée est la conception retenue.** Elle est plus exacte que le
BREP mis à l'échelle, plus rapide en booléen, plus légère en document, et
elle seule permet de modeler un ovale **pour ce qu'il est** plutôt que comme
un rond étiré. Le seul coût — un recalcul par taille distincte — se mesure en
millisecondes.

Reste à trancher, au prochain passage : **lien externe ou forme importée**
(§7.4), et le **budget d'un vrai siège** sur une pierre facettée.
