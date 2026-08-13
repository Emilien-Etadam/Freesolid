# P007 — Selftest : couvrir les ops UI jamais exercées

Couvre le constat **6.1** de `docs/audit/2026-08-audit.md` (priorité
n°9 du top 10). Périmètre strict : `engine/kernel.py` (méthode
`selftest` uniquement — aucune op de production ne doit changer).

## Contexte

Le registre expose 86 ops ; le selftest en exerce la plupart, mais des
boutons entiers de l'UI reposent sur des ops que rien ne teste
end-to-end. Nuance vérifiée depuis l'audit : `list_variables` est
effleurée indirectement (valeur de retour de `set_variable`) — elle
reste à appeler comme op top-level.

## Ops à exercer (avec l'étape cible et l'indicateur attendu)

Étendre les étapes **existantes** — ne pas créer de nouvelle pièce si
l'étape en a déjà une sous la main :

1. **p7 (équations)** :
   - `list_variables` top-level → `p7_list_variables_ok` : la variable
     créée par l'étape y figure avec sa valeur.
   - `delete_variable` → `p7_delete_variable_ok` : après suppression,
     elle a disparu de `list_variables` (créer une variable jetable
     dédiée pour ne pas casser les cotes pilotées du reste de l'étape).
2. **p4 (habillage — la boîte 30×30×10)** :
   - `add_chamfer` en **commit réel** (aujourd'hui seulement testé via
     `preview` annulé) sur une arête sûre de la boîte →
     `p4_chamfer_commit_ok` : le volume diminue ou le nombre de faces
     augmente.
   - `delete_feature` sur ce chanfrein → `p4_delete_feature_ok` :
     l'arbre ne contient plus le chanfrein et le recompute est sain
     (volume revenu à sa valeur d'avant chanfrein, tolérance 1e-6).
3. **p3 ou m2 (esquisses)** :
   - `sketch_edit` : rouvrir une esquisse déjà terminée →
     `p3_sketch_edit_ok` : l'état retourné contient les entités
     attendues.
   - `sketch_delete_geo` : ajouter une ligne jetable puis la supprimer
     → `p3_delete_geo_ok` : le compte d'entités revient à l'initial.
   - `sketch_state` appelé top-level une fois → pas d'indicateur dédié,
     il est déjà validé par son contenu ailleurs.
4. **p10 (assemblage)** :
   - `assembly_tree` top-level → `p10_assembly_tree_ok` : composants et
     joints cohérents avec ce que l'étape a construit.
   - `solve_assembly` top-level → `p10_solve_op_ok` (le solveur interne
     est déjà testé via les joints ; ici on veut l'op du bouton
     « Résoudre »).
   - `array_component` → `p10_array_ok` : le nombre de composants après
     répétition est celui attendu.
5. **p12 (surfaces)** :
   - `surface_revolve` → `p12_surface_revolve_ok` : une surface de
     révolution existe dans l'arbre (section surfaces non vide).
   - `surface_loft` → `p12_surface_loft_ok` : un lissage entre deux
     profils ouverts produit une surface.

## Règles

- Chaque appel passe par `self.<op>(...)` comme les étapes existantes,
  avec des géométries **propres à l'étape** (pas de dépendance cachée à
  l'état laissé par une autre étape — le précédent OCCT SIGSEGV venait
  de là).
- Chaque indicateur est un booléen dans `report` ; le runner
  `scripts/run-selftest.py` échoue si l'un est faux — ne rien inventer
  d'autre.
- Si une op se révèle réellement cassée par ce test (c'est le but du
  filet), la corriger est **hors périmètre** : marquer l'indicateur
  faux, documenter dans la description de PR, et me laisser trancher.
  Exception : une erreur triviale de signature/typo dans l'op peut être
  corrigée dans la même PR, en le signalant.

## Validation avant push

1. `python3 -m pytest tests/ -q` — 143 verts (rien de moteur pur ne
   change).
2. FreeCAD requis pour ce prompt : `PYTHONIOENCODING=utf-8 freecadcmd
   scripts/run-selftest.py` — tout vert. Compte attendu : toujours
   48 étapes (on étend les existantes), **~87 indicateurs** (76 + 11
   nouveaux). Donner le compte exact dans la description de PR.
3. Commit : `[P007] selftest — couverture des ops UI orphelines (équations, habillage, esquisse, assemblage, surfaces)`.
