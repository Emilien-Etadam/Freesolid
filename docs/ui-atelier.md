# Interface « Atelier »

La maquette validée le 2026-10-15 (canevas « Maquette FreeSolid — style
atelier ») fixe la cible : une interface claire et dense dans l'esprit des
modeleurs paramétriques de bureau, sans en copier ni les dessins, ni les
noms, ni les textes. Les icônes restent celles de FreeCAD et de Nodes, les
brouillons `fs_*` bouchant les trous (`docs/icones-a-dessiner.md`).

## Jetons

| Rôle | Clair (défaut) | Note |
|---|---|---|
| Châssis | `#E9EDF1` | fond de la fenêtre |
| Barre de commandes | `#EEF1F4` | |
| Volet (arbre, panneaux) | `#F4F6F8` | |
| Surface (champs) | `#FFFFFF` | |
| Trait | `#C9D1DA` | |
| Encre / secondaire | `#1D2733` / `#5A6573` | |
| Accent / pâle | `#1F6FB2` / `#D6E6F6` | choix, onglet actif, barre de retour |
| Sélection 3D | `#E8892B` | orange, comme aujourd'hui |
| Aperçu | `#F2C94C` | jaune, comme aujourd'hui |
| Valider / annuler | `#2E8B57` / `#C8372D` | |
| Fond de vue | `#FBFCFE` → `#C7D1DC` | dégradé vertical |

Police : IBM Plex Sans pour l'interface, IBM Plex Mono pour les valeurs
(repli : Segoe UI, system-ui ; Consolas, monospace). Le thème sombre reste
au choix dans les paramètres, mêmes jetons.

## Lots, du plus simple au plus complexe

| # | Lot | État |
|---|---|---|
| 1 | Thème Atelier clair par défaut : jetons, police, fond de vue | fait — le sombre reste dans les paramètres ; un choix « sombre » déjà enregistré est gardé |
| 2 | Barre de commandes : onglets sous les boutons, légende sous chaque groupe, grandes icônes | fait |
| 3 | Barre de vue en pilule au centre de la vue, coin de validation en haut à droite | fait |
| 4 | Fil d'Ariane de la sélection en haut à gauche de la vue (pièce › fonction › esquisse › face) | fait — clic : choisir dans l'arbre, double-clic : modifier ; sous la barre de vue |
| 5 | Gestionnaire à onglets : arbre, propriétés, configurations, affichage | fait — Propriétés s’allume à l’ouverture d’une commande ; Arbre remontre l’arbre pendant la commande ; Configurations (activer, ajouter, tableau) ; Affichage (style, corps à masquer) |
| 6 | Arbre volant dans la vue quand un panneau remplace l'arbre | existait déjà (`#tree-flyout`) |
| 7 | Cube d'orientation cliquable en haut à droite, trièdre en bas à gauche | à faire |
| 8 | Volet de ressources replié à droite (matériaux, gabarits, aide) | à faire |
| 9 | Police IBM Plex embarquée (fichiers de police OFL dans l'application) | à faire |
