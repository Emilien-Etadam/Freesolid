# P006 — Hygiène Three.js (dispose) + sélections de panneau invalidées

Couvre les constats **1.5** (IDs périmés dans le PropertyManager),
**4.1, 4.2** (fuites GPU majeures) et, même motif en plus petit,
**4.4, 4.5** de `docs/audit/2026-08-audit.md`. Périmètre :
`app/main.js`, `app/sketch.js`, `app/panel.js`. Aucune modification
moteur.

## 1. Sélections de panneau invalidées à chaque rebuild (1.5)

Invariant du projet : les ids de faces/arêtes meurent à chaque rebuild.
Le viewport le respecte (`selectedFaceId`/`selectedEdges` vidés dans
`showMesh`/`showEdgeLines`) ; le PropertyManager non — un panneau
Congé/Coque ouvert garde ses ids dans `values`, et un Ctrl+Z hors champ
de saisie reconstruit la pièce → OK applique des ids périmés.

- Ajouter à `app/panel.js` une méthode `invalidateSelections()` :
  pour chaque row de type `selection` du panneau actif, vider la valeur
  (tableau vide si `multiple`, sinon `null`), mettre à jour l'affichage
  de la row, et appeler `onChange` du spec (pour que l'aperçu se
  rafraîchisse/s'éteigne). No-op si aucun panneau ouvert.
- L'appeler côté `app/main.js` à l'endroit où le maillage est remplacé
  (`showMesh`), et informer : `say("Sélections réinitialisées — la
  géométrie a changé.")` **uniquement** si au moins une valeur a été
  vidée (la méthode retourne ce compte).
- Ne PAS fermer le panneau : l'utilisateur resélectionne et continue,
  comme dans SolidWorks.
- Attention au cycle : `invalidateSelections` → `onChange` →
  `schedulePreview` est acceptable (le jeton P005 protège), mais le
  rebuild déclenché par un Apply de ce même panneau ne doit pas
  re-noter l'utilisateur pour rien : après un `onApply`, le panneau est
  déjà fermé (`panel.open`/`close` gèrent), donc no-op — le vérifier.

## 2. Dispose systématique des allocations Three.js (4.1, 4.2, 4.4, 4.5)

Règle : **qui alloue dispose**. Ajouter dans `app/main.js` (exporté ou
dupliqué proprement dans `sketch.js` si l'import croisé est laid) un
helper :

```js
function disposeSubtree(root) {
  root.traverse((obj) => {
    obj.geometry?.dispose();
    const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
    for (const m of mats) {
      if (m && m.userData?.own) { m.map?.dispose(); m.dispose(); }
    }
  });
}
```

Convention : les matériaux **partagés** (constantes de module :
`lineMaterial`, `constructionMaterial`, `pointMaterial`, matériaux de
faces, etc.) ne portent pas le flag et ne sont jamais disposés ; tout
matériau créé **par allocation** (sprites de cotes et de labels de
plans — `SpriteMaterial` + `CanvasTexture` —, outlines d'assemblage si
non partagés) est marqué `material.userData.own = true` à la création.

Sites à traiter :

- **`app/sketch.js` `redraw()`** (4.1) : `disposeSubtree(group)` avant
  `group.clear()`. La `previewLine` (réutilisée entre redraws) ne doit
  pas être disposée : la retirer du groupe avant le dispose puis la
  re-ajouter, ou l'exclure explicitement. Vérifier aussi `exit()`
  (le `group.clear()` de sortie d'esquisse doit disposer pareil, la
  previewLine incluse cette fois — elle est recréée à chaque `enter`).
- **`app/main.js` `rebuildPlanes()`** (4.2) : dispose avant
  `planesGroup.clear()`. Bonus autorisé : ne reconstruire que si la
  taille calculée des plans change (cache de la dernière taille) —
  les sprites de labels sont la partie chère.
- **`refreshDatumGhost`** (4.4) : dispose avant remove.
- **Outlines d'assemblage** (4.5) : un seul `LineBasicMaterial`
  partagé de module au lieu d'un par outline (les géométries, elles,
  sont déjà disposées — ne pas y toucher).
- Les sprites de cotes (`makeDimSprite`) et labels de plans doivent
  poser `userData.own = true` sur leur matériau.

Ne PAS toucher aux chemins déjà corrects (mesh pièce, ghost — audit
4.8) sauf pour poser la convention `userData.own` si un site en a
besoin.

## Validation avant push

1. `node --check` sur chaque JS modifié.
2. `python3 -m pytest tests/ -q` — inchangé (143).
3. Dans la description de PR : la liste de chaque site d'allocation
   Three.js touché avec son point de dispose correspondant (le « qui
   alloue dispose » rendu vérifiable), et le scénario 1.5 rejoué à la
   main si un navigateur est disponible (panneau Congé ouvert →
   Ctrl+Z → la sélection s'est vidée, pas d'application d'ids morts).
4. Commit : `[P006] hygiène Three.js — dispose systématique + sélections panneau invalidées au rebuild`.
