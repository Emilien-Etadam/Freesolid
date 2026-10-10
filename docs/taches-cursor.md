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

---

# Lot P3

Mêmes règles communes. **Avant chaque tâche : `git merge clone-sw`** dans
`D:\Dev\Freesolid-cursor`, pour partir du travail de Claude et du
vocabulaire neutre. Ne jamais employer un nom de commande SolidWorks
(« Cotation intelligente », « Convertir les entités »,
« Bossage »…) : reprendre les libellés déjà présents dans
`app/lang/en.json`, ou un terme générique de CAO.

## T28 — Onglet « Évaluer »

**Comportement visé.** Un onglet de ruban « Évaluer » (anglais
« Evaluate ») regroupe les outils d'analyse : Mesurer, propriétés de masse
(le bouton « Évaluer » actuel), Équations, et la détection d'interférences
quand on est en assemblage. Les boutons de la barre du haut restent (raccourcis),
l'onglet les rend découvrables.

**Où.** `app/ribbon.json` (nouvel onglet ; chaque bouton reprend l'`id` du
bouton existant ou déclenche son `click()`), `app/ribbon.js` si un bouton
doit relayer un autre. Test dans `tests/js/` sur la présence de l'onglet et
de ses boutons.

## T29 — Recherche de commandes dans la barre du haut

**Comportement visé.** Un champ de recherche dans la barre du haut (à
droite) : on tape quelques lettres, une liste des commandes du ruban
apparaît (libellé traduit + onglet) ; Entrée ou un clic lance la commande.
Raccourci pour y aller : Ctrl+F (hors champ de saisie). Les commandes
d'esquisse ne sont proposées qu'en esquisse.

**Où.** Réutiliser le modèle pur de `app/shortcutbar.js`
(`ribbonCommands`, filtrage) — ne pas dupliquer la logique ; `app/index.html`
pour le champ, `app/main.js` pour le brancher. Tests dans
`tests/js/shortcutbar.test.mjs` ou un nouveau fichier.

## T30 — Autotest hors de la barre du haut

**Comportement visé.** Le bouton « Autotest » (`#btn-selftest`) quitte la
barre du haut : c'est un outil de diagnostic. On le lance depuis le menu
Aide (« Autotest du moteur ») ; le comportement et le rapport ne changent
pas. Le smoke (`scripts/smoke/`) et le selftest qui cliquent ce bouton
doivent continuer de marcher (garder l'élément dans le DOM, masqué, ou
adapter le smoke).

## T31 — Renommer en place dans l'arbre

**Comportement visé.** Sur une ligne de l'arbre sélectionnée : F2, ou un
second clic lent (plus de ~0,5 s après le premier, sans double-clic),
transforme le libellé en champ éditable sur place. Entrée valide (op
moteur de renommage existante), Échap annule, perte du focus valide. Le
menu contextuel « Renommer » ouvre le même champ au lieu du `prompt()`.
Ne pas déclencher pendant un glisser-déposer (réordonner).

**Où.** `app/main.js` (rendu de l'arbre, menu contextuel). Logique de
détection du « clic lent » dans un petit module pur testé.

## T32 — Zoom au mieux (F) en esquisse

**Comportement visé.** En esquisse, F cadre l'esquisse (sa géométrie, et la
pièce si elle est visible) sans quitter la vue normale au plan : la
direction de vue ne change pas, seuls le centre et le zoom. Hors esquisse,
inchangé. Aujourd'hui le gestionnaire de touches de `app/main.js` sort dès
que `sketchMode.active` : y faire une exception pour F (et Z / Maj+Z).

## T33 — Flèches du clavier

**Comportement visé.** Dans la vue (hors champ de saisie, hors esquisse
pour la rotation) :
- flèches : rotation de la vue par pas de 15° (gauche/droite autour de
  l'axe vertical de l'écran, haut/bas autour de l'axe horizontal) ;
- Ctrl+flèches : panoramique d'un dixième de la vue ;
- Alt+gauche/droite : rotation dans le plan de l'écran (autour de l'axe de
  visée), pas de 15°.
En esquisse, seules Ctrl+flèches (panoramique) restent actives. Les pas
sont calculés dans un module pur testé (`app/navigation.js` existe déjà).

---

# Lot « qualité » (relevé : `docs/releve-qualite.md`)

**Nouvelle branche.** Le lot `clone-sw` est en relecture (PR #89). Dans
`D:\Dev\Freesolid-cursor` : `git fetch` n'est pas nécessaire (même dépôt
local), faire `git checkout -b cursor/qualite qualite` une fois, puis **avant
chaque tâche `git merge qualite`**. Un commit par tâche ; Claude fusionne
`cursor/qualite` dans `qualite`. Mêmes règles communes (deux langues, LF,
clean-room, vérifications). Ces tâches ne changent **pas** l'apparence
générale : la refonte de l'en-tête et des icônes est faite ailleurs.

## Q1 — Messages d'erreur clairs, neutres et traduits

**Constat.** `engine/guard.py` (`_TRANSLATIONS`) explique trois erreurs
FreeCAD, mais ses textes citent SolidWorks (interdit dans tout texte
visible) et n'ont pas d'entrée dans `engine/lang/en.json`. Un congé ou un
chanfrein trop grand, une coque impossible renvoient l'erreur brute
« BRep_API: command not done ».

**Comportement visé.**
- Les trois textes de `guard.py` reformulés sans aucun nom de logiciel tiers,
  et traduits (vérifier comment le message atteint le client et passer par
  le mécanisme de traduction du moteur existant).
- Les erreurs du noyau les plus courantes du flux pièce deviennent des
  phrases utiles, **selon la fonction** qui échoue : congé / chanfrein trop
  grand pour les arêtes choisies (« réduisez le rayon / la distance »), coque
  impossible (épaisseur trop forte pour la pièce), dépouille impossible,
  extrusion vide (« le profil ne produit aucun volume »). Repérer les points
  d'échec dans `engine/kernel.py` (`_dressup`, `add_chamfer`,
  `add_thickness`, `add_draft`, `_recompute`) ; garder le message brut en
  complément discret si utile au diagnostic.
- Une coque plus épaisse que la pièce est refusée avec un message (aujourd'hui
  30 mm sur une plaque de 12 mm passe).
- Tests Python (pur, sans FreeCAD) sur la table de correspondance ; une étape
  de selftest qui provoque un congé trop grand et vérifie le message.

## Q2 — Petites bavures

- Retirer le `console.log("selftest", report)` de `app/main.js`.
- Exports que personne n'importe (ni code ni test) : les rendre internes ou
  les supprimer s'ils sont morts — entre autres `latestAvailableSketch`,
  `booleanToolOptions`, `dressupParams` (features.js), `functionNodeSize`,
  `functionPortLayout` (graph.js), `distancePointSegment`, `arcPoints`
  (geom2d.js), `FILE_DIR_KEY`, `FILE_MODES`, `readFileDir` (filedialog.js),
  `RELEASES_URL`, `LICENSE_URL`, `LANGS` (settings.js), `PART_SHORTCUTS`,
  `SKETCH_TOOLS` (shortcutbar.js), `RECENT_KEY`, `MAX_RECENT`, `readRecent`
  (welcome.js). Vérifier chaque cas avant de toucher.
- Icônes jamais référencées dans `app/icons/` : `bound-expression`,
  `nodes_bez_curve`, `nodes_cview`, `nodes_mview`, `nodes_timer` — les
  retirer (et de `app/icons/README.md`).
- Une seule aide de formatage en mm (aujourd'hui `fmtMm` dans geom2d.js,
  `fmt` dans sketch.js, `mm` dans statusbar.js) et une seule lecture de
  nombre (`num.js` ; `dims.js` et `features.js` refont la leur).
- Une seule aide « point 3D → pixel écran » (copiée 5 fois : main.js et
  sketch.js) et une seule « événement → coordonnées normalisées » (3 fois),
  dans un petit module pur testé.
- Comportement inchangé : tests et selftest verts, vérification à l'écran.

## Q3 — Jetons de style

**Comportement visé.** Aucun changement visible voulu ; tout passe par des
variables.
- Dans `app/index.html`, compléter `:root` : couleurs (fond, panneaux,
  lignes, texte, texte secondaire, accent, erreur, `--warn` qui est utilisé
  sans être défini, succès pour le vert `#6fbf8f` répété 13 fois, survol,
  sélection), espacements `--space-1..4` (4/8/12/16 px), rayons
  `--radius-s/m/l` (4/6/8 px), tailles `--text-xs/s/m/l` (11/12/13/16 px).
  Remplacer les valeurs en dur par ces jetons (les écarts minimes sont
  ramenés au jeton le plus proche).
- Côté scène 3D (`app/main.js`, `app/sketch.js` : ~40 couleurs `0x…`),
  réunir les couleurs dans un module `app/theme.js` qui les lit depuis les
  variables CSS (`getComputedStyle`) avec une valeur de repli — pour qu'un
  futur thème clair change aussi la scène.
- Test JS : `theme.js` rend une couleur de repli sans DOM.
- **Depuis le commit eddf3b7 (Q8)** : l'éclairage, le fond en dégradé et la
  grille vivent dans `app/scenelook.js` (`BACKGROUND_TOP/BOTTOM`, couleurs
  de la grille, lumières). Faire `git merge qualite` avant de commencer ;
  y brancher `theme.js` sans changer les valeurs. `main.js` n'a plus de
  `GridHelper` ni de `scene.background`, et le masque des lignes cachées
  n'a plus de couleur (`colorWrite: false`).


## Préalable commun (depuis c87a170)

`qualite` contient un `.gitattributes` qui impose LF. Après
`git merge qualite`, rafraîchir une fois la copie de travail :
`git rm -r -q --cached . && git reset -q --hard` (aucun travail non commité
ne doit traîner). Le test des textes orphelins doit alors passer aussi sous
Windows.

## Q9a — Panneaux et menu contextuel (part simple)

**Comportement visé.**
- Le panneau d'une fonction sans sélection (« Congé : cliquez d'abord dans
  la zone graphique », `app/features.js` lignes ~73 et ~872) ne s'affiche
  plus comme une erreur : c'est une consigne. La rendre neutre (couleur du
  texte secondaire, pas `--danger`), et ne pas la répéter si la ligne de
  sélection du panneau dit déjà quoi choisir. Garder le rouge pour les
  vraies erreurs (valeur invalide, refus du moteur).
- En esquisse sur une face, la face porteuse n'est plus peinte avec la
  couleur de sélection (orange) : elle reprend la couleur normale de la
  pièce, et la barre d'état n'affiche plus « sél. Face n » pendant
  l'esquisse. À la sortie de l'esquisse, la sélection n'est pas restaurée.
- Menu contextuel de la zone graphique (`main.js`, autour de
  `viewMenuEl`) : s'il est plus haut que la place disponible sous le
  pointeur, il s'ouvre au-dessus ; s'il ne tient nulle part, il défile
  (`max-height` + `overflow-y: auto`) au lieu de recouvrir le ruban.
- Tests JS pour ce qui est pur (placement du menu : petite fonction dans
  `viewmenu.js`), vérification à l'écran en 1366 × 768, FR et EN.
- Ne pas toucher à l'en-tête ni aux icônes (Q6/Q7, maquette en attente).
