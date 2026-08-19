# [N004d] Le smoke lit « rien » au lieu du volume — trouver pourquoi

La branche `cursor/n004c-fusion-2bf2` (PR #47) est **presque verte**. Il
reste deux échecs, et ils ne disent pas ce qu'ils ont l'air de dire.

**Périmètre : le scénario `scripts/smoke/smoke.js`, plus ce que le diagnostic
révélera.** Ne pas modifier l'application avant de savoir.

## L'état exact

Le correctif `openFeaturePanel` (commit `d4eb0ff`) a réglé l'erreur JS et
**tous les échecs N005**. Il ne reste que :

```
N004b : le bossage graphe devrait augmenter le volume (null → null)
N004b : appliquer le graphe devrait changer le volume (null → null)
```

## Ce que « null » veut dire

`volumeOf()` (`smoke.js:1260`) est le seul endroit qui produit ce `null` :

```js
const j = await r.json();
return j.ok ? j.result.volume_mm3 : null;
```

Donc **`mass_properties` a été refusé par le moteur**. Le `null` n'est pas
un volume nul, c'est un refus dont on a jeté le motif.

## Le point qui oriente tout

`volBeforeGraph` est lu **avant** le clic sur `#btn-graph-feature`,
c'est-à-dire **avant qu'une fonction graphe n'existe**. Et il vaut déjà
`null`.

Donc **la fonction graphe n'est pas en cause.** Deux confirmations :

- le selftest headless, qui exerce `add_graph_feature` et `edit_graph_feature`
  (`n4_graphe_perce`, `n4_graphe_reedite`, `n4_graphe_refus_atomique`), est
  **vert dans le même run** ;
- aucun autre échec n'apparaît : la gravure vient d'être rééditée avec succès
  juste avant (`[gravure rééditée] status = "À jour."`).

Autrement dit : à cet instant du scénario, le moteur refuse d'évaluer la
masse d'une pièce qui vient pourtant d'être modifiée avec succès.

## Le livrable

### 1. D'abord : faire parler le refus

**C'est la première chose à faire, avant toute correction.** Un `null` muet a
coûté deux passages de CI à ce seul diagnostic.

`volumeOf()` doit remonter le message du moteur, pas l'écraser :

```js
return j.ok ? j.result.volume_mm3 : ("REFUS: " + (j.error ?? "?"));
```

et les messages d'erreur du scénario doivent l'afficher. Appliquer le même
principe partout où le smoke transforme un refus en valeur muette.

`mass_properties` (`kernel.py:1590`) n'a que deux causes de refus :
`_require_body()` qui ne trouve pas de corps actif, ou
`« pas de solide à évaluer »`. Le message dira laquelle.

### 2. Ensuite : corriger ce que le message révèle

Deux hypothèses, à départager par le message — **ne pas coder les deux** :

- **Pas de corps actif.** Le scénario passe par l'Autotest (P031) juste
  avant, qui rouvre la pièce vitrine en fin de course. Si l'ouverture ne
  rétablit pas le corps actif côté moteur, c'est un défaut d'application, pas
  de test — et il touche tout ce qui suit une ouverture de fichier, pas
  seulement le smoke.
- **Pas de solide.** Alors c'est l'état laissé par une section précédente, et
  c'est au scénario de le rétablir avant de mesurer.

Le premier cas est le plus important : il voudrait dire qu'après « ouvrir un
fichier », l'onglet Évaluer est muet pour l'utilisateur aussi.

### 3. Vérifier l'avertissement de portée, sans le supposer coupable

Le journal porte, à chaque run :

```
PartDesign::Body: Link(s) to object(s) 'GraphShape' go out of the allowed
scope 'GraphBody'. Instead, the linked object(s) reside within 'N/A'.
```

Comparaison faite : le code d'insertion de `add_graph_feature` est
**structurellement identique** à celui de `add_text` — `Part::Feature`,
marquage, `PartDesign::Body`, `BaseFeature`, `add_boolean`. La gravure fait
le même geste sans que rien n'échoue, et le selftest de la fonction graphe
passe.

Donc : **dire dans le commit si cet avertissement est bénin ou non**, après
l'avoir regardé — ne pas le corriger au jugé, et ne pas le laisser sans
verdict non plus.

## Ce qu'il ne faut pas faire

- Ne pas désactiver ni assouplir les deux vérifications qui échouent : elles
  ont raison de se plaindre, c'est leur diagnostic qui manque.
- Ne pas modifier `mass_properties` pour qu'il réponde quand même. S'il
  refuse, il a une raison ; on veut la connaître, pas la faire taire.
- Ne pas retoucher l'application avant que le message n'ait désigné la cause.
- Ne pas toucher `app/vendor/`.

## Validation avant de pousser

```bash
python3 -m pytest -q
node --check app/graph.js && node --check app/main.js
node --test tests/js/*.test.mjs
PYTHONIOENCODING=utf-8 freecadcmd scripts/run-selftest.py
```

Le smoke doit passer **en entier**, les deux modes du graphe compris — c'est
la validation que le N004c visait et n'a pas encore atteinte.

Plateforme de référence : **FreeCAD 1.1.3** (`AGENTS.md`).

## Commit

Pousser **sur la branche `cursor/n004c-fusion-2bf2`**, pour que la PR #47
devienne verte plutôt que d'en ouvrir une seconde. Message en français,
préfixé `[N004d]`, **disant ce que le refus était** et si l'avertissement de
portée est bénin.
