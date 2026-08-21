// Cotes — libellé, ancrage 2D, champ d'édition. Sans Three.js : le
// sprite 3D reste dans sketch.js ; le panneau est le même en esquisse
// et hors esquisse.

import { num } from "./num.js";

/** Libellé d'une cote : « largeur = 60.00 », préfixe Σ si expression. */
export function dimLabel(dim) {
  const number = dim.type === "Angle"
    ? (dim.value * 180 / Math.PI).toFixed(1) + "°"
    : Number(dim.value).toFixed(2);
  return (dim.expr ? "Σ " : "")
    + (dim.name ? dim.name + " = " : "") + number;
}

/** Position 2D d'une cote d'esquisse, dans le plan de l'esquisse. */
export function sketchDimAnchor(dim, entities) {
  const entity = (entities ?? []).find((item) => item.id === dim.geo);
  if (!entity) return null;
  if (entity.type === "line" && entity.p1 && entity.p2) {
    return {
      x: (entity.p1[0] + entity.p2[0]) / 2,
      y: (entity.p1[1] + entity.p2[1]) / 2 + 4,
    };
  }
  const center = entity.c || [0, 0];
  const radius = entity.r ?? 0;
  return { x: center[0] + radius * 0.7, y: center[1] + radius * 0.7 };
}

/**
 * Champ d'édition de cote — le même en esquisse et hors esquisse.
 * `onApply(values, { shown, isSketchAngle })` envoie sketch_set_dim
 * ou set_params selon l'appelant.
 */
export function openDimEditor({ panel, dim, onApply, onCancel }) {
  const isSketchAngle = dim.kind === "sketch" && dim.type === "Angle";
  const shown = dim.expr
    || (isSketchAngle
      ? (dim.value * 180 / Math.PI).toFixed(2)
      : String(+Number(dim.value).toFixed(4)));
  const unit = isSketchAngle || dim.unit === "°" ? "°" : (dim.unit || "mm");
  panel.open({
    icon: "Constraint_Dimension.svg",
    title: "Cote" + (dim.name ? ` — ${dim.name}` : ""),
    groups: [{
      label: "Cote",
      rows: [
        { type: "text", key: "name", label: "Nom", value: dim.name || "",
          placeholder: "largeur",
          showIf: () => dim.kind === "sketch" },
        { type: "text", key: "value", label: "Valeur ou expression",
          value: shown, unit },
      ],
    }],
    note: "Expression : « Variables.Largeur / 2 » ou " +
          "« .Constraints.largeur * 2 » (les noms de cotes de cette " +
          "esquisse s'utilisent avec .Constraints.nom)",
    onApply: (values) => onApply(values, { shown, isSketchAngle }),
    onCancel,
  });
}

export function dimEditPayload(values, dim, { shown, isSketchAngle }) {
  const payload = {};
  if (dim.kind === "sketch") {
    const name = (values.name ?? "").trim();
    if (name !== (dim.name ?? "")) payload.name = name;
  }
  const raw = String(values.value ?? "").trim();
  if (raw && raw !== shown) {
    if (/^-?\d+([.,]\d+)?$/.test(raw)) {
      const parsed = num(raw);
      payload.value = isSketchAngle ? parsed * Math.PI / 180 : parsed;
    } else {
      payload.expr = raw;
    }
  }
  return payload;
}
