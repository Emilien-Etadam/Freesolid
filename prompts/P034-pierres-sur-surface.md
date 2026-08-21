# [P034] Poser une pierre sur une surface, et l'y garder

Première brique de la piste bijouterie
([`docs/bijouterie.md`](../docs/bijouterie.md) §5) : des pierres **aimantées
sur la surface** et **déplaçables à la volée**.

Deux sondes ont tranché sur FreeCAD 1.1.3, toutes deux vertes :
`scripts/spike-pierres.py` pour le placement (Q1-Q7),
`scripts/spike-gemme-parametrique.py` pour la gemme (H1-H9). Les chiffres qui
fondent ce prompt :

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
  modelage, pas du code** : chaque taille est un `.FCStd` **coté par une
  esquisse** ([`docs/bijouterie.md`](../docs/bijouterie.md) §7). *(Le §6 du
  même document décrit une voie « BREP mis à l'échelle » qui a été
  **écartée** : elle perdait 1,18 % de volume et faussait les cotes. Ne pas
  s'y référer.)* ;
- **les sièges** — et ce n'est pas un report de commodité, c'est une
  décision d'architecture : **poser une pierre n'enlève pas de matière.**
  On pose, puis on **combine**, en une opération séparée et explicite
  ([`docs/bijouterie.md`](../docs/bijouterie.md) §7.4 bis). Poser coûte
  0,001 s pour 200 pierres ; creuser en coûte 3,4. Si le siège se creusait
  au placement, chaque déplacement relancerait le booléen et le geste
  « déplaçable à la volée » — l'objet même de ce prompt — deviendrait
  impraticable ;
- les griffes — `add_revolution` et `add_polar_pattern` les couvrent déjà,
  ce sera un prompt suivant ;
- le rapport, la carte des pierres, le contrôle d'écarts.

**La pierre est ici un cylindre plat** — le **premier fichier de la
bibliothèque**, pas un bouchon codé en dur. Un `.FCStd` paramétrable à deux
cotes (diamètre, épaisseur), rangé dans `assets/gemmes/`, posé dans la pièce
par le même chemin que le brillant qui lui succédera.

Le mécanisme est **indifférent** à ce que la pierre contient : il copie un
corps paramétrique, l'instancie et le déplace par `(u, v)`. Que le corps soit
un cylindre plat ou un brillant à 57 facettes ne change aucune décision de ce
prompt. **Ne pas anticiper la gemme réelle** — mais **ne pas non plus coder
la pierre en dur** : le cylindre plat passe par la bibliothèque, sinon le
chemin d'accès n'est jamais exercé et la substitution découvrira ses bugs
trop tard.

## Le livrable

### 0. Le premier fichier de la bibliothèque

`assets/gemmes/cylindre-plat.FCStd` — un `App::VarSet` nommé `Variables`
portant `diametre` et `epaisseur`, une esquisse **entièrement contrainte**
dont les cotes sont liées par expression à ces variables, et un `Pad`. Rien
de plus.

C'est le gabarit que tout le reste consomme. Le construire **par script**
(un court `scripts/` ou une fonction du selftest), pas à la main : la
bibliothèque des 17 tailles se fabriquera de la même façon, et un fichier
binaire posé à la main n'est ni relisible ni rejouable en CI.

Modèle éprouvé pour la construction headless : la sonde
`scripts/spike-gemme-parametrique.py`, fonction `build_library` — esquisse
sur un plan d'origine du corps, contraintes nommées puis
`setExpression("Constraints[i]", "Variables.diametre * k")`.

### 1. Cinq ops, et pas une de plus

Dans `engine/protocol.py` (`OPS`) puis `engine/kernel.py` :

| Op | Params requis | Optionnels | Rend |
|---|---|---|---|
| `place_gem` | `face` (int), `x`, `y`, `z` (float) | `gemme` (nom de gabarit, défaut `cylindre-plat`), `diametre`, `spin`, `lift` | le semis mis à jour |
| `move_gem` | `gem` (str), `index` (int), `x`, `y`, `z` | `face` — absent = même face | idem |
| `spin_gem` | `gem` (str), `index` (int) | `spin`, `lift` — absents = inchangés | idem |
| `remove_gem` | `gem` (str), `index` (int) | — | idem |
| `list_gems` | — | — | la liste, pour l'UI et la suite |

`x, y, z` est le **point du raycast client** : approximatif par construction.
Le moteur le projette (`Surface.parameter`), en tire les `(u, v)` exacts, et
c'est **eux** qu'il retient — jamais le point reçu.

### 2. Où vivent les pierres — aucune annexe, aucune forme figée

**Un `App::Link`** par semis, `ElementCount` + `PlacementList` (0,002 s pour
200, sonde Q7). Sa cible : le **corps paramétrique de la gemme, copié dans le
document** — `Document.copyObject(corps, True)`, qui amène la variable et
l'esquisse avec lui (sonde H9).

**Jamais une forme importée et figée.** La pierre garde ses cotes d'esquisse
dans la pièce ; la bibliothèque est un jeu de **gabarits**, pas une
dépendance d'exécution. Un `.FCStd` de FreeSolid ne doit avoir besoin
d'aucun fichier externe pour s'ouvrir.

Vérifié par la sonde H9 : après copie, la pierre se rediamètre et recalcule ;
et une pièce rouverte **avec la bibliothèque renommée sur le disque** garde
ses solides valides, sans tirer aucun autre document. Coût de l'autonomie :
~7,7 ko par taille distincte.

Un corps copié **par taille distincte**, pas par pierre : deux cents pierres
de 1,5 mm, c'est un corps et deux cents placements. Le moteur tient donc un
cache clé `(gemme, cotes)`.

Piège confirmé par la sonde, à traiter et non à découvrir : deux gemmes
copiées dans le même document donnent `Variables` et `Variables001` —
**FreeCAD renomme en silence**. Retrouver **la** variable de **chaque**
pierre, jamais la première trouvée. H9 montre que les diamètres restent
indépendants une fois cette résolution faite correctement.

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

### 5 bis. L'incantation PartDesign de 1.1.3, déjà dans le dépôt

Si le cylindre plat de la bibliothèque gagne un jour des fonctions répétées
(les facettes du brillant qui lui succédera), **ne pas réinventer l'appel** :
sur 1.1.3, une répétition se crée par **`body.newObject`**, porte ses sources
dans **`Originals`** — pas `Transformed` — et exige un **`body.Tip`**, sans
quoi elle existe sans devenir le solide du corps.

`Kernel._transform` (`engine/kernel.py:2336`) le fait déjà correctement. La
sonde, elle, s'est cassée dessus pour avoir été écrite sans le consulter.

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

- Ne pas modeler les tailles de pierre — le cylindre plat suffit ici.
- **Ne rien creuser.** Aucun booléen dans ce prompt : on pose des solides.
- Ne pas figer une forme dans la pièce : on copie un corps paramétrique.
- Ne pas poser de griffes.
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
freecadcmd scripts/spike-gemme-parametrique.py
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
