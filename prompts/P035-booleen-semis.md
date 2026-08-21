# [P035] Le booléen accepte un semis de pierres

Ce prompt **remplace** `P035-sertir.md`, retiré. Celui-là construisait tout un
outillage de sertissage — gabarits de sièges, jeu de desserrage, ouverture
pour la lumière, garde sur le jonc scindé. Il répondait à une question que
personne n'avait posée : l'auteur combine lui-même, avec la fonction booléenne
qui existe déjà.

Sauf qu'aujourd'hui **elle refuse**.

## Le constat

`add_boolean` (`engine/kernel.py:2912`) exige un `PartDesign::Body` :

```python
if tool_obj is None or tool_obj.TypeId != "PartDesign::Body":
    raise KernelError("corps outil inconnu : {}".format(tool))
```

Un semis est un `App::Link` porteur d'un `ElementCount` et d'un
`PlacementList`. Le booléen le rejette donc, et le geste annoncé — poser les
pierres, puis combiner soi-même — **n'est pas réalisable**. C'est le seul
manque entre P036 et ce flux ; tout le reste est en place.

## Le livrable

### 1. Le booléen accepte un semis comme corps outil

`add_boolean` reconnaît, en plus d'un `PartDesign::Body`, un semis. Il en
tire la forme : le solide de la gemme liée, copié à **chaque** placement de
`PlacementList`, réunis en un `Part.makeCompound`.

Un compound et **une seule** opération — jamais N soustractions. Mesuré :
3,4 s contre 11,1 s à 200 pierres, avec un écart qui grandit
([`docs/bijouterie.md`](../docs/bijouterie.md) §5.6, sonde Q6).

Le chemin d'une forme calculée vers la chaîne PartDesign est **déjà écrit**
dans le dépôt, éprouvé par la gravure de texte : `Part::Feature` porteur de
la forme, enveloppé dans un corps par `BaseFeature`. Le reprendre, ne pas en
inventer un autre.

Les trois types marchent sans distinction — Soustraire, Ajouter,
Intersection. Le premier creuse les logements, le deuxième fond les pierres
dans la pièce pour l'imprimer d'un bloc. **Ce n'est pas au moteur de choisir
lequel a du sens** : l'utilisateur sait ce qu'il fabrique.

### 2. Le semis survit à l'opération — et c'est à confirmer

Un `PartDesign::Boolean` **absorbe** son corps outil. Appliqué tel quel au
semis, il le ferait disparaître de l'arbre : les pierres cesseraient d'être
déplaçables, et tout ce que P034 et P036 ont construit s'arrêterait au
premier booléen.

La voie cohérente avec le reste du projet est donc : **le corps outil est
dérivé du semis**, pas le semis lui-même. Le semis reste dans l'arbre, le
booléen relit `PlacementList` à chaque recompute, et déplacer une pierre
après coup déplace son empreinte.

Le coût — un booléen à chaque déplacement — a déjà sa réponse dans le
dépôt : la **barre de reprise**. `set_tip` avant le booléen pour déplacer à
60 fps, `tip_to_end` pour recalculer une fois. C'est le geste SolidWorks, il
existe, il n'y a rien à écrire pour ça.

> **À confirmer avant d'écrire** : si l'auteur préfère un booléen **terminal**
> qui consomme le semis, dites-le et ce point tombe — le reste du prompt ne
> change pas. Le choix lui appartient, il ne se devine pas.

### 3. Ce que le selftest doit prouver

À ajouter à `Kernel.selftest` :

1. trois pierres posées, **Soustraire** → un seul solide, volume strictement
   inférieur au jonc nu ;
2. les mêmes, **Ajouter** → volume strictement supérieur ;
3. **déplacer une pierre puis reconstruire** → l'empreinte a suivi. C'est le
   test qui distingue un booléen dérivé d'un booléen cuit, et il doit tomber
   si quelqu'un fige le compound un jour.

## Ce qu'il ne faut pas faire

- Ne pas écrire d'opération « sertir » : le booléen existant suffit.
- Ne pas créer de bibliothèque de sièges.
- Ne pas boucler N soustractions.
- Ne pas décider à la place de l'utilisateur lequel des trois types a du sens.
- Ne pas figer les placements du compound : ils se relisent depuis le semis.
- Ne pas toucher `app/vendor/`.

## Validation avant de pousser

```bash
python3 -m compileall -q engine
python3 -m pytest -q
node --check app/main.js
node --test tests/js/*.test.mjs
PYTHONIOENCODING=utf-8 freecadcmd scripts/run-selftest.py
```

Smoke : poser trois pierres sur un jonc, choisir le semis comme corps outil,
Soustraire, vérifier le solide unique ; reculer la barre de reprise, déplacer
une pierre, avancer la barre, vérifier que l'empreinte a suivi.

Plateforme de référence : **FreeCAD 1.1.3** (`AGENTS.md`).

## Commit

Un commit, message en français, préfixé `[P035]`, **donnant le temps mesuré
d'un booléen sur 200 pierres**. Tout texte visible par l'utilisateur est en
français, vocabulaire SolidWorks 2025.
