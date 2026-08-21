# [N010b] Le graphe produit les variations — et la garde couvre où l'esquisse se pose

N010 a livré la répétition variable : une ligne d'arbre, une garde, trois
opérations. Elle marche, mais elle se pilote en écrivant du JSON à la main,
et **il reste un chemin non gardé**.

Ce prompt fait les deux, **dans cet ordre**. La partie 1 se livre même si la
partie 2 devait déborder : on ne rend pas une fonction facile à utiliser en
masse tant qu'un de ses chemins peut se tromper en silence.

## Partie 1 — la garde, là où l'esquisse se pose

`replay_group` réattache une esquisse posée sur une face en appelant
`kernel._top_face_id()` (`replay.py:527`, `kernel.py:4681`) : « la face
orientée vers le haut dont le centroïde est le plus élevé ».

C'est mieux qu'un indice figé — l'heuristique **s'adapte** au lieu de périmer.
Mais si une variation change *quelle* face est la plus haute, l'esquisse se
pose ailleurs, et la pièce est fausse **sans que rien ne le dise**. Même
famille de défaut que celui que N010 vient de fermer, autre chemin.

### Ce qui est invariant, et ce qui ne l'est pas

Le centroïde bouge dès qu'une cote change — inutilisable comme signature. Ce
qui survit à un simple changement de cote :

- le **nombre de faces candidates**, c'est-à-dire celles parmi lesquelles
  `_top_face_id` choisit (`normal.z > 0.5`) ;
- le **type de surface** de la face retenue (`Plane`, `Cylinder`…) ;
- la **direction de sa normale**, arrondie.

Si le compte de candidates change, « la plus haute » ne désigne plus le même
choix : c'est le refus qui compte.

### Le livrable

Une fonction pure dans `engine/replay.py`, sœur de `topology_verdict` :

```python
def attachment_verdict(expected, actual):
    """Rend None si l'esquisse se repose au même endroit, sinon la raison."""
```

Les deux empreintes ont la forme
`{"candidates": 1, "kind": "Plane", "normal": [0.0, 0.0, 1.0]}`.

- Empreinte **à la capture** : dans `_dump_sketch` (l. 254), quand
  `on_face` est vrai, sur la forme du corps source telle qu'elle est.
- Empreinte **au rejeu** : dans `replay_group`, sur le corps temporaire,
  **avant** `_rebuild_sketch`.
- Un refus nomme l'instance, l'esquisse (son `Label`), et ce qui a changé —
  même format que `_topology_refusal` (l. 493), et il annule la répétition
  entière comme le reste.

Corriger au passage la docstring de `_top_face_id` : elle dit « Selftest
helper » alors que la fonction est désormais sur le chemin de production.

**Écrire la limite**, comme pour `topology_verdict` : deux faces candidates
qui échangent leur rang de hauteur, à compte et type égaux, passent. La garde
réduit le risque, elle ne l'annule pas. La consigner comme **un test qui
passe**, pas seulement comme une phrase — c'est ce que N010 a fait avec
`test_topology_verdict_swapped_same_kind_passes`, et c'est ce qui fait qu'une
limite reste vraie au lieu de vieillir.

## Partie 2 — le graphe produit la liste des variations

C'est ce que la doctrine annonce depuis le début
([`docs/nodes-macros.md`](../docs/nodes-macros.md), § « La cible,
reformulée ») : *le graphe produit la liste des variations, le moteur rejoue
le groupe une fois par élément.* Les catégories `number`, `vector` et `list`
reprises de `j8sr0230/Nodes` au N006 servent enfin à quelque chose.

### La couture, et pourquoi elle est bonne

Une fonction pure de plus dans `engine/nodegraph.py` :

```python
def evaluate_instances(graph, variables):
    """Instances d'une répétition variable — pas des formes."""
```

Elle rend **exactement** ce que `parse_repeat_instances` accepte déjà :
`[{"offset": [x, y, z], "params": {"Pad": {"Length": 10}}}, …]`.

Donc le chemin par le graphe hérite sans effort de tout N010 : les nombres
obligatoires, le plafond de 500, le refus des noms de fonction inconnus, la
garde de topologie, le tout-ou-rien. **Ne pas réécrire ces contrôles côté
graphe** — les faire traverser.

`evaluate` (l. 186) ne change pas : elle rend des formes. La sortie d'un
graphe de répétition n'est pas une forme, c'est pourquoi c'est une seconde
entrée et non un drapeau sur la première.

### Deux nœuds, une catégorie

Nouvelle catégorie `repeat` → **« Répétition »** dans
`GRAPH_CATEGORY_LABELS` (`vocab.py:186`).

**`cote`** — « Cote ». Champs : `feature` (texte), `prop` (texte). Entrées :
`valeur` (nombre), `suite` (une autre cote, facultative). Elle émet une
entrée de paramètre par valeur reçue.

**`instance`** — « Instance ». Entrées : `decalage` (point), `cotes` (la
sortie d'une `cote`).

**C'est `suite` qui donne les dimensions multiples**, en chaîne plutôt qu'en
ports numérotés : `cote(Pad, Length) → cote(Pocket, Diameter, suite=…) →
instance`. Une chaîne n'a pas de plafond arbitraire à trois.

La fusion de `suite` avec la cote courante suit **la règle d'appariement déjà
écrite** (module docstring de `nodegraph.py`) : scalaire diffusé, listes de
même longueur appariées, longueurs différentes refusées. Et une règle de
plus, dans le même esprit : **la même `prop` de la même `feature` définie
deux fois dans une chaîne est refusée**, en nommant laquelle — jamais
écrasée silencieusement.

C'est la boucle, et elle vient gratuitement : `serie(0, 40, 5)` dans
`decalage`, `serie(10, 5, 5)` dans `valeur`, et voilà cinq instances.

### Un seul point de vérité dans le `.FCStd`

Le JSON persisté porte **soit `graph`, soit `instances`, jamais les deux** :

```json
{"features": [...], "graph": {...}, "mode": "fuse"}
{"features": [...], "instances": [...], "mode": "fuse"}
```

Quand il y a un graphe, les instances sont **dérivées, pas stockées**. Deux
définitions parallèles de la même chose finissent toujours par diverger —
c'est le défaut qui a mordu ce projet six fois, et c'est la raison pour
laquelle les empreintes de N010 ne sont pas persistées non plus.

`add_repeat_feature` accepte donc `graph` **ou** `instances` (exactement un
des deux, sinon refus nommé) ; `edit_repeat_feature` de même. Le protocole et
son test de contrat disent lequel.

## Partie 3 — l'UI, sur les rails déjà posés

La palette est **déjà générique** : `graphNodePaletteGroups`
(`app/graph.js:504`) affiche ce que `graph_vocabulary` déclare, groupé par
catégorie, avec icônes et grisage. Les deux nœuds y apparaissent sans code
d'UI. Idem pour `newGraphNode`, `functionPortLayout` et `composeGraphPayload`,
qui lisent le vocabulaire.

Il reste deux choses, et deux seulement :

**1. L'éditeur sert deux sortes de lignes.** `enterGraphFeature`
(`app/main.js:3346`) est câblé sur `get_graph_feature` / `edit_graph_feature`.
Lui donner une **sorte** (`graphe` | `repetition`) et brancher les deux appels
dessus. Pas de second éditeur : c'est le même geste sur le même canevas, et
un éditeur dupliqué divergerait.

**2. Une entrée dans `FEATURES`** (`app/features.js`), sur le patron exact de
« Fonction graphe » (l. 621) : bouton, icône, panneau, `openGraphEditor: true`.
Son panneau demande le groupe de fonctions — une ligne
`type: "selection"` avec `multiple: true`, comme les profils du lissage
(l. 272) — et le mode. Titre : **« Répétition variable »**.

Le `note` du panneau doit dire ce que la fonction fait *et ce qu'elle
refuse* : elle rejoue un groupe avec des cotes différentes, et elle s'arrête
plutôt que de produire si la topologie d'une instance ne correspond plus.
Un utilisateur qui rencontre le refus doit l'avoir déjà lu.

## Ce qu'il ne faut pas faire

- **Ne pas revalider côté graphe** ce que `parse_repeat_instances` valide
  déjà. Une seconde implémentation des mêmes règles est une divergence en
  attente.
- **Ne pas persister à la fois le graphe et les instances.**
- **Ne pas** deviner la « bonne » face quand la garde d'attache refuse.
  Refuser, nommer, s'arrêter.
- Ne pas rattraper une prop en double dans une chaîne de cotes par un
  écrasement — refuser en la nommant.
- Ne pas dupliquer l'éditeur de graphe.
- Ne pas plafonner les cotes chaînées à un nombre arbitraire.
- Ne pas ajouter de dépendance ; `engine/nodegraph.py` reste sans FreeCAD,
  `app/graph.js` reste sans DOM.
- Ne pas toucher `app/vendor/`.

## Validation avant de pousser

```bash
python3 -m compileall -q engine
python3 -m pytest -q
node --check app/graph.js && node --check app/main.js
node --test tests/js/*.test.mjs
PYTHONIOENCODING=utf-8 freecadcmd scripts/run-selftest.py
```

Le selftest gagne une section `n10b` avec des indicateurs booléens
top-niveau, volumes calculés à la main dans un commentaire :

1. **Le graphe pilote** : un graphe `serie → cote → instance` produit N
   instances, le volume attendu tombe, et l'arbre ne gagne **qu'une ligne**.
2. **La garde d'attache refuse** : une variation qui change la face la plus
   haute lève, le message nomme l'instance et l'esquisse, et **la pièce est
   inchangée**.
3. **Un seul point de vérité** : `get_repeat_feature` d'une ligne pilotée par
   un graphe rend le graphe et **pas** de liste `instances`.
4. **La chaîne de cotes** : deux `cote` chaînées donnent bien deux cotes par
   instance ; la même prop deux fois est refusée en la nommant.

En cas d'échec, `selftest-echecs.txt` nomme les indicateurs faux — le lire
plutôt que de fouiller la sortie FreeCAD.

Smoke : poser un nœud `instance` dans l'éditeur d'une répétition variable et
appliquer. Étendre le smoke sans casser ses étapes.

Plateforme de référence : `engine/platform.py`, source unique lue par la CI
et le selftest. Ne pas la modifier pour faire passer une sandbox.

## Commit

Un commit (ou une petite série cohérente), message en français, préfixé
`[N010b]`, **disant ce que la garde d'attache ne couvre pas** — deux faces
candidates de même type qui échangent leur rang de hauteur. Tout texte
visible est en français.
