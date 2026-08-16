// Découpe de l'historique autour de la barre de retour.
// Module pur — testable en Node, sans DOM.

function isFreeSketchType(type) {
  return type === "Sketcher::SketchObject";
}

function isVolumeRow(row) {
  return !row.surface && !isFreeSketchType(row.item.type);
}

/** Lignes top-niveau (fonctions + esquisses libres + surfaces),
 *  ordonnées par `order` (index document). */
export function chronologicalHistory(features, surfaces) {
  const featureList = features ?? [];
  const surfaceList = surfaces ?? [];
  const rows = [];
  for (const [index, item] of featureList.entries()) {
    rows.push({ item, surface: false, index });
  }
  for (const [index, item] of surfaceList.entries()) {
    rows.push({ item, surface: true, index: featureList.length + index });
  }
  rows.sort((a, b) => {
    const oa = typeof a.item.order === "number" ? a.item.order : a.index + 1e6;
    const ob = typeof b.item.order === "number" ? b.item.order : b.index + 1e6;
    if (oa !== ob) return oa - ob;
    return a.index - b.index;
  });
  return rows;
}

/** Sépare l'historique en `before` / `after` la barre de retour.
 *
 *  Une surface ou esquisse libre est *après* ssi `rolled_back` est vrai.
 *  Une fonction volumique est après le tip (tip absent + fonctions
 *  présentes = toutes après). Barre `"none"` si aucune ligne. */
export function splitHistoryAroundBar(features, surfaces, tip) {
  const history = chronologicalHistory(features, surfaces);
  if (history.length === 0) {
    return { bar: "none", before: [], after: [] };
  }
  const hasVolume = history.some(isVolumeRow);
  const before = [];
  const after = [];
  let passedTip = false;
  for (const row of history) {
    if (!isVolumeRow(row)) {
      if (row.item.rolled_back) after.push(row);
      else before.push(row);
    } else if (!tip && hasVolume) {
      after.push(row);
    } else if (!passedTip) {
      before.push(row);
      if (row.item.name === tip) passedTip = true;
    } else {
      after.push(row);
    }
  }
  return {
    bar: before.length === 0 ? "start" : "middle",
    before,
    after,
  };
}
