# Macros et graphe de nœuds — parti pris

Décisions du 2026-08-15, à la suite du relevé Chili3D / Nodes de
[`landscape.md`](landscape.md). Ce document fixe **ce qu'on construit et
dans quel ordre** ; il ne décrit pas encore d'UI.

Le parti pris tient en une phrase : **rien ne se met à côté du document — ça
s'y range, ou ça n'existe pas.** Ce qui donne deux objets distincts, à deux
niveaux, et jamais un modèle parallèle :

1. **La vue graphe** (§2) — le graphe *est* le document. Une vue sur les
   fonctions réelles et leurs dépendances, ni fichier, ni format, ni
   synchronisation. Ses nœuds sont de vraies fonctions PartDesign
   rééditables, celles de l'arbre, pas des copies.
2. **La fonction graphe** (§3) — une ligne de l'arbre qui encapsule un flux
   de données, **boucles et listes comprises**, et rend une forme. Le modèle
   de l'esquisse, transposé un étage plus haut.

Le premier ne coûte presque rien et ne sait pas boucler ; le second sait
boucler et coûte un évaluateur. Les deux partagent leur éditeur.

## 1. Ce que « ne rien séparer » fait disparaître

La première rédaction de ce document posait le graphe comme un artefact
distinct, et butait aussitôt sur une question sans bonne réponse :

> L'utilisateur change la cote d'un bossage dans l'arbre, puis relance le
> graphe. Qui gagne ?

Il fallait alors choisir entre la **cuisson** (le graphe génère puis lâche
prise — mais il ne pilote plus rien) et le **lien vivant** (le graphe reste
propriétaire — mais il faut verrouiller les fonctions par une propriété
custom que FreeCAD ignore, donc une édition faite dans FreeCAD périme le
graphe en silence). Les deux étaient des consolations.

**La question ne se pose que parce qu'il y a deux modèles.** Si le graphe
*est* le document, il n'y a plus qu'un point de vérité : double-cliquer une
cote dans l'arbre et tirer un fil dans le graphe sont deux gestes sur les
mêmes objets, passés par les mêmes opérations du protocole. Rien à cuire,
rien à verrouiller, rien à périmer.

Ce qui tombe avec la séparation, et qu'on n'écrira donc pas : le format de
graphe et son évaluateur, la persistance en `App::TextDocument`, le marquage
des fonctions générées, la détection de désynchronisation, et la notion
d'identité stable nœud → fonction. C'est-à-dire l'essentiel du travail.

Le `.FCStd` reste **strictement un document FreeCAD** : aucune métadonnée
FreeSolid, aucune annexe. C'est la promesse du projet, tenue ici sans effort
plutôt que défendue de justesse.

## 2. Les fils existent déjà — il y en a deux sortes

Un graphe, c'est des nœuds et des arêtes. Les nœuds sont les objets du
document. Les arêtes aussi sont déjà là, sous deux formes que FreeCAD
distingue et que l'arbre plat mélange ou cache :

| Arête | D'où elle vient | Ce qu'elle dit |
|---|---|---|
| **Géométrique** | `obj.OutList` — `Profile`, `AttachmentSupport`, `BaseFeature`, corps outils des booléens | *ce bossage consomme cette esquisse, qui s'attache à ce plan, qui dépend de cette face* |
| **Paramétrique** | le moteur d'expressions — `ExpressionEngine`, déjà lu par `_expression_map` (`kernel.py:2166`) | *cette cote vaut `2*largeur + 5`, donc elle est pilotée par la variable `largeur`* |

Le deuxième point mérite d'être vu pour ce qu'il est : **les expressions sont
déjà le flux de données**. `D1@Bossage1 = 2*largeur + 5` est littéralement
une arête entre le `App::VarSet` et une propriété de fonction. La phase A a
construit la couche dataflow du projet sans l'appeler ainsi ; le graphe ne
fait que la rendre visible.

C'est aussi ce qui répond aux « curseurs » de Grasshopper sans rien
inventer : un paramètre d'entrée du graphe est une **variable globale**, elle
existe, elle est persistée, elle est déjà éditable dans le panneau Équations.

## 3. Les boucles et les listes : la fonction graphe

Le modèle de la section 2 ne sait pas exprimer une boucle : semer 500
perçages sur une surface gauche n'est pas une arête entre deux fonctions.
Or c'est précisément l'intérêt du genre — sans listes, un éditeur de nœuds
n'est qu'un arbre dessiné autrement.

**L'hybridation est possible, et son précédent est l'esquisse.**

Un `Sketcher::SketchObject` est **une** ligne de l'arbre. Dedans : de la
géométrie, des contraintes, un solveur, un mode d'édition dédié — tout un
système que le reste du document ignore et n'a pas à connaître. Personne ne
dit que l'esquisse « sépare le modèle » : elle l'**encapsule**. Le document
ne voit qu'un profil consommé par un bossage.

Une **fonction graphe** est la même chose, un étage au-dessus : une ligne de
l'arbre, un éditeur de nœuds dédié à l'intérieur, boucles et listes
comprises, et **une forme en sortie**.

### Pourquoi ça ne réveille pas le problème des deux éditeurs

Le conflit de la section 1 venait d'un graphe qui produisait **plusieurs
fonctions éparpillées dans l'arbre**, chacune éditable des deux côtés. Une
fonction graphe n'en produit **aucune** : ce qu'elle calcule reste dedans,
comme les cercles et les contraintes restent dans l'esquisse. Un seul objet
dans l'arbre, un seul éditeur pour cet objet, aucune resynchronisation.

Les deux décisions cohabitent donc sans se gêner, à deux niveaux différents :

| | Vue graphe du FeatureManager (§2) | Fonction graphe (ici) |
|---|---|---|
| Portée | tout le document | une fonction |
| Modèle | aucun — c'est une vue | interne à la fonction, encapsulé |
| Nœuds | les fonctions réelles | des opérations de calcul |
| Boucles, listes | non | **oui** |
| Sortie | — | une forme, consommée par l'arbre |

Et elles partagent le composant de rendu : le même éditeur de nœuds, une
fois sur des fonctions réelles, une fois sur un flux interne.

### L'insertion dans l'historique — déjà écrite

Le chemin d'une forme calculée hors PartDesign vers la chaîne PartDesign
existe dans le dépôt, éprouvé par la gravure de texte
(`kernel.py:1133-1143`) :

1. construire la forme avec l'API `Part` ;
2. `doc.addObject("Part::Feature", …)` + `.Shape = …` ;
3. l'envelopper dans un `PartDesign::Body` via `BaseFeature` ;
4. `add_boolean(tool=…, type="fuse"|"cut")` pour la combiner dans
   l'historique.

Une fonction graphe emprunte ce chemin tel quel. C'est ce qui rend
l'hybridation crédible : le raccord au reste de la pièce n'est pas à
inventer, il tourne déjà en production sur une autre fonction.

### Persistance : surtout pas un `FeaturePython`

La voie réflexe serait un `Part::FeaturePython` avec un `Proxy` Python. **À
écarter** : FreeCAD sérialise le *chemin du module* du proxy et le
réimporte à l'ouverture. Or le projet a retiré l'addon (P017) — le moteur
est headless, rien n'est installé côté FreeCAD. Le module ne serait pas
importable, et le fichier s'ouvrirait avec un objet cassé.

Retenu à la place : un **`Part::Feature` ordinaire**, plus le graphe rangé
en JSON dans une propriété custom — exactement le motif déjà en place pour
`FreeSolidColor` (`kernel.py:1241`).

- FreeCAD ouvre le fichier et voit **une forme normale**. Pas d'objet
  cassé, pas de module manquant, pas de recalcul en échec.
- FreeSolid relit la propriété, rouvre l'éditeur, recalcule, remplace la
  forme.
- Dans FreeCAD la fonction est figée — ce qu'elle serait de toute façon,
  puisque son évaluateur est le nôtre.

### Le prix, cette fois payé pour de bon

C'est **un vrai évaluateur nouveau** — le premier du projet. Ce qui le rend
acceptable est qu'il est *borné*, et il faut le tenir borné :

- il ne voit qu'une fonction, jamais le document ;
- il appelle l'API `Part`, jamais PartDesign — donc **la géométrie qu'il
  produit est figée à l'intérieur**, même statut que le surfacique avant le
  P016. Le paramétrique reste dehors, dans les entrées du graphe (variables
  globales, expressions) et dans la chaîne qui consomme sa sortie ;
- sa sortie est **une forme**, pas un morceau d'historique.

Sur les *data trees* eux-mêmes : ne pas ajouter `awkward` au premier jour.
Le moteur est en stdlib pure et c'est un choix structurant — des listes
imbriquées Python et **une règle d'appariement documentée** (la partie qui
rend Grasshopper déroutant, à écrire noir sur blanc avant de coder) suffisent
tant que le volume reste raisonnable. `awkward` est l'optimisation de
`j8sr0230/Nodes` pour la masse ; il est LGPL-2.1, donc empruntable le jour où
le volume le justifiera, pas avant.

## 4. Les macros ne sont plus l'étage du dessous

La rédaction précédente faisait du graphe « l'interface graphique des
macros ». **C'est faux dès lors que le graphe est le document** : un graphe
montre l'état d'une pièce, une macro rejoue une suite de gestes. Deux sujets
distincts, qui ne se commandent plus l'un l'autre.

Les macros gardent leur intérêt propre et leur analyse (`landscape.md` §2) :
les 88 opérations de `engine/protocol.py` sont déjà le langage,
l'enregistrement se réduit à journaliser les requêtes reçues par
`server.py`, la relecture à les re-poster. Le morceau dur reste la
**résolution de références** — les ops désignent les fonctions par nom
(`Bossage1`), donc rejouer sur un autre document ne marche pas tout seul.

Et la contrainte de format tient toujours, indépendamment du graphe : une
macro est une **liste d'opérations validées, jamais du Python exécuté**.
L'allowlist d'`Origin` de `server.py` laisse passer les requêtes sans en-tête
`Origin` (curl, scripts locaux) ; tant que le contenu est de la donnée
revalidée par `protocol.py`, la surface d'attaque est celle d'aujourd'hui.

## 5. Le travail réel

Tout se ramène à une chose : **`get_tree` doit émettre les arêtes.**

Aujourd'hui il ne le fait pas (`kernel.py:2234`). Il lit `Profile` dans le
seul but d'imbriquer une esquisse consommée sous sa fonction, puis jette le
reste — `AttachmentSupport`, `BaseFeature`, corps outils. Ce qu'il renvoie
est une liste plate à un niveau d'imbrication, pas un graphe.

| Étape | Où | Coût |
|---|---|---|
| Arêtes géométriques | `get_tree` : champ `deps` par entrée, depuis `obj.OutList` filtré au corps | 🟢 la donnée est dans FreeCAD, il suffit de ne plus la jeter |
| Arêtes paramétriques | même endroit, depuis `_expression_map` | 🟢 le lecteur existe déjà |
| Contrat | `protocol.py` + tests | 🟢 faible, mais c'est un **changement de protocole** : à faire proprement |
| Rendu du graphe | client | 🟧 le vrai morceau — disposition et lisibilité sur une pièce à 60 fonctions |
| Édition dans le graphe | client → ops existantes | 🟧 ensuite, geste par geste, sans opération nouvelle côté moteur |

Ce que la seule lecture rapporte déjà, avant toute édition : la réponse à
« d'où vient cette face ». Une répétition qui référence une esquisse
attachée à un plan qui dépend d'une autre fonction est illisible en liste et
évidente en graphe. Et une cote pilotée par une variable, aujourd'hui
signalée par un simple préfixe Σ, montre enfin **d'où** elle est pilotée.

## L'ordre

1. **Arêtes dans `get_tree`** — géométriques et paramétriques, contrat et
   tests. Seule vraie dépendance de tout le reste.
2. **Vue graphe en lecture seule** — utile immédiatement, et c'est déjà le
   composant de rendu final, celui que la fonction graphe réutilisera.
3. **Édition dans le graphe** — chaque geste retombe sur une opération
   existante ; rien de neuf côté moteur.
4. **Fonction graphe** — le seul étage qui demande du neuf : l'évaluateur
   borné, la règle d'appariement des listes, la propriété de persistance, et
   le raccord par corps outil déjà éprouvé. À ouvrir sur un cas réel choisi
   d'avance (semer des perçages sur une surface est un bon banc d'essai),
   pas dans l'abstrait.
5. **Macros** — sujet indépendant, à mener quand il aura sa propre valeur.

Les étapes 1 à 3 n'ajoutent rien dans le `.FCStd` et n'écrivent pas de
géométrie. L'étape 4 est le vrai investissement, et elle est volontairement
placée après pour arriver avec l'éditeur déjà construit.
