# [N010] La répétition variable — une ligne d'arbre, et une garde qui refuse

C'est le manque que la cible de [`docs/nodes-macros.md`](../docs/nodes-macros.md)
(§ « La cible, reformulée ») désigne comme **le seul vrai** : répéter un
groupe de fonctions **à l'identique** est natif depuis N009 (`features` sur
`add_linear_pattern`) ; le répéter **avec variation** n'existe ni dans
FreeCAD ni dans SolidWorks.

Le moteur de rejeu est déjà écrit et vérifié — `engine/replay.py` (N009) :
`capture_group` (l. 128), `replay_group` (l. 306), `fuse_shapes` (l. 341),
`insert_via_tool_body` (l. 350). Le cas minimal passe au selftest.

**Ce prompt ne réécrit pas le rejeu. Il ajoute ce qui lui manque pour cesser
d'être un spike : une garde, une ligne d'arbre, une opération de protocole.**

## Ce que le spike a mesuré, et qu'il faut prendre au sérieux

`probe_stale_index` (l. 567) a établi un fait qui commande tout le reste :

> Un enlèvement 8×8 laisse `Edge3` intacte mais **renumérote** les indices
> suivants. Un congé posé sur l'indice périmé s'applique alors à **une autre
> arête**, sans lever d'erreur, et change le volume : 6720 → 6703 mm³.
> Mode relevé : `silencieux`.

Autrement dit : sans garde, une répétition de 200 instances peut rendre 200
pièces **subtilement fausses**, et rien ne le dit. C'est le pire résultat
possible — pire qu'un refus, pire qu'un plantage.

**La règle de ce prompt : refuser plutôt que produire.** Une répétition qui
n'est pas sûre ne rend pas de géométrie du tout.

## Le livrable

### 1. La garde de topologie — d'abord la fonction pure

Dans `engine/replay.py`, une fonction **sans FreeCAD**, testable en CI, sur
le modèle de `resolve_pattern_originals` (`kernel.py:63`) :

```python
def topology_verdict(expected, actual):
    """Rend None si le rejeu est sûr, sinon la raison, en français."""
```

`expected` et `actual` ont la même forme — l'empreinte de la forme **telle
qu'elle est au moment précis où la fonction s'applique** :

```python
{"edges": 12, "faces": 6, "kinds": {"Edge3": "Line", "Face1": "Plane"}}
```

`kinds` ne porte **que les sous-éléments réellement référencés** par la
fonction : c'est un dictionnaire de trois entrées, pas un dump de la forme.

Les trois refus, chacun avec un message qui nomme ce qui a changé :

1. **Le compte diffère** — `edges` ou `faces` n'est plus le même. La
   topologie a bougé, tout indice est suspect. Le message donne les deux
   comptes.
2. **Le type diffère** à un indice référencé — `Edge3` était `Line`, elle est
   `Circle`. Même compte, mais renumérotation. Le message nomme le
   sous-élément et les deux types.
3. **L'indice est hors bornes** — `Edge9` sur une forme qui n'a que 8 arêtes.

Sinon : `None`. Le compte **et** le type survivent tous deux à un simple
changement de cote — c'est exactement ce qui les rend utilisables comme
garde : ils ne bronchent pas sur une variation légitime, ils tombent sur une
renumérotation.

**Écrire aussi la limite dans la docstring**, sans l'enjoliver : deux arêtes
de même type qui échangent leur indice passent la garde. Elle réduit le
risque, elle ne l'annule pas. Ne pas prétendre l'inverse dans les libellés.

### 2. L'empreinte, côté FreeCAD

Un helper qui construit ce dictionnaire à partir d'une forme et des indices
déjà lus par `_base_indices` (l. 64).

- **À la capture** : la forme d'avant la fonction, c'est `obj.BaseFeature.Shape`.
  Une fonction à indices qui n'a pas de `BaseFeature` (elle serait la
  première du corps) se refuse à la capture.
- **Au rejeu** : la même empreinte, prise sur la forme courante du corps
  temporaire **juste avant** d'appeler `_replay_feature`.

La garde ne concerne que les fonctions qui portent un indice — congé,
chanfrein, dépouille, coque. Un bossage référence une esquisse, pas un
numéro : rien à vérifier, rien à ralentir.

### 3. Tout ou rien

Une instance qui échoue à la garde **annule la répétition entière**. Pas
d'instance sautée, pas de géométrie partielle : le groupe est un algorithme,
s'il ne s'applique pas à l'instance n° 147, le résultat est faux.

Le message nomme **quelle instance** (`n° 147 sur 200`), **quelle fonction**
(son `Label`, pas son `Name`) et **la raison** rendue par `topology_verdict`.

Atomicité comme `edit_graph_feature` (`kernel.py:1633`) : on évalue et on
construit **d'abord**, on ne touche à la pièce que si tout a réussi.
`replay_group` nettoie déjà son corps temporaire dans un `finally` — ne pas
défaire ça.

### 4. La ligne d'arbre — le patron de la fonction graphe, à l'identique

Reprendre **exactement** le patron de `add_graph_feature` (`kernel.py:1591`),
qui reprend lui-même celui de la gravure. Ne pas en inventer un quatrième.

- `_REPEAT_PROPS`, à côté de `_GRAPH_PROPS` (l. 1354) :
  `FreeSolidRepeatJson`, `FreeSolidRepeatMode`.
- `_mark_repeat_tool` sur le modèle de `_mark_graph_tool` (l. 1367).
- **`_is_internal_tool` (l. 1375) reste le prédicat unique.** Sa docstring dit
  déjà pourquoi : « Deux prédicats parallèles divergeraient — c'est le défaut
  que N001b a dû corriger. » Une propriété de plus, au même endroit.
- La géométrie entre par la route du corps outil, en **un seul booléen** :
  une ligne dans l'arbre, quel que soit le nombre d'instances.
- Le JSON se persiste sur le `Tip`, comme `_persist_graph` (l. 1581).

Libellé : **« Répétition variable — Bossage »** / **« … — Enlèvement »**. Le
terme n'existe pas chez SolidWorks (« Répétition pilotée par une table » est
autre chose) — c'est assumé, la fonction non plus n'existe pas là-bas.

### 5. Ce que le JSON contient — et ce qu'il ne contient pas

```json
{
  "features": ["Pad", "Pocket"],
  "instances": [
    {"offset": [0, 0, 0],  "params": {"Pad": {"Length": 10}}},
    {"offset": [40, 0, 0], "params": {"Pad": {"Length": 20}}}
  ],
  "mode": "fuse"
}
```

- `offset` : le décalage déjà accepté par `replay_group`.
- `params` : **des nombres**. Pas d'expression, pas de `Variables.x` — c'est
  l'évaluateur qui produit des nombres, la ligne d'arbre les consomme.
- **Les empreintes ne sont pas persistées.** Elles se recalculent depuis les
  fonctions source à chaque `add_` / `edit_`, donc elles ne peuvent pas
  décrire un état périmé du document. C'est la même raison qui fait que le
  graphe *est* le document plutôt que sa copie.
- Plafond : une constante nommée, **500 instances**, avec un message qui la
  cite. Le spike a mesuré jusqu'à 200 (`measure_replay_cost`, l. 466) ; 500
  laisse de la marge sans laisser l'attente devenir illimitée.
- Réutiliser `_dump_graph_json` (l. 1507) ou son équivalent pour la sérialisation
  et le plafond de taille — pas une seconde implémentation.

### 6. Le protocole, et l'arbre

Trois opérations dans `engine/protocol.py`, contractées et testées comme
leurs voisines `add_graph_feature` / `edit_graph_feature` /
`get_graph_feature` (l. 113-116) :

```
add_repeat_feature   : features (list), instances (list), mode (str)
edit_repeat_feature  : feature (str), instances (list)
get_repeat_feature   : feature (str)
```

Les deux qui écrivent entrent dans `_TRANSACTIONAL` — un Ctrl+Z défait la
répétition entière, pas une instance.

Dans `get_tree`, `entry()` (l. 3215) pose déjà `item["graph"]` quand la
propriété est là ; poser `item["repeat"]` de la même façon.

**Et l'arête qui compte** : la ligne de répétition doit déclarer les
fonctions source dans ses `deps`, sinon le graphe montre une ligne qui sort
de nulle part. Les fonctions rejouées sont des copies détruites — le lien
n'existe pas dans l'`OutList`, il faut le synthétiser depuis le JSON dans
`_annotate_tree_links` (l. 3153). Vérifier que `dangling_deps` reste vide :
c'est l'invariant que N001b a rendu auto-vérifiant, il ne doit pas retomber.

### 7. Le selftest, section `n10`

Sur le modèle de la section `n9` (`kernel.py:6067`), avec des volumes
calculés à la main dans un commentaire — pas des valeurs relevées après coup :

1. **Ça marche** : un groupe bossage + enlèvement, trois instances de
   longueurs différentes, volume attendu exact, et **une seule ligne**
   ajoutée à l'arbre (le compter, ne pas le supposer).
2. **La garde refuse** : un groupe qui contient un congé sur un indice, et
   une variation qui change la topologie. Le selftest vérifie que
   `add_repeat_feature` **lève**, que le message nomme l'instance et la
   fonction, et que **la pièce est inchangée** (volume identique avant/après).
   C'est l'indicateur le plus important du lot : c'est lui qui prouve qu'on
   ne rend pas 6703 mm³ en croyant en rendre 6720.
3. **La réédition** : `edit_repeat_feature` avec d'autres longueurs change le
   volume et laisse toujours une seule ligne ; `get_repeat_feature` rend ce
   qui a été écrit.
4. **Propreté** : aucun artefact `Repeat*` ni corps temporaire ne survit —
   `_temp_bodies_left` (l. 375) sait déjà le dire.

Les indicateurs sont booléens et top-niveau, pour que `selftest_summary`
(l. 189) les compte et que `selftest-echecs.txt` (N009b) les nomme en cas
d'échec.

## Ce qui n'est pas dans ce prompt

**L'UI.** Ni palette, ni nœud, ni panneau. La liste d'instances s'écrit en
JSON par le protocole. Ce sera N010b : brancher `engine/nodegraph.py` pour
que le graphe **produise** la liste des variations — c'est là que les
catégories `list` et `number` de N006 servent enfin à quelque chose.

Le mécanisme d'abord, prouvé par le selftest ; l'interface ensuite, sur un
mécanisme qui ne bouge plus. Une UI posée sur un rejeu non gardé montrerait
de belles répétitions fausses.

## Ce qu'il ne faut pas faire

- **Ne pas sauter une instance qui échoue.** Tout ou rien.
- **Ne pas rattraper une renumérotation en devinant** la « bonne » arête par
  proximité géométrique. C'est du nommage topologique, c'est un autre
  chantier, et une heuristique silencieuse est exactement le défaut qu'on
  corrige ici.
- Ne pas dupliquer `_is_internal_tool`, ni le patron du corps outil.
- Ne pas persister les empreintes dans le `.FCStd`.
- Ne pas ajouter de dépendance : le moteur reste en stdlib pure, et
  `engine/replay.py` n'importe pas FreeCAD au niveau module.
- Ne pas toucher `app/vendor/`.

## Validation avant de pousser

```bash
python3 -m compileall -q engine
python3 -m pytest -q
PYTHONIOENCODING=utf-8 freecadcmd scripts/run-selftest.py
```

En cas d'échec du selftest, `selftest-echecs.txt` nomme les indicateurs faux
— le lire plutôt que de fouiller la sortie FreeCAD.

Plateforme de référence : la version est dans `engine/platform.py`, source
unique lue par la CI **et** par le selftest (N009b). Si le selftest refuse de
démarrer sur un écart de version, c'est ce fichier qui fait foi — ne pas le
modifier pour faire passer une sandbox.

## Commit

Un commit (ou une petite série cohérente), message en français, préfixé
`[N010]`. Dire dans le message **ce que la garde ne couvre pas** — deux
sous-éléments de même type qui échangent leur indice — pour que la limite
soit écrite quelque part avant qu'on la rencontre.
