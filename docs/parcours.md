# Parcours de pièces réelles

Chaque pièce est construite entièrement à la souris, dans l'interface,
en 1366 × 768. Chaque accroc est noté puis corrigé, ou laissé avec une
raison. Branche `parcours`.

## 1. Équerre percée

Profil en L sur le Plan de face (60 × 40, épaisseur 8), extrusion de
40 mm, deux trous de 6 mm dans l'aile, congé de 5 mm à l'angle intérieur.

| # | Accroc | Suite |
|---|---|---|
| 1 | « Nouvelle pièce » remplace la pièce en cours sans rien demander, modifications perdues. | **Corrigé** : nouveau, ouvrir, nouvel assemblage et récents demandent confirmation si le document a changé depuis son enregistrement (`document_status`). |
| 2 | Le premier clic sur l'origine ne s'y accroche pas : le profil flotte (2 degrés de liberté de trop). | **Corrigé** : l'origine est un point d'accrochage, et le moteur pose une coïncidence avec le point racine (lignes, arcs, centres de cercle). |
| 3 | Panneau Extrusion : le focus va sur la liste « Borgne », pas sur la profondeur. | **Corrigé** : focus sur la première valeur à taper. |
| 4 | Perçage : la face choisie est ignorée ; il faut d'abord une esquisse de cercles. | **Corrigé** : ligne « Positions », chaque clic sur la face pose un centre ; le moteur crée l'esquisse et le perçage d'un coup. |
| 5 | La barre d'icônes contextuelle reste par-dessus quand une commande s'ouvre. | **Corrigé**. |
| 6 | Le message d'un aperçu raté reste après un aperçu réussi. | **Corrigé**. |
| 7 | Le focus sur une valeur ne la sélectionne pas : « 5 » tapé sur « 3 » donne 35. | **Corrigé** : la valeur est sélectionnée. |
| 8 | Une fonction refusée par le moteur ferme le panneau : la saisie est perdue. | **Corrigé** : le panneau revient avec les valeurs saisies. |
| 9 | Barre d'état sur deux lignes avec un message long. | **Corrigé** : une ligne, texte abrégé, entier au survol. |
| 10 | Le message garde « (BRep_API: command not done) ». | **Corrigé** : ce générique du modeleur n'est plus recopié. |
| 11 | Après un refus puis une réussite, l'erreur rouge reste affichée. | **Corrigé** : une opération réussie l'efface. |
| — | Deux onglets sur le même serveur partagent le même document. | Voulu (un document par processus) ; à afficher un jour. |
| — | Les symboles de relations (H, V) se chevauchent sur deux segments proches. | À reprendre (finition). |
| — | Entrée applique la valeur puis une seconde Entrée valide. | Voulu : on voit l'aperçu avant de valider. |

## 2. Boîtier

Rectangle par le centre 100 × 60 sur le Plan de dessus, coté ; extrusion
de 40 mm ; congés de 8 mm sur les quatre arêtes verticales ; coque de
2 mm ouverte sur le dessus ; chanfrein de 1 mm sur le bord extérieur.

| # | Accroc | Suite |
|---|---|---|
| 12 | Le rectangle par le centre n'est pas tenu par son centre (4 degrés de liberté au lieu de 2), et il coûte quatre Ctrl+Z (un par côté). | **Corrigé** : `sketch_add_rectangle`, une seule opération ; centré sur l'origine, ses coins y restent symétriques (selftest p42). |
| 13 | La barre d'icônes contextuelle passe par-dessus la boîte d'orientation. | **Corrigé**. |
| 14 | Après une reconstruction, la barre d'état cite encore « sél. 4 arête(s) ». | **Corrigé**. |
| 15 | Pendant l'aperçu de la coque, la face choisie reste orange et cache l'ouverture. | **Corrigé** : la face choisie s'estompe avec la pièce. |
| 16 | Juste après l'ouverture d'un panneau, Entrée ne valide pas : le premier aperçu marquait le champ comme modifié (tous les panneaux). | **Corrigé**. |
| — | La cote verticale recouvre le symbole « V » du côté coté. | À reprendre (finition, avec le chevauchement des symboles). |
| — | Les flèches gauche/droite tournent autour de l'axe vertical de l'écran : douze appuis montrent la pièce par-dessous. Une rotation autour de l'axe Z de la pièce serait plus naturelle. | À discuter. |
| — | Sélectionner une arête cachée oblige à tourner la vue (pas de vue isométrique arrière dans la boîte d'orientation). | À discuter : vues isométriques des quatre coins. |
| ✓ | Le chanfrein d'une arête suit toute la chaîne tangente (côtés et arrondis). | Bon comportement. |

## 3. Arbre étagé

Demi-profil sur le Plan de face (Ø 24 sur 30 mm, Ø 16 sur 40 mm), révolution
autour de l'axe vertical de l'esquisse ; gorge de circlip par un rectangle
de 2 × 1,5 mm et un enlèvement par révolution ; chanfrein de 1 mm au bout.

| # | Accroc | Suite |
|---|---|---|
| 17 | Esquisse sur un plan qui traverse la pièce : le solide cache les traits (ils étaient « devant », mais la pièce, transparente pour l'aperçu, était dessinée après). | **Corrigé** : les traits, cotes et points d'esquisse passent dans la même passe, devant la pièce. |
| 18 | Un trait vertical traverse chaque cylindre : la couture interne du noyau, tracée comme une arête. | **Corrigé** : les arêtes de couture ne sont plus tracées (selftest p43) ; les ids des autres restent ceux du noyau. |
| 19 | Titre de panneau coupé (« Enlèvement par r… »). | **Corrigé** : il passe sur deux lignes. |
| — | Sur une petite entité, les symboles H/V recouvrent tout le tracé. | À reprendre, avec les autres chevauchements de symboles. |
| — | Après la première fonction, la vue n'est pas recadrée sur la pièce (F le fait). | À discuter : cadrer automatiquement après la première fonction. |
| — | Positionner exactement un profil (la gorge) demande de le coter ; pas de cote entre un point et l'origine testée ici. | À vérifier au prochain parcours. |

## 4. Bride

Disque Ø80 × 12 sur le Plan de dessus, moyeu Ø40 jusqu'à 32 mm, alésage
Ø20 débouchant, un trou Ø8 sur un cercle de perçage de 60 répété six fois
autour de l'axe Z, puis une nervure triangulaire (16 × 16, épaisseur 6,
plan milieu) sur le Plan de face et sa symétrique par le Plan de droite.

| # | Accroc | Suite |
|---|---|---|
| 20 | Perçage : un clic au centre du moyeu pose le trou à 2 mm du centre ; rien n'aimante la position. | **Corrigé** : le moteur envoie le centre exact des arêtes circulaires ; un clic de position s'y aimante (et aux sommets) à moins de 12 px, dans le plan de la face (selftest p43). |
| 21 | L'outil Cotation ignore l'origine : cercle puis origine donne un Ø, pas la distance. | **Corrigé** : l'origine se sélectionne et se cote ; un cercle coté contre un point se prend par son centre. |
| 22 | Pas de relation horizontale / verticale entre deux points (centre de trou et origine). | **Corrigé** : proposée dès que deux points sont sélectionnés, origine comprise. |
| 23 | Seules les cotes alignées existent : impossible de placer un sommet à 20 mm en X et 12 mm en Y de l'origine. | **Corrigé** : entre deux points, un 3e clic pose la cote, avec aperçu ; à côté : verticale, dessus ou dessous : horizontale, entre : alignée (selftest p44). |
| 24 | Les cotes s'empilent au même endroit et cachent la pièce ; elles ne restent pas où on les pose. | **Corrigé** : le clic de pose devient le décalage de la ligne de cote, gardé par la pièce et sauvé avec elle. |
| 25 | Répétition ou symétrie après avoir cliqué une fonction dans l'arbre : la case « Fonctions à répéter » reste vide. | **Corrigé** : la fonction présélectionnée remplit la case (répétitions, symétrie, réseau variable) ; à 3 fonctions et plus, la case dit « fonctions », plus « profils ». |
| — | La barre d'icônes de la face restait au milieu d'une esquisse ouverte et prenait les clics. | **Corrigé** sur `qualite` (smoke de la PR #90). |
| — | L'esquisse d'un perçage reste « sous-contrainte » : son rayon, piloté par le diamètre du perçage, n'est pas coté. | À reprendre. |
| — | Une cote déjà posée ne se déplace pas encore à la souris. | À faire. |
| — | Traits d'esquisse définis (clairs) peu contrastés sur une face claire. | À reprendre (thème). |
