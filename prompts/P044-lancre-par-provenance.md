# [P044] L'ancre d'un semis par provenance, plus par indice

Un semis retient sa face d'appui sous la forme `FreeSolidGemFace = "Face3"` :
un **indice**. La sonde `scripts/spike-toponaming-semis.py` a tourné sur
FreeCAD 1.1.3 en CI et le défaut est démontré — avec le mécanisme qui le
répare, mesuré sur la même pièce.

**Tout ce prompt repose sur des chiffres, pas sur une lecture de source.**
C'est la leçon de `docs/amont-freecad.md` §4quater, où « l'API existe » avait
été conclu juste et « il suffit de stocker le nom » conclu faux.

---

## 1. Le défaut, et pourquoi il fallait un tube pour le voir

Sur un **plein**, la face d'appui est à l'indice 0 et n'en bouge jamais :
OCCT range d'abord les faces du solide de base. Trois changements de topologie
dans la sonde, l'indice n'a pas bronché.

Un jonc réel est un **tube**. L'alésage y est à l'indice **1** :

| | Faces | Indice de l'alésage |
|---|---|---|
| tube pad-é | 4 | **1** |
| après un congé sur le dessus | 6 | **4** |

Un semis posé sur l'alésage désigne `Face2`. Après le congé, `Face2` est une
autre face. Les pierres partent avec.

## 2. Le mécanisme, mesuré

La généalogie d'une face du corps se lit par `getElementMappedName` puis
`getElementHistory`. Sur un jonc elle fait trois barreaux, et les trois se
comportent différemment :

| Barreau | Unique par face ? | Survit à un changement de topologie ? |
|---|---|---|
| `Body` — le conteneur | ✅ | ❌ **perdu** (3 observations) |
| **fonction propriétaire** (`Pad`, `Pocket`, `Fillet`) | ✅ | ✅ **résolu** (4 obs.) |
| `Sketch` — l'ancêtre | ❌ 1 couple pour 3 faces | ✅ mais **ambigu** |

Le nom porté par le corps change de fond en comble à chaque recompute ; celui
porté par une fonction ne bouge pas. Mesure directe : le nom du `Pad` est resté
`#6:1;:G;XTR;:H17e:7,F` **à l'identique** de part et d'autre d'un enlèvement.

Et la généalogie **gagne un barreau** quand une fonction s'ajoute —
`[Body, Pad, Sketch]` devient `[Body, Pocket, Pad, Sketch]`. C'est
exactement pourquoi la recherche porte sur le **couple**, cherché n'importe
où dans la trace, jamais sur un rang fixe.

Coût : **3,2 ms** par résolution, 16 ms pour cinq semis. Et il y a une
référence par **semis**, pas par pierre : 200 pierres sur une face, c'est une
résolution.

---

## 3. Le livrable moteur

### 3.1 `engine/gems.py` — trois fonctions pures

Reprends-les de la sonde, elles sont vérifiées. Aucun import FreeCAD au
niveau module ; `getattr` sur les objets suffit, comme `face_radius_mm`.

```python
def trace_pairs(trace):
    """Normalise getElementHistory en liste de (source, nom)."""

def owner_couple(paires):
    """Le couple à retenir : le barreau le plus profond qui n'est pas
    une esquisse."""

def resolution_verdict(hits):
    """1 → 'résolu', >1 → 'ambigu', 0 → 'perdu'."""
```

**`trace_pairs` doit gérer les deux formes de retour.** `Part::Feature.
getElementHistory` rend une **liste** de couples, `TopoShape.getElementHistory`
un **tuple plat** `(tag, nom, [intermédiaires])`. §4ter les liste toutes les
deux sans dire qu'elles diffèrent ; confondre les deux fait lire `trace[1]`
comme un nom là où c'est déjà un couple.

**Pourquoi « le plus profond qui n'est pas une esquisse »** et non « le rang 1 » :
au moment de la pose, le rang 1 est la **pointe courante**, qui n'est pas
forcément la fonction qui a introduit la face. Poser une pierre sur un corps
qui a déjà trois fonctions stockerait le couple de la pointe. La sonde ne
distingue pas les deux cas — elle capturait toujours avec le `Pad` en pointe —
mais elle montre que les couples de fonction **intermédiaire** survivent aussi
(Q6 : le couple du `Pocket`, capturé après lui, a survécu à l'enlèvement
suivant). Le plus profond est donc le choix sûr : c'est le propriétaire réel,
et §4quater le nomme ainsi.

### 3.2 `engine/kernel.py` — capturer

Deux propriétés de plus sur le lien, à côté de `FreeSolidGemFace` :

```
FreeSolidGemOwner    : nom de la fonction propriétaire
FreeSolidGemElement  : nom mappé sur cette fonction
```

Renseignées à la création du semis (`_new_semis`), depuis l'indice de face
que le client vient de cliquer.

**`FreeSolidGemFace` reste** — comme cache de l'indice résolu, réécrit à
chaque résolution réussie. C'est lui que le client continue de lire.

### 3.3 `engine/kernel.py` — résoudre

Dans `_refresh_gem_placements`, **avant** d'aller chercher la face : si le
semis porte un couple, faire la recherche à l'envers sur les faces du corps
et agir sur le verdict.

- **résolu** → écrire l'indice trouvé dans `FreeSolidGemFace`, vider
  `FreeSolidGemError`, continuer normalement.
- **ambigu** → **ne rien déplacer.** Garder l'indice précédent, poser
  `FreeSolidGemError` : « la face d'appui s'est scindée — les pierres ne
  savent plus laquelle suivre ». Jamais de re-liaison silencieuse : c'est la
  seule chose que la discipline de verdict empruntée à vcad apporte, et elle
  ne vaut que si elle est respectée dans ce cas-là.
- **perdu** → garder l'indice précédent, poser `FreeSolidGemError` : « la face
  d'appui a disparu ».

L'entrée de `_gem_entry` porte déjà `error` / `error_message` et l'arbre les
affiche : rien à inventer côté client.

### 3.4 Migration et repli

- **Documents existants** : un semis sans couple garde son comportement
  actuel (résolution par indice), et **capture le couple au premier
  recompute réussi** depuis l'indice qu'il porte. Une fois, sans bruit.
- **Carte vide** : si `body.Shape.ElementMapSize` est nul — FreeCAD plus
  ancien, forme importée — on ne capture rien et on résout par indice, comme
  aujourd'hui. Le repli doit être explicite dans le code, pas un effet de
  bord d'un `try`.

`engine/platform.py` tient déjà la version de référence ; ne pas y toucher.

---

## 4. Les tests

**Python** (`tests/`, stubs, sans FreeCAD) :

- `trace_pairs` sur les **deux** formes de retour, plus `None`, une chaîne
  d'erreur, une liste vide ;
- `owner_couple` : `[Body, Pocket, Pad, Sketch]` → le `Pad` ; `[Body, Pad,
  Sketch]` → le `Pad` ; `[Body, Sketch]` → le `Body` ; liste vide → `None` ;
- `resolution_verdict` sur les trois cas.

**Selftest** (`kernel.py`) — le scénario exact que la sonde a mesuré, il doit
échouer avant le correctif :

1. tube : esquisse à deux cercles concentriques (10 et 4), pad de 6 ;
2. poser une pierre sur **l'alésage** (le cylindre de rayon 4, indice 1) ;
3. congé de 0,4 sur la face du dessus ;
4. vérifier que le semis désigne la face de rayon 4 à son **nouvel** indice
   (4 dans la sonde), que `error` est faux et que la pierre est toujours là.

Aujourd'hui l'ancre reste sur l'indice 1, qui n'est plus l'alésage.

`python3 -m pytest tests/ -q` et `node --test tests/js/*.test.mjs` au vert.

---

## 5. Ce qu'il ne faut pas faire

- **Ne pas** stocker le nom mappé porté par le **corps**. Il est unique mais
  il est perdu au premier changement de topologie — c'est mesuré trois fois.
- **Ne pas** stocker le couple de l'esquisse : il survit mais il désigne trois
  faces sur trois.
- **Ne pas** chercher le couple à un rang fixe. La généalogie gagne un barreau
  à chaque fonction ajoutée.
- **Ne pas** re-lier en silence sur un « ambigu ». Un semis qui choisit un
  morceau au hasard est pire qu'un semis qui s'arrête et le dit.
- **Ne pas** toucher à `_face_producers` : c'est l'appariement par
  ressemblance géométrique, une autre affaire, et §4quater explique pourquoi
  la provenance lui est préférable.
- **Ne pas** élargir : rien sur les autres références par indice du dépôt
  (`engine/replay.py` en a). Le semis d'abord ; si ça tient, ce sera le
  patron.

Un commit ou une petite série, messages préfixés `[P044]`.
