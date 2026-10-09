# Tâches pour Cursor — lot « clone-sw »

Ces tâches viennent du relevé [`ecarts-solidworks.md`](ecarts-solidworks.md).
Elles ont été choisies parce qu'elles sont bien délimitées : une ou deux
zones de code, sans décision de conception ouverte. Les écarts plus lourds
(cotation, menu contextuel, contraintes d'assemblage, conditions
d'extrusion…) sont traités ailleurs.

## Règles communes — à lire avant chaque tâche

- **Dossier et branche** : travailler **dans `D:\Dev\Freesolid-cursor`**
  (worktree git du même dépôt), sur la branche `cursor/clone-sw`. Ne jamais
  modifier `D:\Dev\Freesolid` ni changer de branche là-bas : Claude y
  travaille en parallèle sur `clone-sw`. Faire **un commit par tâche**, dont
  le message (en français) dit ce qui change pour l'utilisateur. Claude
  fusionne ensuite `cursor/clone-sw` dans `clone-sw`.
- **Serveur de test** : le port 8787 peut être pris par l'application de
  bureau et le 8797 par Claude. Lancer le moteur avec un autre port :
  `FREESOLID_PORT=8798`.
- **Clean-room** : on reproduit un comportement, jamais un texte, une icône,
  un nom ou un logo de Dassault. Les descriptions ci-dessous sont déjà
  reformulées. Une icône nouvelle est un dessin original `app/icons/FreeSolid_*.svg`
  (voir `app/icons/README.md`). Ne pas réutiliser les libellés anglais exacts
  de SolidWorks : écrire un anglais générique de CAO.
- **Deux langues** : le français est la langue source. Tout texte visible
  passe par `t("…")` (`app/i18n.js`) ou par un puits qui le fait déjà
  (`say()`, `panel.open()`, `el()`, `prompt()`/`confirm()` de `main.js`,
  `translateDom()`). Un texte avec variable s'écrit
  `t("Arête {n}", { n })`, **jamais** en gabarit `` `Arête ${n}` ``. Chaque
  nouveau texte reçoit son entrée dans `app/lang/en.json` ; chaque texte du
  moteur, dans `engine/lang/en.json` (gabarit `{}`), via `self._t(...)`.
  Vérifier l'écran en anglais : `localStorage.setItem("freesolid.lang","en")`
  puis recharger.
- **Vérifications** (voir `AGENTS.md`) :
  - `python3 -m compileall -q engine` puis `python3 -m pytest -q`
  - `node --test tests/js/*.test.mjs`
  - si le moteur change : le selftest headless
    (`PYTHONIOENCODING=utf-8 freecadcmd scripts/run-selftest.py`)
  - une vérification à l'écran : serveur `freecadcmd engine/server.py`,
    puis `http://localhost:8787`
- **Pièges connus** :
  - sous Windows, un fichier réécrit en CRLF fait échouer le test i18n
    « pas d'entrée orpheline » (les textes multilignes ne se retrouvent
    plus) : écrire en LF ;
  - aucune variable locale ne doit s'appeler `t` dans `app/` (un test le
    vérifie) ;
  - une nouvelle op moteur doit être ajoutée dans `engine/protocol.py`
    (`OPS`) **et** dans la liste figée de `tests/test_protocol.py`
    (`test_ops_snapshot_keys`) ; si elle modifie le document, l'ajouter à
    `_TRANSACTIONAL` en bas de `engine/kernel.py`.
- **Suivi** : à la fin de chaque tâche, passer sa ligne à « fait » dans le
  tableau de suivi de `docs/ecarts-solidworks.md`.

---

## T18 — Chanfrein : distance-distance et distance-angle

**Comportement visé.** Le panneau du chanfrein propose un type :
- distance égale (le comportement actuel) ;
- deux distances (une de chaque côté de l'arête) ;
- distance et angle.

Selon le type, il montre les champs utiles. Une case « inverser » échange
les deux côtés. L'aperçu jaune suit chaque changement.

**Où.**
- Panneau : `app/features.js`, entrée `btn-chamfer` (vers la ligne 447).
- Moteur : `add_chamfer` dans `engine/kernel.py` (vers la ligne 3255).
  `PartDesign::Chamfer` a les propriétés `ChamferType`
  (« Equal distance », « Two distances », « Distance and Angle »), `Size`,
  `Size2`, `Angle` et `FlipDirection`.
- Protocole : paramètres optionnels de `add_chamfer` dans
  `engine/protocol.py`.
- Réédition : vérifier que le double-clic sur le chanfrein rouvre les bons
  champs.

**Fini quand** les trois types fonctionnent, sont rééditables, l'aperçu
suit, et le selftest reste vert.

## T20 — Révolution : choisir l'axe

**Comportement visé.** Le panneau Révolution (et Enlèvement par
révolution) a une zone « Axe » où l'on choisit :
- une ligne de l'esquisse, de préférence une ligne de construction ;
- un axe d'origine X, Y ou Z ;
- ou rien : on garde alors l'axe vertical de l'esquisse, comme aujourd'hui.

Une option « deux directions » ou « plan milieu » est un plus.

**Où.**
- Panneau : `app/features.js`, entrées révolution et enlèvement par
  révolution (vers les lignes 119 à 137).
- Moteur : `add_revolution`, `add_groove` et `_revolved` dans
  `engine/kernel.py` (vers la ligne 3007). La propriété `ReferenceAxis`
  accepte `(sketch, ["V_Axis"])`, `(sketch, ["H_Axis"])`,
  `(sketch, ["Edge3"])` ou un axe d'origine (`_AXIS_ROLES` existe déjà).

**Fini quand** une révolution autour d'une ligne de construction donne le
bon solide, l'axe se rééditte, et le selftest reste vert.

## T14 — Barre d'affichage tête haute : styles et visibilité

**Comportement visé.** Dans la barre de vue (`#viewbar`), deux menus
déroulants s'ajoutent :
- **Style d'affichage** : ombré avec arêtes (le mode actuel), ombré sans
  arêtes, filaire, lignes cachées estompées.
- **Masquer / afficher** : plans, origine, esquisses, aperçu des arêtes.

Les choix sont mémorisés dans `localStorage`, comme le réglage de la
molette dans `app/navigation.js`.

**Où.**
- `app/index.html` : `#viewbar` et son CSS.
- `app/main.js` :
  - `baseMaterial` et `partEdges`, à rendre en filaire (`wireframe`) ou à
    masquer ;
  - `planesGroup`, `originGroup` et `sketchLineMeshes` pour la visibilité.
- Icônes : dessins originaux `FreeSolid_*.svg`.

**Fini quand** chaque style se voit sur un bossage avec congé, et que les
réglages survivent au rechargement.

## T17 — Barre de menus

**Comportement visé.** Une barre de menus texte en haut :
- **Fichier** : Nouveau, Ouvrir, Enregistrer, Exporter, Mise en plan.
- **Édition** : Annuler, Rétablir, Reconstruire, Supprimer.
- **Affichage** : vues standard, Zoom au mieux, boîte d'orientation,
  origine.
- **Insertion** : les fonctions du ruban, groupées comme dans le ruban.
- **Outils** : Mesurer, Évaluer, Équations, Paramètres.
- **Aide** : À propos, Signaler un problème.

Chaque entrée affiche son raccourci clavier s'il existe. Les menus
s'ouvrent au clic, se parcourent au survol une fois ouverts, et Échap les
ferme.

**Où.**
- `app/index.html` : en-tête.
- Les commandes existent déjà comme boutons (`btn-…`, `view-…`) : le menu
  **déclenche ces boutons** (`click()`) au lieu de dupliquer leur logique.
- Le contenu du menu Insertion se lit dans `app/ribbon.json`, pour rester
  synchronisé avec le ruban.
- Textes : tout passe par `t()`.

**Fini quand** chaque entrée déclenche la même action que le bouton
correspondant, en français et en anglais.

## T12 — Barre de raccourcis sous le curseur (touche S)

**Comportement visé.** La touche S ouvre, sous le curseur, une petite
boîte d'outils contextuelle :
- en esquisse : les outils de tracé et la cotation ;
- hors esquisse : esquisse, bossage, enlèvement, congé, chanfrein,
  répétitions.

Un champ de recherche filtre **toutes** les commandes du ruban par leur
libellé. Échap, ou un clic à côté, ferme la boîte.

La spline perd la touche S : en esquisse, S appelle maintenant la boîte.

**Où.**
- `app/sketch.js`, `onKey` : retirer `s → spline`.
- `app/main.js` : écouteur clavier global (vers « vues standard »).
- La boîte d'orientation (`#orient-box`) est un bon modèle de panneau
  flottant à reproduire.
- Les commandes à proposer se lisent dans `app/ribbon.json` et
  `#sketchbar`.

**Fini quand** S ouvre la boîte dans les deux modes, la recherche trouve
« congé » ou « fillet » selon la langue, et la spline reste accessible
par son bouton.

## T23 — Ouvrir / Enregistrer : un vrai dialogue de fichiers

**Comportement visé.** Ouvrir, Enregistrer sous et Exporter ouvrent un
dialogue qui remplace le `prompt()` actuel où l'on tape un chemin :
- liste du dossier courant (dossiers d'abord) ;
- remonter au dossier parent ;
- filtre par type (`.FCStd`, `.step`, `.stl`, `.3mf`) ;
- champ du nom de fichier ;
- confirmation avant d'écraser un fichier existant.

Le dernier dossier utilisé est mémorisé.

**Où.**
- Client : `app/main.js`, gestionnaires `btn-open`, `btn-save` et
  `btn-export` (vers les lignes 5292 à 5340).
- Moteur : nouvelle op en lecture seule `list_dir(path)`. Elle doit
  respecter la **même prison de chemins** que l'ouverture et
  l'enregistrement (`_user_path` → `protocol.resolve_user_path`) et ne
  rien lister hors de la zone autorisée. Ajouter des tests dans
  `tests/test_security.py`.
- Application de bureau (`desktop/`) : le dialogue natif de Tauri est une
  option, mais le dialogue web doit fonctionner dans le navigateur.

**Fini quand** on ouvre et enregistre sans taper de chemin, et que les
tests de sécurité prouvent qu'on ne liste rien hors de la prison.

## T24 — Écran d'accueil et Nouveau (Ctrl+N)

**Comportement visé.**
- Au démarrage sans document, et via un bouton « Accueil », un panneau
  central propose :
  - Nouvelle pièce, Nouvel assemblage, Ouvrir ;
  - les fichiers récents : chemins mémorisés dans `localStorage` à chaque
    ouverture ou enregistrement réussi, avec un clic pour rouvrir ;
  - une astuce du jour tirée d'une petite liste (raccourcis clavier,
    souris).
- Ctrl+N ouvre un petit dialogue Pièce / Assemblage (la mise en plan sera
  ajoutée plus tard).

**Où.**
- `app/main.js` : démarrage (`call("ping")` en fin de fichier), boutons
  `btn-new` et `btn-newasm`.
- `app/index.html` : le panneau et son CSS. S'inspirer de `#orient-box`
  pour le style.

**Fini quand** l'accueil apparaît sur un moteur vierge, disparaît dès
qu'un document existe, et que les récents rouvrent le bon fichier.

## T21 — Congé : aperçu complet et bulle de rayon dans la vue

**Comportement visé.**
1. **Aperçu.** Dans l'aperçu jaune du congé, la face arrondie
   n'apparaît pas : on voit une bande sombre, alors que le résultat final
   est correct. Il faut corriger l'aperçu. Piste : `ghostMaterial` dans
   `app/main.js` (vers la ligne 803) est en `FrontSide`, et les normales
   de la face arrondie sont peut-être inversées. Essayer
   `side: THREE.DoubleSide`, ou recalculer les normales dans `showGhost`.
2. **Bulle de rayon.** Pendant le congé, une étiquette « R = … »
   s'affiche près de l'arête choisie, comme les cotes de fonction
   (`createDimSprite`). Un double-clic dessus place le focus sur le champ
   Rayon du panneau.

**Fini quand** l'aperçu montre la face arrondie sur un bloc, et que la
bulle suit le rayon saisi.
