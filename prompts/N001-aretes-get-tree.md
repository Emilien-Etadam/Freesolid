# [N001] Les arêtes de dépendance dans `get_tree`

Première brique de la série **N** (nœuds), dont le parti pris est fixé dans
[`docs/nodes-macros.md`](../docs/nodes-macros.md). Toute la série repose sur
celle-ci : aujourd'hui le moteur **jette** les dépendances entre fonctions,
et sans elles il n'y a ni vue en graphe ni éditeur de nœuds.

**Périmètre : le moteur seul. Aucune UI, aucun rendu, aucun fichier de
`app/` modifié.** Le dessin du graphe est le N002.

## Le constat

`Kernel.get_tree` (`engine/kernel.py:2234`) construit une liste plate à un
seul niveau d'imbrication. Il lit bien `Profile` — mais dans l'unique but de
ranger une esquisse consommée sous la fonction qui la consomme, puis il
abandonne tout le reste : `AttachmentSupport`, `BaseFeature`, corps outils
des booléens, et les expressions.

Les données existent pourtant déjà des deux côtés :

- **arêtes géométriques** — `obj.OutList`, que FreeCAD tient à jour ;
- **arêtes paramétriques** — `obj.ExpressionEngine`, déjà lu par le helper
  `Kernel._expression_map` (`engine/kernel.py:2166`).

## Le livrable

### 1. Deux champs par entrée de l'arbre

Chaque entrée produite par la fonction interne `entry()` de `get_tree` —
fonctions du corps **et** esquisses imbriquées en `children` — gagne :

| Champ | Type | Contenu |
|---|---|---|
| `deps` | `list[str]` | noms d'objets dont cette entrée dépend, arêtes géométriques |
| `driven` | `dict[str, str]` | `{chemin de propriété: expression}`, les propriétés pilotées |

`deps` est une liste de **noms internes** (`Sketch001`, `XZ_Plane`), pas de
labels : le client fait la correspondance avec les entrées qu'il a déjà.

Les deux champs sont **omis quand ils sont vides**, comme `children` l'est
déjà. Une pièce sans expression ne doit pas se mettre à trimballer des
`"driven": {}` partout.

### 2. La règle d'arête, et elle est stricte

> Une arête n'est émise que si sa cible est **elle-même un nœud du même
> payload** — une fonction, une esquisse, un plan de référence, une surface
> ou un corps déjà présent dans la réponse.

Autrement dit : **aucune arête pendante.** Un `OutList` contient toutes
sortes de choses (l'Origin, le VarSet, des objets internes) ; tout ce qui ne
correspond à aucun nœud dessinable est écarté. Le client doit pouvoir tracer
chaque arête sans jamais avoir à en ignorer une.

### 3. Le filtrage est une fonction pure, testable sans FreeCAD

Contrainte d'architecture, elle n'est pas négociable (voir `AGENTS.md`) :
la règle ci-dessus s'écrit dans une **fonction pure prenant des noms, pas
des objets FreeCAD**, par exemple

```python
def visible_deps(dep_names, known_names):
    """Noms de `dep_names` qui désignent un nœud de `known_names`, dédoublonnés, ordre d'entrée conservé."""
```

placée dans `engine/protocol.py` (ou un module pur voisin), et appelée par
`get_tree` avec `[o.Name for o in obj.OutList]`. C'est ce qui rend la règle
vérifiable en CI, là où `get_tree` ne l'est pas.

### 4. Tests

- **pytest** — la fonction pure : cible connue conservée, cible inconnue
  écartée, doublons supprimés, ordre stable, liste vide → liste vide.
- **selftest** (`engine/kernel.py`, section rapport) — deux points de
  contrôle sur un cas réel :
  - `n1_deps_pad_sketch` : le bossage a bien son esquisse dans ses `deps` ;
  - `n1_driven_ok` : après avoir posé une expression sur une cote, la
    propriété concernée apparaît dans le `driven` de sa fonction.

### 5. Documentation

Mettre à jour la docstring de `get_tree` : elle décrit la forme du payload,
elle doit décrire les deux nouveaux champs et la règle d'arête.

## Ce qu'il ne faut pas faire

- Ne pas toucher à `app/` — le rendu est le N002.
- Ne pas toucher à `app/vendor/`, jamais.
- Ne pas ajouter d'opération au protocole : `get_tree` existe, on enrichit
  sa réponse. `OPS` est inchangé.
- Ne pas essayer de **parser** les expressions pour en extraire les noms de
  variables. On émet la chaîne brute ; l'appariement avec les variables
  connues est un travail de client, assumé comme tel.
- Ne pas changer la forme existante du payload : `children`, `planes`,
  `bodies`, `surfaces`, `tip` gardent leur structure. On ajoute, on ne
  réorganise pas.

## Coordination avec la série P

**Décision du 2026-08-15 : la série N démarre une fois la série P terminée.**
N001 arrive donc **après P021**, et pas avant — ce prompt est écrit avant
lui, il faut le relire à la lumière du code tel qu'il sera.

Deux points à vérifier au moment de l'exécuter, parce que P021 passe par le
même endroit :

- **`get_tree` aura déjà été enrichi** par P021 d'un `tree["variables"]` en
  haut du dictionnaire de retour. Aucune contradiction — `deps` et `driven`
  sont des champs *par entrée*, `variables` est un champ *de payload*. On
  ajoute à côté, on ne réorganise rien, et la consigne « ne pas changer la
  forme existante » s'applique aussi à ce que P021 aura posé.
- **La section de rapport du selftest aura gagné `p7_tree_variables`.** Les
  points de contrôle `n1_*` s'ajoutent à la suite, sans y toucher.

Bénéfice à saisir une fois les deux en place : P021 crée un dossier
« Équations » listant les variables globales, et le champ `driven` de N001
dit **quelles fonctions chaque variable pilote**. De quoi afficher
« utilisée par : Bossage1 » dans ce dossier — c'est la moitié du gestionnaire
d'équations de SolidWorks, et elle devient gratuite. À traiter dans un prompt
dédié, pas ici : le périmètre de N001 reste le moteur seul.

## Validation avant de pousser

```bash
python3 -m compileall -q engine
python3 -m pytest -q
PYTHONIOENCODING=utf-8 freecadcmd scripts/run-selftest.py   # si FreeCAD dispo
```

Le selftest exige FreeCAD **1.0.x** (voir `AGENTS.md` — 1.1 fait diverger
l'assemblage). S'il n'est pas disponible, le signaler dans le message de
commit.

## Commit

Un commit, message en français, préfixé `[N001]`.

---

*Suite prévue, à écrire une fois le N001 vérifié : **N002** vue graphe en
lecture seule, **N003** édition dans le graphe, **N004** fonction graphe
(boucles et listes), **N005** macros.*
