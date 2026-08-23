# [P042] Lire ce qu'on pose — diamètre au clavier, écart affiché

Poser les pierres une par une marche (P034), les glisser marche (P036), les
combiner marche (P035). Ce qui manque n'est pas un automatisme : c'est de
**voir ce qu'on fait pendant qu'on le fait**.

Un bijoutier pave à la main. Il pose une pierre, la glisse jusqu'à ce que
l'écart avec ses voisines lui plaise, ajuste le diamètre, recommence. Aujourd'hui
FreeSolid lui laisse faire tout ça **à l'aveugle** : aucun chiffre à l'écran, et
le diamètre ne se change qu'en rouvrant un panneau.

Trois manques, un seul geste :

1. deux touches, **`+` et `−`**, qui changent le diamètre de 0,1 mm ;
2. l'affichage permanent du **diamètre** ;
3. l'affichage de la **distance entre les pierres** — en continu pendant qu'on
   en glisse une.

Rien d'automatique. Aucun remplissage de face. Le pavage reste le geste de la
main ; on lui donne des yeux.

---

## 1. Ce qu'il faut mesurer, et comment

### La distance qui compte

Entre deux pierres, deux chiffres différents :

- **l'entraxe** — distance entre les centres ;
- **l'écart** — distance entre les bords : `entraxe − (Ø₁ + Ø₂)/2`.

C'est **l'écart** que le bijoutier lit. Négatif, les pierres s'interpénètrent.
La demi-somme des diamètres, et non un seul : deux semis de tailles
différentes peuvent voisiner sur la même face, et c'est un cas de travail
courant, pas un cas limite.

### Sur toutes les pierres, pas sur un semis

Le calcul balaye **toutes les pierres de tous les semis** de la pièce. Deux
semis voisins sur la même face sont deux tailles côte à côte : les ignorer
l'un l'autre rendrait le chiffre faux là où il sert le plus.

Chaque semis reçoit ensuite le minimum de ses propres pierres.

### Une double boucle suffit — mesuré

Pas de grille de hachage. Un pavé posé à la main compte des dizaines de
pierres, pas des milliers, et la double boucle symétrique (chaque paire vue
une fois) coûte, en Python :

| Pierres | Coût |
|---|---|
| 50 | 0,3 ms |
| 100 | 1,0 ms |
| 200 | 4,6 ms |
| 400 | 17,4 ms |
| 800 | 67 ms |

À chaque `get_tree`, 4,6 ms pour 200 pierres ne se voit pas. J'ai essayé une
grille de hachage avant d'écrire ce prompt et je l'ai eue fausse deux fois —
elle rate le voisin quand il est dans la même case, et quand il est à plus
d'une case. Elle ne servirait qu'au-delà du millier de pierres, effectif qu'un
placement à la main n'atteint pas. Si ça arrive un jour, on la remettra sur
l'établi avec un test contre la référence.

---

## 2. Le livrable moteur

### 2.1 `engine/gems.py` — une fonction pure

```python
def voisines_min_mm(points, rayons):
    """Pour chaque pierre : (entraxe, écart) avec sa plus proche voisine.

    ``points`` : liste de (x, y, z). ``rayons`` : demi-diamètres, même
    ordre. Rend une liste de (entraxe_mm, ecart_mm), ``(None, None)``
    quand il n'y a pas d'autre pierre.
    """
```

Double boucle symétrique : `for i … for j in range(i+1, n)`, chaque paire mise
à jour des deux côtés. Aucun import FreeCAD — testable avec des tuples nus,
comme `face_radius_mm`.

**La plus proche voisine se choisit sur l'entraxe, pas sur l'écart.** Les deux
ne classent pas pareil dès que les diamètres diffèrent, et c'est l'entraxe qui
dit qui est le voisin.

### 2.2 `_gem_entry` — deux clés de plus

```python
"voisine_min_mm": …,   # entraxe de la paire la plus serrée du semis
"ecart_min_mm": …,     # son écart bord à bord — négatif = elles se touchent
```

`None` quand la pièce compte moins de deux pierres.

Ne **pas** supprimer `entraxe_mm` / `ecart_sieges_mm` : `app/progress.js` les
lit et P040 vient de caler ses seuils dessus.

Le balayage étant global, il ne peut pas vivre dans `_gem_entry` qui ne voit
qu'un lien. Calcule-le une fois dans `list_gems` / le chemin de `get_tree`, et
passe le résultat à `_gem_entry`.

### 2.3 `app/progress.js` — préférer la mesure au calcul

`seatingGapMm(gem)` rend `ecart_min_mm` quand il existe, et retombe sur
`entraxe_mm − diametre` sinon.

C'est plus qu'un raffinement. `entraxe_mm` vaut `2πR / effectif` : il suppose
que les pierres font le tour complet du jonc. Sur la géométrie qui a consommé
12,1 GiB (r = 11,94 mm, 50 pierres), il tombe sur un écart de `+4,25e-4 mm`,
donc `gap > 0`, donc la branche `radius <= 12` de `combineNeedsMemoryWarning`
n'est atteignable que sur une égalité de flottants exacte : **l'alarme mémoire
ne se déclenche pas sur le cas qu'elle vise**. Une vraie mesure la rend
atteignable — et rend inutile le prompt P041 que j'avais écrit pour ça.

### 2.4 `resize_gem` — la nouvelle opération

```
resize_gem(gem: str, diametre: float) → get_tree()
```

**Les `(u, v)` ne bougent pas.** Seul le diamètre change. C'est tout l'intérêt :
l'entraxe reste fixe, l'écart suit le diamètre, et le designer voit le chiffre
bouger pendant qu'il tape.

Le corps de gabarit est mis en cache par `(gemme, diamètre)` dans
`_gem_bodies` : **il peut servir plusieurs semis**. Écrire la VarSet en place
changerait aussi les autres, silencieusement. La règle :

- ce corps ne sert que **ce** semis → écrire `varset.diametre`, et corriger
  l'entrée de `_gem_bodies` ;
- il en sert d'autres → `_ensure_gem_body(gemme, nouveau)`, relier le
  `LinkedObject`, laisser tomber le corps devenu orphelin (`_remove_gem_body`).

**Ne fusionne pas** avec un semis existant de même face et même nouveau
diamètre, même si ça laisse deux semis jumeaux dans l'arbre. Fusionner
renumérote les pierres, donc casse la sélection en cours — or la sélection est
exactement ce que le clavier vise. Mets à jour le `Label`.

Passe par `self._recompute()`, jamais `doc.recompute()` : c'est là que
`_refresh_gem_placements` réécrit `PlacementList`. P036 s'est cassé les dents
dessus.

Déclarer l'opération dans `engine/protocol.py` et dans la liste d'ops en fin
de `kernel.py`.

---

## 3. Le livrable client

### 3.1 Sélectionner

`app/main.js` ligne ~1008 : au `pointerup`, `if (!drag.moved) return;` jette
déjà le clic sans glissement. C'est le crochet — **un clic sans glissement
sélectionne la pierre**, et avec elle son semis.

- la pierre sélectionnée se distingue à l'œil (teinte, ou contour — au choix,
  mais visible) ;
- `Échap` désélectionne ; cliquer hors d'une pierre aussi ;
- ajouter `diametre` à `mesh.userData.gem` (il porte déjà `spins` et `lifts`) —
  le client en a besoin pour calculer les écarts sans rien demander.

### 3.2 Le bandeau

Un bloc dans `#viewport`, en haut à gauche, sous `#viewbar`. Visible quand une
pierre est sélectionnée :

```
Ø 1,50 mm · 12 pierres
écart mini 0,18 mm
```

- l'écart en **rouge** quand il est négatif ;
- `écart mini —` quand la pièce n'a qu'une pierre ;
- français, virgule décimale, deux décimales.

### 3.3 La ligne d'écart — le cœur du geste

Un segment tracé entre deux pierres, avec l'écart écrit dessus. Rouge quand il
est négatif. `createDimSprite` (`app/sketch.js`) fait déjà l'étiquette.

Deux moments :

- **pendant un glissement** : de la pierre glissée vers sa plus proche
  voisine, recalculé à chaque `pointermove`. La pierre glissée est exclue du
  calcul de ses propres voisines. C'est ça, poser une pierre en voyant ce
  qu'on fait.
- **à l'arrêt, semis sélectionné** : sur la **paire la plus serrée** de la
  pièce. Le bandeau donne le chiffre, la ligne dit *où*.

Tout côté client, depuis les positions déjà connues (`gemWorldPositions()`,
ligne ~433) et les diamètres ajoutés en 3.1. **Zéro appel réseau pendant le
glissement** — c'est ce qui fait la différence entre un chiffre qui suit la
souris et un chiffre qui saute.

### 3.4 Les deux touches

Dans le `keydown` global (`main.js` ~1431), après les gardes existantes
(`sketchMode.active`, puis le test `INPUT|SELECT|TEXTAREA`) :

- `+` → diamètre + 0,1 mm
- `−` → diamètre − 0,1 mm

Accepter le pavé numérique (`event.code === "NumpadAdd"` / `"NumpadSubtract"`)
en plus de `event.key` : sur un clavier AZERTY, `+` demande déjà `Maj`.

- sans effet si aucune pierre n'est sélectionnée ;
- plancher à 0,1 mm — jamais de diamètre nul ou négatif ;
- **le bandeau et la ligne se mettent à jour immédiatement**, avant la réponse
  du moteur : `voisine_min_mm` ne dépend pas du diamètre (les `(u, v)` sont
  figés), donc `écart = entraxe − nouveau_diamètre` se calcule sur place. La
  réponse du moteur réconcilie ensuite ;
- ne pas empiler les appels : si une touche part pendant qu'un `resize_gem`
  est en vol, garder la dernière valeur voulue et n'envoyer qu'au retour.

Le diamètre change pour **tout le semis** — c'est le modèle de données, une
pierre n'a pas de diamètre propre. Le bandeau le dit déjà en affichant le
compte à côté du Ø.

---

## 4. Les tests

**Python** (`tests/test_gems.py`, tuples nus, sans FreeCAD) :

- `voisines_min_mm` : même résultat que la référence naïve sur 200 points
  tirés au sort (graine fixe) ;
- deux pierres de diamètres différents → l'écart vaut bien
  `entraxe − (Ø₁ + Ø₂)/2` ;
- une seule pierre → `(None, None)` ;
- deux pierres qui se chevauchent → écart négatif.

**JS** (`tests/js/progress.test.mjs`) : `seatingGapMm` préfère `ecart_min_mm` ;
la géométrie `r = 11,94 / 50 pierres / ecart_min_mm = +4,25e-4` déclenche bien
l'alerte, là où elle se taisait.

**Selftest** (`kernel.py`) : poser deux pierres voisines sur un cylindre,
vérifier `ecart_min_mm` ; `resize_gem` de +0,5 mm, vérifier que
`voisine_min_mm` n'a **pas** bougé et que `ecart_min_mm` a baissé de 0,5.

`python3 -m pytest tests/ -q` et `node --test tests/js/*.test.mjs` au vert
avant de pousser.

---

## 5. Ce qu'il ne faut pas faire

- **Rien d'automatique.** Pas de remplissage de face, pas de répartition, pas
  de suggestion de position. Le placement reste manuel.
- **Ne pas** déplacer les pierres quand le diamètre change. Les positions sont
  figées : c'est le principe du réglage au clavier.
- **Ne pas** poser une étiquette 3D par pierre. Une ligne à la fois, celle qui
  compte.
- **Ne pas** toucher au chemin booléen de P035/P040. Poser reste séparé de
  combiner.
- **Ne pas** élargir : ni bibliothèque de tailles, ni orientation suivant les
  lignes de courbure, ni écart entre pierres non voisines. Ça viendra.

Un commit ou une petite série, messages préfixés `[P042]`.
