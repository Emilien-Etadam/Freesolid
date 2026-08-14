# P011 — Registry des panneaux de fonctions (dédoublonner main.js)

Couvre le constat **5.1** de l'audit. `main.js` répète pour chaque
fonction le même bloc bouton → `panel.open` → `onChange`/`onApply` —
des centaines de lignes de copier-coller. Objectif : un **registry
déclaratif** + une boucle de branchement unique. **Zéro changement de
comportement** : mêmes libellés français, mêmes specs de rows, mêmes
aperçus, mêmes ops.

Périmètre : `app/main.js` et, si le volume le justifie, un nouveau
`app/features.js` importé par `main.js` (le registry seul — pas de
grand découpage de main.js, c'est un autre chantier). Rien d'autre.

## Le registry

Une entrée par fonction « mécanique » :

```js
{
  button: "btn-pad",              // id du bouton du ruban
  icon: "PartDesign_Pad.svg",
  title: "Bossage/Base extrudé",
  groups: (ctx) => [...],         // les rows actuelles, à l'identique
  build: (v, ctx) => ({ op: "add_pad", params: {...} }) | null,
  refresh: "part",                // part | any — quel refresh après OK
}
```

et UNE fonction de branchement qui fait ce que chaque bloc fait
aujourd'hui : clic → `featureCommand`-équivalent (sortie d'esquisse
auto, refus en mode assemblage — réutiliser l'existant) →
`panel.open({ icon, title, groups, onChange: build→schedulePreview,
onApply: build→refresh(call(...)) })`. Si `build` rend `null`
(sélection manquante), l'aperçu s'éteint et OK ne part pas — comme
aujourd'hui.

## Quoi migrer, quoi laisser

- **À migrer** : les panneaux dont le flux est exactement
  ouvrir → éditer → aperçu → OK : Bossage, Enlèvement, Révolution,
  Rainure (groove), Congé, Chanfrein, Coque/épaisseur, Dépouille,
  Assistant de perçage, Répétitions linéaire/circulaire, Symétrie,
  Lissage, Balayage, Hélice, Texte, les quatre surfaciques, Combiner
  (booléennes) si son panneau suit le même flux.
- **À laisser tel quel** (bespoke) : équations, mesurer, évaluer,
  cotes d'esquisse, tout l'assemblage (insérer/déplacer/joint/répéter/
  interférences/éclaté), ouvrir/enregistrer/exporter, mise en plan,
  plan de référence si son flux diffère, édition de fonction existante
  (double-clic arbre). En cas de doute sur un panneau : le laisser et
  le noter.
- Les helpers partagés existants (`dressupPanel`, `revolvedPanel`,
  `surfacePanel`…) peuvent devenir des fabriques d'entrées du registry
  — c'est l'esprit.

## Garde-fous

- Diff net attendu : **négatif** dans `main.js` (c'est le but). Pas de
  nouvelle abstraction au-delà du registry + bind (pas de framework
  maison).
- Ne pas toucher à `panel.js`, ni aux jetons P005, ni à
  `invalidateSelections` — le bind les réutilise.
- Chaque entrée migrée doit produire **exactement** les mêmes appels
  serveur qu'avant (op + params). En cas d'écart découvert dans
  l'existant (bug latent), ne pas le corriger silencieusement : le
  noter dans la PR.

## Validation avant push

1. `node --check` sur chaque JS modifié/créé.
2. `node --test tests/js/*.test.mjs` — 50 verts (le solveur n'est pas
   concerné, mais le banc doit rester vert).
3. `python3 -m pytest tests/ -q` — 153 verts.
4. **Smoke local obligatoire** (c'est LE filet de ce refactor) :
   `scripts/smoke/README.md` — parcours vert, zéro erreur console.
5. Description de PR : tableau panneau → migré / laissé (raison), et le
   delta de lignes de `main.js`.
6. Commit : `[P011] registry des panneaux — dédoublonnage de main.js, zéro changement de comportement`.
