# P022 — Esquisse robuste : fin de tracé propre, contour ouvert annoncé

## Contexte — bug utilisateur reproduit (ne pas re-diagnostiquer)

Geste réel : tracer une ligne, finir le tracé par **double-clic**. Le
deuxième clic du double-clic ajoute un segment de **longueur nulle**
(sonde : `line (17.8,-15.1)->(17.8,-15.1)` — points identiques). Ce
segment dégénéré fait ensuite boucler le solveur à chaque recompute :
« Error build geometry: Both points are equal », « Invalid solution from
DogLeg/LevenbergMarquardt/BFGS/SQP », « Solving the sketch failed » — en
cascade dans la console serveur.

Second constat : Terminer une esquisse au contour ouvert ne dit rien
(« À jour. »). Le message clair n'arrive qu'au bossage. L'utilisateur
s'attend à être prévenu au moment de Terminer.

## Mission

### 1. Client — `app/sketch.js` : plus de segments de longueur nulle

- Outil **ligne** (tracé en chaîne) : un clic à moins du seuil de snap
  (`SNAP_PX`) du dernier point posé n'ajoute **pas** de segment — il
  termine la chaîne, exactement comme Échap. Le double-clic est ainsi
  couvert par construction (son 2e clic tombe sur le point précédent).
- Vérifier les autres outils en chaîne (spline notamment) : même garde —
  deux points consécutifs identiques ne créent pas d'entité ni de point
  de passage doublé.
- Aucun changement pour un clic légitimement proche mais au-delà du
  seuil : on ne veut pas empêcher les petits segments voulus.

### 2. Moteur — `engine/kernel.py` : défense en profondeur

- `sketch_add_line` : si les deux extrémités coïncident (distance
  < 1e-7 mm), lever `KernelError("segment de longueur nulle — les deux "
  "points coïncident")` au lieu de créer l'entité.
- `sketch_add_spline` : refuser de même deux points de contrôle
  consécutifs identiques (message analogue).
- Ces gardes protègent aussi l'API directe (curl, scripts).

### 3. Terminer une esquisse au contour ouvert : le dire

- `sketch_finish` (moteur) : après la fermeture, déterminer si la
  géométrie **non-construction** forme au moins une boucle fermée
  (réutiliser la même logique de détection que le message existant du
  bossage — `Part.sortEdges` ou équivalent déjà en place). Ajouter au
  retour de `sketch_finish` un champ `open_profile: true|false`.
- Client : si `open_profile` est vrai, la barre de statut affiche —
  information, pas blocage :
  « Esquisse fermée — contour ouvert : utilisable comme trajectoire ou
  surface, pas comme profil de bossage. »
  Une esquisse ouverte reste légitime (trajectoire de balayage, surface
  extrudée) : ne rien interdire, informer.
- Esquisse vide ou 100 % construction : pas de message (rien d'anormal).

### 4. Tests

- Selftest : dans une étape existante (p3 par exemple), deux indicateurs :
  `p3_zero_line_refused` (sketch_add_line dégénérée → KernelError, aucune
  entité ajoutée) et `p3_open_profile_flag` (`sketch_finish` d'une
  esquisse à une seule ligne renvoie `open_profile: true`, celui d'un
  rectangle renvoie `false`).
- `scripts/smoke/smoke.js` : après le rectangle existant, un pas court :
  outil ligne, deux clics puis **double-clic sur le second point**,
  vérifier par `sketch_state` qu'il n'existe **aucune** entité de
  longueur nulle (comparer p1/p2 de chaque ligne), puis supprimer la
  ligne ajoutée (ou Ctrl+Z) pour ne pas perturber les pas suivants.
- `tests/js` : si la garde client est factorisable en fonction pure
  (points → ajouter ou terminer), la tester ; sinon la couverture vit
  dans le smoke.

## Contraintes

- Ne pas toucher `app/vendor/`.
- Textes utilisateur en français, vocabulaire SolidWorks 2025.
- `python3 -m pytest tests/ -q`, `node --check` sur chaque JS modifié,
  selftest complet si FreeCAD disponible (sinon le signaler).
- Commit(s) préfixés `[P022]`.
