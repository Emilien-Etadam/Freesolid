# P018 — Dépouille fiable : plan neutre au choix, échec franc au lieu du no-op

## Contexte — diagnostic vérifié (ne pas re-diagnostiquer)

La dépouille « ne fonctionne pas » d'après l'utilisateur. Diagnostic mesuré
sur FreeCAD 1.0.2 headless (volume avant/après sur un pavé 40×30×15,
angle 3°) :

- faces latérales (ids 0–3) : la dépouille **fonctionne** (volume change) ;
- faces dessus/dessous (ids 4–5, perpendiculaires au plan neutre) : OCCT
  émet « Adding face failed on FaceN. Omitted » sur stderr et produit un
  **no-op silencieux** — volume strictement identique, aucune erreur,
  l'interface affiche « À jour. ».

Cause : `add_draft` (engine/kernel.py) fige le plan neutre sur le Plan de
dessus (XY). Une face perpendiculaire au plan neutre ne peut pas être
dépouillée par rapport à lui ; OCCT l'omet sans échouer. L'utilisateur
clique la face du dessus (geste le plus naturel), la commande « réussit »
sans rien faire.

## Mission

### 1. Moteur — `engine/kernel.py`, `add_draft`

- Nouveau paramètre optionnel `neutral` ∈ {"XY", "XZ", "YZ"}, défaut "XY"
  (comportement actuel inchangé quand absent). Il pilote
  `feature.NeutralPlane` via `_origin_feature`.
- Détection du no-op : mémoriser `body.Shape.Volume` avant la création de
  la fonction ; après le `_recompute()` réussi, si
  `abs(volume_après - volume_avant) < 1e-9`, retirer la fonction
  (`doc.removeObject`) et lever
  `KernelError("cette face ne peut pas être dépouillée par rapport à ce "
  "plan neutre — choisissez un autre plan neutre ou une autre face")`.
  Attention : retirer la fonction AVANT de lever, et recomputer pour
  laisser le document sain (même discipline transactionnelle que le
  `except KernelError` existant).
- Le no-op se teste sur le volume du corps, pas sur le retour d'OCCT :
  l'avertissement « Omitted » ne remonte pas en Python.

### 2. Protocole — `engine/protocol.py`

- `add_draft` : documenter le paramètre optionnel `neutral` (str) dans le
  commentaire de l'entrée OPS, comme les autres optionnels. Pas de
  changement de `_Req` (le paramètre est optionnel, hors tuple typé) —
  mais ajouter la validation de valeur dans le kernel : `neutral` hors
  {"XY","XZ","YZ"} → `KernelError("plan neutre inconnu : …")`.

### 3. Client — `app/features.js`, panneau Dépouille

- Ajouter une ligne `select` « Plan neutre » avec les libellés SolidWorks
  des plans : `[["XY", "Plan de dessus"], ["XZ", "Plan de face"],
  ["YZ", "Plan de droite"]]`, valeur par défaut "XY".
- Supprimer la ligne note « Plan neutre : Plan de dessus » (remplacée par
  le select).
- `build` passe `neutral: v.neutral` dans les params.
- L'erreur du moteur (no-op détecté) remonte par le chemin d'erreur
  existant — rien à ajouter côté client, vérifier seulement qu'elle
  s'affiche dans la barre de statut.

### 4. Selftest — `engine/kernel.py`, étape « p2: dépouille + coque »

Étendre l'étape existante (pas d'étape nouvelle) avec deux indicateurs :

- `p2_draft_noop_refuse` : sur un pavé, `add_draft` de la face du dessus
  avec plan neutre XY doit lever `KernelError` (le no-op est refusé) et
  l'arbre ne doit pas contenir de Dépouille résiduelle en erreur.
- `p2_draft_neutral_ok` : la même face du dessus avec `neutral="XZ"` doit
  réussir avec un volume qui change.

### 5. Tests — `tests/`

- `tests/test_protocol.py` : le snapshot OPS ne change pas (paramètre
  optionnel) — vérifier que la suite passe telle quelle.
- Si un test unitaire pur (sans FreeCAD) est possible sur la validation de
  `neutral`, l'ajouter ; sinon la couverture vit dans le selftest.

## Contraintes

- Ne pas toucher `app/vendor/`.
- Textes utilisateur en français, vocabulaire SolidWorks 2025.
- `python3 -m pytest tests/ -q` et `node --check app/features.js` avant de
  pousser. Selftest complet si FreeCAD est disponible, sinon le signaler
  dans le commit.
- Commit(s) préfixés `[P018]`.
