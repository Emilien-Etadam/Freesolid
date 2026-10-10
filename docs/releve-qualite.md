# Relevé qualité — cap « mini-SolidWorks propre »

Relevé du 2026-10-10, après le lot `clone-sw` (PR #89). Le cap : un modeleur
de pièces propre, avec une belle interface, avant toute fonction spécialisée.
Ne sont pas visés pour l'instant : la tôlerie, les assemblages poussés et la
mise en plan poussée.

Méthode :
- l'application regardée dans le navigateur intégré, en 1920 × 1080 et en
  1366 × 768 (écran de portable courant), en mode pièce, en esquisse et avec
  des panneaux ouverts ;
- un survol de tout le code (tailles, styles, icônes, doublons, tests) ;
- des scénarios d'erreur du flux pièce, envoyés directement au moteur.

Priorités : **P1** gêne tout le monde à chaque séance, **P2** se voit vite,
**P3** finition.

---

## 1. Interface

### 1.1 L'en-tête mange l'écran — P1

| Écran | Hauteur de l'en-tête | Part de l'écran | Zone graphique |
|---|---|---|---|
| 1920 × 1080 | 255 px | 24 % | 1660 × 799 |
| 1366 × 768 | 365 px | 48 % | 1106 × 377 (40 % de l'écran) |

L'en-tête empile trois bandeaux :
- la barre de menus (29 px) ;
- la barre du haut (37 px), avec la recherche de commandes sur une ligne à
  elle seule dès 1366 px ;
- le ruban : 189 px en 1920, davantage en 1366. Ses groupes passent sur deux
  ou trois lignes, parce que le groupe Modélisation fait à lui seul 1167 px de
  large (chaque bouton porte son libellé à droite de l'icône).

La barre du haut **répète** aussi ce que d'autres endroits offrent déjà :
- les menus : Nouveau, Ouvrir, Enregistrer, Exporter, Annuler, Rétablir ;
- l'onglet Évaluer : Mesurer, Équations, Évaluer.

**Piste.** Un en-tête de 130 px au plus en 1366 :
- un ruban compact sur une ligne, avec l'icône au-dessus d'un libellé court ;
- les boutons secondaires plus petits, et ce qui ne tient pas dans un
  débordement « » ;
- les onglets, l'accès rapide (annuler, rétablir, enregistrer) et la recherche
  sur une seule ligne.

### 1.2 Icônes hétérogènes — P1

Sur 135 icônes :
- 79 viennent de FreeCAD : multicolores, au style ancien, qui jurent sur fond
  sombre ;
- 51 viennent de Nodes ;
- 5 seulement sont originales.

Plusieurs boutons n'ont que du texte : Accueil, Mesurer, Sélectionner,
Décaler, Image, Interférences, Résoudre, Éclater, Déplacer. Des glyphes
servent d'icônes (📌 × ✓ ✗), et la boîte d'orientation est entièrement en
texte.

**Piste.** Un jeu d'icônes original et cohérent : monochrome, trait de
1,5 px, couleur du texte, plus l'accent pour l'élément actif. On commencerait
par les onglets Fonctions et Esquisse, puis on étendrait au reste.

### 1.3 Système visuel — P2

- Seulement 8 variables CSS. On compte 55 couleurs en dur dans le CSS
  (14 hex distincts, dont `#6fbf8f` 13 fois et `#4f8fdb`, qui double
  `--accent`), plus 41 couleurs en dur dans la scène 3D côté JS.
- `--warn` est utilisé mais jamais défini.
- On trouve 9 tailles de police, 8 rayons d'angle et 47 marges intérieures
  différentes.
- Il n'y a pas de thème clair.

**Piste.** Des jetons de couleurs, d'espacements (4 / 8 / 12 / 16), de rayons
(4 / 6 / 8) et de tailles de texte (11 / 12 / 13 / 16), que tout le CSS et la
scène 3D utilisent. Le thème clair viendrait ensuite (P3).

### 1.4 Rendu 3D — P2

- La pièce est d'un gris plat, avec peu de relief et des arêtes peu marquées.
- Le fond est très sombre et uni, et la grille domine la scène.

**Piste.** Un éclairage plus doux (ambiance et deux lumières orientées), un
matériau légèrement satiné, des arêtes fines et nettes, un fond en léger
dégradé et une grille qui s'estompe au loin. Survol et sélection garderaient
des couleurs cohérentes avec les jetons.

### 1.5 Panneaux, volets, menus — P2

- Quand un panneau s'ouvre, le volet d'arbre flottant recouvre environ 200 px
  de la vue en 1366.
- Les messages d'aide ressemblent à des erreurs (« Congé : cliquez d'abord
  dans la zone graphique ») et répètent l'indication de la zone de sélection.
- Le menu contextuel compte 18 entrées, sans icônes, et déborde sur le ruban.
- En esquisse sur une face, cette face reste surlignée en orange (la couleur
  de sélection). La barre d'état garde aussi « Face 5 · sél. Face 5 ».

### 1.6 Accueil — P3

La boîte est petite et sobre, sans aperçu des fichiers récents.

---

## 2. Fiabilité du flux pièce

| Constat | Prio |
|---|---|
| Un congé ou un chanfrein trop grand renvoie l'erreur brute du noyau : « BRep_API: command not done ». | P1 |
| Les messages expliqués (`engine/guard.py`) citent **SolidWorks** dans le texte affiché (règle clean-room), et ils ne sont pas traduits en anglais. | P1 |
| Une coque de 30 mm sur une plaque de 12 mm est acceptée sans message. | P2 |
| Le premier trait juste après « Esquisse sur cette face » s'est posé au mauvais endroit (vu une fois, à reproduire). | P2 |
| Un clic droit sans mouvement de souris préalable ouvre le menu de la vue au lieu de celui de la face : le menu lit l'état de survol, pas le point cliqué. | P3 |
| Une fonction refusée consomme quand même un numéro (« Congé001 »). | P3 |

---

## 3. Code

- `app/main.js` fait 6727 lignes, avec 233 fonctions et 89 variables globales
  modifiables. Découpage proposé, sans changer le comportement :
  - `graphview.js` (1600 lignes) ;
  - `tree.js` (1350) ;
  - `picking.js` (870) ;
  - `viewport.js` (900, plans compris) ;
  - `viewcube.js` (300) ;
  - `assembly.js` (500) ;
  - `measure.js` (350) ;
  - `contextmenu.js` (190).
- `engine/kernel.py` fait 8691 lignes : une seule classe de 252 méthodes, dont
  environ 2380 lignes de selftest dans le code de production. Plusieurs
  bannières de section ne correspondent plus à leur contenu. Découpage
  proposé : des modules par thème, réunis dans la classe :
  - assemblage, surfaces, mise en plan, texte, fonctions graphe ;
  - fonctions volumiques, paramètres, fichiers ;
  - tessellation et arbre, esquisse ;
  - le selftest dans son propre module.
- Doublons :
  - la projection à l'écran, 5 fois ;
  - le passage du pointeur aux coordonnées normalisées, 3 fois ;
  - le formatage en mm, 3 fois ;
  - la lecture des nombres « 6,5 », refaite dans `dims.js` et `features.js`
    alors que `num.js` existe.
- Petites bavures :
  - environ 25 exports que personne n'importe ;
  - un `console.log` oublié dans `main.js` ;
  - 5 icônes jamais utilisées.
- Ni `main.js` ni `sketch.js` n'ont de test propre.

---

## 4. Lot proposé

| # | Chantier | Prio | Qui |
|---|---|---|---|
| Q1 | Messages d'erreur : textes clean-room, traduction anglaise, erreurs du noyau (congé ou chanfrein trop grand…) en phrases claires | P1 | Cursor |
| Q2 | Petites bavures : `console.log`, exports et icônes inutilisés, `--warn`, aides en double (mm, projection, nombres) | P2 | Cursor |
| Q3 | Jetons de style : couleurs, espacements, rayons, tailles de texte, côté CSS et côté scène 3D | P2 | Cursor |
| Q4 | Découpage de `main.js` en modules, à comportement identique | P2 | Claude |
| Q5 | Découpage de `kernel.py`, selftest sorti du code de production | P2 | Cursor, après Q4 |
| Q6 | En-tête compact (≤ 130 px en 1366) | P1 | Claude, sur maquette validée |
| Q7 | Jeu d'icônes original | P1 | Claude dessine un échantillon à valider, Cursor décline le reste |
| Q8 | Rendu 3D | P2 | Claude |
| Q9 | Panneaux, volet d'arbre, menu contextuel, face d'esquisse | P2 | Claude et Cursor |
| Q10 | Bugs : premier trait en esquisse sur face, clic droit sans survol, coque trop épaisse | P2 | Claude |
| Q11 | Thème clair | P3 | plus tard |

Q1 à Q3 n'engagent aucune décision de design : Cursor peut les prendre tout
de suite. Q6 et Q7 attendent une maquette et un échantillon validés.

## Suivi

| # | État |
|---|---|
| Q1 | confié à Cursor |
| Q2 | confié à Cursor |
| Q3 | confié à Cursor |
| Q4 à Q11 | en attente de validation |
