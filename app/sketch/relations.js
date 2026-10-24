// Esquisse : les relations manuelles (boutons de la barre, selon la
// sélection) et le panneau Relations, qui les liste et les supprime.

import { t } from "../i18n.js";
import { applicableRelations } from "../geom2d.js";

export function installRelations(sk) {
  const { call, say, mode, safe, uniqueSelectionGeos, openEntityPanel } = sk;

  //: relation -> nombre d'entités attendues. symmetric : 2 points + l'axe.
  const CONSTRAINT_NEEDS = {
    horizontal: 1, vertical: 1, fixed: 1,
    parallel: 2, perpendicular: 2, equal: 2, tangent: 2,
    coincident: 2, concentric: 2, collinear: 2, midpoint: 2,
    onobject: 2, coradial: 2,
    symmetric: 3, intersection: 3,
  };

  function applyConstraint(kind) {
    if (!mode.state) return;
    let needed = CONSTRAINT_NEEDS[kind];
    // Horizontale / verticale : une ligne, ou deux points alignés.
    const lastTwo = mode.selection.slice(-2);
    if ((kind === "horizontal" || kind === "vertical") && lastTwo.length === 2
        && lastTwo.every((pick) => pick.point != null)) {
      needed = 2;
    }
    if (mode.selection.length < needed) {
      say(t("Relation : sélectionnez d'abord {n} entité(s) avec l'outil Sélectionner",
        { n: needed }), true);
      return;
    }
    const selection = mode.selection.slice(-needed);
    const params = { sketch: mode.state.sketch, kind,
                     geo1: selection[0].geo };
    if (selection[0].point != null) params.point1 = selection[0].point;
    if (selection[1]) {
      params.geo2 = selection[1].geo;
      if (selection[1].point != null) params.point2 = selection[1].point;
    }
    if (needed >= 3 && selection[2]) params.geo3 = selection[2].geo;
    safe(call("sketch_constrain", params));
  }

  for (const kind of Object.keys(CONSTRAINT_NEEDS)) {
    document.getElementById("sk-c-" + kind)
      .addEventListener("click", () => applyConstraint(kind));
  }

  /** Avec une sélection, seules les relations qu'elle permet restent
   *  actives (et sont mises en avant) ; sans sélection, toutes. */
  function updateRelationButtons() {
    const selection = mode.active ? mode.selection : [];
    const possible = selection.length
      ? applicableRelations(selection, mode.state?.entities) : null;
    for (const kind of Object.keys(CONSTRAINT_NEEDS)) {
      const button = document.getElementById("sk-c-" + kind);
      if (!button) continue;
      button.disabled = !!possible && !possible.includes(kind);
      button.classList.toggle("suggest", !!possible?.includes(kind));
    }
  }

  // ---------- panneau Relations (voir et supprimer) ----------

  async function openRelationsPanel() {
    if (!mode.state) return;
    if (uniqueSelectionGeos().length !== 1) {
      say("Relations : sélectionnez d'abord UNE entité " +
          "(outil Sélectionner)", true);
      return;
    }
    await openEntityPanel(uniqueSelectionGeos()[0]);
  }

  document.getElementById("sk-relations")
    .addEventListener("click", openRelationsPanel);

  return { updateRelationButtons };
}
