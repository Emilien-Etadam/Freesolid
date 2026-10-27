# Paramètres

Le panneau Paramètres (l'engrenage, Outils > Paramètres, Aide > À propos)
est rangé comme les options des modeleurs courants : des onglets, l'arbre
des pages à gauche, la page choisie à droite.

- **Options du système** : gardées par le navigateur (`localStorage`),
  elles valent pour tous les documents.
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

Plusieurs de ces réglages ont aussi un bouton ailleurs (la barre de vue,
la barre d'esquisse, le menu Affichage) : bouton et panneau changent le
même réglage.

## Ajouter une option

Un champ se décrit dans `settingsFields()` (`app/settings.js`) : sa page,
son cadre (`group`), sa sorte (`check`, `radio`, `select`, `number`), son
libellé, sa valeur par défaut, et le réglage qu'il lit et écrit (`store`,
`get`, `set`). Le réglage lui-même est passé par `main.js` dans `stores`
(`{ read, apply }`). L'arbre, la recherche, Réinitialiser et OK s'en
servent sans autre code. Chaque libellé, cadre, note et choix reçoit son
entrée dans `app/lang/en.json` : `tests/js/settings.test.mjs` le vérifie.
