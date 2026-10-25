// Fonctions — habillage : congé, chanfrein (arête, sommet), coque,
// dépouille.

import { t } from "../i18n.js";
import { num, plainNumber } from "../num.js";
import {
  dressup,
  measureRow,
  readMeasure,
  sameMeasure,
  storedMeasure,
} from "./commun.js";

function dressupParams(sel) {
  return sel.kind === "edges"
    ? { edges: sel.edges } : { face: sel.face };
}

/** Coque : faces à ouvrir (une ou plusieurs), épaisseur, sens. */
export function shellBuild(v) {
  const faces = (v.faces?.items ?? []).map((item) => item.face)
    .filter((face) => face != null);
  const thickness = num(v.thickness);
  if (!faces.length || !(thickness > 0)) return null;
  return { op: "add_thickness",
           params: { faces, thickness, outward: !!v.outward } };
}

function expressionText(raw) {
  const text = String(raw ?? "").trim();
  return text.length > 0 && plainNumber(text) == null;
}

const CHAMFER_KINDS = new Set(["egale", "deux", "angle"]);

/** Champs du panneau : le type décide de ce qui est visible. */
export function chamferRows({
  kind = "egale", size = 2, size2 = 2, angle = 45, flip = false,
} = {}) {
  return [
    { type: "select", key: "kind", value: kind, label: "Type de chanfrein",
      options: [["egale", "Distance égale"], ["deux", "Deux distances"],
                ["angle", "Distance et angle"]] },
    measureRow("size", "Distance", size, "mm"),
    measureRow("size2", "Seconde distance", size2, "mm",
      (v) => v.kind === "deux"),
    measureRow("angle", "Angle", angle, "°",
      (v) => v.kind === "angle"),
    { type: "check", key: "flip", label: "Inverser les côtés",
      value: !!flip, showIf: (v) => v.kind === "deux" || v.kind === "angle" },
  ];
}

/** Valeur affichée : l'expression si la cote `key` en a une, sinon le nombre. */
export function chamferFieldValue(params, key, fallback) {
  const found = (params ?? []).find((item) => item.key === key);
  if (found?.expr) return found.expr;
  if (found && found.value != null) return found.value;
  return fallback;
}

/** Chanfrein de sommet : une distance égale, ou une par arête. */
export function vertexChamferRows({ distances = [2, 2, 2] } = {}) {
  const same = distances.every((d) => d === distances[0]);
  return [
    { type: "select", key: "vkind", value: same ? "egale" : "trois",
      options: [["egale", "Distance égale"], ["trois", "Une par arête"]] },
    { type: "number", key: "d1", label: "Distance", value: distances[0],
      unit: "mm", min: 0.01 },
    { type: "number", key: "d2", label: "Distance 2", value: distances[1],
      unit: "mm", min: 0.01, showIf: (v) => v.vkind === "trois" },
    { type: "number", key: "d3", label: "Distance 3", value: distances[2],
      unit: "mm", min: 0.01, showIf: (v) => v.vkind === "trois" },
  ];
}

/** Distances du panneau → [d] ou [d1, d2, d3] ; null si l'une est fausse. */
export function vertexChamferDistances(v) {
  const keys = v.vkind === "trois" ? ["d1", "d2", "d3"] : ["d1"];
  const values = keys.map((key) => num(v[key]));
  return values.every((d) => d > 0) ? values : null;
}

/** Params `add_chamfer`, ou null si les champs visibles sont invalides. */
export function chamferCreationParams(v) {
  const kind = v.kind || "egale";
  if (!CHAMFER_KINDS.has(kind)) return null;
  const size = plainNumber(v.size);
  if (!(size > 0)) return null;
  const params = { size, chamfer_type: kind };
  if (kind === "deux") {
    const size2 = plainNumber(v.size2);
    if (!(size2 > 0)) return null;
    params.size2 = size2;
    params.flip = !!v.flip;
  } else if (kind === "angle") {
    const angle = plainNumber(v.angle);
    if (!(angle > 0) || !(angle < 90)) return null;
    params.angle = angle;
    params.flip = !!v.flip;
  }
  return params;
}

/** Message français quand la saisie ne peut pas être appliquée. */
export function chamferProblem(v) {
  const kind = v.kind || "egale";
  const size = plainNumber(v.size);
  if (size == null) {
    if (!expressionText(v.size)) return "Distance de chanfrein invalide";
  } else if (!(size > 0)) {
    return "Distance de chanfrein invalide";
  }
  if (kind === "deux") {
    const size2 = plainNumber(v.size2);
    if (size2 == null) {
      if (!expressionText(v.size2)) return "Seconde distance de chanfrein invalide";
    } else if (!(size2 > 0)) {
      return "Seconde distance de chanfrein invalide";
    }
  }
  if (kind === "angle") {
    const angle = plainNumber(v.angle);
    if (angle == null) {
      if (!expressionText(v.angle)) return "Angle de chanfrein invalide";
    } else if (!(angle > 0) || !(angle < 90)) {
      return "Angle de chanfrein invalide";
    }
  }
  return "Valeurs du chanfrein invalides";
}

/**
 * Valeurs `set_params` pour rééditer un chanfrein.
 * `{}` si rien n'a changé, `null` si la saisie est invalide.
 */
export function chamferEditValues(v, chamfer, params) {
  const kind = v.kind || "egale";
  if (!CHAMFER_KINDS.has(kind)) return null;
  const sizeStored = storedMeasure(params, "size", chamfer.size);
  const size = readMeasure(v.size, sizeStored, { min: 0, max: Infinity });
  if (size == null) return null;
  const values = { kind, size };
  const flip = kind === "egale" ? false : !!v.flip;
  let secondSame = true;
  if (kind === "deux") {
    const stored = storedMeasure(params, "size2", chamfer.size2);
    const size2 = readMeasure(v.size2, stored, { min: 0, max: Infinity });
    if (size2 == null) return null;
    values.size2 = size2;
    values.flip = flip;
    secondSame = sameMeasure(size2, stored);
  } else if (kind === "angle") {
    const stored = storedMeasure(params, "angle", chamfer.angle);
    const angle = readMeasure(v.angle, stored, { min: 0, max: 90 });
    if (angle == null) return null;
    values.angle = angle;
    values.flip = flip;
    secondSame = sameMeasure(angle, stored);
  } else {
    values.flip = false;
  }
  const unchanged = kind === chamfer.type
    && flip === !!chamfer.flip
    && sameMeasure(size, sizeStored)
    && secondSame;
  return unchanged ? {} : values;
}

export const HABILLAGE = [
  dressup({
    button: "btn-fillet",
    op: "add_fillet",
    icon: "fillet", title: "Congé",
    selectionLabel: "Éléments à arrondir",
    accepts: ["edges", "face"],
    hint: "Cliquez des arêtes (Ctrl = ajouter) ou une face",
    group: "Paramètres du congé",
    rows: [{ type: "number", key: "radius", label: "Rayon", value: 3,
             unit: "mm", min: 0.01 }],
    build: (v) => {
      const radius = num(v.radius);
      return radius > 0
        ? { op: "add_fillet",
            params: { ...dressupParams(v.sel), radius } }
        : null;
    },
  }),
  dressup({
    button: "btn-chamfer",
    op: "add_chamfer",
    icon: "chamfer", title: "Chanfrein",
    selectionLabel: "Éléments à chanfreiner",
    accepts: ["edges", "face"],
    hint: "Cliquez des arêtes (Ctrl = ajouter) ou une face",
    group: "Paramètres du chanfrein",
    rows: chamferRows(),
    build: (v) => {
      const params = chamferCreationParams(v);
      return params
        ? { op: "add_chamfer",
            params: { ...dressupParams(v.sel), ...params } }
        : null;
    },
    invalid: (v) => chamferProblem(v),
  }),
  {
    button: "btn-vertex-chamfer",
    op: "add_vertex_chamfer",
    icon: "vertex_chamfer", title: "Chanfrein de sommet",
    groups: () => [
      { label: "Sommet",
        rows: [{ type: "selection", key: "pos", accepts: ["vertex"],
                 hint: "Cliquez près d'un coin de la pièce" }] },
      { label: "Distances", rows: vertexChamferRows() },
    ],
    build: (v) => {
      const item = v.pos?.kind === "vertex" ? v.pos : null;
      const distances = vertexChamferDistances(v);
      return item && distances
        ? { op: "add_vertex_chamfer",
            params: { point: [item.x, item.y, item.z], distances } }
        : null;
    },
    invalid: (v) => (v.pos ? "Distance de chanfrein invalide"
      : "Cliquez près d'un coin de la pièce"),
    refresh: "part",
  },
  {
    button: "btn-shell",
    op: "add_thickness",
    icon: "shell", title: "Coque",
    dressup: true,
    groups: (ctx) => {
      const first = ctx.selection(["face"]);
      return [
        { label: "Faces à supprimer",
          rows: [{ type: "selection", key: "faces", accepts: ["face"],
                   multiple: true,
                   hint: "Cliquez les faces à ouvrir — un second clic retire",
                   value: { kind: "face",
                            items: first?.face != null ? [first] : [] } }] },
        { label: "Paramètres",
          rows: [
            { type: "number", key: "thickness", label: "Épaisseur",
              value: 2, unit: "mm", min: 0.01 },
            { type: "check", key: "outward", label: "Coque vers l'extérieur",
              value: false },
          ] },
      ];
    },
    build: (v) => shellBuild(v),
    invalid: (v) => ((v.faces?.items ?? []).length
      ? "Épaisseur invalide"
      : { text: t("Coque : cliquez au moins une face à ouvrir"), tone: "guide" }),
    refresh: "part",
  },
  dressup({
    button: "btn-draft",
    op: "add_draft",
    icon: "draft", title: "Dépouille",
    selectionLabel: "Faces à dépouiller",
    group: "Angle de dépouille",
    rows: [
      { type: "number", key: "angle", label: "Angle", value: 3,
        unit: "°", min: 0.01 },
      { type: "select", key: "neutral", value: "XY", label: "Plan neutre",
        options: [["XY", "Plan de dessus"], ["XZ", "Plan de face"],
                  ["YZ", "Plan de droite"]] },
    ],
    build: (v) => {
      const angle = num(v.angle);
      return angle > 0
        ? { op: "add_draft",
            params: { face: v.sel.face, angle, neutral: v.neutral } }
        : null;
    },
  }),
];
