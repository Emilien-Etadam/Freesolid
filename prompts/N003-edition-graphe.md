# [N003] Câbler les paramètres à la souris

Troisième brique de la série **N** ([`docs/nodes-macros.md`](../docs/nodes-macros.md)).
Le N002 a rendu le graphe lisible ; N003 le rend agissant — sur **une seule
chose**, celle qu'un graphe fait mieux qu'une liste : la couche
paramétrique.

**Périmètre : le client seul. Aucun fichier de `engine/` modifié, aucune
opération ajoutée au protocole.** Tous les gestes ci-dessous retombent sur
des opérations qui existent déjà.

## L'idée

Aujourd'hui, piloter une cote par une variable se fait en tapant `= largeur`
dans un champ du panneau. La couche paramétrique est donc **visible** dans le
graphe depuis le N002, mais toujours **manipulable** ailleurs.

N003 fait de ce lien un geste : **tirer un fil d'une variable vers une
fonction**. C'est le geste Grasshopper, et il atterrit sur `set_params` sans
qu'une ligne de moteur bouge.

## Ce que le moteur donne déjà

| Geste voulu | Opération existante | Détail vérifié |
|---|---|---|
| Poser une liaison | `set_params(feature, {prop: "largeur"})` | une chaîne non numérique est traitée comme expression (`kernel.py:2511`) |
| Couper une liaison | `set_params(feature, {prop: <nombre>})` | une valeur numérique appelle `setExpression(prop, None)` avant d'écrire (`kernel.py:2521`) |
| Connaître les cotes d'une fonction | `get_params(feature)` | rend `[{prop, value, expr?}]` — le nom, la valeur **et** l'expression en cours |

Deux propriétés de `set_params` à exploiter plutôt qu'à redouter :

- Elle est **atomique**. Une expression refusée restaure tout et laisse la
  pièce intacte (`_restore_props`, acquis du P032). Un fil mal tiré ne peut
  donc pas corrompre le document — c'est ce qui rend le geste sûr.
- Elle renvoie l'arbre. Le rafraîchissement du graphe passe par le chemin
  existant, rien de nouveau à câbler.

## Le livrable

### 1. Tirer un fil : variable → fonction

Départ sur un nœud **variable**, arrivée sur un nœud **fonction**.

À l'arrivée, la fonction a en général plusieurs cotes éditables : proposer
un **choix parmi ses propriétés**, alimenté par `get_params(feature)` —
appelé **au moment du dépôt**, jamais par image. Afficher pour chacune son
libellé français et son unité : `PROP_LABELS` (`app/main.js`) fait déjà cette
correspondance, ne pas en écrire une seconde. Une propriété déjà pilotée se
signale comme telle, avec l'expression en cours.

Au choix d'une propriété : `set_params(feature, {prop: <nom de la variable>})`.

Pendant le glisser, un fil provisoire suit le pointeur et les cibles
valides se distinguent — un dépôt sur une esquisse, un plan ou une surface
n'aboutit à rien et doit se voir **avant** le relâchement, pas après.

### 2. Couper un fil paramétrique

Sur une arête `param` : menu contextuel → « Supprimer la liaison », et la
touche `Suppr` quand l'arête est sélectionnée.

Couper appelle `set_params(feature, {prop: <valeur courante>})`, la valeur
que `get_params` donne à côté de l'expression. **La géométrie ne doit pas
bouger** : on fige la cote sur ce qu'elle vaut, on ne la remet pas à zéro.
C'est la différence entre délier et casser.

### 3. Les actions ordinaires, depuis le graphe

Pour ne pas obliger à retourner dans l'arbre à chaque geste, le clic droit
sur un nœud ouvre **le menu contextuel du FeatureManager** —
`openMenu(event, feature)` (`app/main.js:1897`), tel quel. Renommer,
modifier, supprimer, couleur : tout ce qu'il propose déjà, sans rien
redéfinir.

Ne pas construire un second menu. S'il manque une entrée, elle manque aussi
dans l'arbre, et c'est un autre sujet.

### 4. Erreurs et annulation

Un refus du moteur s'affiche par `say(..., true)` comme partout ailleurs, et
le graphe se redessine sur l'arbre revenu — la pièce est déjà intacte, il n'y
a rien à défaire à la main.

`undo` couvre ces gestes sans traitement particulier : ce sont des
`set_params` ordinaires. Le vérifier, ne pas l'implémenter.

## Ce qu'il ne faut pas faire

- **Ne pas recâbler la géométrie.** Redirigier un `Profile` vers une autre
  esquisse, ou réattacher une esquisse à un autre plan, demanderait une
  opération nouvelle : `_EDITABLE_PROPS` (`kernel.py:2262`) ne contient que
  douze propriétés numériques, et rien d'autre n'est modifiable. C'est le
  geste que tout utilisateur d'éditeur de nœuds essaiera en premier ; la
  réponse est **non pour l'instant**, parce qu'il touche au nommage
  topologique, la partie du modèle où l'on ne s'aventure pas en passant.
  Rendre les arêtes `geom` visiblement non tirables plutôt que de les
  laisser croire manipulables.
- **Ne pas déplacer les nœuds**, même comme confort : une position déplacée
  à la main devrait être persistée, et cet endroit n'existe toujours pas.
- Ne pas ajouter d'opération au protocole : `OPS` est inchangé.
- Ne pas appeler `get_params` en continu — au dépôt, une fois.
- Ne pas toucher `engine/`, ni `app/vendor/`.

## Validation avant de pousser

```bash
python3 -m pytest -q
node --check app/graph.js && node --check app/main.js
node --test tests/js/*.test.mjs
```

Ce qui est logique pure — quelles cibles sont valides pour un fil, quelle
valeur fige une coupure — va dans `app/graph.js` et se teste par
`node --test`, comme le reste du module. Le glisser lui-même n'est pas
testable ainsi ; c'est le rôle du smoke.

Scénario navigateur (`scripts/smoke/`) : créer une variable, ouvrir le
graphe, tirer un fil de la variable vers le bossage, choisir la profondeur,
vérifier que l'arête `param` apparaît et que la cote suit ; couper la
liaison, vérifier que la géométrie ne bouge pas. Zéro erreur console.
Étendre le smoke existant sans casser ses étapes.

Plateforme de référence : **FreeCAD 1.1.3** (`AGENTS.md`). Si FreeCAD n'est
pas disponible, le signaler dans le message de commit.

## Commit

Un commit (ou une petite série cohérente), message en français, préfixé
`[N003]`. Tout texte visible est en français, vocabulaire SolidWorks 2025.
