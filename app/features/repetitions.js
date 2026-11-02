// Fonctions — répétitions linéaire et circulaire, symétrie.

import { num } from "../num.js";

// ---------- répétitions et symétrie ----------
// Répéter des fonctions du corps actif, ou des corps entiers : chaque
// occurrence d'un corps devient un nouveau corps qui suit sa source
// (add_body_pattern).
// Fonctions à répéter : clic dans l'arbre (plusieurs, un second clic
// retire) ; vide = la dernière fonction. Direction : un axe d'origine ou
// une arête droite cliquée dans la zone graphique.
// Corps concernés : les enlèvements de matière répétés creusent aussi
// les autres corps choisis.

const repeatsBodies = (v) => v.target === "bodies";

export function patternTargetGroup() {
  return {
    label: "Répéter",
    rows: [{ type: "select", key: "target", value: "features",
             options: [["features", "Des fonctions"],
                       ["bodies", "Des corps"]] }],
  };
}

/** Une case par corps de la pièce ; le corps actif est coché. */
export function patternBodiesGroup(ctx) {
  return {
    label: "Corps à répéter",
    showIf: repeatsBodies,
    rows: (ctx?.lastTree?.bodies ?? []).map((body) => ({
      type: "check", key: `src:${body.name}`, label: body.label,
      value: !!body.active })),
  };
}

/** Corps cochés → noms, dans l'ordre de l'arbre. */
export function patternBodiesParams(v) {
  return Object.keys(v).filter((key) => key.startsWith("src:") && v[key])
    .map((key) => key.slice(4));
}

const otherBodies = (ctx) =>
  (ctx?.lastTree?.bodies ?? []).filter((body) => !body.active);

/** Corps concernés : rien tant que la pièce n'a qu'un corps. */
export function patternScopeGroup(ctx) {
  const others = otherBodies(ctx);
  if (!others.length) return null;
  return {
    label: "Corps concernés",
    showIf: (v) => !repeatsBodies(v),
    rows: [
      { type: "select", key: "scopeMode", value: "active",
        options: [["active", "Corps actif seulement"],
                  ["all", "Tous les corps"],
                  ["selected", "Corps choisis"]] },
      ...others.map((body) => ({
        type: "check", key: `scope:${body.name}`, label: body.label,
        value: false, showIf: (v) => v.scopeMode === "selected" })),
      { type: "note", readonly: true,
        text: "Seuls les enlèvements de matière creusent les autres corps",
        showIf: (v) => v.scopeMode && v.scopeMode !== "active" },
    ],
  };
}

export function patternScopeParams(v, ctx) {
  const others = otherBodies(ctx);
  const chosen = v.scopeMode === "all" ? others
    : v.scopeMode === "selected"
      ? others.filter((body) => v[`scope:${body.name}`]) : [];
  return chosen.length ? { scope: chosen.map((body) => body.name) } : {};
}

/** Groupes d'une répétition : quoi répéter, puis `own` (direction, plan). */
function patternGroups(ctx, own) {
  return [
    patternTargetGroup(),
    { ...patternFeaturesGroup(ctx), showIf: (v) => !repeatsBodies(v) },
    patternBodiesGroup(ctx),
    ...own,
    patternScopeGroup(ctx),
  ].filter(Boolean);
}

/** Des corps → add_body_pattern (`kind`) ; des fonctions → `op`. */
function patternBuild(v, ctx, op, kind, params) {
  if (repeatsBodies(v)) {
    const bodies = patternBodiesParams(v);
    return bodies.length
      ? { op: "add_body_pattern", params: { kind, bodies, ...params } }
      : null;
  }
  return { op, params: { ...params, ...patternFeaturesParams(v),
                         ...patternScopeParams(v, ctx) } };
}

function patternInvalid(v) {
  return repeatsBodies(v) && !patternBodiesParams(v).length
    ? "Cochez au moins un corps à répéter" : "Valeurs invalides";
}

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
    op: ["add_linear_pattern", "add_body_pattern"],
    icon: "linear_pattern",
    title: "Réseau linéaire",
    groups: (ctx) => patternGroups(ctx, [
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
    ]),
    build: (v, ctx) => {
      const length = num(v.length);
      const count = parseInt(v.count, 10);
      const second = v.dir2 ? linearSecondDirection(v) : {};
      return length && count >= 2 && second
        ? patternBuild(v, ctx, "add_linear_pattern", "linear",
          { ...patternDirectionParams(v), length, count,
            spacing: v.mode === "spacing", ...second })
        : null;
    },
    invalid: patternInvalid,
    refresh: "part",
  },
  {
    button: "btn-polpattern",
    op: ["add_polar_pattern", "add_body_pattern"],
    icon: "polar_pattern",
    title: "Réseau circulaire",
    groups: (ctx) => patternGroups(ctx, [
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
    ]),
    build: (v, ctx) => {
      const angle = num(v.angle);
      const count = parseInt(v.count, 10);
      return angle && count >= 2
        ? patternBuild(v, ctx, "add_polar_pattern", "polar",
          { ...patternDirectionParams(v), count, angle })
        : null;
    },
    invalid: patternInvalid,
    refresh: "part",
  },
  {
    button: "btn-mirror",
    op: ["add_mirror", "add_body_pattern"],
    icon: "mirror",
    title: "Symétrie",
    groups: (ctx) => patternGroups(ctx, [
      {
        label: "Plan de symétrie",
        rows: [
          { type: "select", key: "plane", value: "YZ",
            options: [["YZ", "Plan de droite"], ["XZ", "Plan de face"],
                      ["XY", "Plan de dessus"]] },
        ],
      },
    ]),
    build: (v, ctx) => patternBuild(v, ctx, "add_mirror", "mirror",
                                    { plane: v.plane }),
    invalid: patternInvalid,
    refresh: "part",
  },
];
