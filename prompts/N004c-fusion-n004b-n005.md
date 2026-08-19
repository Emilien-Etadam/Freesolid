# [N004c] Réconcilier l'éditeur de fonction graphe avec les nœuds constructifs

La branche `cursor/n004b-editeur-fonction-graphe-0df6` (PR #46) **ne peut pas
être fusionnée** : elle est partie de `815e893`, c'est-à-dire avant que le
code du N005 n'atterrisse sur `main` (#44). Les deux ont ensuite étendu le
même éditeur de graphe.

Conséquence à connaître : **la CI n'a jamais tourné sur cette PR**. GitHub ne
peut pas calculer le commit de fusion d'une branche en conflit, donc
l'événement `pull_request` ne se crée pas. Ce n'est pas un échec de test,
c'est une absence de test.

**Mission : rebaser N004b sur `main` à jour et unifier les deux mécanismes.**
Le travail des deux prompts doit survivre en entier.

## Ce qui entre en collision

Trois fichiers : `app/index.html` (3 zones), `tests/js/graph.test.mjs` (2), et
`app/main.js` (**19 zones**). Ce ne sont pas des conflits de texte mais deux
conceptions du même mécanisme :

| Symbole | N005 (sur `main`) | N004b |
|---|---|---|
| `graphWiring` | `{ from, kind, … }` | `{ from, …, mode }` |
| `startGraphWire` | `(node, event, kind)` | `(node, event, options = {})` |
| `openGraphPalette` | `({ profileSketch, clientX, clientY })` | `(clientX, clientY)` |
| `closeGraphPalette` | palette du document | palette de la fonction |
| élément DOM | `graphPalette` | `graphPaletteEl` — **même id `graph-palette`** |
| `graphSelectedEdge` | `{ from, to, kind }` | `{ from, to, kind, input? }` |

Deux palettes différentes partagent un identifiant DOM et un nom de fonction ;
deux sortes de fil partagent une variable d'état sous deux noms de
discriminant. C'est là, et seulement là, qu'il faut décider.

## La conception à retenir

Ne pas juxtaposer les deux : **unifier**.

### Un seul mécanisme de fil, trois natures

```js
startGraphWire(node, event, kind)   // kind ∈ "param" | "construct" | "port"
graphWiring = { from, kind, … }     // « kind », pas « mode »
```

- `param` — variable → cote (N003), graphe du document ;
- `construct` — esquisse → palette (N005), graphe du document ;
- `port` — sortie → port d'entrée nommé (N004b), **dans une fonction graphe**.

Les cibles valides, les surbrillances de dépôt et le fil provisoire se
choisissent sur `kind`. Un `kind` n'est proposé que dans le mode où il a un
sens : pas de fil `port` dans le graphe du document, pas de fil `construct`
dans une fonction graphe.

### Une seule palette, deux sources

Un seul élément `#graph-palette`, un seul couple `openGraphPalette` /
`closeGraphPalette`. Le contenu dépend du mode :

- graphe du document → `FEATURES`, via `graphPaletteItems` (N005) ;
- fonction graphe → `graph_vocabulary` (N004b).

Le paramètre `profileSketch` du N005 n'a de sens que dans le premier cas ;
le garder, ignoré dans l'autre.

### Un seul aiguillage pour la suppression

`deleteSelectedGraphNode` (N005) et `deleteGraphFnSelection` (N004b) sont
deux chemins pour la touche `Suppr`. Un seul point d'entrée qui aiguille sur
`graphFn.active` — et non deux écouteurs qui se marchent dessus.

### Ce qui ne collide pas doit survivre intact

Côté N005 : `deleteFeatureWithConfirm`, `graphPlacementCtx`,
`applyGraphNodeSelection`, `openFeaturePanel`, `graphSelectedName`,
`graphPaletteProfile`, `graphFitNames`, le bouton `#btn-graph-add`,
l'estompage des nœuds après la barre de reprise.

Côté N004b : l'état `graphFn`, les ports (`graphPortAt`,
`appendFunctionPorts`, `setDataDropHighlights`), les littéraux
(`openLiteralEditor`, `formatLiteral`, `isPointValue`),
`renderGraphFunction`, le déplacement de nœuds (`startFunctionNodeDrag`,
`moveFunctionNode`), `exitGraphFeature`, la barre `#graph-fn-bar`, et
l'opération `graph_vocabulary` avec son verrou à trois sources.

`graphEdgeEnds` gagne son troisième paramètre `edge` sans que l'appel du
graphe du document en pâtisse.

## Ce qu'il ne faut pas faire

- **Ne pas résoudre en gardant un seul côté.** Les deux prompts sont
  fusionnés ou en attente de l'être ; perdre l'un des deux est un échec, pas
  un arbitrage.
- Ne pas dupliquer la palette en deux éléments DOM pour éviter d'arbitrer :
  ce serait la septième table parallèle de cette série.
- Ne pas ajouter d'opération : `graph_vocabulary` est la seule du N004b, et
  elle reste la seule.
- Ne pas toucher `engine/` au-delà de ce que N004b y a déjà fait.
- Ne pas toucher `app/vendor/`.

## Validation avant de pousser

```bash
python3 -m pytest -q
node --check app/graph.js && node --check app/main.js && node --check app/features.js
node --test tests/js/*.test.mjs
PYTHONIOENCODING=utf-8 freecadcmd scripts/run-selftest.py
```

Les deux suites de tests JS doivent survivre : celles du N005 (placement,
profil, marqueurs, nœuds après la barre) **et** celles du N004b (vocabulaire,
ports, littéraux, sortie unique). Si l'une a été réécrite pour passer, c'est
que la fusion a perdu un comportement.

**Le smoke doit couvrir les deux modes dans la même exécution** — c'est le
seul filet contre une réconciliation qui marcherait sur chaque geste pris
isolément mais pas sur leur cohabitation :

1. graphe du document : sélectionner l'esquisse, poser un bossage par la
   palette, vérifier le nœud relié ;
2. créer une fonction graphe, l'ouvrir, câbler un port, appliquer, vérifier
   le volume ;
3. **en sortir et refaire un geste du point 1** — c'est là qu'un état de fil
   mal remis à zéro se voit.

Zéro erreur console sur l'ensemble.

Plateforme de référence : **FreeCAD 1.1.3** (`AGENTS.md`).

## Commit

Rebaser sur `main` à jour, puis un commit (ou une petite série cohérente),
message en français, préfixé `[N004c]`, **disant ce qui a été unifié**.
Pousser sur une branche qui part du `main` actuel — pas sur l'ancienne.

## Pour la suite

Partir de `main` à jour avant de commencer un prompt. N004b a été lancé
pendant que N005 était encore en vol, sur les mêmes fichiers : c'est
l'origine de tout ce travail supplémentaire.
