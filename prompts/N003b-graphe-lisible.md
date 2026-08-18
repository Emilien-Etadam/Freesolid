# [N003b] Rendre le graphe lisible : croisements, courbes, icônes

Correctif d'aspect de la série **N**. Le graphe fonctionne
(N002 le dessine, N003 le rend agissant) mais il est **illisible** sur une
pièce réelle. Ce prompt ne change aucun comportement : il change ce qu'on voit.

**Périmètre : le client seul. Aucun fichier de `engine/` modifié, aucune
opération ajoutée, aucun geste nouveau.**

## Le diagnostic

Trois causes, mesurables dans le code :

1. **Aucune minimisation de croisements.** `buildGraph` (`app/graph.js`)
   range par couches via `longestLayers`, puis trie chaque couche par
   `order`. C'est l'étape 1 de Sugiyama sans l'étape 2. Sur la pièce
   vitrine, les fils se croisent en tous sens.
2. **Les arêtes sont des segments droits** — `svgEl("line", …)`
   (`app/main.js:2528`). Un faisceau de droites qui se coupent se lit comme
   un schéma électrique, pas comme un graphe.
3. **Les nœuds sont des rectangles nus** de 148×32 (`appendGraphShape`) :
   ni icône, ni distinction visuelle par nature. Or le FeatureManager
   affiche déjà une icône par ligne, et la table `TREE_ICONS`
   (`app/main.js:981`) fait la correspondance type → fichier.

## Le livrable

### 1. Minimiser les croisements

**D'abord un spike, avant d'écrire quoi que ce soit.**

La bibliothèque de référence est [`@dagrejs/dagre`](https://github.com/dagrejs/dagre)
(MIT, fork maintenu — l'ancien `dagre` ne l'est plus). Elle fait le Sugiyama
complet : rangs, réduction des croisements, positionnement.

Le projet charge déjà three.js par **import map depuis un CDN**
(`app/index.html:604`), donc une dépendance ESM distante est admise par
l'architecture. Mais `app/graph.js` est aujourd'hui **pur et sans
dépendance**, et c'est ce qui le rend testable par `node --test`.

Le spike répond à une seule question : **`@dagrejs/dagre` s'importe-t-il
proprement en ESM navigateur *et* sous `node --test`, sans traîner lodash
ni build ?**

- **Si oui** : l'utiliser. Remplacer `longestLayers` et le placement par un
  appel dagre dans `buildGraph`. Le reste de `buildGraph` — nœuds, arêtes,
  filtre anti-arête-pendante — ne bouge pas. La déclarer dans l'import map à
  côté de three.js.
- **Si non** : écrire la réduction de croisements à la main. L'heuristique
  **barycentre** est le classique : quelques passes descendantes puis
  montantes, chaque nœud replacé à la moyenne des positions de ses voisins
  de la couche précédente, en conservant l'ordre en cas d'égalité. C'est
  une cinquantaine de lignes, ça reste pur, et vos tests restent intacts.

**Ne pas trancher à l'avance : faire le spike, choisir, et dire lequel dans
le message de commit.** Les deux voies sont acceptables ; ce qui ne l'est
pas, c'est de garder l'ordre actuel.

Dans les deux cas, la sortie doit rester **déterministe** — deux appels sur
le même arbre donnent les mêmes coordonnées. Le test existant le vérifie
déjà ; il ne doit pas être affaibli.

### 2. Arêtes en courbes

Remplacer `<line>` par un `<path>` en **Bézier cubique**, avec des poignées
horizontales — le tracé habituel des éditeurs de nœuds :

```
M x1,y1  C x1+d,y1  x2-d,y2  x2,y2
```

`d` proportionnel à l'écart horizontal, borné pour éviter les boucles sur
les arêtes courtes.

La zone de clic (`.graph-edge-hit`, posée par le N003) doit suivre **le même
tracé** : une arête qui se clique ailleurs qu'où elle se voit est pire que
des droites. Le fil provisoire du glisser suit la même courbe.

Les deux natures restent distinctes comme aujourd'hui (`geom` / `param`) —
on change la forme, pas le code couleur.

### 3. Icônes dans les nœuds

Chaque nœud porte l'icône que sa ligne porte déjà dans l'arbre :
`TREE_ICONS[type]` pour les fonctions, et les icônes déjà utilisées pour
les autres natures — `Sketcher_Sketch.svg`, `Std_Plane.svg`,
`Part_3D_object.svg`, `VarSet.svg`, `PartDesign_Body.svg`.

**Ne pas tenir une seconde table** : réutiliser `TREE_ICONS`, et compléter
cette table-là si un type manque.

Attention au détail technique : `treeIcon()` fabrique un `<img>` HTML,
inutilisable tel quel dans du SVG. Un nœud SVG a besoin d'un
`<image href="icons/…">`. Écrire le petit équivalent SVG à côté de
`treeIcon`, pas une réécriture de l'existant.

Le libellé doit rester lisible : tronquer avec une ellipse plutôt que de
déborder du rectangle, et exposer le libellé complet en infobulle.

### 4. Ce qui doit continuer de marcher

Aucun comportement du N002 ni du N003 ne change. Après ce prompt :

- panoramique, zoom, survol qui éclaire les arêtes incidentes ;
- clic = sélection du FeatureManager, double-clic = édition, clic droit =
  `openMenu` ;
- fil variable → fonction, sélecteur de cote, coupure qui fige la valeur ;
- cibles valides distinguées **avant** le relâchement ;
- arêtes `geom` visiblement non tirables.

Le smoke existant couvre ces gestes : **il doit passer sans être modifié.**
S'il faut le retoucher, c'est qu'un comportement a bougé — et ce n'est pas
le sujet de ce prompt.

## Ce qu'il ne faut pas faire

- **Ne pas changer de bibliothèque de rendu.** Ni React Flow, ni
  litegraph, ni rete : les unes imposent React et un bundler que le projet
  n'a pas, les autres passent au canvas et feraient perdre l'intégration
  SVG/CSS, la sélection et le thème. Aucune ne fait la mise en page, qui est
  le vrai problème.
- Ne pas déplacer les nœuds à la souris : la position n'a toujours nulle
  part où être persistée.
- Ne pas toucher `engine/`, ni `app/vendor/`.
- Ne pas ajouter d'appel réseau au rendu.

## Validation avant de pousser

```bash
python3 -m pytest -q
node --check app/graph.js && node --check app/main.js
node --test tests/js/*.test.mjs
```

Tests à ajouter dans `tests/js/graph.test.mjs` :

- **moins de croisements** qu'avant sur un cas construit pour se croiser —
  compter les paires d'arêtes qui se coupent, et vérifier que le nombre
  baisse par rapport au tri par `order` seul ;
- déterminisme conservé ;
- si dagre est retenu, que le module s'importe bien sous `node --test`.

Smoke navigateur : inchangé, et il doit passer tel quel.

Plateforme de référence : **FreeCAD 1.1.3** (`AGENTS.md`).

## Commit

Un commit (ou une petite série cohérente), message en français, préfixé
`[N003b]`, **indiquant la voie retenue au point 1** (dagre ou barycentre
maison) et pourquoi.
