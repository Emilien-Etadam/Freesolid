# [P034] Poser une pierre sur une surface, et l'y garder

Première brique de la piste bijouterie
([`docs/bijouterie.md`](../docs/bijouterie.md) §5) : des pierres **aimantées
sur la surface** et **déplaçables à la volée**.

La sonde `scripts/spike-pierres.py` a tranché sur FreeCAD 1.1.3 — verdict
vert. Les chiffres qui fondent ce prompt :

| | |
|---|---|
| `Surface.parameter(point)` → (u, v) | marche sur plan, cylindre, tore et B-spline. Les trois voies testées rendent des valeurs identiques : **une seule suffit** |
| L'aimantation | 0,00007 à 0,008 mm entre le point cliqué et le point exact. Invisible |
| **L'ancrage (u, v)** | jonc 10 → 12 mm : la pierre reste **collée, même hauteur, même angle**, normale radiale. Un placement figé aurait décollé de **2,0 mm** |
| `isPartOfDomain(u, v)` | refuse un point tombé dans un trou |
| `App::Link` + `PlacementList` | 200 pierres posées en **0,002 s** |

## Le périmètre — ce prompt ne fait QUE le mécanisme

**Ne sont PAS dans ce prompt**, et ne doivent pas y entrer :

- la bibliothèque des 17 tailles de pierre — chantier à part, et **du
  modelage, pas du code** : une gemme est un `.brep`, pas une fonction
  paramétrique ([`docs/bijouterie.md`](../docs/bijouterie.md) §6) ;
- les sièges et les griffes — `add_boolean`, `add_revolution` et
  `add_polar_pattern` les couvrent déjà, ce sera un prompt suivant ;
- le rapport, la carte des pierres, le contrôle d'écarts.

**Une pierre est ici un cône simple**, posé comme témoin. On construit le
*mécanisme* ; il doit être juste avant qu'on y accroche de la géométrie.

Le témoin est volontairement trivial, et il le restera : le mécanisme est
**indifférent** à ce que la pierre contient. Il pose un `Part::Feature` dans
un `App::Link` et le déplace par `(u, v)` — que la forme dedans soit un cône
ou un brillant relu d'un `.brep` ne change aucune décision de ce prompt. **Ne
pas anticiper la gemme réelle** : la substitution se fera sans retouche.

## Le livrable

### 1. Cinq ops, et pas une de plus

Dans `engine/protocol.py` (`OPS`) puis `engine/kernel.py` :

| Op | Params requis | Optionnels | Rend |
|---|---|---|---|
| `place_gem` | `face` (int), `x`, `y`, `z` (float) | `size`, `spin`, `lift` | le semis mis à jour |
| `move_gem` | `gem` (str), `index` (int), `x`, `y`, `z` | `face` — absent = même face | idem |
| `spin_gem` | `gem` (str), `index` (int) | `spin`, `lift` — absents = inchangés | idem |
| `remove_gem` | `gem` (str), `index` (int) | — | idem |
| `list_gems` | — | — | la liste, pour l'UI et la suite |

`x, y, z` est le **point du raycast client** : approximatif par construction.
Le moteur le projette (`Surface.parameter`), en tire les `(u, v)` exacts, et
c'est **eux** qu'il retient — jamais le point reçu.

### 2. Où vivent les pierres — aucune annexe

**Un `App::Link`** par semis, `ElementCount` + `PlacementList` (0,002 s pour
200, sonde Q7). Sa cible : un `Part::Feature` portant le cône témoin.

L'ancrage se range en **propriétés FreeCAD natives**, groupe `FreeSolid` —
exactement le motif déjà en place pour `FreeSolidColor`
(`engine/kernel.py:1747`) :

| Propriété | Type | Contenu |
|---|---|---|
| `FreeSolidGemFace` | `App::PropertyString` | la face d'ancrage (`"Face3"`) |
| `FreeSolidGemU`, `FreeSolidGemV` | `App::PropertyFloatList` | les paramètres, un couple par pierre |
| `FreeSolidGemSpin`, `FreeSolidGemLift` | `App::PropertyFloatList` | rotation autour de la normale, enfoncement |

Ce sont des propriétés FreeCAD, sauvegardées et relues par FreeCAD nu : le
`.FCStd` reste **strictement un document FreeCAD**, comme promis au README.

### 3. Le recalcul à la reconstruction — c'est LE point du prompt

À chaque recompute, `PlacementList` se **recalcule** depuis `(u, v)` et la
**face courante**. Rien d'autre ne justifie de mener ça en BRep.

Le test qui le prouve, et qui doit tomber si on régresse :

> poser une pierre sur le flanc d'un cylindre → changer le rayon du cylindre
> → la pierre est toujours **sur** la surface (distance < 1e-6), à la même
> hauteur et au même angle.

À ajouter au selftest (`Kernel.selftest`), pas seulement aux tests unitaires :
c'est un comportement géométrique, il se vérifie sur FreeCAD.

### 4. Le drag, côté client — le partage planegcs, resservi

Le dépôt a tranché ce problème une fois pour l'esquisse. **Reprendre le même
partage, ne pas en inventer un autre** :

- **`pointermove`** → raycast sur la tessellation déjà en mémoire, la pierre
  suit immédiatement. **Aucun aller-retour** ;
- **`pointerup`** → un seul `move_gem`, projection exacte, recalage.

Le survol hors domaine (`isPartOfDomain` faux, sonde Q3) **refuse le dépôt**
et le signale — la pierre revient à sa position d'avant le drag.

Rendu : `THREE.InstancedMesh` — une géométrie, N matrices. Il n'y en a aucun
dans `app/main.js` aujourd'hui ; 200 pierres en objets séparés ne tiendraient
pas.

### 5. Les normales exactes dans `pack_mesh`

`geometry.computeVertexNormals()` (`app/main.js:323`) moyenne les normales de
triangles : la pierre facetterait visiblement en glissant sur un jonc.

`protocol.pack_mesh` accepte un **`normals` optionnel**, rempli par
`face.normalAt(u, v)` à chaque sommet de la tessellation ; le client s'en sert
quand il est là et retombe sur `computeVertexNormals()` sinon. Champ
optionnel, donc pas de rupture de contrat.

Bénéfice collatéral assumé : **tout l'ombrage de l'app y gagne**, pas
seulement les pierres. Si ce point déstabilise le smoke, le sortir dans un
prompt séparé plutôt que de le bâcler.

### 6. Les deux règles que la sonde impose

1. **Ne jamais interpoler `u`, ni comparer des écarts de `u`** pour juger
   qu'une pierre en touche une autre : sur une surface périodique `u` boucle
   à 2π (sonde Q4), deux voisines peuvent être à 2π l'une de l'autre en
   paramètre. Les écarts se mesurent **en 3D**, toujours.
2. **Ne jamais stocker de matrice de placement**, ni comme cache, ni « en
   attendant ». Une matrice figée finit toujours par faire autorité un jour
   de reconstruction, et le bénéfice entier disparaît.

### 7. Ce qu'on dit à l'utilisateur

Sur une **surface libre**, l'ancrage dérive : 0,13 mm mesurés en bombant un
chaton B-spline de 2,0 à 3,5 (sonde Q2b) — la pierre reste sur la surface et
se réoriente, mais glisse. Cause : une B-spline interpolée se re-paramétrise
quand ses pôles bougent.

Nulle sur les surfaces analytiques — révolution, balayage, cylindre, tore,
**c'est-à-dire le jonc**. Donc : **prévenir quand la face d'ancrage est une
B-spline**, une fois, dans le panneau. Ne pas le masquer, ne pas en faire un
blocage.

## Ce qu'il ne faut pas faire

- Ne pas modeler les tailles de pierre — le cône témoin suffit ici.
- Ne pas creuser les sièges ni poser de griffes.
- Ne pas stocker de placement figé (cf. règle 2).
- Ne pas ajouter de dépendance : le moteur reste en stdlib pure hors FreeCAD.
- Ne pas toucher `app/vendor/`.
- Ne pas élargir `pack_mesh` au-delà du champ `normals` optionnel.

## Le point ouvert, à ne pas trancher en silence

`FreeSolidGemFace` stocke un **nom de face** (`"Face3"`). Toute édition en
amont renumérote les faces d'OCCT : c'est le **toponaming**, et à 200 pierres
il ne pardonne pas. Le dépôt vit déjà avec pour `add_fillet` et `add_text`,
mais à trois congés, pas à deux cents pierres.

Ce prompt **assume l'index** pour livrer le mécanisme. Il demande en
contrepartie de **constater le décrochage** plutôt que de le subir : si la
face d'ancrage n'existe plus ou a changé de nature au recompute, le semis se
signale en erreur dans l'arbre — il ne se disperse pas en silence.

Les deux ancrages solides (sur courbe, sur esquisse de points) sont décrits
en [`docs/bijouterie.md`](../docs/bijouterie.md) §5.4 et feront l'objet d'un
prompt à part, une fois ce mécanisme éprouvé.

## Validation avant de pousser

```bash
python3 -m compileall -q engine
python3 -m pytest -q
node --check app/main.js
node --test tests/js/*.test.mjs
PYTHONIOENCODING=utf-8 freecadcmd scripts/run-selftest.py
freecadcmd scripts/spike-pierres.py
```

Smoke : poser une pierre sur le flanc d'un cylindre, la faire glisser à la
souris, vérifier qu'elle reste plaquée pendant le drag, qu'elle se recale au
relâchement, et qu'elle **suit la surface après un changement de cote**.
Étendre le smoke sans casser ses étapes.

Plateforme de référence : **FreeCAD 1.1.3** (`AGENTS.md`).

## Commit

Un commit (ou une petite série cohérente), message en français, préfixé
`[P034]`, **disant ce qui est assumé sur le toponaming**. Tout texte visible
par l'utilisateur est en français, vocabulaire SolidWorks 2025.
