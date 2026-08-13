# P008 — Protocole : types et bornes des paramètres, op imbriquée, snapshot

Couvre les constats **3.6** (validation de présence seule), **3.7**
(`preview.params` opaque) et **6.2** (trous de `tests/test_protocol.py`)
de `docs/audit/2026-08-audit.md` — dernier item du top 10. Périmètre :
`engine/protocol.py`, `engine/server.py` (si nécessaire),
`tests/test_protocol.py`, `tests/test_security.py`. **Aucune
modification de `kernel.py` ni du client.**

## 1. Schéma typé des paramètres (3.6)

Aujourd'hui `validate_request` vérifie la **présence** des paramètres
requis, pas leur type : `{"op": "add_pad", "params": {"length": "x"}}`
passe et casse plus loin en « erreur moteur non traduite ».

Faire évoluer le registre `OPS` vers des specs typées **sans changer
son API publique** (`validate_request(payload) -> (op, params)`) :

- Chaque paramètre requis déclare un type parmi : `float` (accepte
  aussi `int`, refuse `bool`), `int` (refuse `bool` et les floats non
  entiers), `str`, `list`, `dict`, `bool`. Format de déclaration au
  choix (tuples `(nom, type)`, dict…) tant que le registre reste
  lisible et déclaratif.
- Bornes simples là où l'absurde casse le moteur : les comptes
  (`count`, `cols`, `rows`, occurrences…) exigent `int >= 1` (et un
  plafond raisonnable, ex. 10 000) ; les noms d'op/feature/sketch sont
  des `str` non vides.
- Les paramètres **optionnels** ne sont PAS déclarés (comportement
  actuel conservé) — hors périmètre de les typer tous ; seuls les
  requis sont couverts.
- Messages d'erreur en français, précis :
  `paramètre length : nombre attendu, reçu "x"`.
- Ne pas convertir les valeurs (pas de coercition `"5"` → 5.0) : le
  kernel garde ses conversions actuelles ; on refuse juste ce qui
  n'est pas du bon type JSON.

Attention au client existant : l'UI envoie des nombres JSON natifs
partout où le registre exigera `float`/`int` — vérifier au grep
(`call(`) qu'aucun appel n'envoie de chaîne pour un paramètre requis
typé nombre. En cas de doute sur un paramètre, le laisser non typé
plutôt que de casser l'UI.

## 2. Op imbriquée de `preview` (3.7)

`preview` reçoit `{op, params}` et fait aujourd'hui un `getattr` sans
re-valider. Corriger dans la couche protocole/serveur :

- L'op imbriquée doit exister dans `OPS`, être dans l'ensemble des ops
  prévisualisables (le kernel a `_PREVIEWABLE` — si la couche protocole
  ne peut pas l'importer proprement, valider au moins l'existence dans
  `OPS` et les params typés, le kernel gardant son propre garde
  `_PREVIEWABLE`).
- Ses `params` passent par la même validation typée que s'ils
  arrivaient en op top-level.
- `preview` de `preview` : refusé explicitement.

## 3. Tests (6.2 + les nouveaux)

Dans `tests/test_protocol.py` :

- Snapshot anti-dérive : assert sur l'ensemble **exact** des clés
  d'`OPS` (liste triée en dur dans le test — toute op ajoutée/retirée
  doit se voir dans un diff de test).
- Déclarations manquantes relevées par l'audit : asserts sur les
  tuples de `set_param`, `sketch_edit`, `sketch_state`,
  `sketch_delete_geo` ; `pack_edges([])`.
- Nouveaux : type accepté / refusé pour un `float`, un `int` borné
  (`count: 0` refusé, `count: 1` accepté, bool refusé pour un nombre),
  `str` vide refusée pour un nom ; `preview` avec op inconnue refusée,
  `preview` imbriquant `preview` refusé, `preview` avec params typés
  invalides refusé.
- Le message d'erreur français est asserté sur au moins un cas.

## Validation avant push

1. `python3 -m pytest tests/ -q` — 143 existants + nouveaux, tout vert.
2. Si FreeCAD dispo : selftest — **48 étapes / 87 indicateurs verts**
   attendus. Le selftest appelle les ops en interne (pas via
   `validate_request`), il ne doit donc pas bouger ; s'il casse, c'est
   qu'un type déclaré est faux (ex. un param que le kernel accepte en
   float ET en str) — corriger la déclaration, pas le kernel.
3. `node --check` non requis (client intouché) — le confirmer dans la
   PR (« aucun fichier app/ modifié »).
4. Commit : `[P008] protocole typé — types/bornes des paramètres, validation de l'op imbriquée preview, snapshot OPS`.
