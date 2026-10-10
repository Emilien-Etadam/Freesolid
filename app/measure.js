// Évaluer (propriétés de masse) et Mesurer (distance entre deux éléments).
// `measuring` reste dans main.js : le survol, le cadre de sélection et
// le menu le lisent. Ici on le met à jour via ctx.

import { t } from "./i18n.js";
import { num } from "./num.js";

/** Élément visé par Mesurer : l'arête survolée, sinon la face, sinon rien. */
export function measurePick(hoveredEdgeGroup, edgeGroups, hoveredGroup, meshGroups) {
  if (hoveredEdgeGroup >= 0) {
    return { kind: "edge", id: edgeGroups[hoveredEdgeGroup].edgeId };
  }
  if (hoveredGroup >= 0) {
    return { kind: "face", id: meshGroups[hoveredGroup].faceId };
  }
  return null;
}

/** Branche Évaluer et Mesurer. `onMeasurePointerUp` consomme le clic
 *  quand la mesure est en cours. */
export function installMeasure(ctx) {
  const { call, say, panel } = ctx;
  let lastDensity = 1.24; // PLA — le défaut d'un atelier d'impression 3D
  let measureFirst = null;

  async function openEvaluatePanel() {
    let props;
    try {
      props = await call("mass_properties", { density: lastDensity });
    } catch (error) {
      say(error.message, true);
      return;
    }
    const fixed = (v, n = 1) => v.toFixed(n);
    panel.open({
      icon: "view-measurement.svg",
      title: t("Évaluer"),
      groups: [
        { label: t("Propriétés de masse"),
          rows: [{ type: "list", items: [
            { label: t("Volume : {v} cm³",
              { v: fixed(props.volume_mm3 / 1000, 2) }) },
            { label: t("Masse : {m} g (à {d} g/cm³)",
              { m: fixed(props.mass_g), d: props.density }) },
            { label: t("Surface : {s} cm²", { s: fixed(props.area_mm2 / 100) }) },
            { label: t("Centre de gravité : ")
                     + props.center_of_mass.map((v) => fixed(v)).join(", ") },
            { label: t("Encombrement : ")
                     + props.bounding_box.map((v) => fixed(v)).join(" × ")
                     + " mm" },
          ] }] },
        { label: t("Matière"),
          rows: [{ type: "number", key: "density", label: t("Densité"),
                   value: lastDensity, unit: "g/cm³", min: 0.001 }] },
      ],
      note: t("PLA ≈ 1,24 · PETG ≈ 1,27 · ABS ≈ 1,04 · Alu ≈ 2,70 · " +
            "Acier ≈ 7,85 — OK recalcule avec la densité saisie"),
      onApply: (v) => {
        const density = num(v.density);
        if (density > 0) {
          lastDensity = density;
          openEvaluatePanel();
        }
      },
    });
  }

  document.getElementById("btn-evaluate")
    .addEventListener("click", openEvaluatePanel);

  document.getElementById("btn-measure").addEventListener("click", () => {
    if (!ctx.lastTree) {
      say("Mesurer : ouvrez d'abord une pièce", true);
      return;
    }
    ctx.measuring = true;
    measureFirst = null;
    say("Mesurer : cliquez deux éléments (faces ou arêtes) — Échap pour " +
        "quitter");
  });

  function onMeasurePointerUp() {
    if (!ctx.measuring) return false;
    const pick = measurePick(
      ctx.hoveredEdgeGroup, ctx.edgeGroups, ctx.hoveredGroup, ctx.meshGroups);
    if (!pick) return true;
    const label = (p) => (p.kind === "edge"
      ? t("arête {n}", { n: p.id }) : t("face {n}", { n: p.id }));
    if (!measureFirst) {
      measureFirst = pick;
      say(t("Mesurer : {a} — cliquez le second élément", { a: label(pick) }));
    } else {
      const first = measureFirst;
      ctx.measuring = false;
      measureFirst = null;
      call("measure", { a_kind: first.kind, a_id: first.id,
                        b_kind: pick.kind, b_id: pick.id })
        .then((r) => say(t("Distance {a} ↔ {b} : {d} mm",
          { a: label(first), b: label(pick), d: r.distance.toFixed(3) })))
        .catch((error) => say(error.message, true));
    }
    return true;
  }

  function cancelMeasure() {
    ctx.measuring = false;
    measureFirst = null;
    say("Mesure annulée.");
  }

  return { onMeasurePointerUp, cancelMeasure };
}
