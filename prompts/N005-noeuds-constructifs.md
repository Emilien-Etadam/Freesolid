# [N005] Ajouter et supprimer des fonctions depuis le graphe

Le graphe sait lire l'arbre (N002) et câbler ses paramètres (N003). Il ne
sait pas encore **le construire**. Ce prompt lui donne la palette : poser un
nœud crée une vraie fonction PartDesign, en supprimer un la supprime.

C'est l'aboutissement du parti pris de
[`docs/nodes-macros.md`](../docs/nodes-macros.md) : *le graphe **est** le
document*. Jusqu'ici il le regardait ; ici il le modifie.

**Périmètre : le client seul. Aucun fichier de `engine/` modifié, aucune
opération ajoutée au protocole.** Tout retombe sur les opérations existantes.

## Ce qui est déjà en place

La plomberie est complète, elle est simplement branchée ailleurs :

| Brique | Où | Ce qu'elle donne |
|---|---|---|
| Palette déclarative | `FEATURES` (`app/features.js`) | 22 entrées : icône, titre, formulaire, `build` → `{op, params}` |
| Profil au moment de créer | `withSketchProfile` (`app/features.js:63`) | injecte déjà `sketch: ctx.selectedSketch.name` dans les paramètres |
| Sélection depuis le graphe | N002 | le clic sur un nœud esquisse appelle `onSketchRowClick`, qui pose `selectedSketch` |
| Formulaire | `panel.open` (`app/panel.js`) | le même panneau que le ruban |
| Suppression | `delete_feature` | opération existante |
| Point d'insertion | `set_tip` / `tip_to_end` | la barre de reprise, glissable depuis le P021 |

Autrement dit : **sélectionner une esquisse dans le graphe puis lancer une
fonction crée déjà cette fonction sur cette esquisse.** Il manque seulement
que la palette soit atteignable depuis le graphe, et qu'un geste l'y pose.

## Le livrable

### 1. La palette dans le graphe

Un double-clic sur le fond du graphe — ou un bouton de sa barre — ouvre une
palette des fonctions constructibles, **alimentée par `FEATURES`**. Icône et
titre viennent de la table ; ne pas en tenir une seconde.

Au choix d'une fonction : le **panneau existant** s'ouvre (`panel.open`), le
formulaire est celui du ruban, et la validation envoie le `{op, params}` que
`build` produit. Aucun chemin de création nouveau.

### 2. Le profil vient du fil, pas d'un menu

Si un **nœud esquisse est sélectionné** dans le graphe au moment de poser la
fonction, il devient le profil — c'est déjà le comportement de
`withSketchProfile`, il suffit de ne pas le contourner.

Le geste naturel à offrir en plus : **tirer un fil depuis un nœud esquisse
vers le fond**, ce qui ouvre la palette avec cette esquisse comme profil.
C'est le geste Grasshopper, et il retombe sur `add_pad(length, sketch=…)`.

Réutiliser la mécanique de glisser du N003 (fil provisoire, cibles
distinguées) plutôt que d'en écrire une seconde.

### 3. Supprimer un nœud

`Suppr` sur un nœud fonction sélectionné, et l'entrée correspondante du menu
contextuel — qui est déjà `openMenu`, donc rien à ajouter s'il propose déjà
la suppression. La confirmation et le message d'erreur sont ceux de l'arbre.

### 4. Où la fonction se pose dans l'historique

Un graphe n'a pas d'ordre intrinsèque, l'historique si. La fonction se crée
**là où la barre de reprise se trouve**, exactement comme depuis le ruban.

Le graphe doit donc **montrer cette position** : les nœuds situés après la
barre s'affichent estompés, comme leurs lignes le sont déjà dans l'arbre. Un
utilisateur qui pose une fonction sans voir où elle atterrit sera surpris une
fois sur deux.

### 5. Les trois murs, à rendre visibles plutôt qu'à contourner

Ce sont des limites de PartDesign, pas des oublis. L'interface doit les
**dire**, pas les laisser découvrir par un échec :

- **Les fonctions d'habillage ne se posent pas depuis le graphe seul.**
  Congé, chanfrein, dépouille, perçage prennent un indice de face ou
  d'arête (`dressup`, `dressupParams`), qui vient du clic dans le viewport
   3D. Les proposer dans la palette **grisées avec leur raison** quand rien
  n'est sélectionné, et actives quand une face l'est — pas les masquer.
- **On ne recâble pas une fonction existante.** Le fil géométrique se pose
  **à la création**, jamais après : aucune opération ne change le `Profile`
  d'un bossage, et en ajouter une toucherait au nommage topologique. Les
  arêtes `geom` restent non tirables, comme au N003.
- **L'historique est linéaire.** Deux branches ne fusionnent que par des
  corps et un booléen. Le graphe reste un historique dessiné en graphe, pas
  une toile libre — ne pas laisser croire qu'on peut brancher n'importe quoi
  sur n'importe quoi.

## Ce qu'il ne faut pas faire

- Ne pas ajouter d'opération au protocole : `OPS` est inchangé.
- Ne pas dupliquer `FEATURES`, `panel.open`, `openMenu` ni la sélection.
  S'il manque une fonction dans la palette, elle manque aussi dans le ruban.
- Ne pas déplacer les nœuds à la souris : la position reste calculée.
- Ne pas contourner un des trois murs par un enchaînement d'opérations —
  notamment **ne pas émuler le recâblage par suppression et recréation**,
  qui perdrait les fonctions en aval sans prévenir.
- Ne pas toucher `engine/`, ni `app/vendor/`.

## Validation avant de pousser

```bash
python3 -m pytest -q
node --check app/graph.js && node --check app/main.js
node --test tests/js/*.test.mjs
```

La logique décidable va dans `app/graph.js` et se teste par `node --test` :
quelles fonctions de `FEATURES` sont posables selon le contexte (esquisse
sélectionnée ou non, face sélectionnée ou non), et quel profil part avec la
création.

Scénario navigateur (`scripts/smoke/`) : depuis le graphe, sélectionner
l'esquisse, poser un bossage par la palette, vérifier qu'un nœud bossage
relié à cette esquisse apparaît et que le volume augmente ; supprimer ce
nœud, vérifier le retour à l'état d'avant. Zéro erreur console. Étendre le
smoke sans casser ses étapes.

Plateforme de référence : **FreeCAD 1.1.3** (`AGENTS.md`).

## Commit

Un commit (ou une petite série cohérente), message en français, préfixé
`[N005]`. Tout texte visible est en français, vocabulaire SolidWorks 2025.
