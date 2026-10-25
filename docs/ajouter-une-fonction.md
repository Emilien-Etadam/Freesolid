# Ajouter une fonction

Une fonction de CAO, c'est une **op du moteur** (`engine/`) et un **panneau
de l'app** (`app/`). Chaque côté la déclare une fois. Le reste en est
dérivé : les tables du protocole, la pile d'annulation, l'aperçu, le rejeu,
la liaison du bouton.

Les tests de cohérence refusent une fonction à moitié déclarée et donnent
son nom. Lancez-les tôt : ils servent de liste de contrôle.

Plus bas, un exemple complet : la Coque (`add_thickness`).

## La recette

| # | Fichier | Ce qu'on y écrit |
|---|---|---|
| 1 | mixin du domaine — `engine/solids.py`, `engine/surfacefeat/<module>.py`… | la méthode, du même nom que l'op |
| 2 | `engine/ops/<famille>.py` | le descripteur `Op(...)` |
| 3 | `engine/vocab.py` | le `Term` d'un nouveau TypeId (libellé de l'arbre, FR et EN), son genre neutre (`TYPE_KEYS`) |
| 4 | `engine/lang/en.json` | chaque message d'erreur de la méthode |
| 5 | `tests/ops_instantane.json`, `tests/test_protocol.py` | l'op dans l'instantané et dans `test_ops_snapshot_keys` |
| 6 | `engine/selftest/<domaine>.py` + `_etapes()` | une étape, ses indicateurs |
| 7 | `app/features/<famille>.js` | l'entrée de `FEATURES` |
| 8 | `app/ribbon.json` | le bouton |
| 9 | `app/icons.js` (+ `app/icons/`) | le rôle d'icône |
| 10 | `app/tree.js`, `app/typekeys.js` | l'icône du genre (`TREE_ICONS`), le libellé des cotes rééditables (`PARAM_LABELS`), la famille du genre |
| 11 | `app/history.js` | le libellé d'annulation (`STEP_LABELS`) |
| 12 | `app/lang/en.json` | chaque texte visible : bouton, infobulle, panneau, refus, libellé d'annulation |
| 13 | `scripts/smoke/smoke.js` | le bouton dans `FEATURE_PANELS` |
| 14 | `tests/js/…` | un test du `build()` du panneau |

### Moteur

**1. La méthode.**

- Elle vit dans le mixin du domaine. La docstring de la famille d'ops
  le nomme, par exemple `"Méthodes : solids.py, vertexchamfer.py."`.
- FreeCAD s'importe dans le corps de la fonction, jamais en tête de
  module.
- Elle refuse avec `KernelError("…")` et un message en français.
- Le libellé de l'objet se pose avec `label_for_type(TypeId, self.lang)`.
- Elle rend `self.get_tree()`.

**2. Le descripteur** (`engine/ops/_base.py` documente chaque champ) :

- `Req(...)` : les paramètres requis, typés, et `optional={...}`.
- `undo=True` pour une op qui modifie le document : c'est un pas
  d'annulation.
- `preview=True` si l'aperçu jaune peut l'exécuter puis l'annuler.
- `creates` et `indexed` disent quel TypeId l'op crée, et s'il porte des
  indices de faces ou d'arêtes.
- Toute `add_*` a **soit** `replay=` (la fonction qui la recrée depuis sa
  capture), **soit** `no_replay="raison"`.

**3–4.** Pour un nouveau TypeId :

- ajoutez son `Term` dans `vocab.py` : c'est le nom affiché, et le terme
  SolidWorks français fait foi ;
- ajoutez son genre dans `TYPE_KEYS` (même fichier) : en minuscules, sans
  `::`, le nom de l'op sans `add_` (`add_thickness` -> `thickness`).
  L'interface ne lit que ce genre (`type_key`), jamais le TypeId ;
- si OCCT peut échouer avec un message opaque, ou sans message, ajoutez
  l'explication dans `engine/guard.py` (`_OPAQUE_BY_KIND`).

Chaque message de `KernelError` reçoit sa ligne dans
`engine/lang/en.json`. Les `{}` y deviennent des gabarits.
`tests/test_i18n.py` refuse un message écrit en toutes lettres qui n'a pas
d'entrée. Un message calculé, comme le texte d'une exception, lui
échappe.

**5. L'instantané du protocole.**

- Dans `tests/ops_instantane.json`, à la main, une ligne par op : dans
  `ops`, puis dans `annulables`, `previsualisables`, `rejouables` et
  `indices` selon le descripteur.
- Ne touchez jamais à `reconstitution` : c'est une mesure datée, qui sort
  dans le selftest.
- Le diff de ce fichier *est* le changement de protocole qu'on relit en
  revue.

**6. Le selftest.**

- Écrivez une fonction `pNN_nom(self, mark, report, etat)` dans le module
  du domaine.
- Elle commence par `mark("pNN: …")`.
- Elle pose des booléens `report["pNN_…"]`.
- Inscrivez-la dans `_etapes()` (`engine/selftest/__init__.py`), juste
  avant `_etapes_des_plugins`.
- L'ordre compte : une étape qui part de sa propre pièce
  (`self.new_part(...)`) ne dépend d'aucune autre ; une étape qui lit
  `etat` dit quelle étape l'a posé.

### App

**7. L'entrée de `FEATURES`.** Elle va dans la famille qui lui
correspond ; `app/features.js` rassemble les familles.

- `button` : l'id du bouton du ruban.
- `op` : l'op du moteur que `build` appelle. C'est une liste si le panneau
  choisit entre deux ops.
- `icon` et `title` : le rôle d'icône et le titre du panneau, en français.
- `groups(ctx)` : les groupes de champs. `ctx.selection(accepts)` pré-remplit
  la case avec ce qui est déjà cliqué.
- `build(v, ctx)` rend `{ op, params }`, ou `null` tant que la saisie est
  incomplète. Avec `null`, l'aperçu s'éteint et OK reste bloqué.
- `invalid(v)` : le texte qui explique un `null`.
- `refresh: "part"` ou `"any"`.
- `dressup: true` quand la fonction s'appuie sur une sélection de faces
  ou d'arêtes. Le graphe ne la place alors qu'avec une sélection.
- `preview: false` si l'op n'a pas `preview=True`.
- Une sélection suivie d'une valeur tient dans l'aide `dressup({...})` de
  `features/commun.js`.

**8–10. Ruban, icône, arbre.**

- Le bouton s'écrit `{"id", "titre", "icon", "libelle", "taille"}`.
  `docs/ruban.md` dit où le ranger.
- Une icône nouvelle va dans `app/icons/` (voir `app/icons/README.md`) ;
  son rôle, dans `ICONS`.
- Pour un nouveau genre (`type_key`) :
  - son icône d'arbre va dans `TREE_ICONS` ;
  - sa famille, dans `BODY_FEATURE_KEYS` ou `SURFACE_KEYS`
    (`app/typekeys.js`) : c'est elle qui ouvre le menu contextuel ;
  - une cote rééditable par double-clic a sa clé neutre dans `PARAM_KEYS`
    (`engine/vocab.py`, la clé du formulaire de création) et son libellé
    dans `PARAM_LABELS`, par clé ; l'interface ne lit et n'écrit que la
    clé (`key` de `get_params`, `set_params`) ;
  - côté moteur, sa propriété doit figurer dans `_EDITABLE_PROPS`
    (`engine/equations.py`).

**11–12.** Le libellé d'annulation est en français ; sa traduction et
celles de tous les textes du panneau vont dans `app/lang/en.json`. Les
tests vérifient :

- les textes du ruban ;
- ceux des panneaux : titre, groupes, champs, aides, choix et refus ;
- les libellés d'annulation.

## Exemple complet : la Coque

Les extraits du moteur sont abrégés (`…`) ; le panneau est recopié tel
quel. Les fichiers font foi.

**Moteur — la méthode** (`engine/solids.py`, `SolidsMixin`) :

```python
def add_thickness(self, face=None, thickness=None, faces=None,
                  outward=False):
    from engine.kernel import KernelError, label_for_type, …
    picked = [int(f) for f in (faces or [])]
    if not picked and face is not None:
        picked = [int(face)]
    if not picked:
        raise KernelError("coque : cliquez au moins une face à ouvrir")
    …
    feature = body.newObject("PartDesign::Thickness", "Thickness")
    feature.Base = (tip, ["Face{}".format(f + 1) for f in picked])
    feature.Value = float(thickness)
    feature.Reversed = not outward
    feature.Label = label_for_type("PartDesign::Thickness", self.lang)
    …
    return self.get_tree()
```

**Moteur — le descripteur et son rejeu** (`engine/ops/habillage.py`) :

```python
def _rejouer_coque(kernel, feat, sketch, cote):
    …
    kernel.add_thickness(faces=feat["faces"], thickness=cote("Value"),
                         outward=not feat["reversed"])

Op("add_thickness", Req(("thickness", float),
                        optional={"face": int, "faces": list,
                                  "outward": bool}),
   undo=True, preview=True, creates="PartDesign::Thickness", indexed=True,
   replay=_rejouer_coque),
```

**Moteur — nom, gabarit, traductions :**

- `engine/vocab.py` : `Term("PartDesign_Thickness", "PartDesign::Thickness", "Coque", "Shell")`,
  et `"PartDesign::Thickness": "thickness"` dans `TYPE_KEYS`.
- `engine/guard.py` : `_OPAQUE_BY_KIND["PartDesign::Thickness"]` explique
  une coque impossible (« l'épaisseur est trop forte pour cette pièce »).
- `engine/lang/en.json` :
  `"coque : cliquez au moins une face à ouvrir": "shell: click at least one face to open"`,
  et de même pour l'épaisseur invalide et le gabarit.

**Instantané** (`tests/ops_instantane.json`) : la ligne
`"add_thickness": {"requis": ["thickness"], …}` sous `ops`, puis le nom
sous `annulables`, sous `previsualisables`, sous `rejouables`
(`["PartDesign::Thickness", "add_thickness"]`) et sous `indices`.
`"add_thickness"` figure aussi dans la liste de `test_ops_snapshot_keys`.

**Selftest** (`engine/selftest/fonctions.py`, inscrite dans `_etapes()`) :

```python
def p38_coque_plusieurs_faces(self, mark, report, etat):
    mark("p38: coque sur plusieurs faces, vers l'extérieur")
    self.new_part("Pièce coque")
    self.add_rect_sketch(40, 20)
    self.add_pad(10)
    …
    tree = self.add_thickness(faces=[top, side], thickness=1)
    …
    report["p38_coque_multi"] = …
```

**App — le panneau** (`app/features/habillage.js`, tel quel) :

```js
export function shellBuild(v) {
  const faces = (v.faces?.items ?? []).map((item) => item.face)
    .filter((face) => face != null);
  const thickness = num(v.thickness);
  if (!faces.length || !(thickness > 0)) return null;
  return { op: "add_thickness",
           params: { faces, thickness, outward: !!v.outward } };
}

{
  button: "btn-shell",
  op: "add_thickness",
  icon: "shell", title: "Coque",
  dressup: true,
  groups: (ctx) => {
    const first = ctx.selection(["face"]);
    return [
      { label: "Faces à supprimer",
        rows: [{ type: "selection", key: "faces", accepts: ["face"],
                 multiple: true,
                 hint: "Cliquez les faces à ouvrir — un second clic retire",
                 value: { kind: "face",
                          items: first?.face != null ? [first] : [] } }] },
      { label: "Paramètres",
        rows: [
          { type: "number", key: "thickness", label: "Épaisseur",
            value: 2, unit: "mm", min: 0.01 },
          { type: "check", key: "outward", label: "Coque vers l'extérieur",
            value: false },
        ] },
    ];
  },
  build: (v) => shellBuild(v),
  invalid: (v) => ((v.faces?.items ?? []).length
    ? "Épaisseur invalide"
    : { text: t("Coque : cliquez au moins une face à ouvrir"), tone: "guide" }),
  refresh: "part",
},
```

**App — le reste, une ligne par fichier :**

| Fichier | Ligne |
|---|---|
| `app/ribbon.json` | `{"id": "btn-shell", "titre": "Coque — les faces cliquées deviennent des ouvertures", "icon": "shell", "libelle": "Coque", "taille": "large"}` |
| `app/icons.js` | `shell: "PartDesign_Thickness.svg",` |
| `app/tree.js` | `thickness: "shell",` dans `TREE_ICONS` ; la clé `thickness` est déjà dans `PARAM_LABELS` |
| `app/typekeys.js` | `"thickness"` dans `BODY_FEATURE_KEYS` |
| `app/history.js` | `add_thickness: "Coque",` |
| `app/lang/en.json` | `"Coque": "Shell"`, l'infobulle, `"Faces à supprimer"`, `"Coque vers l'extérieur"`, l'aide, les refus |
| `scripts/smoke/smoke.js` | `{ id: "btn-shell", tab: "features" },` |
| `tests/js/extrude.test.mjs` | `shellBuild` : plusieurs faces, vers l'extérieur ; sans face ou sans épaisseur, `null` |

## Vérifier

```sh
python3 -m compileall -q engine && python3 -m pytest -q
node --test tests/js/*.test.mjs
npx --prefix scripts/lint eslint -c scripts/lint/eslint.config.mjs app
PYTHONIOENCODING=utf-8 ~/.local/bin/micromamba run -n freecad freecadcmd scripts/run-selftest.py
```

Ce que chaque test refuse :

- **`tests/js/coherence.test.mjs`** refuse une entrée qui :
  - n'a pas d'`op` ;
  - déclare une op inconnue, ou une op sans `undo=True` ;
  - a un aperçu alors que son op n'a pas `preview=True` ;
  - n'a pas de bouton dans `ribbon.json`.

  Il refuse une op du catalogue écrite en toutes lettres dans
  `app/features/` (dans un `build`, le plus souvent) qu'aucune entrée ne
  déclare.

  Il refuse aussi une op annulable sans libellé d'historique, ou avec un
  libellé non traduit.
- **`tests/test_ops_catalogue.py`** refuse une op sans méthode dans
  `Kernel`, et une `add_*` qui n'a ni `replay` ni `no_replay`.
- **`tests/test_ops_instantane.py`** et **`test_ops_snapshot_keys`**
  refusent un changement de protocole absent de l'instantané.
- **`tests/test_param_keys.py`** refuse une cote rééditable sans clé
  neutre, une clé absente des formulaires de création, une cote affichée
  sans libellé, et un nom de propriété FreeCAD dans le code de `app/`.
- **`tests/test_type_keys.py`** refuse un TypeId créé sans genre dans
  `TYPE_KEYS`, un genre qui ne suit pas le nom de l'op, et une famille
  d'`app/typekeys.js` qui ne suit pas la table. **`tests/js/typekeys.test.mjs`**
  refuse un type FreeCAD « Espace::Type » écrit dans le code de `app/`.
- **Les tests i18n** (`tests/js/i18n.test.mjs`, `tests/test_i18n.py`)
  refusent les entrées orphelines. Ils refusent aussi une traduction
  manquante : texte du ruban, texte d'un panneau, ou message de
  `KernelError` écrit en toutes lettres.
- **Le smoke** (`scripts/smoke/smoke.js`) refuse un bouton de `FEATURES`
  absent de `FEATURE_PANELS`, puis ouvre chaque panneau dans un vrai
  navigateur.

Une fonction de plugin suit `plugins/README.md`, pas cette recette.
