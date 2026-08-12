# P003 — Robustesse moteur : cycle de vie des documents FreeCAD

Couvre les constats **2.1, 2.2, 2.3** (docs orphelins), **2.4**
(UndoLimit) et **2.6** (`make_drawing` hors transaction) de
`docs/audit/2026-08-audit.md`. Périmètre strict : `engine/kernel.py`
(+ selftest dans le même fichier). Aucune modification client.

## 1. Documents orphelins (2.1 – 2.3)

Trois chemins d'échec laissent aujourd'hui un document FreeCAD ouvert
dans `App.listDocuments()` alors que le kernel ne le référence plus.
À corriger :

- **`open_part`** : si, après `App.openDocument(path)`, aucun Body ni
  Link n'est trouvé → fermer ce document (`App.closeDocument(doc.Name)`)
  avant de lever `KernelError`. Attention : `_close_current()` a déjà été
  appelé — après le raise, le kernel doit rester dans un état cohérent
  « aucune pièce ouverte » (`self._doc = None`, `self._body = None`),
  pas avec un `_doc` pointant sur un document fermé.
- **`_import_cad`** : si `Part.Shape().read(path)` (ou la suite) échoue
  alors que le document neuf est déjà créé → fermer ce document, remettre
  `self._doc = None` / `self._body = None`, puis lever `KernelError`
  avec le message actuel.
- **`insert_component`** : si le document pièce vient d'être ouvert par
  cet appel (il n'était pas déjà dans `App.listDocuments()`) et qu'il
  n'a pas de Body → le fermer avant de lever. S'il était déjà ouvert
  (déjà inséré une fois), ne pas y toucher.

Règle générale : celui qui ouvre ferme en cas d'échec ; un document
déjà ouvert par quelqu'un d'autre n'est jamais fermé.

## 2. UndoLimit (2.4)

Chaque op UI est une transaction : la pile d'undo grossit sans borne en
longue session. Ajouter une petite méthode privée (ex. `_setup_doc(doc)`)
appelée sur **tout** document que le kernel crée ou adopte (`new_part`,
`open_part`, `_import_cad`, `new_assembly`, et le document pièce de
`insert_component` s'il est ouvert ici) qui pose :

```python
doc.UndoMode = 1
doc.UndoLimit = 80
```

(80 actions d'undo — au-delà du Ctrl+Z réaliste, borne la mémoire.)
Remplacer les affectations `UndoMode = 1` existantes par cet appel
unique.

## 3. `make_drawing` transactionnel (2.6)

`make_drawing` crée des objets TechDraw dans le document puis les
supprime dans un `finally` — hors transaction, et si `removeObject`
échoue, des résidus restent. Deux exigences :

- Ajouter `"make_drawing"` à `_TRANSACTIONAL` : l'op entière (création
  page/vue, export DXF, suppression) devient une transaction — en cas
  d'exception, `dispatch` fait `abortTransaction` et le document revient
  net.
- Garder le cleanup du `finally` (le cas nominal commit la transaction,
  la page ne doit pas survivre dans l'arbre), mais si un `removeObject`
  échoue, lever `KernelError("mise en plan : nettoyage incomplet — …")`
  au lieu d'avaler, pour que l'abort de transaction fasse le ménage.

Vérifier après coup qu'un `make_drawing` réussi ne laisse **aucun**
objet TechDraw dans `doc.Objects` (l'indicateur selftest ci-dessous le
prouve).

## 4. Selftest (obligatoire)

Ajouter à l'étape selftest existante de la mise en plan (ou à sa suite)
ces indicateurs :

- `p14_drawing_clean_ok` (ou nom cohérent avec l'étape existante) :
  après `make_drawing`, aucun objet dont le `TypeId` commence par
  `"TechDraw::"` dans le document.
- Nouvelle étape « cycle de vie » : appeler `open_part` sur un chemin
  de fichier `.FCStd` **valide mais vide de Body** (le créer via
  `App.newDocument` + `saveAs` dans le tempdir, puis le fermer) ;
  vérifier que `KernelError` est levée **et** que
  `len(App.listDocuments())` n'a pas augmenté → `lifecycle_orphan_ok`.
- `lifecycle_undo_limit_ok` : le document courant a `UndoLimit == 80`.

## Validation avant push

1. `python3 -m pytest tests/ -q` — 130 verts.
2. Si FreeCAD dispo : `PYTHONIOENCODING=utf-8 freecadcmd
   scripts/run-selftest.py` — toutes étapes vertes, y compris les
   nouveaux indicateurs (48+ étapes / 76+ indicateurs attendus).
3. Commit : `[P003] robustesse moteur — docs orphelins, UndoLimit, make_drawing transactionnel`.
