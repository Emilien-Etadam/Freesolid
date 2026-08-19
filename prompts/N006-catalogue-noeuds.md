# [N006] Reprendre le catalogue de nœuds de `j8sr0230/Nodes`

Le vocabulaire de la fonction graphe compte **six** types (N004). C'est de
quoi semer des perçages, pas de quoi travailler. Plutôt que d'inventer une
taxonomie, on reprend celle de
[`j8sr0230/Nodes`](https://github.com/j8sr0230/Nodes) — **LGPL-2.1, la même
licence que ce projet**, donc reprenable sans réserve.

## Ce qui se reprend, et ce qui ne se reprend pas

Relevé fait sur le dépôt :

| Leur dépôt | Reprenable ? |
|---|---|
| `icons/` — ~60 SVG (`nodes_box.svg`, `nodes_arc.svg`, `nodes_add.svg`…) | **Oui, tels quels.** Même licence, même geste que les icônes FreeCAD déjà vendorées |
| `nodes/` — 16 catégories : `alpha`, `analyzers`, `curves`, `generators`, `group`, `list`, `modifiers`, `number`, `scene`, `script`, `spatial`, `surfaces`, `text`, `transforms`, `vector`, `viz` | **Oui, comme taxonomie** — noms, regroupements, sémantique des ports |
| `core/`, `lib/` et le corps des nœuds | **Non.** Ils tournent dans le Python GUI de FreeCAD, avec `awkward`, `qtpy` et `pyqt-node-editor` |

La licence permettrait de prendre le code aussi. Ce n'est pas la licence qui
l'interdit, c'est l'architecture : notre évaluateur (`engine/nodegraph.py`)
est **stdlib pure, sans import FreeCAD**, et rend des instructions ; leur
framework tirerait Qt et `awkward` dans un moteur headless servant un client
navigateur. **Importer leur pile coûterait plus cher que réécrire les
nœuds** — et la réécriture est courte, une fois la taxonomie donnée.

Ce qu'on économise vraiment, et c'est beaucoup : **le travail de conception**
— quels nœuds existent, comment ils se groupent, comment leurs ports se
nomment — affiné sur 674 commits. Plus les icônes.

## Le livrable

### 1. Les icônes, vendorées comme les autres

Copier les SVG de leur `icons/` dans `app/icons/`, **en gardant leurs noms
d'origine** (`nodes_*.svg`) — même convention que les icônes FreeCAD, pour
retrouver la source d'un grep.

Étendre `app/icons/README.md` sur le modèle existant : source, licence
LGPL-2.1 héritée, convention de nommage. C'est une obligation de
redistribution, pas une politesse.

Ne pas reprendre les deux PNG (`nodes_default.png`, `nodes_status_icon.png`),
qui relèvent de leur interface Qt.

### 2. Le catalogue complet, déclaré d'un coup

Déclarer **toute** la taxonomie dans `engine/vocab.py` — qui est déjà « la
source unique de vérité de la terminologie » — avec pour chaque nœud : son
type, son libellé **français**, sa catégorie, son icône, ses ports.

`graph_vocabulary` (N004b) la sert déjà au client ; elle n'a pas à changer de
forme, seulement à retourner davantage.

**Chaque entrée porte un état :** implémentée, ou pas encore. Le catalogue est
donc **visible en entier dès ce prompt**, et se remplit ensuite.

### 3. La palette montre tout, grise ce qui manque

Reprendre le motif déjà éprouvé au N005 pour les fonctions d'habillage : un
nœud non implémenté apparaît **grisé, avec sa raison** — jamais masqué. On
voit ce que l'outil saura faire, et ce qu'il ne sait pas encore.

Grouper la palette par catégorie, avec leurs noms traduits.

### 4. Ce qui s'implémente dans ce prompt

Seulement les catégories qui n'exigent **aucune géométrie nouvelle**, parce
qu'elles prolongent l'évaluateur pur :

- **`number`** — opérations et constantes ; `calcul` et `nombre` existants s'y
  rangent ;
- **`vector`** — composition et décomposition ; `point` existant s'y range ;
- **`list`** — génération, longueur, aplatissement, décalage ; `serie`
  existant s'y range. **C'est la catégorie qui compte le plus** : c'est elle
  qui donne les boucles.

Les six types actuels sont **reclassés**, pas dupliqués. Si un nom de nœud
existant diffère du leur, prendre le leur et migrer — mieux vaut une rupture
maintenant qu'une divergence de vocabulaire durable.

Le reste — `generators`, `curves`, `surfaces`, `modifiers`, `spatial`,
`analyzers`, `transforms` — se déclare mais ne s'implémente pas ici ; ce sont
des appels à l'API `Part`, ils viendront par catégorie.

Ne pas déclarer `scene`, `viz`, `script`, `group`, `alpha` : ils relèvent de
leur interface FreeCAD et n'ont pas de sens ici. **Dire dans le commit
pourquoi ils sont écartés**, pour que la question ne se repose pas.

### 5. Le verrou, comme au N004b

Le test qui compare `graph_vocabulary`, `_NODE_INPUTS` et `vocab.py` doit
continuer de passer, et couvrir les nouveaux types. Un nœud déclaré sans
ports, ou implémenté sans être déclaré, doit faire tomber la CI.

Ajouter : **toute icône déclarée existe dans `app/icons/`**. Une icône
manquante ne doit pas se découvrir à l'écran.

## Ce qu'il ne faut pas faire

- Ne pas copier `core/`, `lib/`, ni le corps de leurs nœuds.
- Ne pas ajouter `awkward`, `qtpy` ni aucune dépendance : le moteur reste en
  stdlib pure.
- Ne pas implémenter les catégories géométriques « tant qu'on y est ».
- Ne pas masquer les nœuds non implémentés.
- Ne pas toucher `app/vendor/`.

## Validation avant de pousser

```bash
python3 -m compileall -q engine
python3 -m pytest -q
node --check app/graph.js && node --check app/main.js
node --test tests/js/*.test.mjs
PYTHONIOENCODING=utf-8 freecadcmd scripts/run-selftest.py
```

Smoke : ouvrir une fonction graphe, vérifier que la palette affiche les
catégories, qu'un nœud non implémenté est grisé avec sa raison, et qu'un
nœud de `list` se pose et s'évalue. Étendre le smoke sans casser ses étapes.

Plateforme de référence : **FreeCAD 1.1.3** (`AGENTS.md`).

## Commit

Un commit (ou une petite série cohérente), message en français, préfixé
`[N006]`, **listant les catégories écartées et pourquoi**. Tout texte visible
est en français.
