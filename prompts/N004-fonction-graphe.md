# [N004] La fonction graphe — moteur : évaluateur, persistance, insertion

Quatrième brique de la série **N**, et la seule qui demande du neuf. Le parti
pris est fixé dans [`docs/nodes-macros.md`](../docs/nodes-macros.md) §3 :

> Une **fonction graphe** est une ligne de l'arbre, un éditeur de nœuds dédié
> à l'intérieur, boucles et listes comprises, et **une forme en sortie**. Le
> modèle est celui de l'esquisse : un `SketchObject` est une ligne de l'arbre
> qui encapsule géométrie, contraintes et solveur, que le reste du document
> ignore.

**Périmètre : le moteur seul. Aucun fichier de `app/` modifié.** L'éditeur de
nœuds dédié est le N004b — ce prompt livre ce sur quoi il se branchera, et se
valide par selftest avec un graphe écrit à la main.

C'est **le premier évaluateur du projet**. Tout l'enjeu est de le garder
borné.

## Ce qui n'est pas à inventer

L'insertion, la persistance et la réédition ont déjà leur patron dans le
dépôt : **la gravure de texte**. Une fonction graphe est une gravure dont la
géométrie vient d'un graphe au lieu d'une police.

| Besoin | Où c'est déjà fait |
|---|---|
| Forme `Part` insérée dans la chaîne PartDesign | `add_text` : `Part::Feature` → `PartDesign::Body` via `BaseFeature` → `add_boolean(fuse\|cut)` |
| Paramètres persistés et rééditables | `_TEXT_PROPS` (`kernel.py:1265`), propriétés custom sur la ligne |
| Artefacts internes cachés de l'arbre | `_mark_text_tool` / `_is_text_tool` (`kernel.py:1276`) |
| Réédition atomique | `edit_text` : la géométrie est reconstruite **d'abord** ; si elle échoue, la pièce n'est pas modifiée |
| Retrouver le corps outil | `obj.Group` puis `BaseFeature` (`kernel.py:1362`) |

Suivre ce patron, ne pas en inventer un second.

## Le livrable

### 1. `engine/nodegraph.py` — l'évaluateur, **pur**

C'est la contrainte d'architecture centrale, et le prolongement de ce que
`AGENTS.md` impose : **aucun import FreeCAD**, donc testable en CI.

```python
def evaluate(graph, variables):
    """Instructions géométriques d'un graphe, ou lève GraphError.

    `graph`     : {"nodes": [...], "edges": [...], "output": <id>}
    `variables` : {nom: valeur} — les variables globales, valeurs courantes
    Retour      : [{"shape": "box"|"cylinder", ...}] — des instructions,
                  pas des formes.
    """
```

**L'évaluateur ne fabrique aucune géométrie.** Il rend une liste plate
d'instructions décrivant quoi construire et où. C'est le kernel qui les
traduit en `Part`. C'est ce qui rend la partie difficile — sémantique des
listes, cycles, plafonds — vérifiable sans FreeCAD.

### 2. Le vocabulaire de nœuds, volontairement court

Six types, juste de quoi couvrir le banc d'essai (semer des perçages sur une
grille) et rien de plus. On élargira sur besoin constaté, pas par
anticipation.

| Nœud | Entrées | Sortie |
|---|---|---|
| `nombre` | une valeur littérale | nombre |
| `variable` | un nom | la valeur courante, depuis `variables` |
| `serie` | départ, pas, nombre | **liste** de nombres |
| `calcul` | deux entrées, opération (`+ - * /`) | nombre ou liste |
| `point` | x, y, z | point ou liste de points |
| `cylindre` / `boite` | dimensions, point d'ancrage | instruction(s) de forme |

Le nœud désigné par `output` fournit le résultat. Un graphe dont la sortie
n'est pas une forme est refusé.

### 3. La règle d'appariement — le cœur du prompt

C'est ce qui rend Grasshopper puissant **et** déroutant. Elle se décide ici,
une fois, et s'écrit noir sur blanc dans la docstring du module :

- un **scalaire face à une liste** se diffuse : `serie(0,10,5) * 2` donne
  cinq valeurs ;
- **deux listes de même longueur** s'apparient terme à terme ;
- **deux listes de longueurs différentes sont refusées**, avec un message
  qui donne les deux longueurs.

Le troisième point est un choix, pas une facilité. Grasshopper rallonge la
plus courte en répétant son dernier élément ; c'est précisément ce qui fait
qu'on obtient sept perçages en en attendant cinq, sans que rien ne le
signale. **Un refus explicite est relâchable plus tard ; une répétition
silencieuse ne l'est plus** une fois que des pièces en dépendent.

### 4. Les garde-fous de l'évaluateur

- **Cycles refusés**, avec le nom d'un nœud du cycle dans le message.
- **Plafond du nombre d'éléments produits**, refus explicite au-delà —
  jamais de troncature silencieuse. Le protocole plafonne déjà les
  comptes à `_COUNT_MAX = 10000` (`protocol.py`) : rester cohérent.
- **Entrées manquantes, type inattendu, `output` inconnu** : refus avec un
  message en français qui nomme le nœud fautif.
- Division par zéro, `serie` à pas nul ou à compte négatif : refusés.

### 5. Les opérations

Trois, et le protocole les valide comme les autres :

| Op | Paramètres | Effet |
|---|---|---|
| `add_graph_feature` | `graph`, `mode` (`fuse`\|`cut`) | évalue, construit la forme, l'insère par la route du corps outil |
| `edit_graph_feature` | `feature`, `graph` | réévalue et remplace — **atomique**, comme `edit_text` |
| `get_graph_feature` | `feature` | rend le graphe persisté |

Le graphe est persisté en JSON dans une propriété custom
(`App::PropertyString`) sur la ligne créée, sur le modèle de `_TEXT_PROPS`.
Le `.FCStd` reste un document FreeCAD normal : une forme et une propriété
texte, rien qu'un `Part::FeaturePython` ou un proxy à réimporter.

L'entrée d'arbre de la fonction porte un champ `graph`, comme la gravure
porte `text` — c'est ce que le N004b relira pour rouvrir l'éditeur.

### 6. Le masquage des artefacts — **ne pas dupliquer**

La fonction graphe crée les mêmes artefacts internes qu'une gravure : un
`Part::Feature` et un corps outil, qui doivent rester hors de l'arbre.

`_is_text_tool` fait déjà ce travail pour le texte. **Généraliser ce test
plutôt qu'en ajouter un second à côté.** Deux définitions parallèles de « cet
objet est-il interne ? » reproduiraient exactement le défaut que le N001b a
eu à corriger — l'ensemble qui filtre finit par diverger de ce que le payload
expose.

Après ce prompt, `protocol.dangling_deps` doit toujours rendre une liste vide
sur une pièce portant une fonction graphe.

## Ce qu'il ne faut pas faire

- **Ne pas produire de fonctions PartDesign depuis le graphe.**
  L'évaluateur appelle l'API `Part`, jamais PartDesign : la géométrie qu'il
  produit est **figée à l'intérieur**, et le paramétrique reste dehors — dans
  les entrées du graphe et dans la chaîne qui consomme sa sortie. Même statut
  que le surfacique avant le P016.
- **Ne pas utiliser `Part::FeaturePython`.** FreeCAD réimporte le module du
  proxy à l'ouverture, or l'addon a été retiré au P017 : le fichier
  s'ouvrirait avec un objet cassé. Un `Part::Feature` ordinaire plus une
  propriété texte.
- **Ne pas ajouter la dépendance `awkward`.** Le moteur est en stdlib pure et
  c'est structurant. Des listes imbriquées Python suffisent au vocabulaire
  ci-dessus.
- Ne pas élargir le vocabulaire de nœuds « tant qu'on y est ».
- Ne pas toucher `app/` — l'éditeur est le N004b.

## Validation avant de pousser

```bash
python3 -m compileall -q engine
python3 -m pytest -q
PYTHONIOENCODING=utf-8 freecadcmd scripts/run-selftest.py   # si FreeCAD dispo
```

**pytest** — l'essentiel du test est ici, puisque l'évaluateur est pur :

- diffusion d'un scalaire sur une liste ;
- appariement de deux listes de même longueur ;
- **refus de deux longueurs différentes**, message citant les deux ;
- cycle refusé, nœud nommé ;
- plafond dépassé refusé, sans troncature ;
- `output` inconnu, entrée manquante, pas nul, division par zéro ;
- un graphe « grille de cylindres » rend le bon nombre d'instructions, aux
  bonnes positions.

**selftest** — le banc d'essai en vrai, graphe écrit à la main :

- `n4_graphe_perce` : une grille de cylindres en `mode: "cut"` sur une plaque
  fait baisser le volume du nombre attendu de perçages ;
- `n4_graphe_reedite` : `edit_graph_feature` avec un compte différent change
  le volume, et la pièce reste saine ;
- `n4_graphe_refus_atomique` : un graphe invalide est refusé **sans modifier
  la pièce** — même exigence que le P032 sur les expressions ;
- `n4_arbre_propre` : les artefacts n'apparaissent pas dans l'arbre, et
  `dangling_deps` reste vide.

Plateforme de référence : **FreeCAD 1.1.3** (`AGENTS.md`).

## Commit

Un commit (ou une petite série cohérente), message en français, préfixé
`[N004]`. Tout texte visible est en français, vocabulaire SolidWorks 2025.
