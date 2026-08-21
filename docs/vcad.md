# vcad — relevé du 2026-08-21

*Entrée de veille qui a débordé du tableau de [`landscape.md`](landscape.md).*

[ecto/vcad](https://github.com/ecto/vcad) est le pari inverse du nôtre, mené
jusqu'au bout : noyau BRep réécrit de zéro, application finie devant, licence
permissive. Il mérite un document à part — non comme concurrent à surveiller,
mais parce qu'il est la seule occasion disponible de regarder **ce que ce pari
coûte**, et surtout de constater ce qu'il fait apparaître *au-dessus* du
noyau : la couche où nous n'avons pas de grand frère, et où lui a déjà écrit.

Tout ce relevé est organisé autour d'une seule question, celle qui décide de
tout dans ce projet : **de quel côté de la frontière tombe la chose ?**
Ce qui tombe côté FreeCAD, on ne l'écrit pas — on l'a déjà, mieux vieilli.
Ce qui tombe côté FreeSolid, on est seuls, et c'est là que vcad est utile.
Voir [`amont-freecad.md`](amont-freecad.md) pour la règle générale.

## 1. Carte d'identité

| | |
|---|---|
| Dépôt | [ecto/vcad](https://github.com/ecto/vcad) — Municipal Robotics Corporation |
| Licence | **Apache-2.0** |
| Taille | ~445 000 lignes de Rust en **92 crates** ; ~80 000 lignes de TypeScript dans `packages/app` (React + Three.js) ; 12 paquets npm ; 433 Mo de dépôt |
| Activité | soutenue — dernier commit 2026-08-20, PR #826 |
| Périmètre affiché | noyau BRep maison, app web, app Tauri, CLI, serveur MCP, banc d'essai IA (`mecheval`, 242 Mo dont 198 Mo de leaderboard versionné) |
| Compilation | impossible seul : dépend de `../tang` (maths) et `../phyz` (physique), deux dépôts frères publics du même auteur |
| Prétention affichée | « remplacer Fusion 360, Onshape et similaires » |

## 2. La thèse inverse, en très grand

Le relevé du 2026-08-02 range [`waffle-iron`](https://github.com/sequoia-hope/waffle-iron)
dans la case « noyau réécrit from scratch, UI à faire ». vcad est la même
case, **soixante-dix fois plus grande**, avec l'interface finie et un modèle
économique derrière. C'est le meilleur exemplaire disponible du pari que ce
projet a refusé, et il ne change rien à la doctrine — il la documente.

Ce que le pari a coûté se lit dans l'arborescence : 26 000 lignes rien que
pour les booléens (`crates/vcad-kernel-booleans`), un crate séparé pour les
congés, un pour la tessellation, un pour STEP, un pour le nommage
topologique. Ce sont exactement les postes que FreeSolid reçoit gratuitement
et déjà éprouvés, et le motif « pas vibe-codable » du relevé du 2026-08-02
tient : la profondeur de ces crates n'a rien à voir avec leur nombre.

Mais le pari a eu un effet secondaire intéressant. En n'ayant **aucun**
grand frère, vcad a dû écrire lui-même toute la couche que FreeCAD, chez
nous, résout soit dans son noyau (et on l'hérite), soit dans son interface
Qt (et on ne l'hérite pas, parce qu'on a jeté Qt). C'est là — et là
seulement — qu'il y a quelque chose à prendre.

## 3. Licence : pourquoi on prend des idées et jamais des lignes

Apache-2.0 contre notre LGPL-2.1-**or-later**. Le raisonnement est en trois
temps, et il ne conclut pas comme celui de Chili3D :

1. **Apache-2.0 est incompatible avec la LGPL-2.1 seule** (clauses de
   brevet et d'indemnisation, position constante de la FSF). Copier un
   fichier tel quel dans FreeSolid en l'état est donc exclu.
2. **Le « or-later » ouvre pourtant une porte.** Apache-2.0 est compatible
   avec la (L)GPL-3.0 dans le sens Apache → GPLv3. Comme nos fichiers sont
   distribuables en LGPL-3.0, un emprunt de code est techniquement
   faisable — au prix de faire passer **l'ensemble distribué** de FreeSolid
   sous LGPL-3.0.
3. **C'est ce prix-là qui tranche, et il n'est pas le prix évident.** Le
   coût n'est pas juridique, il est stratégique : une contribution à FreeCAD
   doit être remontable en **LGPL-2.1-or-later**. Le jour où une ligne de
   FreeSolid descend d'Apache-2.0, cette ligne — et tout ce qui en dérive —
   **ne peut plus jamais partir en amont**. On se désynchronise de FreeCAD
   dans le seul sens qui compte.

D'où la règle, qui vaut pour vcad et pour tout dépôt permissif :

> **On lit vcad, on en tire des idées, on écrit nos propres lignes.**
> Aucun fichier, aucun bloc, aucune traduction ligne à ligne. Le prix d'un
> copier-coller n'est pas la licence, c'est la porte amont qu'il ferme.

Ce n'est pas de la prudence de principe : les quatre emprunts ci-dessous
sont des **idées de conception** de quelques dizaines de lignes chacune une
fois transposées en Python ou en JS. Il n'y a rien à copier, seulement à
comprendre. (Le point mérite confirmation avant tout emprunt réel de code —
mais comme on n'en prévoit aucun, il reste théorique.)

Rappel de la grille complète des licences croisées : [`amont-freecad.md`](amont-freecad.md) §3.

## 4. La frontière — le tableau qui décide

| Ce que vcad a écrit | De quel côté ça tombe chez nous | Verdict |
|---|---|---|
| Noyau BRep, booléens, congés, coques, balayages, STEP | **FreeCAD** | 🔴 rien à prendre — hérité, et mieux vieilli |
| Solveur de contraintes 2D (Levenberg-Marquardt sur résidus, `vcad-kernel-constraints`) | **FreeCAD** — planegcs, déjà vendoré dans `app/vendor/` | 🔴 on a déjà mieux |
| Tessellation, normales à angle vif, cuisson de rendu | **FreeCAD** (`Shape.tessellate`) | 🔴 rien à prendre |
| **Nommage topologique persistant** (`vcad-kernel-naming`) | **FreeCAD** — la carte d'éléments est à eux, **et exposée en Python** (tranché le 2026-08-21) | 🟢 **réduit** : le mécanisme tombe (le moteur a mieux), seule la *discipline de verdict* est prise — §5.1 |
| **Reçu de vérification** (`vcad-receipt`) | **FreeSolid** — rapport de selftest | 🟢 à prendre |
| **Garde de confiance pré-dispatch** (`packages/mcp/src/trust-boundary.ts`) | **FreeSolid** — `engine/server.py`, `engine/protocol.py` | 🟢 à prendre |
| **Schéma d'outils dérivé de l'IR** (`vcad_tool_derive::ToolSchema`) | **FreeSolid** — `engine/vocab.py` | 🟢 à prendre |
| **Banc d'essai CAO** (`mecheval`) | **FreeSolid** pour le harnais · **FreeCAD** pour ce qu'il mesure | 🟢 direction, pas emprunt de code — et le meilleur levier amont du relevé |
| App React + Three.js + zustand (80 kloc) | **FreeSolid** | 🔴 autre stack — regarder, jamais copier |
| DAG déclaratif `.vcad`, expressions, paramètres | **FreeCAD** (`.FCStd`, moteur d'expressions, `App::VarSet`) | 🔴 on a déjà l'équivalent, et rééditable |

Légende : 🟢 à prendre · 🟠 à instruire par un spike avant de décider ·
🔴 rien à prendre.

Ce tableau dit quelque chose de rassurant sur l'architecture : **tous les
emprunts tombent du même côté**, le nôtre, et aucun ne demande d'écrire de
la géométrie. C'est le même bon signe que la conclusion du relevé du
2026-08-15.

## 5. Les emprunts, en détail

### 5.1 — Le nommage topologique, ou plutôt : la garde de rejeu

> **Corrigé le 2026-08-21.** Cette section proposait d'emprunter à vcad
> son repli géométrique (`EdgeHint`). La reconnaissance amont du même jour
> a montré que **FreeCAD 1.1.3 expose déjà la carte d'éléments en Python** :
> le mécanisme tombe, seule la discipline de verdict est retenue. Le
> raisonnement d'origine est conservé ci-dessous parce qu'il reste la
> meilleure description du problème — mais **la conclusion est en fin de
> section**, pas au fil du texte.

**Le meilleur morceau du dépôt.** `crates/vcad-kernel-naming` : 776 lignes,
un seul fichier, 7 tests, lisible d'une traite.

Ce que vcad y fait :

- les faces d'une primitive sont nommées par **leur rôle dans l'opération
  génératrice** (`cube:top`, `cylinder:side`), pas par un index d'arène ;
- après un booléen, une face de sortie **hérite du nom de l'unique face
  d'entrée portée par la même surface** ; les faces découpées en plusieurs
  morceaux reçoivent un ordinal déterministe, trié par centroïde quantifié
  (`cube:top.0`, `cube:top.1`) ;
- **une arête se nomme par ses deux faces adjacentes**, en ordre canonique ;
- la résolution est **fail-closed** : `Resolved` / `Ambiguous` / `Lost`,
  jamais de re-liaison silencieuse ;
- quand le nom ne suffit plus, repli géométrique sur un **`EdgeHint`**
  enregistré au moment où la référence est créée : `{milieu, direction,
  longueur}`, tolérance proportionnelle à la longueur (25 %), direction
  comparée au signe près (|cos| ≥ 0,95).

**Où passe la frontière, précisément.** Le nommage topologique *dans le
document* est le travail de FreeCAD, et il est fait : le « toponaming fix »
de la 1.0 est l'une des raisons pour lesquelles ce projet garde ce moteur
(cf. [`architecture-app.md`](architecture-app.md)). **Nous ne réécrirons
jamais de carte d'éléments.**

Mais `engine/replay.py` n'est pas ça. C'est une garde **à nous**, née d'un
besoin qui n'existe que chez nous : rejouer un groupe de fonctions (N010)
dont les références de sous-éléments sont des chaînes (`Edge3`, `Face2`)
stockées dans notre propre enregistrement de fonction. Cette garde est
aujourd'hui volontairement grossière, et son docstring le dit :

| | `engine/replay.py` aujourd'hui | Ce que l'`EdgeHint` ajouterait |
|---|---|---|
| Ce qui est enregistré | nombre d'arêtes, nombre de faces, **type** des sous-éléments référencés (`shape_fingerprint`) | + signature géométrique de chaque sous-élément référencé |
| Le verdict | binaire : rejeu sûr / refus en français (`topology_verdict`) | trois états : résolu (par index · par géométrie), ambigu, perdu |
| Le trou connu | « deux arêtes de même type qui échangent leur indice passent la garde » — dit noir sur blanc dans le code | fermé : deux arêtes de même type mais de milieu/longueur différents ne se confondent plus |
| Ce qu'on peut faire d'un échec | rien, sauf refuser | **retrouver** la référence, ou refuser en nommant la raison |

Le gain n'est pas « une garde plus sévère », c'est **un changement de
nature** : on passe de *réduire le risque* à *retrouver la référence*. Et
la matière première est entièrement disponible côté FreeCAD, sans API
exotique : `shape.Edges[i]` donne les extrémités, donc milieu, direction et
longueur ; `shape.Faces[i]` donne le type de surface, l'aire et le centre
de gravité.

Retombée immédiate ailleurs : le constat **1.5** de
[`audit/2026-08-audit.md`](audit/2026-08-audit.md) (« IDs face/arête
invalidés dans le viewport, conservés dans le panneau ») propose comme
remède de vider la sélection à chaque rebuild. Avec une signature
géométrique, le panneau peut faire mieux que l'oublier : la **ré-ancrer**,
ou dire honnêtement qu'elle est perdue.

**Côté FreeCAD, à instruire d'abord : la question a été tranchée le
2026-08-21, et elle annule l'essentiel de ce qui précède.**

La question posée était : FreeCAD expose-t-il en Python de quoi suivre un
sous-élément à travers un recompute ? **Réponse : oui**, et depuis notre
version de référence. Vérifié dans les bindings du tag **1.1.3** —
`ComplexGeoData.getElementMappedName` / `getElementIndexedName` /
`getElementName`, les attributs `ElementMap`, `ElementReverseMap`,
`ElementMapSize`, `ElementMapVersion`, `Tag`, et
`Part::Feature.getElementHistory(name, recursive=…)`. Le détail est en
[`amont-freecad.md`](amont-freecad.md) §4ter.

**Ce qui survit de cet emprunt, et ce qui tombe :**

| | Verdict |
|---|---|
| L'`EdgeHint` (milieu / direction / longueur) comme mécanisme de repli | 🔴 **abandonné** — le moteur a mieux, et de la vraie provenance plutôt qu'une ressemblance géométrique |
| Nommer une arête par ses deux faces adjacentes | 🔴 abandonné — même raison |
| **La discipline de verdict** : résolu (par nom · par géométrie) / ambigu / perdu, et **jamais de re-liaison silencieuse** | 🟢 **retenu** — c'est une idée d'API, pas un mécanisme, et FreeCAD ne l'impose pas : `getElementIndexedName` rend un nom, pas un verdict |

**Côté FreeSolid, à écrire — et la tâche a changé de nature.** Ce n'est
plus « durcir la garde », c'est **stocker le bon identifiant** : nos
enregistrements de fonction gardent `Edge3` / `Face2`, c'est-à-dire le nom
*indexé*, le fragile. Enregistrer à côté le nom **mappé**, et le résoudre
au rejeu, fait disparaître la cause au lieu de compenser l'effet. La garde
`shape_fingerprint` reste, en filet, pour les cas sans mappage — et
`topology_verdict` gagne le verdict à trois états ci-dessus.

Un spike reste nécessaire, mais lui aussi a changé de question : plus
« est-ce exposé ? » (oui) mais « **la carte est-elle peuplée pour nos
objets ?** » — `ElementMapSize` et `Tag` non nuls sur un `PartDesign::Pad`
après recompute. Dix lignes dans le selftest.

C'était l'ordre correct : on ne réimplémente pas avant d'avoir vérifié. La
vérification a coûté une heure et a supprimé un module.

### 5.2 — Le reçu de vérification : le verdict à trois états

`crates/vcad-receipt`. Un reçu est la preuve vérifiable par machine qui
voyage avec le document : une liste versionnée de *claims*, chacune nommant

- ce qui est affirmé,
- **l'oracle qui l'a vérifié, et sa version**,
- la valeur prédite et la valeur mesurée, **avec unités explicites**,
- un verdict à **trois** états.

La règle de la maison, chez eux, est notre règle : *fail-closed*. Un oracle
qui n'a **pas pu** tourner rend `Unverifiable`, qui n'est jamais confondu
avec un succès ; et l'agrégation propage cette discipline — un reçu sans
claim, ou avec une seule claim invérifiable, ne peut pas se lire comme
vérifié.

**Frontière : entièrement côté FreeSolid.** Rien à voir avec FreeCAD, ni
avec le format `.FCStd`.

Nous avons déjà l'intuition, et même l'implémentation partielle :
`engine/platform.py` refuse une version FreeCAD autre que la référence
(1.1.3) sauf repli explicite `FREESOLID_ALLOW_FREECAD`, et marque alors le
rapport « **les mesures ne sont pas comparables** ». C'est exactement un
`Unverifiable` qui refuse de se lire comme un `Pass`. Ce qui manque, c'est
la **généralisation** : aujourd'hui la discipline s'applique à un seul
oracle (la version), et le reste du rapport de selftest est binaire.

Ce qu'on en tire, concrètement, pour `scripts/run-selftest.py` : chaque
mesure porte son oracle et sa version, ses unités, et un verdict à trois
états — *vérifié* / *échoué* / *invérifiable*. Le total ne peut pas être
vert s'il reste un invérifiable. Le rapport devient comparable d'un run à
l'autre au lieu d'être lisible seulement par celui qui vient de le lancer.

### 5.3 — La garde de confiance : pure, synchrone, avant le dispatch

`packages/mcp/src/trust-boundary.ts`. Le problème posé y est le nôtre à un
mot près : un agent ingère du contenu non fiable (fichiers STEP importés,
descriptions de pièces) et détient par ailleurs un pouvoir d'action. Le
module est la barrière mécanique entre les deux — un contrôle **pur et
synchrone, exécuté avant tout handler**, qui refuse les *formes
d'arguments* dont une injection aurait besoin, indépendamment de ce dont le
modèle a été convaincu.

Ce qui est bon dans la conception, et transposable tel quel :

- les règles sont **volontairement bêtes et vérifiables**, pas heuristiques
  (« identifiants opaques seulement », « pas d'URL dans une adresse ») ;
- la garde **ne réécrit jamais un argument** — elle refuse ;
- le refus porte un préfixe **greppable et stable** (`TRUST_BOUNDARY:`) ;
- elle est *fail-closed* : ce qui n'est pas reconnu est refusé.

**Frontière : entièrement côté FreeSolid.** C'est notre protocole JSON et
notre serveur ; FreeCAD n'a pas de surface équivalente à protéger, puisque
chez lui l'utilisateur *est* déjà dans le processus.

Le rapprochement avec notre audit est direct — les constats **3.1** (jail
de chemins), **3.2** (CSRF `Origin`/token), **3.3** (traversal
`startswith`), **3.4** (`setExpression` sans allowlist), **3.5**
(`_EDITABLE_PROPS` en écriture), **3.6** (validation de présence, pas de
types ni de bornes) sont **six instances du même trou** : la validation
vit dispersée dans les handlers de `engine/kernel.py` au lieu d'être une
barrière unique traversée avant eux. `engine/protocol.py` valide déjà la
*présence* des champs et est la seule source de vérité des 98 opérations —
c'est le bon endroit, il lui manque la moitié « formes refusées ».

Ce qu'on en tire : une passe de garde unique, pure, testable sans FreeCAD,
franchie par toute opération avant le dispatch ; refus en français avec un
préfixe stable ; jamais de correction silencieuse d'un argument. C'est-à-dire
un remède commun aux six constats, au lieu de six rustines.

### 5.4 — Le schéma d'outils dérivé du vocabulaire

`crates/vcad-ir` + la macro `vcad_tool_derive::ToolSchema` : le schéma JSON
des outils exposés à l'IA est **généré depuis les types de l'IR**. Une seule
source de vérité pour le format du document et pour la surface d'outils de
l'agent ; les deux ne peuvent pas diverger, parce qu'il n'y a qu'un endroit
où elles sont écrites.

**Frontière : entièrement côté FreeSolid.** `engine/vocab.py` est déjà notre
catalogue unique (types de nœuds, ports, catégories, icônes, état
implémenté), et `engine/protocol.py` est déjà la seule vérité des
opérations. L'idée n'ajoute pas une source, elle en **dérive** : générer
depuis ce qui existe le schéma que consommerait un agent, plutôt que de
l'écrire à côté et de le laisser vieillir.

C'est de l'hygiène plus que de la fonctionnalité, mais c'est l'hygiène qui
empêche exactement la classe de bug que ce projet redoute : deux
descriptions du même vocabulaire qui se désynchronisent en silence.

### 5.5 — Le banc d'essai, et le seul vrai levier amont du relevé

`mecheval/` : suite d'évaluation CAO pour modèles d'IA. Trois sous-suites —
**A** (autoring CAO), **B** (noyau, sans IA), **C** (mécanismes simulés).
Graders déterministes, **pas de LLM-juge**, blobs de run immuables et
auditables. Statut affiché v0.0, « design phase » ; 198 Mo de leaderboard
versionné dans le dépôt.

Comme code : rien à prendre. Comme **idée**, la suite B mérite mieux qu'un
coup d'œil, parce que sa liste est exactement la grille de non-régression
qui nous manque : stress booléen, aller-retour STEP, taux de succès des
congés, convergence du solveur de contraintes, qualité de tessellation.

**Et c'est ici que la frontière produit quelque chose de nouveau.** Ces
cinq mesures ne mesurent pas FreeSolid : elles mesurent **le moteur**. Un
banc de ce type, branché sur FreeCAD headless via notre protocole, ne
produit pas seulement notre filet de sécurité — chacun de ses échecs est
**un rapport de bug FreeCAD accompagné d'un reproducteur minimal en
`freecadcmd`**, c'est-à-dire précisément ce que les mainteneurs de FreeCAD
reçoivent le plus rarement et utilisent le mieux.

C'est la meilleure illustration de la doctrine amont de
[`amont-freecad.md`](amont-freecad.md) : en construisant l'outil dont nous
avons besoin pour nous, on fabrique gratuitement la matière d'une
contribution que nous sommes, par position, particulièrement bien placés
pour produire. Un client headless instrumenté et versionné sur une version
de référence unique, c'est un banc d'essai que FreeCAD n'a pas.

À ne pas confondre avec un projet : la suite B se construit **par
accumulation**, un cas à la fois, dans le selftest existant. Rien à créer à
côté.

## 6. Ce qu'on ne prend pas, et pourquoi

- **Le noyau, sous toutes ses formes.** C'est le pari refusé au 2026-08-02,
  et rien dans ce relevé ne le rouvre. On ne change pas les os.
- **Le solveur de contraintes.** `vcad-kernel-constraints` est un
  Levenberg-Marquardt sur résidus. planegcs *est* le solveur de FreeCAD,
  vingt ans de cas dégénérés derrière lui, déjà compilé en WASM et déjà
  vendoré chez nous. Nous avons strictement mieux — le sujet est clos.
- **L'application React.** 80 000 lignes de TypeScript sur une autre stack
  que notre JS sans framework. Même statut que Chili3D : **référence
  visuelle éventuelle, jamais réserve de code** — et pour vcad, la raison
  n'est pas la licence mais la porte amont (§3).
- **Le format `.vcad` et son DAG déclaratif.** Nous avons `.FCStd`, le
  moteur d'expressions et `App::VarSet`, et notre graphe est une *vue* sur
  l'arbre, pas un second modèle documentaire — décision de
  [`nodes-macros.md`](nodes-macros.md), inchangée.

## 7. Le signal de prudence

92 crates, dont `vcad-kernel-qcd`, `neutronics`, `photonics`, `antenna`,
`orbit`, `particle`, `acoustics`, `em`, `topopt`… au-dessus d'un booléen de
26 000 lignes et d'un noyau qui ne compile pas sans deux dépôts frères.
Ce rapport largeur/profondeur invite à juger **chaque crate sur son code,
pas sur son nom** — c'est d'ailleurs ce qui a été fait ici : les quatre
emprunts retenus sont tous des fichiers courts, lus en entier.

Corollaire pratique : rien dans ce relevé ne repose sur une promesse
d'arborescence. Si un jour l'un des emprunts devait être ré-instruit, il
suffira de relire un fichier.

## 8. Conclusion

**La doctrine ne bouge pas, et le tableau de la frontière explique pourquoi
elle tient.** vcad a écrit 445 000 lignes de Rust, dont la quasi-totalité
tombe côté FreeCAD chez nous — c'est-à-dire du travail que ce projet a eu
raison de ne pas refaire. Ce qui reste, une fois la frontière tracée, ce
sont quatre idées de conception situées **entièrement de notre côté**,
chacune transposable en quelques dizaines de lignes de Python ou de JS :

| Emprunt | Où ça atterrit | Ce que ça vaut |
|---|---|---|
| Discipline de verdict sur les références (résolu / ambigu / perdu) | `engine/replay.py` — **par-dessus la carte d'éléments de FreeCAD**, pas à la place | la garde passe de « réduire le risque » à « retrouver la référence » ; ferme aussi le constat 1.5 de l'audit. Le mécanisme géométrique de vcad, lui, est abandonné : le moteur a mieux (§5.1) |
| Reçu à trois états | `scripts/run-selftest.py` | un rapport comparable d'un run à l'autre ; « n'a pas pu tourner » ≠ « passé » |
| Garde pré-dispatch pure | `engine/protocol.py` | un remède commun aux six constats de sécurité 3.1–3.6 |
| Schéma d'outils dérivé | `engine/vocab.py` | supprime une classe de dérive avant qu'elle existe |

Et une cinquième chose, qui n'est pas un emprunt mais une **direction** :
la suite B de `mecheval` montre que le banc d'essai dont nous avons besoin
pour nous est aussi la meilleure contribution que nous puissions faire à
FreeCAD. C'est la suite naturelle de ce relevé, et elle est instruite dans
[`amont-freecad.md`](amont-freecad.md).

Aucun de ces cinq points ne demande d'écrire de la géométrie. Comme au
2026-08-15 : c'est le bon signe.
