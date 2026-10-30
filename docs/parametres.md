# Paramètres

Le panneau Paramètres (l'engrenage, Outils > Paramètres, Aide > À propos)
est rangé comme les options des modeleurs courants : des onglets, l'arbre
des pages à gauche, la page choisie à droite.

- **Options du système** : gardées par le navigateur (`localStorage`),
  elles valent pour tous les documents.
- **Propriétés du document** : gardées dans le fichier ouvert (une
  propriété cachée `FreeSolidOptions` du `.FCStd`, en JSON), elles le
  suivent d'une machine à l'autre. Sans document ouvert, l'onglet est
  grisé. Elles ne passent pas par l'historique d'annulation, comme les
  propriétés du fichier.
- **Recherche** : en haut à droite. Elle ignore la casse et les accents,
  cherche tous les mots dans le libellé d'une option, son cadre, ses choix
  et le nom des pages, dans la langue affichée. L'arbre ne garde que les
  pages qui répondent (et leur parent) ; les options trouvées sont
  surlignées, la première est amenée dans la vue.
- **OK** applique les changements ; **Annuler**, Échap ou × les oublient.
  La langue et le thème rechargent la page à la validation.
- **Réinitialiser…** remet les valeurs par défaut de la page, ou de tout
  l'onglet, dans les champs ; OK les applique.

## Les pages

| Page | Options | Gardé dans |
|---|---|---|
| Général | langue, libellés du ruban ; lien vers les raccourcis clavier | `freesolid.lang`, `freesolid.ribbonLabels` |
| Couleurs | thème (clair, sombre, selon le système) | `freesolid.theme` |
| Esquisse | vue tournée face au plan à l'ouverture ; symboles de relation, cotes, peigne de courbure | `freesolid.sketchPrefs` |
| Esquisse > Relations et accrochages | accrocher pendant le tracé, chaque sorte d'accrochage, valeur du pas d'angle, accrocher à la grille | `freesolid.sketchSnaps`, `freesolid.sketchPrefs` |
| Affichage | style d'affichage, perspective ; plans, origine, esquisses, aperçu des arêtes | `freesolid.display` |
| Sélection | ce que le clic peut viser (le filtre de sélection) | `freesolid.selectFilter` |
| Arbre de création | arbre à plat | `freesolid.flatTree` |
| Vue | sens du zoom de la molette, zoom vers le curseur | `freesolid.reverseWheel`, `freesolid.zoomToCursor` |
| À propos | versions de FreeSolid et du moteur, liens, mises à jour | — |

Onglet **Propriétés du document** (ops `document_options`,
`set_document_options` ; `engine/docoptions.py`) :

| Page | Options | Clé |
|---|---|---|
| Unités | décimales des longueurs (0 à 6) et des angles (0 à 4), dans les cotes et les lectures ; les unités restent le millimètre, le gramme et la seconde | `length_decimals`, `angle_decimals` |
| Grille | pas de grille fixe en esquisse (0,01 à 1 000 mm), celui de l'accrochage à la grille et des longueurs rondes avec Maj ; sans lui, le pas suit le zoom | `grid_fixed`, `grid_step` |
| Qualité d'image | finesse des facettes affichées : grossière, normale, fine, très fine (écart de corde 0,5 / 0,1 / 0,05 / 0,02 mm et angle entre facettes 0,5 / 0,1 / 0,07 / 0,05 rad ; les arêtes, la moitié de l'écart) | `quality` |

L'arbre (`get_tree`, `assembly_tree`) renvoie ces propriétés dans
`options` ; `tessellate`, `tessellate_edges` et `tessellate_assembly`
prennent la qualité du document quand on ne leur donne pas d'écart.
Sur une courbure ordinaire, c'est l'angle qui fixe le nombre de facettes :
`face.tessellate` ne le règle pas (il prend 0,1 rad). La qualité normale
reste donc celle du noyau, maillage gardé en cache dans la pièce ; les
autres maillent une copie sans maillage (`shape.copy(True, False)`, faces
dans le même ordre) avec `MeshPart.meshFromShape`, à leur écart et leur
angle. Mailler la pièce elle-même ne marcherait pas dans les deux sens :
OCCT y garde le maillage le plus fin déjà calculé.

Plusieurs de ces réglages ont aussi un bouton ailleurs (la barre de vue,
la barre d'esquisse, le menu Affichage) : bouton et panneau changent le
même réglage.

## Ajouter une option

Un champ se décrit dans `settingsFields()` (`app/settings.js`) : sa page,
son cadre (`group`), sa sorte (`check`, `radio`, `select`, `number`), son
libellé, sa valeur par défaut, et le réglage qu'il lit et écrit (`store`,
`get`, `set`). Le réglage lui-même est passé par `main.js` dans `stores`
(`{ read, apply }`). L'arbre, la recherche, Réinitialiser et OK s'en
servent sans autre code. Une propriété du document s'ajoute aussi dans
`DEFAULTS` (et ses bornes dans `_RANGES`) de `engine/docoptions.py` : le
test JS compare les valeurs par défaut des deux côtés. Chaque libellé, cadre, note et choix reçoit son
entrée dans `app/lang/en.json` : `tests/js/settings.test.mjs` le vérifie.
