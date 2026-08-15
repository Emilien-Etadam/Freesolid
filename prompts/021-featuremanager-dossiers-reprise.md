# P021 — FeatureManager : dossiers en tête + barre de reprise en glisser-déposer

Deux demandes utilisateur sur l'arbre de création.

## 1. Dossiers en tête d'arbre, comme SolidWorks

En haut du FeatureManager, avant les plans, trois dossiers repliables avec
compteur, dans cet ordre :

- **Corps volumiques (N)** : la liste des corps actuelle (corps actif en
  gras, corps inactifs cliquables pour activer, pastille couleur, menu
  contextuel) déménage dans ce dossier — comportements strictement
  inchangés, seul l'emplacement change.
- **Corps surfaciques (N)** : la section surfaces existante (clic =
  sélection, double-clic = modifier, clic droit = menu) déménage ici —
  comportements inchangés.
- **Équations (N)** : les variables globales (`list_variables`). Chaque
  ligne affiche `nom = valeur`. Double-clic sur le dossier ou une ligne :
  ouvre le dialogue Équations existant (`btn-equations`). N = nombre de
  variables. Ne pas dupliquer la logique d'édition — le dossier est une
  vitrine, le dialogue reste l'éditeur.

Règles :

- Repli/dépli par flèche `▸`/`▾` comme les fonctions, état mémorisé en
  mémoire de session (pas localStorage) ; par défaut : dossiers repliés
  sauf s'ils contiennent une erreur ou que la pièce est multi-corps.
- Un dossier vide s'affiche grisé avec « (0) » — comme SolidWorks, il ne
  disparaît pas.
- `list_variables` ne doit être appelé que lors d'un rafraîchissement
  d'arbre déjà en cours (pas d'appel réseau supplémentaire par frame) :
  l'idéal est d'inclure les variables dans `get_tree` côté moteur
  (`tree["variables"] = [{name, value}]`, calculé dans le même appel) et
  de faire lire ce champ par le client. Mettre à jour le selftest :
  l'étape p7 existante gagne un indicateur `p7_tree_variables` (la
  variable créée apparaît dans l'arbre).

## 2. Barre de reprise en glisser-déposer

La barre « ▲ barre de retour arrière ▲ » se déplace aujourd'hui par menu
contextuel (« barre de retour ») et double-clic (retour à la fin). Ajouter
le geste SolidWorks : la tirer à la souris.

- **Drag** : pointerdown sur la barre → suivre le pointeur ; pendant le
  drag, un indicateur d'insertion (ligne accent) se dessine entre les
  fonctions au-dessus/au-dessous de la position du curseur ; la liste des
  positions valides = entre deux fonctions du corps actif, avant la
  première, après la dernière.
- **Drop** : relâcher → `set_tip` sur la fonction juste au-dessus de la
  position choisie (ou `tip_to_end` si après la dernière). Un drop sans
  déplacement = aucun appel.
- **Rendu** : les fonctions situées après la barre (hors historique
  actif) s'affichent grisées + icône estompée, comme SolidWorks. C'est
  peut-être déjà partiellement le cas — harmoniser.
- Événements pointeur natifs (`pointerdown`/`move`/`up` + capture), pas
  d'API HTML5 drag-and-drop (curseur et indicateur mieux contrôlés, même
  approche que les drags du viewport).
- Conserver le double-clic et le menu contextuel existants.

## Validation

- `python3 -m pytest tests/ -q`, `node --check` sur chaque JS modifié.
- Selftest si FreeCAD disponible (nouvel indicateur `p7_tree_variables`),
  sinon le signaler dans le commit.
- Scénario navigateur (`scripts/smoke/`) : après le bossage, tirer la
  barre de reprise au-dessus du bossage (le solide disparaît), la
  redescendre (il revient), zéro erreur console. Étendre le smoke
  existant sans casser les étapes actuelles.
- Commit(s) préfixés `[P021]`. Ne pas toucher `app/vendor/`. Français,
  vocabulaire SolidWorks 2025.
