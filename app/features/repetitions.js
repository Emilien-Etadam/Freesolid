// Fonctions — répétitions linéaire et circulaire, symétrie.

import { num } from "../num.js";

// ---------- répétitions et symétrie ----------
// Fonctions à répéter : clic dans l'arbre (plusieurs, un second clic
// retire) ; vide = la dernière fonction. Direction : un axe d'origine ou
// une arête droite cliquée dans la zone graphique.

export function patternFeaturesGroup(ctx) {
  return {
    label: "Fonctions à répéter",
    rows: [{ type: "selection", key: "features", accepts: ["feature"],
             multiple: true, value: ctx?.selection?.(["feature"]) ?? null,
             hint: "Cliquez les fonctions dans l'arbre — vide : la dernière" }],
  };
}

export function patternFeaturesParams(v) {
  const items = v.features?.items ?? [];
  return items.length ? { features: items.map((i) => i.name) } : {};
}

export function patternDirectionRows(defaultAxis) {
  return [
    { type: "select", key: "dirKind", value: "axis",
      options: [["axis", "Axe d'origine"], ["edge", "Arête"]] },
    { type: "select", key: "axis", value: defaultAxis,
      options: [["X", "Axe X"], ["Y", "Axe Y"], ["Z", "Axe Z"]],
      showIf: (v) => v.dirKind !== "edge" },
    { type: "selection", key: "edge", accepts: ["edges"],
      hint: "Cliquez une arête droite",
      showIf: (v) => v.dirKind === "edge" },
    { type: "check", key: "reversed", label: "Inverser la direction",
      value: false },
  ];
}

/** Deuxième direction d'un réseau linéaire → params, null si invalide. */
export function linearSecondDirection(v) {
  const length2 = num(v.length2);
  const count2 = parseInt(v.count2, 10);
  if (!(length2 > 0) || !(count2 >= 2)) return null;
  return { axis2: v.axis2 || "Y", length2, count2, reversed2: !!v.reversed2 };
}

export function patternDirectionParams(v) {
  const params = { reversed: !!v.reversed };
  const edge = v.edge?.edges?.[0];
  if (v.dirKind === "edge" && edge != null) params.edge = edge;
  else params.axis = v.axis;
  return params;
}

export const REPETITIONS = [
  {
    button: "btn-linpattern",
    op: "add_linear_pattern",
    icon: "linear_pattern",
    title: "Réseau linéaire",
    groups: (ctx) => [
      patternFeaturesGroup(ctx),
      {
        label: "Direction 1",
        rows: [
          ...patternDirectionRows("X"),
          { type: "select", key: "mode", value: "spacing",
            options: [["spacing", "Pas entre occurrences"],
                      ["extent", "Longueur totale"]] },
          { type: "number", key: "length", label: "Distance",
            value: 20, unit: "mm", min: 0.01 },
          { type: "number", key: "count", label: "Nombre d'occurrences",
            value: 3, min: 2, step: 1 },
        ],
      },
      {
        label: "Direction 2",
        rows: [
          { type: "check", key: "dir2", label: "Deuxième direction",
            value: false },
          { type: "select", key: "axis2", value: "Y",
            options: [["X", "Axe X"], ["Y", "Axe Y"], ["Z", "Axe Z"]],
            showIf: (v) => v.dir2 },
          { type: "check", key: "reversed2", label: "Inverser la direction",
            value: false, showIf: (v) => v.dir2 },
          { type: "number", key: "length2", label: "Distance",
            value: 20, unit: "mm", min: 0.01, showIf: (v) => v.dir2 },
          { type: "number", key: "count2", label: "Nombre d'occurrences",
            value: 2, min: 2, step: 1, showIf: (v) => v.dir2 },
        ],
      },
    ],
    build: (v) => {
      const length = num(v.length);
      const count = parseInt(v.count, 10);
      const second = v.dir2 ? linearSecondDirection(v) : {};
      return length && count >= 2 && second
        ? { op: "add_linear_pattern",
            params: { ...patternDirectionParams(v), length, count,
                      spacing: v.mode === "spacing", ...second,
                      ...patternFeaturesParams(v) } }
        : null;
    },
    invalid: "Valeurs invalides",
    refresh: "part",
  },
  {
    button: "btn-polpattern",
    op: "add_polar_pattern",
    icon: "polar_pattern",
    title: "Réseau circulaire",
    groups: (ctx) => [
      patternFeaturesGroup(ctx),
      {
        label: "Axe",
        rows: [
          ...patternDirectionRows("Z"),
          { type: "number", key: "angle", label: "Angle total", value: 360,
            unit: "°", min: 0.01 },
          { type: "number", key: "count", label: "Nombre d'occurrences",
            value: 4, min: 2, step: 1 },
        ],
      },
    ],
    build: (v) => {
      const angle = num(v.angle);
      const count = parseInt(v.count, 10);
      return angle && count >= 2
        ? { op: "add_polar_pattern",
            params: { ...patternDirectionParams(v), count, angle,
                      ...patternFeaturesParams(v) } }
        : null;
    },
    invalid: "Valeurs invalides",
    refresh: "part",
  },
  {
    button: "btn-mirror",
    op: "add_mirror",
    icon: "mirror",
    title: "Symétrie",
    groups: (ctx) => [
      patternFeaturesGroup(ctx),
      {
        label: "Plan de symétrie",
        rows: [
          { type: "select", key: "plane", value: "YZ",
            options: [["YZ", "Plan de droite"], ["XZ", "Plan de face"],
                      ["XY", "Plan de dessus"]] },
        ],
      },
    ],
    build: (v) => ({ op: "add_mirror",
                     params: { plane: v.plane, ...patternFeaturesParams(v) } }),
    refresh: "part",
  },
];
