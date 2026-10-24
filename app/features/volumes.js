// Fonctions — volumes : bossage, enlèvement, révolutions, perçage,
// lissage, balayage, hélice, gravure ; conditions de fin d'extrusion.

import { t } from "../i18n.js";
import { num, plainNumber } from "../num.js";
import {
  dressup,
  measureRow,
  NO_SKETCH_AVAILABLE,
  readMeasure,
  resolveProfileSketch,
  sameMeasure,
  storedMeasure,
} from "./commun.js";

/** Perçage : les centres cliqués (sélection « point ») → { face, points }
 *  pour le moteur, null s'il n'y en a pas (la dernière esquisse sert),
 *  { error } s'ils ne sont pas sur une même face. */
export function holePositions(sel) {
  const items = sel?.items ?? [];
  if (!items.length) return null;
  const face = items[0].face;
  if (items.some((i) => i.face !== face)) {
    return { error: "Perçage : les positions doivent être sur une même face" };
  }
  return { face, points: items.map((i) => [i.x, i.y, i.z]) };
}

/** Libellé d'un contour : son numéro et sa taille. */
export function contourLabel(index, size) {
  const [w, h] = size ?? [0, 0];
  return t("Contour {n} — {w} × {h} mm", {
    n: index + 1, w: plainNumber(w), h: plainNumber(h) });
}

/** Rangées « un contour, une case » pour une esquisse à plusieurs
 *  contours ; `used` : ceux déjà pris (tous si absent). */
export function contourRows(sizes, used = null) {
  return (sizes ?? []).map((size, i) => ({
    type: "check", key: `contour${i}`, label: contourLabel(i, size),
    value: used ? used.includes(i) : true }));
}

/** Contours cochés → liste d'index, `null` si tous (le profil entier),
 *  `[]` si aucun. */
export function checkedContours(v, count) {
  const chosen = [];
  for (let i = 0; i < count; i++) {
    if (v[`contour${i}`] !== false) chosen.push(i);
  }
  return chosen.length === count ? null : chosen;
}

/** Ligne d'arbre de l'esquisse choisie comme profil. */
function profileSketchEntry(ctx) {
  const profile = resolveProfileSketch(ctx);
  if (!profile) return null;
  const stack = [...(ctx.lastTree?.features ?? [])];
  while (stack.length) {
    const item = stack.pop();
    if (item.name === profile.name) return item;
    if (item.children) stack.push(...item.children);
  }
  return null;
}

/** Fonctions à profil d'esquisse : ligne « Profil : … », params.sketch
 *  si présélection, garde si aucune esquisse disponible. */
function withSketchProfile(entry) {
  return {
    ...entry,
    sketchProfile: true,
    groups: (ctx) => {
      const profile = resolveProfileSketch(ctx);
      const groups = typeof entry.groups === "function"
        ? entry.groups(ctx) : entry.groups;
      const sizes = profileSketchEntry(ctx)?.contours;
      return [
        { label: "Profil",
          rows: [{ type: "note",
            text: t("Profil : {p}", { p: profile ? profile.label : "—" }) }] },
        ...(sizes?.length > 1
          ? [{ label: "Contours", rows: contourRows(sizes) }] : []),
        ...groups,
      ];
    },
    build: (v, ctx) => {
      const built = entry.build(v, ctx);
      if (!built) return null;
      if (ctx.selectedSketch?.name) {
        built.params = { ...built.params, sketch: ctx.selectedSketch.name };
      }
      const sizes = profileSketchEntry(ctx)?.contours;
      if (sizes?.length > 1) {
        const contours = checkedContours(v, sizes.length);
        if (contours && !contours.length) return null;
        if (contours) built.params = { ...built.params, contours };
      }
      return built;
    },
    guard: (ctx) => {
      const blocked = entry.guard?.(ctx);
      if (blocked) return blocked;
      return resolveProfileSketch(ctx) ? null : NO_SKETCH_AVAILABLE;
    },
    invalid: (v, ctx) => {
      if (!resolveProfileSketch(ctx)) return NO_SKETCH_AVAILABLE;
      return typeof entry.invalid === "function"
        ? entry.invalid(v, ctx) : (entry.invalid ?? "Valeurs invalides");
    },
  };
}

function lineAxisLabel(line) {
  const key = line.construction
    ? "Ligne de construction {n} ({x1}, {y1}) → ({x2}, {y2})"
    : "Ligne {n} ({x1}, {y1}) → ({x2}, {y2})";
  return t(key, {
    n: line.id + 1,
    x1: line.x1, y1: line.y1, x2: line.x2, y2: line.y2,
  });
}

/** Options d'axe : vertical, lignes (construction d'abord), origine. */
export function revolutionAxisOptions(sketch, current = "vertical") {
  const options = [
    ["vertical", "Axe vertical de l'esquisse"],
    ["horizontal", "Axe horizontal de l'esquisse"],
  ];
  const lines = [...(sketch?.lines ?? [])].sort((a, b) =>
    Number(b.construction) - Number(a.construction) || a.id - b.id);
  for (const line of lines) options.push(["line:" + line.id, lineAxisLabel(line)]);
  options.push(
    ["X", "Axe X de l'origine"],
    ["Y", "Axe Y de l'origine"],
    ["Z", "Axe Z de l'origine"],
  );
  if (current && !options.some(([value]) => value === current)) {
    const id = Number(String(current).replace(/^line:/, ""));
    options.push([current, t("Ligne {n} ({x1}, {y1}) → ({x2}, {y2})", {
      n: Number.isFinite(id) ? id + 1 : current,
      x1: "—", y1: "—", x2: "—", y2: "—",
    })]);
  }
  return options;
}

/** Groupes du panneau révolution / gorge, à la création comme à la réédition. */
export function revolutionGroups(sketch, {
  angle = 360, axis = "vertical", reversed = false, midplane = false,
} = {}) {
  return [
    { label: "Direction 1", rows: [
      { type: "select", key: "cond", value: midplane ? "milieu" : "one",
        options: [["one", "Une direction"], ["milieu", "Plan milieu"]] },
      measureRow("angle", "Angle", angle, "°"),
      { type: "check", key: "reversed", label: "Inverser la direction",
        value: !!reversed && !midplane,
        showIf: (v) => v.cond !== "milieu" },
    ] },
    { label: "Axe", rows: [
      { type: "select", key: "axis", label: "Axe", value: axis,
        options: revolutionAxisOptions(sketch, axis) },
    ] },
  ];
}

/** Params `add_revolution` / `add_groove`, ou null si l'angle est invalide. */
export function revolutionCreationParams(v, op) {
  const angle = plainNumber(v.angle);
  if (!(angle > 0) || angle > 360) return null;
  const params = { angle };
  const axis = v.axis || "vertical";
  if (axis !== "vertical") params.axis = axis;
  if (v.cond === "milieu") params.midplane = true;
  else if (v.reversed) params.reversed = true;
  return { op, params };
}

export function revolutionProblem() {
  return "Angle de révolution invalide";
}

/**
 * Valeurs `set_params` pour rééditer une révolution ou une gorge.
 * `{}` si rien n'a changé, `null` si l'angle est invalide.
 */
export function revolutionEditValues(v, revolution, params) {
  const stored = storedMeasure(params, "Angle", revolution.angle);
  const angle = readMeasure(v.angle, stored, { min: 0, max: 360.0001 });
  if (angle == null) return null;
  const axis = v.axis || "vertical";
  const midplane = v.cond === "milieu";
  const reversed = midplane ? false : !!v.reversed;
  const values = {};
  if (!sameMeasure(angle, stored)) values.Angle = angle;
  if (axis !== (revolution.axis || "vertical")) values.axis = axis;
  if (reversed !== !!revolution.reversed || midplane !== !!revolution.midplane) {
    values.Reversed = reversed;
    values.Midplane = midplane;
  }
  return values;
}

function revolved({ button, op, icon, title }) {
  return withSketchProfile({
    button, icon, title,
    groups: (ctx) => revolutionGroups(resolveProfileSketch(ctx)),
    build: (v) => revolutionCreationParams(v, op),
    invalid: () => revolutionProblem(),
    refresh: "part",
  });
}

// ---------- conditions de fin d'extrusion (bossage, enlèvement) ----------
// Direction 1 : borgne, jusqu'au suivant, jusqu'au dernier / à travers
// tout, jusqu'à une face (décalage), plan milieu ; dépouille. Direction 2
// facultative. Le moteur traduit (engine/extrude.py).

const EXTRUDE_CONDITIONS = {
  pad: [["borgne", "Borgne"], ["suivant", "Jusqu'au suivant"],
        ["dernier", "Jusqu'au dernier"], ["face", "Jusqu'à la face"],
        ["milieu", "Plan milieu"]],
  pocket: [["travers", "À travers tout"], ["borgne", "Borgne"],
           ["suivant", "Jusqu'au suivant"], ["face", "Jusqu'à la face"],
           ["milieu", "Plan milieu"]],
};

const usesLength = (cond) => cond === "borgne" || cond === "milieu";

export function extrudeGroups(kind) {
  const conditions = EXTRUDE_CONDITIONS[kind];
  const second = conditions.filter(([c]) => c !== "face" && c !== "milieu");
  return [
    {
      label: "Direction 1",
      rows: [
        { type: "select", key: "cond", value: conditions[0][0],
          options: conditions },
        { type: "number", key: "length", label: "Profondeur", value: 10,
          unit: "mm", min: 0.01, showIf: (v) => usesLength(v.cond) },
        { type: "selection", key: "face", accepts: ["face"],
          label: "Face d'arrivée", hint: "Cliquez la face d'arrivée",
          showIf: (v) => v.cond === "face" },
        { type: "number", key: "offset", label: "Décalage", value: 0,
          unit: "mm", showIf: (v) => v.cond === "face" },
        { type: "check", key: "reversed", label: "Inverser la direction",
          value: false, showIf: (v) => v.cond !== "milieu" },
        { type: "number", key: "taper", label: "Dépouille", value: 0,
          unit: "°" },
        { type: "check", key: "taperOut", label: "Dépouille vers l'extérieur",
          value: false, showIf: (v) => (num(v.taper) ?? 0) !== 0 },
      ],
    },
    {
      label: "Direction 2",
      rows: [
        { type: "check", key: "dir2", label: "Deuxième direction",
          value: false, showIf: (v) => v.cond !== "milieu" },
        { type: "select", key: "cond2", value: second[0][0], options: second,
          showIf: (v) => v.dir2 && v.cond !== "milieu" },
        { type: "number", key: "length2", label: "Profondeur", value: 10,
          unit: "mm", min: 0.01,
          showIf: (v) => v.dir2 && v.cond !== "milieu"
            && v.cond2 === "borgne" },
        { type: "number", key: "taper2", label: "Dépouille", value: 0,
          unit: "°", showIf: (v) => v.dir2 && v.cond !== "milieu" },
      ],
    },
    {
      label: "Paroi mince",
      rows: [
        { type: "check", key: "thin", label: "Paroi d'épaisseur constante",
          value: false },
        { type: "select", key: "thinType", value: "un",
          options: THIN_TYPES, showIf: (v) => v.thin },
        { type: "number", key: "thinT", label: "Épaisseur", value: 2,
          unit: "mm", min: 0.01, showIf: (v) => v.thin },
        { type: "number", key: "thinT2", label: "Épaisseur côté 2",
          value: 2, unit: "mm", min: 0.01,
          showIf: (v) => v.thin && v.thinType === "deux" },
        { type: "check", key: "thinReversed", label: "Inverser le côté",
          value: false, showIf: (v) => v.thin && v.thinType !== "milieu" },
        ...(kind === "pad" ? [
          { type: "check", key: "thinCaps", label: "Extrémités fermées",
            value: false, showIf: (v) => v.thin && capsAllowed(v) },
          { type: "number", key: "thinCapT", label: "Épaisseur des extrémités",
            value: 1, unit: "mm", min: 0.01,
            showIf: (v) => v.thin && v.thinCaps && capsAllowed(v) },
        ] : []),
      ],
    },
  ];
}

// Extrémités fermées (extrusion, profil fermé) : profondeurs borgnes et
// sans dépouille — la cavité se règle sur elles.
const capsAllowed = (v) => usesLength(v.cond) && !(num(v.taper) ?? 0)
  && !(v.dir2 && v.cond !== "milieu"
       && (v.cond2 !== "borgne" || (num(v.taper2) ?? 0)));

// Paroi mince : vers l'extérieur d'un profil fermé (à droite du tracé
// d'un profil ouvert) ; « Inverser le côté » passe de l'autre côté.
const THIN_TYPES = [["un", "Un côté"], ["milieu", "Plan milieu"],
                    ["deux", "Deux côtés"]];

/** Paroi mince pour le moteur, ``undefined`` sans, ``null`` si invalide. */
function thinParams(v, op) {
  if (!v.thin) return undefined;
  const thickness = Math.abs(num(v.thinT) ?? 0);
  if (!thickness) return null;
  const type = v.thinType ?? "un";
  const thin = { type, thickness, reversed: type !== "milieu" && !!v.thinReversed };
  if (type === "deux") {
    const thickness2 = Math.abs(num(v.thinT2) ?? 0);
    if (!thickness2) return null;
    thin.thickness2 = thickness2;
  }
  if (op === "add_pad" && v.thinCaps && capsAllowed(v)) {
    const caps = Math.abs(num(v.thinCapT) ?? 0);
    if (!caps) return null;
    thin.caps = caps;
  }
  return thin;
}

/** Paramètres moteur, ou null si la saisie est incomplète. */
export function extrudeBuild(op, v) {
  const params = { reversed: !!v.reversed };
  const midplane = v.cond === "milieu";
  params.cond = midplane ? "borgne" : v.cond;
  if (midplane) params.midplane = true;
  if (usesLength(v.cond)) {
    const length = Math.abs(num(v.length) ?? 0);
    if (!length) return null;
    params.length = length;
  }
  if (v.cond === "face") {
    if (v.face?.face == null) return null;
    params.face = v.face.face;
    params.offset = num(v.offset) ?? 0;
  }
  const taper = Math.abs(num(v.taper) ?? 0);
  if (taper) params.taper = v.taperOut ? -taper : taper;
  if (v.dir2 && !midplane) {
    params.cond2 = v.cond2;
    if (v.cond2 === "borgne") {
      const length2 = Math.abs(num(v.length2) ?? 0);
      if (!length2) return null;
      params.length2 = length2;
    }
    const taper2 = num(v.taper2) ?? 0;
    if (taper2) params.taper2 = taper2;
  }
  const thin = thinParams(v, op);
  if (thin === null) return null;
  if (thin) params.thin = thin;
  return { op, params };
}

export function extrudeInvalid(v) {
  if (v.cond === "face" && v.face?.face == null) {
    return "Jusqu'à la face : cliquez la face d'arrivée";
  }
  if (thinParams(v, "add_pad") === null) return "Épaisseur de paroi invalide";
  return "Profondeur invalide";
}

export const VOLUMES = [
  withSketchProfile({
    button: "btn-pad",
    icon: "nodes_extrude",
    title: "Extrusion",
    groups: () => extrudeGroups("pad"),
    build: (v) => extrudeBuild("add_pad", v),
    invalid: extrudeInvalid,
    refresh: "part",
  }),
  withSketchProfile({
    button: "btn-pocket",
    icon: "pocket",
    title: "Enlèvement extrudé",
    groups: () => extrudeGroups("pocket"),
    build: (v) => extrudeBuild("add_pocket", v),
    invalid: extrudeInvalid,
    refresh: "part",
  }),
  revolved({
    button: "btn-revolution",
    op: "add_revolution",
    icon: "revolve",
    title: "Révolution",
  }),
  revolved({
    button: "btn-groove",
    op: "add_groove",
    icon: "groove",
    title: "Enlèvement par révolution",
  }),
  {
    button: "btn-hole",
    icon: "hole",
    title: "Perçage",
    groups: () => [
      { label: "Positions",
        rows: [{ type: "selection", key: "pos", accepts: ["point"],
                 multiple: true,
                 hint: "Cliquez les centres des trous sur une face" }] },
      {
        label: "Type de perçage",
        rows: [
          { type: "select", key: "cut", value: "none",
            options: [["none", "Perçage"], ["lamage", "Lamage"],
                      ["fraisage", "Fraisage"]] },
          { type: "number", key: "diameter", label: "Diamètre", value: 6,
            unit: "mm", min: 0.01 },
          { type: "number", key: "cutDiameter", label: "Ø de tête",
            value: 11, unit: "mm", min: 0.01,
            showIf: (v) => v.cut !== "none" },
          { type: "number", key: "cutDepth", label: "Prof. lamage",
            value: 3, unit: "mm", min: 0.01,
            showIf: (v) => v.cut === "lamage" },
          { type: "number", key: "cutAngle", label: "Angle", value: 90,
            unit: "°", min: 1, showIf: (v) => v.cut === "fraisage" },
        ],
      },
      {
        label: "Condition de fin",
        rows: [
          { type: "select", key: "cond", value: "travers",
            options: [["travers", "À travers tout"],
                      ["borgne", "Borgne"]] },
          { type: "number", key: "depth", label: "Profondeur", value: 15,
            unit: "mm", min: 0.01, showIf: (v) => v.cond === "borgne" },
        ],
      },
    ],
    note: "Sans position cliquée, la dernière esquisse sert (un cercle " +
          "par perçage). Le diamètre saisi remplace celui des cercles.",
    build: (v) => {
      const diameter = num(v.diameter);
      if (!(diameter > 0)) return null;
      const params = { diameter, cut: v.cut };
      const positions = holePositions(v.pos);
      if (positions?.error) return null;
      if (positions) Object.assign(params, positions);
      if (v.cond === "borgne") {
        const depth = num(v.depth);
        if (!(depth > 0)) return null;
        params.depth = depth;
      } else {
        params.through = true;
      }
      if (v.cut !== "none") {
        const cutDiameter = num(v.cutDiameter);
        if (!(cutDiameter > diameter)) return null; // le lamage englobe le trou
        params.cut_diameter = cutDiameter;
        if (v.cut === "lamage") {
          const cutDepth = num(v.cutDepth);
          if (!(cutDepth > 0)) return null;
          params.cut_depth = cutDepth;
        } else {
          const cutAngle = num(v.cutAngle);
          if (cutAngle > 0) params.cut_angle = cutAngle;
        }
      }
      return { op: "add_hole", params };
    },
    invalid: (v) => (holePositions(v.pos)?.error
      ?? "Valeurs du perçage invalides"),
    refresh: "part",
  },
  {
    button: "btn-loft",
    icon: "loft",
    title: "Lissage",
    groups: () => [
      { label: "Profils",
        rows: [{ type: "selection", key: "profiles", accepts: ["sketch"],
                 multiple: true,
                 hint: "Cliquez les esquisses dans l'arbre, dans " +
                       "l'ordre du lissage" }] },
      { label: "Options",
        rows: [
          { type: "check", key: "subtractive",
            label: "Enlever de la matière", value: false },
          { type: "check", key: "ruled", label: "Lissage droit (réglé)",
            value: false },
          { type: "check", key: "closed", label: "Boucle fermée",
            value: false },
        ] },
    ],
    build: (v) => {
      const items = v.profiles?.items ?? [];
      if (items.length < 2) return null;
      return { op: "add_loft", params: {
        sketches: items.map((i) => i.name),
        subtractive: !!v.subtractive,
        ruled: !!v.ruled,
        closed: !!v.closed } };
    },
    invalid: "Lissage : au moins deux profils",
    refresh: "part",
  },
  {
    button: "btn-sweep",
    icon: "sweep",
    title: "Balayage",
    groups: () => [
      { label: "Profil",
        rows: [{ type: "selection", key: "profile", accepts: ["sketch"],
                 hint: "Cliquez l'esquisse du profil dans l'arbre" }] },
      { label: "Trajectoire",
        rows: [{ type: "selection", key: "spine",
                 accepts: ["sketch", "surface"],
                 hint: "Puis la trajectoire : une esquisse ou une spline 3D" }] },
      { label: "Options",
        rows: [{ type: "check", key: "subtractive",
                 label: "Enlever de la matière", value: false }] },
    ],
    build: (v) => {
      if (!v.profile || !v.spine) return null;
      if (v.profile.name === v.spine.name) return null;
      return { op: "add_sweep", params: {
        profile: v.profile.name,
        spine: v.spine.name,
        subtractive: !!v.subtractive } };
    },
    invalid: "Balayage : un profil puis une trajectoire (différents)",
    refresh: "part",
  },
  {
    button: "btn-helix",
    icon: "nodes_helix",
    title: "Hélice",
    groups: () => [{
      label: "Paramètres",
      rows: [
        { type: "number", key: "pitch", label: "Pas", value: 8,
          unit: "mm", min: 0.01 },
        { type: "number", key: "height", label: "Hauteur", value: 40,
          unit: "mm", min: 0.01 },
      ],
    }],
    note: "Le profil (dernière esquisse) tourne autour de l'axe " +
          "vertical de son esquisse — dessinez-le décalé de l'axe.",
    build: (v) => {
      const pitch = num(v.pitch);
      const height = num(v.height);
      return pitch > 0 && height > 0
        ? { op: "add_helix", params: { pitch, height } } : null;
    },
    invalid: "Pas et hauteur doivent être positifs",
    refresh: "part",
  },
  dressup({
    button: "btn-text",
    icon: "nodes_text", title: "Texte",
    selectionLabel: "Face d'appui",
    group: "Texte",
    rows: [
      { type: "text", key: "content", label: "Texte", value: "",
        placeholder: "REF-001" },
      { type: "number", key: "size", label: "Hauteur", value: 8,
        unit: "mm", min: 0.1 },
      { type: "number", key: "depth", label: "Profondeur", value: 1,
        unit: "mm", min: 0.01 },
      { type: "check", key: "emboss", label: "En relief (bossage)",
        value: false },
      { type: "number", key: "x", label: "Décalage X", value: 0,
        unit: "mm" },
      { type: "number", key: "y", label: "Décalage Y", value: 0,
        unit: "mm" },
    ],
    build: (v) => {
      const content = (v.content ?? "").trim();
      const size = num(v.size);
      const depth = num(v.depth);
      if (!content || !(size > 0) || !(depth > 0)) return null;
      return { op: "add_text", params: {
        text: content, face: v.sel.face, size, depth,
        x: num(v.x) ?? 0, y: num(v.y) ?? 0,
        emboss: !!v.emboss } };
    },
  }),
];
