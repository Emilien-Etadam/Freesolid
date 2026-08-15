# P016 — Surfaces paramétriques, éditables comme dans SolidWorks

Décision utilisateur : les surfaces doivent être **rééditables** —
paramètres, esquisses sources et expressions — comme le reste de
l'historique. Fini les formes figées à la création.

Le moyen, validé par sonde sur FreeCAD 1.0.x headless : les objets
paramétriques **natifs C++** de l'atelier Part (`Part::Extrusion`,
`Part::Revolution`, `Part::Loft`, `Part::Offset`). Ils suivent
l'édition du paramètre ET de l'esquisse source, acceptent
`setExpression`, et le fichier reste un .FCStd standard rouvrable dans
FreeCAD stock (aucun proxy Python).

Périmètre : `engine/kernel.py`, `app/main.js`, `tests/`, selftest.
Signatures des ops inchangées (pas de changement protocole).

## 1. Moteur — migration des ops

| Op | Avant (figé) | Après (paramétrique) |
|---|---|---|
| `surface_extrude` | forme calculée | `Part::Extrusion` — `Base`=esquisse, `DirMode`/`Dir` = normale du plan d'esquisse (comportement actuel conservé), `LengthFwd`, `Solid=False` |
| `surface_revolve` | forme calculée | `Part::Revolution` — `Source`, `Axis`/`Base` = axe vertical de l'esquisse (comme aujourd'hui), `Angle`, `Solid=False` |
| `surface_loft` | forme calculée | `Part::Loft` — `Sections`, `Solid=False`, `Ruled=False` |
| `surface_thicken` | `makeOffsetShape(fill=True)` | `Part::Offset` — `Source`, `Value`, `Fill=True` (doit toujours produire un solide : `p12_thicken_solid_ok` reste vert) |
| `surface_sew` | figé | **reste figé** — pas d'objet paramétrique natif pour la couture. Commentaire en tête de l'op + flag `"static": true` dans l'entrée d'arbre |

Points d'attention :

- Les esquisses sources vivent dans le corps PartDesign ; un objet Part
  qui les référence peut déclencher un avertissement de scope — le
  selftest tranche : si ça recompute proprement headless, on garde ;
  sinon, déplacer les esquisses de surfaces au niveau document et le
  dire dans la PR.
- `_recompute` après création ; en cas d'échec OCCT, supprimer l'objet
  créé et lever `KernelError` (pas d'objet cassé dans l'arbre).
- Les fichiers existants contiennent des surfaces figées
  (`Part::Feature`) : l'arbre et le rendu doivent continuer à les
  afficher. Elles restent non éditables — `get_params` sur elles rend
  une liste vide, l'UI n'affiche pas de panneau d'édition.
- L'entrée d'arbre `surfaces` gagne `"type"` (TypeId court) et, pour
  les paramétriques, `"sketches": [noms des esquisses sources]`.

## 2. Édition

- `get_params` / `set_params` acceptent les objets surface : étendre
  `_EDITABLE_PROPS` avec `LengthFwd` (extrusion) et `Value` (offset) —
  `Angle` y est déjà. La whitelist P004 continue de s'appliquer ; les
  expressions passent par `validate_expression` comme partout.
- `app/main.js` : double-clic sur une surface dans l'arbre → le même
  panneau d'édition que les fonctions (la machinerie existante par
  `get_params`, libellés français : « Longueur », « Angle »,
  « Épaisseur »). Une surface figée (ancienne ou couture) n'ouvre pas
  de panneau — message : « Surface figée — non éditable ».
- Les esquisses sources listées sous la surface dans l'arbre (comme
  les esquisses sous les fonctions) ; double-clic → `sketch_edit`
  existant. À la sortie d'esquisse, le refresh reconstruit — la
  surface doit suivre sans intervention.

## 3. Selftest (étendre p12)

- `p12_surface_edit_ok` : `set_params` sur `LengthFwd` d'une extrusion
  → l'aire de la forme change dans la proportion attendue.
- `p12_surface_follows_sketch_ok` : éditer l'esquisse source
  (`sketch_edit` + `sketch_move` + `sketch_finish`) → la surface a
  changé (aire différente, état sain).
- `p12_surface_expr_ok` : expression sur `LengthFwd`
  (`"15 * 2"` → 30), valeur vérifiée.
- `p12_surface_reopen_ok` : `save_part` + `open_part` → la surface
  paramétrique est toujours là, valide, et `set_params` fonctionne
  encore après réouverture.
- Les indicateurs p12 existants restent verts (révolution, lissage,
  couture, épaissir-solide).

## Validation avant push

1. `python3 -m pytest tests/ -q` — 157 verts (pas de changement
   protocole).
2. `node --check` + `node --test` — 50 verts.
3. Selftest FreeCAD : 48 étapes, **99 indicateurs verts** attendus
   (95 + 4).
4. Smoke local vert.
5. Description de PR : le geste complet en capture — créer une surface,
   double-clic, changer la longueur, la voir suivre ; et le constat de
   scope (avertissement ou pas) documenté.
6. Commit : `[P016] surfaces paramétriques — objets Part natifs, édition par panneau, expressions`.
