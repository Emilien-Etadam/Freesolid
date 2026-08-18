# [N004b] L'éditeur de la fonction graphe

Le N004 a donné à la fonction graphe son évaluateur, sa persistance et son
insertion. Il lui manque tout : **on ne peut écrire son graphe qu'en JSON à
la main.** Ce prompt lui donne son éditeur.

C'est le seul endroit du projet où le câblage est **libre**. Le graphe du
document est un historique dessiné en graphe, contraint par PartDesign
(N005, §« les trois murs »). L'intérieur d'une fonction graphe ne l'est pas :
c'est un flux de données, boucles et listes comprises, façon Grasshopper.

**Périmètre : le client, plus une opération de lecture côté moteur** (§1).

## Le précédent : le mode esquisse

Une fonction graphe s'ouvre comme une esquisse s'ouvre. `sketchMode`
(`app/sketch.js`) est le patron : un mode actif, une entrée, une sortie, et
le reste de l'interface qui sait qu'il est actif.

- **Entrer** : double-clic sur un nœud de fonction graphe dans le graphe du
  document — le même geste qui ouvre une esquisse depuis sa ligne.
- **Sortir** : `Échap`, ou le geste équivalent à « fermer l'esquisse ».
- Pendant l'édition, le graphe du document est remplacé par celui de la
  fonction. On ne montre pas les deux : ce sont deux modèles distincts, et
  les mélanger visuellement rouvrirait la confusion que tout ce chantier a
  évitée.

## Le livrable

### 1. Une opération de lecture : le vocabulaire des nœuds

`_NODE_INPUTS` (`engine/nodegraph.py:59`) dit quels ports chaque type de nœud
possède. Le client ne peut pas lire du Python.

**Ne pas en recopier une table côté client.** Ajouter une opération de
lecture seule — `graph_vocabulary`, sans paramètre — qui rend les types, leur
libellé français et leurs ports :

```json
[{"type": "cylindre", "label": "Cylindre",
  "inputs": [{"key": "rayon", "label": "Rayon"}, …],
  "shape": true}]
```

Le libellé va dans `engine/vocab.py`, qui est déjà « la source unique de
vérité de la terminologie » — pas dans `nodegraph.py`, qui reste un
évaluateur, ni dans le client.

C'est la **seule** opération ajoutée par ce prompt, et elle ne modifie rien.
Toute autre table de ports côté client serait la sixième occasion de cette
série de faire diverger deux définitions de la même chose ; les cinq
précédentes ont toutes fini en correctif.

### 2. Créer une fonction graphe

`add_graph_feature` n'a aujourd'hui aucun point d'entrée dans l'interface.
Lui en donner **un seul** : une entrée dans `FEATURES` (`app/features.js`),
avec son bouton de ruban.

Elle apparaîtra alors **automatiquement dans la palette du graphe**, que le
N005 alimente depuis cette même table. Une entrée, deux surfaces.

Le formulaire demande le mode (`fuse` / `cut`) et crée une fonction au
graphe minimal, qu'on ouvre ensuite pour la remplir.

### 3. Le canevas de la fonction

Réutiliser le rendu et les gestes déjà construits — panoramique, zoom,
survol, sélection, palette, glisser de fil (N002, N003, N005). **Ne pas
écrire un second éditeur** : `docs/nodes-macros.md` pose que les deux
partagent leur composant.

Ce qui change à l'intérieur, et seulement cela :

- **Les nœuds sont des types de calcul**, pas des fonctions du document —
  la palette vient de `graph_vocabulary`.
- **Le câblage est libre** : toute sortie peut alimenter tout port d'entrée,
  et un même nœud peut alimenter plusieurs cibles. C'est l'inverse de la
  règle du graphe du document, où les arêtes `geom` sont non tirables.
- **Les ports d'entrée sont nommés et visibles.** Un `point` a `x`, `y`, `z` ;
  un `cylindre` a `rayon`, `hauteur`, `ancrage`. Un fil se dépose sur un port,
  pas sur un nœud — c'est ce qui distingue un éditeur de nœuds d'un
  diagramme.
- **Un port sans fil accepte une valeur littérale** saisie sur place :
  l'évaluateur le prévoit déjà (« à défaut par un littéral du même nom sur
  le nœud »).
- **Un nœud est désigné comme sortie**, visiblement, et un seul.

### 4. Quand ça s'applique

Chaque évaluation reconstruit la géométrie et rejoue le booléen :
**pas d'application à chaque fil tiré.** Une commande explicite envoie
`edit_graph_feature`, sur le modèle du panneau d'édition qui valide un
formulaire entier d'un coup.

Sortir du mode sans avoir appliqué doit le dire, pas jeter le travail en
silence.

### 5. Les erreurs de l'évaluateur, montrées sur le nœud

`GraphError` est déjà en français et **nomme le nœud fautif** — c'était une
exigence du N004, elle sert ici. Un refus doit **désigner ce nœud dans le
canevas**, pas seulement afficher un message en bas.

C'est vrai des cycles, des longueurs de listes différentes, du plafond, de la
division par zéro. La règle d'appariement est stricte exprès ; encore
faut-il qu'elle se comprenne d'un coup d'œil.

Le refus ne modifie pas la pièce (atomicité acquise au N004) : ne pas
recharger l'arbre ni fermer le mode sur une erreur.

### 6. Ce que l'interface doit dire

Deux limites que l'utilisateur ne devinera pas, et qui ne sont pas des bugs :

- **La géométrie produite est figée.** Changer une variable globale ne
  recalcule pas la fonction ; il faut la rouvrir et appliquer. À écrire dans
  le mode, pas à laisser découvrir.
- **Le résultat est une forme**, combinée par un booléen — pas une chaîne de
  fonctions PartDesign. Ce qui est calculé dedans n'apparaît pas dans l'arbre.

## Ce qu'il ne faut pas faire

- Ne pas ajouter d'opération autre que `graph_vocabulary`. La création, la
  réédition et la lecture existent depuis le N004.
- Ne pas tenir une table de ports, de types ou de libellés côté client.
- Ne pas écrire un second moteur de rendu ni un second glisser de fil.
- Ne pas évaluer côté client : l'évaluateur est `engine/nodegraph.py`, et il
  est seul juge. Le client compose du JSON, il ne calcule pas de géométrie.
- Ne pas déplacer les nœuds à la souris tant que leur position n'a nulle part
  où être persistée — **sauf** si vous la rangez dans le JSON du graphe, qui
  est justement persisté. Dans ce cas c'est légitime : le dire dans le commit.
- Ne pas toucher `app/vendor/`.

## Validation avant de pousser

```bash
python3 -m pytest -q
node --check app/graph.js && node --check app/main.js
node --test tests/js/*.test.mjs
PYTHONIOENCODING=utf-8 freecadcmd scripts/run-selftest.py   # si FreeCAD dispo
```

**pytest** : `graph_vocabulary` rend bien un port par entrée de
`_NODE_INPUTS`, et tout type de l'évaluateur y figure — un test qui casse si
un type est ajouté d'un côté seulement.

**node --test** : la composition du JSON à partir des nœuds et des fils
(logique pure de `app/graph.js`) — un fil vers un port inconnu est refusé
avant l'envoi, un port sans fil prend son littéral, la sortie désignée est
unique.

**Smoke** : créer une fonction graphe, l'ouvrir, poser une `serie` et un
`cylindre`, câbler, appliquer, vérifier que le volume change ; provoquer une
erreur d'appariement et vérifier que le nœud fautif est désigné et la pièce
intacte. Étendre le smoke sans casser ses étapes.

Plateforme de référence : **FreeCAD 1.1.3** (`AGENTS.md`).

## Commit

Un commit (ou une petite série cohérente), message en français, préfixé
`[N004b]`. Tout texte visible est en français, vocabulaire SolidWorks 2025.
