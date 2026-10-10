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
