# [P041] L'alarme ne sonnera jamais — une bande, pas une égalité

P040 a trouvé le bon facteur : **c'est l'écart entre sièges qui décide**, pas
le nombre, pas la courbure. Le protocole et le verdict ne sont pas à
reprendre.

Ce prompt corrige une seule chose : **la règle qui en découle ne se
déclenchera jamais.**

## Le constat

`combineNeedsMemoryWarning` (`app/progress.js:162`) compare l'écart en
flottant brut :

- `gap < 0` → alarme ;
- `gap > 0` → silence ;
- `gap === 0` → alarme si le jonc fait ≤ 12 mm.

Le rayon ne sert donc **qu'à l'égalité exacte à zéro** — une valeur qu'une
géométrie réelle ne prendra pas, puisque l'écart vaut `2πr/n − Ø`.

Le cas de P039 qui a consommé **12,1 GiB** le prouve :

| | Rayon | Pierres | Écart réel | Verdict actuel |
|---|---|---|---|---|
| Explosion P039 | 11,94 mm | 50 | **+4,25 × 10⁻⁴ mm** | `gap > 0` → **silence** |

Il ne tombait sur zéro exact que parce que la sonde **construisait le rayon
depuis l'entraxe** : `r = 50 × 1,5 / 2π` redonne exactement 1,5, l'aller-retour
s'annulant au dernier bit. Une bague dessinée à la main, non.

**La géométrie qui a mangé douze gigaoctets ne recevrait aujourd'hui aucun
avertissement.**

## Le livrable

### 1. Une bande de frôlement, proportionnelle au diamètre

Le critère physique n'est pas « écart nul » mais « les sièges se frôlent ».
Remplacer les comparaisons exactes par une bande relative au diamètre de
pierre — un écart de 0,001 mm sur une pierre de 1,5 mm n'est pas la même
chose que sur une de 6 mm.

Le rayon garde son rôle **dans la bande**, où les données de P039 divergent
vraiment : à écart nul, 11,94 mm a explosé quand 47,75 mm est passé en 41 s.
Hors de la bande, il ne sert à rien et ne doit pas peser.

### 2. Mesurer où la bande s'arrête — avant de la fixer

C n'a que deux points de part et d'autre : **+0,085 mm passe** (1,1 s),
**−0,12 mm explose** (81 s). Entre les deux, rien mesuré — et l'explosion de
P039 se trouve précisément là, à +0,0004 mm.

Une campagne **D**, dans la continuité de C : jonc 9 mm, 30 pierres, écarts
de **−0,05 · −0,01 · 0 · +0,01 · +0,02 · +0,05** mm. Elle dit où bascule le
coût, et la bande se pose sur la mesure au lieu d'être devinée.

**Ne pas choisir la largeur avant que D ait répondu.** C'est la troisième fois
qu'un seuil se cale sur ce que les données ne disent pas ; les deux premières
portaient sur la mauvaise variable, celle-ci sur la mauvaise comparaison.

### 3. Le test qui aurait attrapé le défaut

Un cas dans `tests/js/progress.test.mjs` :

> un semis de 50 pierres sur un jonc de 11,94 mm et Ø 1,5 mm — la géométrie
> exacte qui a consommé 12,1 GiB — **doit** recevoir l'avertissement mémoire.

Il tombe aujourd'hui. C'est le meilleur juge de la correction : la règle doit
attraper le cas réel, pas le cas construit par la sonde.

## Ce qu'il ne faut pas faire

- Ne pas toucher au mécanisme d'avancement de P037 ni au protocole de P040.
- Ne pas comparer des écarts par égalité de flottants.
- Ne pas fixer la largeur de bande avant la campagne D.
- Ne pas faire peser le rayon hors de la bande : B l'a innocenté à écart
  franchement positif, de 8 à 48 mm.
- Ne pas toucher `app/vendor/`.

## Une piste pour plus tard, à ne pas traiter ici

P040 a trouvé que le coût part de la **reconstruction de l'arbre** (~79 s sur
122), pas du booléen (~2–3 s). P037 posait l'inverse — c'était mon erreur.

Un recompute de document itère sur des objets : il est donc **plus
observable** qu'un booléen opaque, et l'avancement pourrait y être plus fin
qu'une phase nommée. À reprendre dans un prompt à part, une fois la bande
posée.

## Validation avant de pousser

```bash
python3 -m compileall -q engine
python3 -m pytest -q
node --check app/main.js
node --test tests/js/*.test.mjs
PYTHONIOENCODING=utf-8 freecadcmd scripts/run-selftest.py
freecadcmd scripts/spike-booleen-semis.py
```

Plateforme de référence : **FreeCAD 1.1.3** (`AGENTS.md`).

## Commit

Un commit, message en français, préfixé `[P041]`, **donnant la campagne D et
la largeur de bande qu'elle justifie**. Si D ne montre pas de bascule nette,
le dire : une bande large et assumée vaut mieux qu'une bande étroite et
inventée. Tout texte visible par l'utilisateur est en français, vocabulaire
SolidWorks 2025.
