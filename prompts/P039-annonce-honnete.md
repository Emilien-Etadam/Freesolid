# [P039] L'annonce ment déjà d'un facteur 4

P037 a livré un mécanisme d'avancement juste : `progress` répond hors verrou,
le noyau pousse par callback, aucun pourcentage inventé. **Ce prompt ne
touche à rien de tout ça.**

Il corrige la seule chose qui cloche : **l'estimation annoncée à
l'utilisateur.**

## Le constat, dans les chiffres du rapport de livraison

`app/progress.js:8` :

```js
export const COMBINE_SECONDS_PER_STONE = 43 / 200;
```

Une constante linéaire, tirée d'**une** mesure sur **une** machine. Le
rapport de livraison de P037 la dément dans le même souffle :

| | Annoncé | Mesuré |
|---|---|---|
| 10 pierres, sur la VM | 2 s | **7,6 s** — 3,8 fois plus |
| 200 pierres, sur la VM | 43 s | **~13 Go de RSS, plus de 18 minutes, sans finir** |

Le second cas n'est pas de la lenteur, c'est un **mode de défaillance**. À
13 Go, le système peut tuer FreeCAD, et l'utilisateur perd son document —
après avoir cliqué « Continuer » sur une boîte qui lui promettait
43 secondes.

Une estimation fausse est pire que pas d'estimation : elle fait accepter une
attente qu'on aurait refusée.

## Le livrable

### 1. Calibrer sur la machine, pas sur une constante

La phase de **compound est comptable, rapide, et arrive en premier**. Elle
donne un débit mesuré ici et maintenant, pour cette gemme, sur cette machine.

L'estimation du booléen s'en déduit — avec un facteur d'échelle mesuré, pas
supposé. Et la mesure se conserve entre deux appels : la deuxième combinaison
d'une session sait ce que la première a coûté.

### 2. À défaut de savoir, ne pas prétendre

Tant qu'aucune mesure locale n'existe, **ne pas donner de point**. Une
fourchette ne ment pas :

> « 200 pierres — de plusieurs dizaines de secondes à quelques minutes selon
> la machine. Continuer ? »

C'est moins satisfaisant qu'un nombre rond. C'est surtout moins faux.

### 3. Le risque mémoire se dit

Au-delà d'un seuil — à fixer d'après les mesures de l'étape 4, pas d'après
une intuition — l'avertissement change de nature :

> « 200 pierres — cette opération peut demander plusieurs Go de mémoire et
> ne pas aboutir sur une machine modeste. Enregistrez avant de continuer. »

Proposer l'échappatoire qui existe déjà : **reculer la barre de reprise** et
combiner par lots plus petits, en plusieurs fonctions. Plusieurs booléens de
50 pierres aboutissent là où un de 200 s'étouffe.

### 4. Mesurer la courbe avant toute nouvelle promesse

**C'est la partie qui compte, et elle vient avant les trois autres.**

Une sonde, sur le modèle de `scripts/spike-*.py` : le booléen d'un semis à
**25, 50, 100 et 200 pierres**, avec pour chacun le temps **et la mémoire**
(`resource.getrusage(...).ru_maxrss`, stdlib). Arrêter proprement au-delà
d'un plafond plutôt que de faire ramer la machine.

Ce que la sonde doit trancher : **le coût est-il linéaire, ou explose-t-il ?**
Les deux mesures existantes suggèrent qu'il explose — 760 ms par pierre à
10, contre 215 ms par pierre supposés par la constante — mais deux points sur
deux machines différentes ne font pas une courbe.

Aucune estimation ne doit être écrite dans le code avant que cette sonde ait
répondu.

## Pourquoi ce prompt existe

Cette erreur est la mienne avant d'être celle de personne. J'ai mesuré
`Part.cut` sur des cônes, annoncé « 3,4 s pour 200 pierres », et cité ce
chiffre quatre fois dont deux dans des prompts — jusqu'à ce que la livraison
de P035 le corrige à 43 s. P037 a repris ces 43 s et les a figés dans une
constante.

La règle qui aurait évité les deux : **une mesure unique n'est pas une
courbe, et une courbe sur une machine n'est pas une promesse.**

## Ce qu'il ne faut pas faire

- Ne pas toucher au mécanisme d'avancement de P037 : il est juste.
- Ne pas écrire de nouvelle constante avant la sonde de l'étape 4.
- Ne pas remplacer un nombre faux par un autre nombre faux.
- Ne pas cacher le risque mémoire derrière une formulation rassurante.
- Ne pas toucher `app/vendor/`.

## Validation avant de pousser

```bash
python3 -m compileall -q engine
python3 -m pytest -q
node --check app/main.js
node --test tests/js/*.test.mjs
PYTHONIOENCODING=utf-8 freecadcmd scripts/run-selftest.py
freecadcmd scripts/spike-booleen-semis.py
```

Les tests de `app/progress.js` doivent couvrir le cas « aucune mesure
locale » : l'annonce est alors une fourchette, jamais un point.

Plateforme de référence : **FreeCAD 1.1.3** (`AGENTS.md`). Si la sonde tourne
ailleurs, **le dire** — c'est précisément le genre d'écart qui a produit le
défaut qu'on corrige.

## Commit

Un commit, message en français, préfixé `[P039]`, **donnant la courbe mesurée
à l'étape 4** — temps et mémoire pour chaque nombre de pierres, et sur quelle
machine. Tout texte visible par l'utilisateur est en français, vocabulaire
SolidWorks 2025.
