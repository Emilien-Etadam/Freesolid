# [P043] Le booléen suit la cote, la sélection suit la pierre

P042 est livrée et sa CI est verte. Le mécanisme est bon : `voisines_min_mm`
est juste et testé contre la référence, `resize_gem` traite correctement le
cas du gabarit partagé, le bandeau et la ligne d'écart tiennent. **Rien de
tout ça n'est à reprendre.**

Trois défauts, dont un silencieux. Ils sont tous petits.

---

## 1. Le booléen ne suit pas le diamètre — le grave

`_gem_placement_fingerprint` (`engine/kernel.py`) ne signe que les
**placements** : position et quaternion de chaque instance.

```python
chunks.append("{:.6f},{:.6f},{:.6f},{:.6f},{:.6f},{:.6f},{:.6f}".format(
    float(base.x), float(base.y), float(base.z),
    float(qx), float(qy), float(qz), float(qw)))
return "{}#{}".format(link.Name, "|".join(chunks))
```

`resize_gem` ne bouge aucun placement — c'est son principe. Donc l'empreinte
est identique, donc `_set_gem_boolean_shape` rend `False`, donc `obj.Shape`
n'est pas réécrite.

**Enchaînement complet, et c'est le geste que P042 crée :**

1. poser des pierres, combiner → le métal est creusé à Ø 1,5 ;
2. taper `+` deux fois → les pierres affichées passent à Ø 1,7 (ce sont des
   `App::Link` du corps redimensionné, elles suivent) ;
3. **le logement dans le métal reste à Ø 1,5.**

Rien ne le dit. L'écran montre des pierres qui débordent de leur logement, ou
pire, un logement trop grand qu'on ne voit pas. La pièce exportée est fausse.

### Le correctif

Faire entrer le diamètre dans l'empreinte :

```python
return "{}#{:.6f}#{}".format(
    link.Name, self._gem_diametre(link), "|".join(chunks))
```

Le diamètre ne suffit pas tout seul à décrire la forme du gabarit — un jour il
y aura des tailles avec plusieurs cotes. Signe donc **toutes les variables de
la VarSet** du gabarit lié, triées par nom, plutôt que le seul `diametre` :
c'est le même travail et ça ne se re-cassera pas quand la bibliothèque
s'étoffera.

Le nom du gabarit (`FreeSolidGemTemplate`) doit y entrer aussi : changer de
taille sans changer de cote donnerait sinon la même empreinte.

### Le test qui le tient

Dans le selftest (`kernel.py`), après le bloc `p042` : poser deux pierres,
combiner, relever le volume de la pièce, `resize_gem` de +0,5 mm, recomputer,
relever à nouveau. **Le volume doit avoir changé.** Aujourd'hui il ne bouge
pas — c'est exactement ce que ce prompt corrige, et le test doit échouer avant
le correctif.

---

## 2. La sélection ne suit pas la pierre d'une face à l'autre

`selectedGem` est posé au `pointerdown` (`app/main.js` ~1227) et n'est plus
jamais mis à jour. Or `move_gem` vers une **autre face** retire la pierre du
semis source et l'ajoute à la fin du semis destination (`kernel.py`, branche
`else` de `move_gem`) : ni le nom ni l'indice ne survivent.

Deux issues, toutes deux fausses :

- le semis source garde d'autres pierres → `restoreGemSelection` voit que le
  nom existe encore, garde `{A, k}`, et la surbrillance saute sur **la pierre
  qui a pris la place** (l'ancienne `k+1`). `+` et `−` redimensionnent alors le
  semis A, pas celui où la pierre vient d'atterrir ;
- la pierre était seule → `_drop_empty_semis` supprime A, la sélection tombe,
  le bandeau disparaît. La pierre qu'on vient de poser n'est plus sélectionnée.

C'est le croisement exact des deux fonctions demandées : glisser d'une face à
l'autre (P036) et régler au clavier (P042).

### Le correctif

`move_gem` rend déjà l'arbre. Au retour, retrouver la pierre à sa nouvelle
adresse et y reposer la sélection.

Le plus simple et le plus sûr : que **le moteur dise où elle est allée**.
`move_gem` rend `get_tree()` ; ajoute-lui la destination, par exemple

```python
tree["gem_moved"] = {"gem": dest.Name, "index": nouvel_index}
```

Le client lit cette clé après le `refresh` et appelle `selectGem(...)`. Deviner
côté client — « la dernière pierre du semis de la face visée » — marcherait
aujourd'hui et se casserait au premier changement de `_append_stone`.

Sur une même face, l'indice ne change pas : la clé porte alors la même adresse
qu'avant, et le client n'a rien de spécial à faire.

---

## 3. La bande de frôlement est justifiée par un chiffre que le moteur ne
produit pas

`COMBINE_MEMORY_GRAZE_MM = 1e-3` a été ajouté avec ce commentaire :

> L'arc à +4,25e-4 mm n'est pas un écart, c'est du bruit (corde vs arc).

**L'observation est juste et elle est fine.** Mais elle démontre l'inverse de
ce qu'on en a tiré. `entraxe_mm = 2πR/n` est une longueur d'**arc** ;
`voisines_min_mm` mesure une **corde**. Pour la géométrie visée :

| | Valeur | Écart à Ø 1,5 |
|---|---|---|
| arc `2πR/n` | 1,5004247 | **+4,25 × 10⁻⁴** |
| corde `2R·sin(π/n)` | 1,4994376 | **−5,62 × 10⁻⁴** |

Vérifié en appelant `voisines_min_mm` livrée sur 50 points d'un cercle de
rayon 11,94 : elle rend `ecart_min_mm = −0,0005624`. **Négatif.** Le test
`gap < 0` se déclenche seul, sans aucune bande.

Le test livré construit pourtant un objet avec `ecart_min_mm: 4.25e-4` — la
valeur d'arc, que le moteur ne peut pas rendre pour cette géométrie. Il passe,
mais il valide la bande sur une entrée impossible. C'est la quatrième fois
qu'un seuil de ce fichier se cale sur un chiffre qui ne veut pas dire ce que
son nom annonce ; celui-là est de mon fait, pas du vôtre — mon prompt disait
que la mesure rendrait l'alarme atteignable sans dire *comment*.

### Le correctif

- **Corriger le test** : lui faire construire les 50 points du cercle et
  appeler `voisines_min_mm`, plutôt que d'écrire une constante à la main. Un
  test qui fabrique son entrée ne peut pas fabriquer une entrée impossible.
- **Confiner la bande au chemin de repli.** Quand `ecart_min_mm` est présent,
  comparer à zéro franc : la mesure est une distance réelle, pas une
  approximation. La bande garde tout son sens sur `entraxe_mm − diametre`, où
  l'erreur arc-corde vaut justement ~1 × 10⁻³ mm à l'échelle d'une bague — et
  ça, c'est une bonne raison, chiffrée, de la garder là.

---

## 4. Le petit — l'écart optimiste entre deux tailles

`updateGemHud` calcule, pendant qu'une touche est en vol :

```js
ecart = gem.voisine_min_mm - diametre;
```

Or `ecart_min_mm = voisine_min_mm − (Ø₁ + Ø₂)/2`. Si la plus proche voisine
appartient à un **autre** semis, de diamètre différent, l'aperçu se trompe de
`(Ø_soi − Ø_autre)/2`. Il se corrige au retour du moteur, mais il clignote.

`updateGapOverlay` connaît déjà les deux diamètres via `pairMetrics`. Prends
l'écart de la paire la plus serrée qu'il calcule, au lieu de refaire une
soustraction avec un seul diamètre.

---

## Ce qu'il ne faut pas faire

- **Ne pas** retoucher `voisines_min_mm`, le bandeau, la ligne d'écart, les
  touches, ni la branche « gabarit partagé » de `resize_gem` : tout ça est bon.
- **Ne pas** en profiter pour élargir. Quatre correctifs, rien d'autre.

`python3 -m pytest tests/ -q` et `node --test tests/js/*.test.mjs` au vert,
selftest si FreeCAD est disponible. Messages préfixés `[P043]`.
