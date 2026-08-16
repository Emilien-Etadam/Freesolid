# P030 — La barre de reprise couvre aussi les surfaces et les esquisses libres

Demande utilisateur : « la barre de retour en arrière doit aussi prendre
en compte les fonctions de surfaces et d'esquisses ». C'est un
**renversement assumé de P028/P029** : le hissage systématique des
surfaces et esquisses libres au-dessus de la barre disparaît. À la
place, la barre se déplace dans l'historique chronologique complet
(fonctions volumiques + surfaces + esquisses libres) et tout ce qui est
sous elle est reculé : grisé dans l'arbre, absent du viewport.

## Diagnostic vérifié (ne pas re-diagnostiquer)

`body.Tip` ne couvre que la chaîne PartDesign — les surfaces (`Part::*`)
et les esquisses libres sont hors chaîne, il faut donc un marquage
séparé. Sondé sur FreeCAD 1.0.2 headless (Pad + esquisse libre +
`Part::Extrusion` surfacique) :

- une propriété custom `App::PropertyBool` posée via `addProperty`
  (précédent `FreeSolidColor`) **persiste au save/reopen** ;
- `obj.Visibility` existe aussi en headless sur `Part::Extrusion` et
  `Sketcher::SketchObject`, se pose, et **persiste au save/reopen** ;
- `body.Tip = None` puis `tip_to_end()` avec surface + esquisse libre
  présentes : recompute sans erreur.

Décision : la propriété custom `FreeSolidRolledBack` est la **source de
vérité** (un utilisateur FreeCAD peut basculer `Visibility` à la barre
espace sans vouloir dire « reculé »). `Visibility` est **mise en
miroir** (False quand reculé, True sinon) pour que le .FCStd standard
reste honnête ouvert dans FreeCAD.

## Mission moteur — `engine/kernel.py` (+ commentaire `engine/protocol.py`)

Définition : les *lignes d'historique* sont les entrées top-niveau —
fonctions PartDesign de `body.Group`, esquisses **libres**, surfaces
(`_SURFACE_TYPE_IDS`) — ordonnées par `order` (index dans
`doc.Objects`, P027). Les esquisses consommées suivent leur parent.

1. `set_tip(feature)` accepte désormais le nom de **n'importe quelle
   ligne d'historique** (fonction, esquisse libre ou surface) : la
   cible devient la *dernière ligne visible*. Concrètement :
   - lignes d'`order` ≤ cible → visibles : flag effacé
     (`FreeSolidRolledBack = False`, `Visibility = True`) ;
   - lignes d'`order` > cible → reculées : surfaces et esquisses
     libres flaguées (`True`, `Visibility = False`) ;
   - `body.Tip` = dernière fonction PartDesign parmi les visibles
     (None s'il n'y en a aucune).
   - Le refus historique « la barre de retour se pose sur une
     fonction… pas sur une esquisse » **disparaît** (obsolète). Un nom
     qui n'est pas une ligne d'historique (plan, corps, esquisse
     consommée, inconnu) → `KernelError` en français.
2. `set_tip()` sans argument = barre tout en haut : `Tip = None` **et**
   toutes les surfaces/esquisses libres flaguées.
3. `tip_to_end()` : efface tous les flags + `Tip` = dernière fonction.
   Ne doit plus lever « aucune fonction dans la pièce » quand il existe
   des surfaces/esquisses sans fonction volumique (efface les flags,
   `Tip` inchangé/None) ; l'erreur ne reste que si l'historique est
   entièrement vide.
4. `get_tree()` : champ `"rolled_back"` (bool, `getattr` défaut False)
   sur les entrées de surfaces **et** sur les lignes d'esquisses libres
   de `features`.
5. `tessellate()` : les surfaces flaguées sont exclues (faces **et**
   buffer `curves`), les esquisses libres flaguées exclues de
   `sketches`.
6. `_free_sketches()` exclut les esquisses flaguées → `_latest_sketch`
   ne peut pas piocher une esquisse sous la barre (on ne référence pas
   ce qui est reculé), et l'exclusion du `tessellate` en découle.
7. Selftest — nouveaux indicateurs booléens :
   `p30_set_tip_on_sketch`, `p30_set_tip_on_surface`,
   `p30_rolled_surface_absent_mesh`, `p30_rolled_sketch_absent_mesh`,
   `p30_rolled_sketch_not_reusable` (fonction refusée faute d'esquisse
   disponible), `p30_tip_to_end_restores`. La persistance save/reopen
   se teste en pytest si le selftest ne s'y prête pas.

## Mission client — `app/main.js` (+ nouveau module pur)

1. Extraire `chronologicalHistory` + `splitHistoryAroundBar` dans un
   module pur importable `app/history.js` (main.js l'importe), pour les
   tester en node.
2. Nouvelle règle de découpe — `isLiftedHistoryRow` **disparaît** :
   - une ligne surface/esquisse libre est *après* la barre ssi son
     `rolled_back` est vrai ;
   - une fonction volumique est *après* la barre comme aujourd'hui
     (après le tip ; tip absent avec fonctions présentes = toutes
     après) ;
   - `before`/`after` chacun en ordre chronologique ; barre `"none"`
     si aucune ligne d'historique, sinon toujours affichée entre les
     deux (le cas `before` vide = barre en tête). Un objet créé barre
     reculée (non flagué) apparaît au-dessus de la barre — c'est
     l'insertion à la barre, à la SolidWorks.
3. Grisage : les surfaces sous la barre prennent `rolled-back`
   (`appendSurfaceRow` gagne une option) ; l'exemption P029 « une
   esquisse libre n'est jamais reculée » est **retirée** de
   `appendFeatureHistoryRow`.
4. Drag de la barre : les crans (`rollbackSlotPositions`) doivent
   compter **toutes** les lignes d'historique rendues, surfaces
   comprises — poser une classe/attribut commun (ex. `data-hist`) sur
   ces lignes au rendu et s'en servir. `applyRollbackSlot` envoie
   `set_tip {feature: <nom de la ligne juste au-dessus du cran>}`
   quel que soit son type (cran 0 → `set_tip {}`) ; la logique de saut
   `tipTargetBefore` disparaît. La liste utilisée pour les crans doit
   être **la même liste fusionnée que le rendu** (before ⧺ after),
   pas un tri recalculé.
5. Menu contextuel : rien à coder — `openMenu` est déjà accroché aux
   lignes surface et esquisse et `ctx-rollback` toujours visible ;
   c'était le refus moteur qui bloquait. Vérifier seulement que
   « barre de retour ici » marche désormais sur ces lignes.
6. Hygiène de sélection : si la surface ou l'esquisse sélectionnée
   devient reculée (absente du mesh au refresh), la désélectionner
   proprement. Le double-clic « modifier » sur une ligne reculée garde
   le comportement actuel des fonctions volumiques (pas de nouveau
   blocage).
7. `availableSketches` (features.js) ignore les esquisses
   `rolled_back` — cohérent avec `_latest_sketch` moteur.

## Validation

- `python3 -m pytest tests/ -q` — nouveaux cas : `set_tip` sur nom
  d'esquisse et de surface (flags + Tip corrects), `tessellate` exclut,
  `tip_to_end` restaure, `_latest_sketch` saute les flaguées,
  persistance des flags au save/reopen.
- `node --check` sur chaque JS modifié ; tests node pour
  `app/history.js` (découpe : cas solides seuls, surface reculée,
  esquisse reculée, historique sans fonction volumique, barre en tête,
  barre en bout).
- `scripts/smoke/smoke.js` — étendre les pas existants : avec surface +
  esquisse libre présentes, glisser la barre au-dessus d'elles puis
  vérifier : lignes grisées (`.rolled-back`),
  `__freesolidDebug.surfaceMeshCount === 0` et
  `sketchLineCount === 0` ; barre en bas → compteurs restaurés, plus
  de grisage.
- Commit(s) préfixés `[P030]`. Ne pas toucher `app/vendor/`.
