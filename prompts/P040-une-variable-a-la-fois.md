# [P040] Une variable à la fois, et dans le régime d'une bague

P039 a retiré la constante linéaire et refusé de promettre un point : c'est
acquis, et le mécanisme n'est pas à reprendre.

Mais sa sonde **fait varier deux choses à la fois**, et les seuils livrés
sont calés sur celle qui n'est probablement pas la cause.

## Le confond, en chiffres

`ring_radius_mm(count)` tient l'entraxe à 1,5 mm, donc **le jonc grandit avec
le nombre de pierres** :

| Pierres | Rayon | Entraxe réel | Temps | RSS |
|---|---|---|---|---|
| 25 | 10,00 mm | **2,51 mm** | 0,74 s | 0,16 GiB |
| 50 | 11,94 mm | 1,50 mm | **200 s** | **12,1 GiB** |
| 100 | 23,87 mm | 1,50 mm | plafond | — |
| 200 | 47,75 mm | 1,50 mm | 41 s | 1,93 GiB |

- **Le point à 25 n'est pas comparable** : son rayon a été plafonné à 10 mm,
  son entraxe vaut donc 2,51 mm. Il n'est pas rapide parce qu'il y a peu de
  pierres, mais parce qu'elles sont deux fois plus écartées.
- **Entre les trois points à entraxe égal, le coût décroît quand le jonc
  s'aplatit** : 11,94 explose, 23,87 plafonne, 47,75 passe. C'est monotone en
  **rayon**, pas en nombre.

L'origine du confond est une consigne que j'avais écrite en corrigeant Q6 —
« à entraxe constant, seul le nombre varie ». C'est faux : tenir l'entraxe
**force** le rayon à suivre le nombre. Les deux variables sont liées par
construction, et aucune expérience de ce protocole ne peut les séparer.

## Ce qui rend l'affaire urgente

Le régime que le produit vise est le pire du lot. **Une bague fait 8 à 10 mm
de rayon.** Les points à 23,87 et 47,75 mm sont des bracelets ; le seul point
proche d'une vraie bague — 11,94 mm — est celui qui a consommé 12 GiB.

Et les seuils actuels se trompent des deux côtés : ils crient au loup à 200
pierres (41 s, 1,9 GiB, tout va bien) et se taisent à 25 pierres serrées sur
un jonc de bague, cas jamais mesuré.

## Le livrable

### 1. Trois campagnes, une variable chacune

Étendre `scripts/spike-booleen-semis.py` — ne pas en écrire une autre.

| Campagne | Fixe | Varie | Répond à |
|---|---|---|---|
| **A** | rayon **9 mm** (bague) | 10, 20, 30, 40 pierres | le coût croît-il avec le **nombre** ? |
| **B** | 30 pierres | rayon 8, 12, 24, 48 mm | la **courbure** est-elle le facteur ? |
| **C** | rayon 9 mm, 30 pierres | entraxe, par le diamètre de pierre | l'**écart entre sièges** décide-t-il ? |

C ne se lance que si A et B ne suffisent pas à désigner une cause.

Chaque point rend **temps et RSS pic**, avec un plafond qui arrête proprement
plutôt que de faire ramer la machine. Et **le rayon, l'entraxe et le diamètre
de pierre figurent dans chaque ligne du rapport** — c'est leur absence qui a
rendu la première courbe ininterprétable.

### 2. Recaler les seuils sur ce que les données désignent

Si le facteur est la courbure ou l'entraxe et non le nombre, les seuils de
`app/progress.js` changent de variable. Ils sont aujourd'hui :

```js
export const COMBINE_MEMORY_WARN_STONES = 50;
export const COMBINE_CONFIRM_MIN_STONES = 30;
```

Le moteur connaît le rayon de la face d'ancrage et l'écart entre pierres — il
peut donc les fournir au client, qui décide sur la bonne grandeur.

**Ne rien recaler avant que les campagnes aient parlé.** Un seuil déplacé au
jugé ne vaut pas mieux que celui qu'il remplace.

### 3. Si le coût vient des quasi-tangences

C'est l'hypothèse que la monotonie en rayon suggère : les booléens OCCT
souffrent des surfaces qui se frôlent, d'autant plus fréquentes que la pièce
se referme.

Si les campagnes la confirment, la conséquence n'est pas qu'un seuil
d'affichage : **un semis serré sur une bague peut ne jamais aboutir**, et
l'utilisateur doit l'apprendre avant de lancer, pas après douze gigaoctets.
Le dire alors franchement, et proposer les lots — reculer la barre de
reprise, combiner par paquets — comme la voie normale et non comme un
pis-aller.

## Ce qu'il ne faut pas faire

- Ne pas toucher au mécanisme d'avancement de P037 : il est juste.
- Ne pas faire varier deux grandeurs dans une même campagne.
- Ne pas rendre un point sans son rayon, son entraxe et son diamètre.
- Ne pas recaler un seuil avant que les campagnes aient répondu.
- Ne pas mesurer hors du régime d'une bague sans le dire.
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

Plateforme de référence : **FreeCAD 1.1.3** (`AGENTS.md`). Machine et version
dans le rapport — l'écart entre machines fait partie du sujet.

## Commit

Un commit, message en français, préfixé `[P040]`, **donnant les trois
campagnes et disant laquelle des variables décide**. Si aucune ne ressort
nettement, le dire aussi : un résultat qui ne tranche pas est un résultat, et
vaut mieux qu'une conclusion arrangée. Tout texte visible par l'utilisateur
est en français, vocabulaire SolidWorks 2025.
