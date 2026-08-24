# [P048] Rendre le `git mv` vrai, et le prouver par un test

P047 a sorti les 44 méthodes de `Kernel`. Ma relecture concluait « il reste
deux détails ». **Un balayage exhaustif en trouve six**, et il faut le dire :
j'avais mesuré ce que le plugin appelle **vers** le noyau, jamais ce que le
noyau référence **vers** la bijouterie. Deux directions, deux réponses.

Objectif de cet incrément : `plugins/bijouterie/` devient **autonome**, de sorte
que le déplacer vers le dépôt privé soit littéralement un `git mv` — et qu'un
test le prouve, plutôt qu'un prompt l'affirme.

---

## 1. `engine/gems.py` ne déménage pas : il se **coupe**

C'est la découverte qui change la forme du travail. Sur ses **26 fonctions**,
le noyau n'en utilise que **deux** :

```python
# engine/kernel.py:3989, dans _face_mesh
from engine.gems import is_bspline_surface, project_uv
```

Or `_face_mesh` est un **service du noyau** — tessellation d'une face avec
normales exactes — et il figure dans la surface plugin épinglée. Ces deux
fonctions ne sont pas de la bijouterie : ce sont des utilitaires de surface qui
se trouvent habiter le mauvais fichier.

- `is_bspline_surface`, `project_uv` → **`engine/surfaces.py`**, avec leurs
  tests. Elles restent au noyau.
- **Les 24 autres** → `plugins/bijouterie/gems.py`.

`sanitize_gemme` apparaît dans `engine/plugins.py` mais **seulement dans un
docstring** — vérifié. Ce n'est pas une dépendance, ne la traite pas comme
telle.

C'est le seul point qui **casserait** au `git mv` : un `ImportError` au premier
`tessellate`. Les autres coupures laissent du code mort, pas une panne.

---

## 2. Le sac d'état par plugin

`self._gem_bodies = {}` vit encore dans le noyau, en trois endroits :
`kernel.py:254-255` (constructeur, avec un commentaire qui nomme les gabarits)
et `kernel.py:542` (fermeture de document). Le plugin y lit et y écrit.

Le registre doit offrir un **état par plugin et par document** :

```python
registre.state("bijouterie")   # dict, remis à zéro là où l'était _gem_bodies
```

Les deux points de remise à zéro sont **exactement** ceux qui existent — ne les
déplace pas, le cycle de vie du document en dépend.

Ajoute `state` à la liste `_SURFACE_PLUGIN` de `tests/test_plugins.py` : c'est
un membre que des plugins hors dépôt appelleront, il doit être épinglé comme
les onze autres.

---

## 3. Ce qui reste au noyau, et pourquoi

**Deux reconnaissances par nom de propriété** :

| Où | Quoi |
|---|---|
| `kernel.py:1657-1658` | `_is_internal_tool` teste `FreeSolidGemTool` / `FreeSolidGemBooleanTool` |
| `kernel.py:3736` | un `App::Link` portant `FreeSolidGemFace` sort de l'arbre |

**Laisse-les.** Le commentaire déjà en place dit juste : *« le noyau reconnaît
une propriété, il n'appelle plus le métier bijouterie »*. Une chaîne qui ne
correspond à rien est inerte — sans le plugin, aucun objet ne porte ces
propriétés et les tests sont simplement faux. Ça ne casse pas.

Les transformer en crochets serait une abstraction de plus, conçue depuis un
seul client. On l'a évitée en P046 et P047 ; on l'évite encore.

**En revanche, `_TRANSACTIONAL` (`kernel.py:7412`) doit perdre les six ops** :
elles sont désormais déclarées dans `plugins/bijouterie/plugin.json`, et P046 a
posé la fusion. La liste en dur est **redondante**, donc elle ment le jour où
le manifeste change. Vérifie au passage que `list_gems` reste bien **non**
transactionnelle des deux côtés — c'est une lecture.

---

## 4. Les fichiers qui rejoignent le plugin

Purement bijouterie, aucun ne sert au noyau :

```
engine/gems.py            → plugins/bijouterie/gems.py   (moins les 2 de §1)
tests/test_gems.py        → plugins/bijouterie/tests/
tests/test_gem_boolean_fingerprint.py  → idem
scripts/build-gem-library.py           → plugins/bijouterie/scripts/
scripts/spike-pierres.py               → idem
scripts/spike-gemmes-brep.py           → idem
scripts/spike-gemme-parametrique.py    → idem
scripts/spike-booleen-semis.py         → idem
scripts/spike-toponaming-semis.py      → idem
assets/gemmes/                         → plugins/bijouterie/assets/
```

`engine/gems.py:library_dir()` calcule le chemin de la bibliothèque depuis la
racine du dépôt : il doit désormais partir du répertoire du **plugin**.

**La CI** : l'étape « Spike toponaming des semis (informatif) » suit la sonde.
Tant que le plugin est dans le dépôt, garde-la en corrigeant le chemin ; elle
partira avec lui.

`pytest` doit ramasser `plugins/*/tests/`. Une ligne de configuration, pas une
réorganisation.

---

## 5. Ce qui **ne** bouge pas, et il faut le dire

**`scripts/smoke/smoke.js`** garde ses 47 lignes bijouterie. Le JS n'a pas été
séparé — c'est le morceau dur, et il attend son tour. Ses tests ne peuvent pas
partir avant lui.

**`tests/test_protocol.py::test_ops_snapshot_keys`** garde les six ops. Elles
sont réellement dans `OPS` tant que le plugin est là. Le jour du départ, c'est
une ligne à retirer.

Les nommer ici évite qu'on les découvre au `git mv` en croyant à une panne.

---

## 6. Le test qui rend la promesse vérifiable

C'est le livrable qui compte le plus, parce qu'il transforme une affirmation en
contrôle :

```python
def test_le_noyau_n_importe_rien_du_plugin():
    """Le jour du git mv, aucun import ne doit se briser."""
```

Il balaye les sources de `engine/` et échoue si l'une importe `engine.gems`,
`bijouterie`, ou quoi que ce soit sous `plugins/`. Lecture statique du texte
des modules — pas d'import réel, donc ça tourne en CI sans FreeCAD.

Sans ce test, la prochaine ligne `from engine.gems import …` réapparaîtra sans
bruit, et on le découvrira le jour du déplacement.

---

## 7. Les tests

- `test_le_noyau_n_importe_rien_du_plugin` (§6) ;
- `state` épinglé dans `_SURFACE_PLUGIN` ; un test que deux plugins ont des
  états **distincts**, et qu'un nouveau document les remet à zéro ;
- les tests déplacés passent depuis leur nouvel emplacement ;
- `_TRANSACTIONAL` : les six ops restent transactionnelles **via le manifeste**
  — le test doit vérifier le comportement, pas la liste ;
- selftest : les 24 indicateurs, inchangés.

`python3 -m pytest tests/ -q` **et** les tests du plugin,
`node --test tests/js/*.test.mjs`, byte-compile de `engine` et `plugins`.

---

## 8. Ce qu'il ne faut pas faire

- **Ne pas** sortir la bijouterie du dépôt. P048 rend le `git mv` possible ;
  le faire est votre geste, quand le dépôt privé existe.
- **Ne pas** toucher au JS (§5).
- **Ne pas** transformer les deux reconnaissances par propriété en crochets
  (§3).
- **Ne pas** déplacer les points de remise à zéro de l'état (§2).
- **Ne pas** changer un comportement. L'oracle est le même depuis P046 : les
  24 indicateurs, et rien d'autre qui bouge.

Un commit ou une petite série, messages préfixés `[P048]`.
