# [N004e] `mass_properties` ne doit plus lâcher une erreur Python

Dernier point bloquant de la PR #47. Le `REFUS:` posé au N004d a fait son
travail — un seul run a donné ce que trois runs muets n'avaient pas donné :

```
REFUS: 'Part.Compound' object has no attribute 'CenterOfMass'
```

**Périmètre : `engine/`, plus un point de contrôle de selftest.**

## Ce que le message dit, et ce qu'il corrige dans le diagnostic

Le N004d supposait « pas de corps actif ». **C'était faux.** Le calcul passe
les deux gardes de `mass_properties` (`kernel.py:1597`) — il y a un corps, il
a des solides — et plante **après**, sur `shape.CenterOfMass`.

La forme du corps actif est un **`Part.Compound`**, pas un solide unique.
FreeCAD 1.1.3 n'expose pas `CenterOfMass` sur ce type.

Le correctif `open_part` du N004d reste utile — retenir un corps outil
interne comme corps actif était une anomalie réelle — mais **il ne traitait
pas cette cause-ci**. Ne pas le défaire.

## Le livrable

### 1. Aucune erreur Python brute ne doit sortir du moteur

C'est le vrai défaut, indépendant de tout le reste : un utilisateur peut
aujourd'hui lire `'Part.Compound' object has no attribute 'CenterOfMass'`
dans l'interface. Le projet a `engine/guard.py` précisément pour que ça
n'arrive pas.

`mass_properties` doit :

- **fonctionner sur une forme compound** — les grandeurs demandées se
  calculent sur ses solides (volume et aire s'additionnent ; le centre de
  gravité est la moyenne des centres pondérée par les volumes ;
  `BoundBox` marche déjà sur un compound) ;
- **refuser en français** si même ça n'est pas possible, via `KernelError`
  et le vocabulaire de `guard.py` — jamais une `AttributeError` nue.

Vérifier au passage les autres lectures de ces attributs
(`kernel.py:1325`, `2381`, `4261`, `4488`) : si l'une d'elles peut recevoir
un compound, elle a le même défaut. **Ne corriger que celles qui le peuvent
réellement** — pas de durcissement décoratif.

### 2. Puis chercher pourquoi la forme est un compound

C'est l'anomalie de fond : un `PartDesign::Body` normal porte **un** solide.
Qu'il en porte plusieurs, réunis en compound, veut dire qu'une opération en
amont a laissé la pièce dans un état inattendu.

Le contexte est connu : ça se produit après que l'Autotest a rouvert la pièce
vitrine, laquelle porte une gravure. **Chercher, dire ce qui a été trouvé
dans le message de commit** — et ne corriger la cause que si elle est claire.
Si elle ne l'est pas, le point 1 suffit à débloquer, et l'anomalie se note
plutôt que se bricole.

### 3. Le point de contrôle qui manquait

C'est l'absence de ce filet qui a laissé passer un mauvais diagnostic au tour
précédent. Ajouter au selftest :

- `n4e_evaluer_apres_ouverture` : après `open_part` d'une pièce **portant une
  gravure**, `mass_properties` répond — volume fini et positif, centre de
  gravité présent.

Ce point de contrôle doit **échouer** si l'on redéfait le correctif
`open_part` du N004d ou celui du point 1. C'est sa raison d'être : jusqu'ici,
« quels corps comptent » et « quelles formes sont évaluables » n'étaient
verrouillés nulle part.

## Ce qu'il ne faut pas faire

- Ne pas défaire le correctif `open_part` du N004d.
- Ne pas faire taire `mass_properties` en rendant des zéros ou `null` : soit
  il calcule, soit il refuse avec une phrase compréhensible.
- Ne pas toucher au smoke : il dit déjà la vérité depuis le `REFUS:`.
- Ne pas toucher `app/`, ni `app/vendor/`.

## Validation avant de pousser

```bash
python3 -m compileall -q engine
python3 -m pytest -q
PYTHONIOENCODING=utf-8 freecadcmd scripts/run-selftest.py
```

Le smoke doit passer **en entier** — c'est le dernier obstacle de la PR #47,
qui porte tout le travail N004b, N004c et N004d.

Plateforme de référence : **FreeCAD 1.1.3** (`AGENTS.md`).

## Commit

Pousser **sur la branche `cursor/n004c-fusion-2bf2`**, pour que la PR #47
devienne verte. Message en français, préfixé `[N004e]`, **disant si la cause
du compound a été trouvée** ou si elle reste ouverte.
