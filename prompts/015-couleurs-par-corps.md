# P015 — Apparences : couleur par corps

Produit (`docs/fonctions-manquantes.md` : « Apparences / matériaux
visuels »). En multi-corps, tout est du même gris — SolidWorks colore
les corps, et c'est ce qui rend un modèle multi-corps lisible.

Périmètre : `engine/kernel.py`, `engine/protocol.py`, `app/main.js`,
`tests/`, selftest. La couleur est une **propriété du fichier** (elle
doit survivre à enregistrer/rouvrir), pas un état de session.

## 1. Moteur

- Nouvelle op `set_body_color(body, color)` — `color` = `"#rrggbb"`
  (str, validée par regex, `KernelError` sinon) ou `null`/`""` pour
  revenir au défaut.
- Persistance **headless-compatible** : les corps n'ont pas de
  ViewObject en freecadcmd. Stocker dans une propriété custom :
  `body.addProperty("App::PropertyString", "FreeSolidColor",
  "FreeSolid", "Couleur d'affichage")` (une fois), puis
  `body.FreeSolidColor = "#aabbcc"`. C'est enregistré dans le .FCStd
  et inoffensif dans FreeCAD standard. Retour : `get_tree`.
- `get_tree` expose la couleur : chaque entrée de `bodies` gagne
  `"color": "#rrggbb" | null` (lecture `getattr(body,
  "FreeSolidColor", "") or None`).
- Transactionnel : `set_body_color` dans `_TRANSACTIONAL` (un Ctrl+Z).
- Protocole : `_Req(("body", str), "color")` (color non typé : str ou
  null) + snapshot OPS et assert de déclaration mis à jour.

## 2. Client

- **Menu contextuel de l'arbre** sur un corps : entrée « Couleur… » →
  `<input type="color">` (déclenché programmatiquement, pas de panneau
  complet pour un color picker) + « Couleur par défaut » pour effacer.
  Après `set_body_color`, refresh.
- **Rendu** : aujourd'hui le viewport a un mesh corps actif + un mesh
  « autres corps ». Pour colorer par corps :
  - si la tessellation renvoie déjà de quoi séparer les corps,
    construire un mesh par corps et lui donner son matériau
    (couleur du corps, ou celle du thème si null) ;
  - sinon, étendre `tessellate` pour renvoyer les maillages par corps
    (comme `tessellate_assembly` sait le faire par composant) — en
    gardant la compatibilité du format actuel pour le corps actif
    (le picking de faces ne doit pas bouger : mêmes groupes, mêmes
    ids).
  - Le corps actif garde son matériau interactif actuel (survol,
    sélection de faces) — sa couleur de base devient celle du corps si
    définie.
- Matériaux par corps : conventions P006 (`userData.own = true`,
  dispose au rebuild).
- L'arbre affiche une pastille de couleur devant les corps colorés
  (petit carré CSS, pas d'image).

## 3. Selftest

Étendre l'étape multi-corps (p9 ou équivalente) :

- `set_body_color` sur un corps → `p9_color_ok` : `get_tree` renvoie
  la couleur posée.
- Enregistrer + rouvrir la pièce (le selftest sait déjà faire) →
  `p9_color_persist_ok` : la couleur est toujours là après réouverture.
- `set_body_color(body, "rouge")` → `KernelError` attendue →
  `p9_color_invalid_ok`.

## Validation avant push

1. `python3 -m pytest tests/ -q` — snapshot OPS à jour, tout vert.
2. `node --check` + `node --test` — 50 verts.
3. Selftest FreeCAD : 48 étapes, 95 indicateurs verts attendus (92+3).
4. Smoke local vert (le parcours n'utilise pas la couleur mais le
   rendu par corps ne doit rien casser).
5. Description de PR : capture multi-corps avec deux couleurs.
6. Commit : `[P015] apparences — couleur par corps (persistée dans le .FCStd)`.
