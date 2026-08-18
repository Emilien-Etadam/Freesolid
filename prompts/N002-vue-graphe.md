# [N002] La vue en graphe du FeatureManager — lecture seule

Deuxième brique de la série **N** ([`docs/nodes-macros.md`](../docs/nodes-macros.md)).
Le N001 a posé les arêtes côté moteur ; ce prompt les dessine.

**Périmètre : le client seul. Aucun fichier de `engine/` modifié, aucune
opération ajoutée au protocole, aucun appel réseau nouveau.** Tout part de
l'arbre déjà en mémoire (`lastTree`).

**Lecture seule.** Pas de déplacement de nœud, pas de création d'arête, pas
d'édition dans le graphe — c'est le N003.

## Ce que le moteur fournit déjà

`get_tree` livre, par entrée (fonction, esquisse imbriquée, surface, esquisse
de surface) :

- `deps` — noms internes des nœuds dont l'entrée dépend, **arêtes
  géométriques**. Garanti sans arête pendante : chaque cible est un nœud du
  même payload (`protocol.dangling_deps` le vérifie à chaque CI).
- `driven` — `{propriété: expression}`, chaîne brute.

Et au niveau du payload : `planes` (avec `name`), `surfaces`, `bodies`,
`variables` (`[{name, value}]`).

## Le livrable

### 1. `app/graph.js` — module **pur**, sans DOM

C'est la contrainte d'architecture du prompt, et le pendant client de ce que
`AGENTS.md` impose au moteur : la logique se teste sans navigateur.

```js
export function buildGraph(tree) // -> { nodes, edges }
```

Aucun accès à `document`, `window`, ni au réseau. Entrée : l'objet d'arbre.
Sortie : des données positionnées, prêtes à dessiner.

**Les nœuds.** Fonctions, esquisses imbriquées, surfaces et leurs esquisses,
plans de référence (`planes`, identifiés par leur `name`), variables
globales. Un **corps** n'est un nœud que si une arête le désigne — sinon il
encombre sans rien apprendre.

Chaque nœud porte au moins : `name`, `label`, `kind` (le vocabulaire
SolidWorks déjà présent dans l'arbre), `layer`, `x`, `y`.

**Les arêtes**, deux natures à distinguer :

| Nature | Source | Règle |
|---|---|---|
| `geom` | `deps` | reprise telle quelle |
| `param` | `driven` × `variables` | une arête variable → nœud par variable citée dans l'expression |

**Piège du rapprochement paramétrique — à traiter explicitement.** Une
expression est une chaîne (`2 * largeur + 5`). Il faut **découper en
identifiants et comparer des identifiants entiers**. Une comparaison par
sous-chaîne ferait correspondre une variable `larg` à l'intérieur de
`largeur` — arête inventée, et d'autant plus perfide qu'elle ne se voit que
sur un document réel. Ce cas doit figurer dans les tests.

**Disposition.** Couche par plus long chemin depuis les racines ; à
l'intérieur d'une couche, ordre par le champ `order` de l'arbre. Résultat
**déterministe** : deux appels sur le même arbre donnent les mêmes
coordonnées. Pas de minimisation de croisements en v1 — c'est un manque
assumé, pas un oubli ; le noter en commentaire plutôt que de bricoler.

**Invariant à préserver.** Toute extrémité d'arête doit être un nœud du
graphe. C'est la version client de `dangling_deps` — si le rapprochement
paramétrique fabrique une arête vers une variable inexistante, le bug est ici.

### 2. `tests/js/graph.test.mjs` — `node --test`

- couches : une chaîne esquisse → bossage → congé donne trois couches
  croissantes ;
- déterminisme : deux appels, mêmes coordonnées ;
- identifiants entiers : variables `larg` et `largeur`, expression
  `2 * largeur + 5` → **une seule** arête, vers `largeur` ;
- plusieurs variables dans une expression → une arête par variable ;
- invariant : sur un arbre représentatif, aucune extrémité d'arête hors des
  nœuds ;
- arbre vide ou sections absentes → `{nodes: [], edges: []}`, pas
  d'exception.

### 3. Le rendu — `app/main.js`, `app/index.html`, CSS existante

**Emplacement** : un calque en **SVG inline** au-dessus de `#viewport`,
masqué par défaut. SVG et non canvas : le survol et le clic par nœud ou par
arête sont gratuits, c'est exactement ce dont une vue de lecture a besoin.

**Ouverture** : un bouton dans `#viewbar`, à côté de `#btn-clip`, avec une
icône du jeu existant (`app/icons/`) — ne pas en dessiner une nouvelle.
Fermeture par le même bouton et par `Échap`.

**Gestes**, tous en événements pointeur natifs comme le reste de l'app :

- glisser sur le fond : panoramique ;
- molette : zoom centré sur le pointeur ;
- survol d'un nœud : ses arêtes incidentes se distinguent, les autres
  s'estompent — c'est la réponse à « d'où vient cette face » ;
- clic sur un nœud : **la même sélection que le clic sur sa ligne du
  FeatureManager**. Réutiliser les gestionnaires existants
  (`onSketchRowClick`, `onDatumRow`, `onSurfaceClick`, `onPlaneRow`) ;
  **ne pas dupliquer la logique de sélection**. Un nœud sélectionné se
  distingue dans le graphe comme la ligne se distingue dans l'arbre ;
- double-clic : le même effet que dans l'arbre (`editFeature` /
  `onSketchRowDblClick`), par réutilisation directe — pas de nouveau chemin
  d'édition.

**Distinction des deux natures d'arête** : les arêtes `param` se lisent au
premier coup d'œil comme différentes des `geom` (trait, couleur ou les
deux). Les variables se distinguent aussi des fonctions par leur forme de
nœud. Chercher la cohérence avec la palette existante plutôt qu'une
nouvelle.

**Rafraîchissement** : le graphe se redessine depuis `lastTree` quand
l'arbre est rafraîchi, sans appel réseau supplémentaire — même règle que le
dossier Équations du P021. S'il est fermé, ne rien calculer.

**Tenue en charge** : rester utilisable sur une pièce d'une soixantaine de
fonctions. Si le rendu impose un plafond, l'afficher plutôt que de tronquer
en silence.

## Ce qu'il ne faut pas faire

- Ne pas toucher `engine/` — le moteur livre déjà tout.
- Ne pas toucher `app/vendor/`, jamais.
- Ne pas ajouter d'appel réseau : `lastTree` suffit.
- Ne pas rendre le graphe éditable, même « juste le déplacement de nœuds » —
  une position déplacée à la main devrait être persistée quelque part, et
  ce quelque part n'existe pas encore. La disposition reste calculée.
- Ne pas dupliquer la sélection, l'édition ou le menu contextuel : les
  gestionnaires du FeatureManager existent, on les appelle.

## Validation avant de pousser

```bash
python3 -m pytest -q
node --check app/graph.js && node --check app/main.js
node --test tests/js/*.test.mjs
```

Scénario navigateur (`scripts/smoke/`) : après le bossage, ouvrir le graphe,
vérifier qu'il dessine au moins l'esquisse et le bossage reliés, le fermer,
zéro erreur console. Étendre le smoke existant sans casser ses étapes.

Plateforme de référence : **FreeCAD 1.1.3** (`AGENTS.md`). Si FreeCAD n'est
pas disponible, le signaler dans le message de commit.

## Commit

Un commit (ou une petite série cohérente), message en français, préfixé
`[N002]`. Tout texte visible est en français, vocabulaire SolidWorks 2025.
