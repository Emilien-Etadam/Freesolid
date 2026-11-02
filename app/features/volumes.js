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
  const stored = storedMeasure(params, "angle", revolution.angle);
  const angle = readMeasure(v.angle, stored, { min: 0, max: 360.0001 });
  if (angle == null) return null;
  const axis = v.axis || "vertical";
  const midplane = v.cond === "milieu";
  const reversed = midplane ? false : !!v.reversed;
  const values = {};
  if (!sameMeasure(angle, stored)) values.angle = angle;
  if (axis !== (revolution.axis || "vertical")) values.axis = axis;
  if (reversed !== !!revolution.reversed || midplane !== !!revolution.midplane) {
    values.reversed = reversed;
    values.midplane = midplane;
  }
  return values;
}

function revolved({ button, op, icon, title, merge = false }) {
  return withSketchProfile({
    button, op, icon, title,
    groups: (ctx) => [...revolutionGroups(resolveProfileSketch(ctx)),
                      ...(merge ? mergeGroups(ctx?.lastTree?.bodies) : [])],
    build: (v, ctx) => {
      const built = revolutionCreationParams(v, op);
      if (!built || !merge) return built;
      built.params = { ...built.params,
                       ...mergeParams(v, ctx?.lastTree?.bodies) };
      return built;
    },
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

/** Groupes du panneau extrusion / enlèvement. `edit` : les valeurs de la
 *  fonction qu'on réédite (`extrudeEditInitial`). La face d'arrivée ne se
 *  re-choisit pas ; la paroi mince garde son genre, ses épaisseurs et son
 *  côté se changent. */
export function extrudeGroups(kind, edit = null) {
  // Extrémités fermées : la cavité veut des profondeurs borgnes.
  const caps = (edit?.thin?.caps ?? 0) > 0;
  // Premier volume de son corps : aucun « jusqu'à » n'a où s'arrêter.
  const blind = caps || !!edit?.alone;
  const conditions = EXTRUDE_CONDITIONS[kind].filter(([c]) => !edit
    || (blind ? c === "borgne" || c === "milieu"
      : c !== "face" || edit.cond === "face"));
  const second = EXTRUDE_CONDITIONS[kind].filter(([c]) =>
    c !== "face" && c !== "milieu" && (!blind || c === "borgne"));
  const depth = (key, value, showIf) => (edit
    ? measureRow(key, "Profondeur", value, "mm", showIf)
    : { type: "number", key, label: "Profondeur", value, unit: "mm",
        min: 0.01, showIf });
  const tapered = !caps;
  return [
    {
      label: "Direction 1",
      rows: [
        { type: "select", key: "cond", value: edit?.cond ?? conditions[0][0],
          options: conditions },
        depth("length", edit?.length ?? 10, (v) => usesLength(v.cond)),
        ...(edit ? [] : [
          { type: "selection", key: "face", accepts: ["face"],
            label: "Face d'arrivée", hint: "Cliquez la face d'arrivée",
            showIf: (v) => v.cond === "face" }]),
        { type: "number", key: "offset", label: "Décalage",
          value: edit?.offset ?? 0, unit: "mm",
          showIf: (v) => v.cond === "face" },
        { type: "check", key: "reversed", label: "Inverser la direction",
          value: edit?.reversed ?? false, showIf: (v) => v.cond !== "milieu" },
        ...(tapered ? [
          { type: "number", key: "taper", label: "Dépouille",
            value: edit?.taper ?? 0, unit: "°" },
          { type: "check", key: "taperOut",
            label: "Dépouille vers l'extérieur",
            value: edit?.taperOut ?? false,
            showIf: (v) => (num(v.taper) ?? 0) !== 0 },
        ] : []),
      ],
    },
    {
      label: "Direction 2",
      rows: [
        { type: "check", key: "dir2", label: "Deuxième direction",
          value: edit?.dir2 ?? false, showIf: (v) => v.cond !== "milieu" },
        { type: "select", key: "cond2", value: edit?.cond2 ?? second[0][0],
          options: second, showIf: (v) => v.dir2 && v.cond !== "milieu" },
        depth("length2", edit?.length2 ?? 10, (v) => v.dir2
          && v.cond !== "milieu" && v.cond2 === "borgne"),
        ...(tapered ? [
          { type: "number", key: "taper2", label: "Dépouille",
            value: edit?.taper2 ?? 0, unit: "°",
            showIf: (v) => v.dir2 && v.cond !== "milieu" }] : []),
      ],
    },
    ...(edit ? thinEditGroups(edit.thin) : [{
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
    }]),
  ];
}

/** Paroi mince d'une fonction qu'on réédite : ses épaisseurs et son côté. */
function thinEditGroups(thin) {
  if (!thin) return [];
  return [{
    label: "Paroi mince",
    rows: [
      measureRow("thinT", "Épaisseur", thin.thinT, "mm"),
      ...(thin.type === "deux"
        ? [measureRow("thinT2", "Épaisseur côté 2", thin.thinT2, "mm")] : []),
      ...(thin.type !== "milieu" ? [
        { type: "check", key: "thinReversed", label: "Inverser le côté",
          value: !!thin.reversed }] : []),
      ...(thin.caps > 0
        ? [measureRow("thinCapT", "Épaisseur des extrémités", thin.thinCapT,
                      "mm")] : []),
    ],
  }];
}

/** Valeurs du panneau pour une fonction qu'on réédite : ses conditions
 *  (`feature.extrude`), ses cotes, expressions comprises (`params`), sa
 *  paroi mince (`thin`). */
export function extrudeEditInitial(feature) {
  const state = feature.extrude;
  const value = (key, fallback) => {
    const found = (feature.params ?? []).find((p) => p.key === key);
    return found?.expr ?? found?.value ?? fallback;
  };
  const thin = feature.thin;
  return {
    cond: state.midplane ? "milieu" : state.cond,
    alone: !!state.alone,
    length: value("length", 10),
    offset: state.offset,
    reversed: state.reversed,
    taper: Math.abs(state.taper),
    taperOut: state.taper < 0,
    dir2: !!state.cond2,
    cond2: state.cond2 ?? undefined,
    length2: value("length2", 10),
    taper2: state.taper2,
    thin: thin ? {
      type: thin.type, reversed: thin.reversed, caps: thin.caps,
      thinT: value("thinT", thin.thickness),
      thinT2: value("thinT2", thin.thickness2),
      thinCapT: value("thinCapT", thin.caps),
    } : null,
  };
}

/**
 * Valeurs `set_params` pour rééditer une extrusion ou un enlèvement : ce
 * qui a changé, dans les clés de la création. `{}` si rien n'a changé,
 * `null` si une cote visible est invalide.
 */
export function extrudeEditValues(v, feature) {
  const state = feature.extrude;
  const params = feature.params;
  const values = {};
  const midplane = v.cond === "milieu";
  const cond = midplane ? "borgne" : v.cond;
  const dir2 = !!v.dir2 && !midplane;
  const cond2 = dir2 ? v.cond2 : null;
  const reversed = midplane ? false : !!v.reversed;
  const near = (a, b) => Math.abs(a - b) < 1e-9;
  const taperSize = Math.abs(num(v.taper) ?? 0);
  const taper = v.taperOut ? -taperSize : taperSize;
  const taper2 = dir2 ? (num(v.taper2) ?? 0) : 0;
  if (cond !== state.cond) values.cond = cond;
  if (midplane !== state.midplane) values.midplane = midplane;
  if (reversed !== state.reversed) values.reversed = reversed;
  if (!near(taper, state.taper)) values.taper = taper;
  if (cond2 !== (state.cond2 ?? null)) values.cond2 = cond2;
  if (dir2 && !near(taper2, state.taper2)) values.taper2 = taper2;
  if (cond === "face") {
    const offset = num(v.offset) ?? 0;
    if (!near(offset, state.offset)) values.offset = offset;
  }
  const bounds = { min: 0, max: Infinity };
  const measure = (key, fallback, always = false) => {
    const stored = storedMeasure(params, key, fallback);
    const read = readMeasure(v[key], stored, bounds);
    if (read == null) return false;
    if (always || !sameMeasure(read, stored)) values[key] = read;
    return true;
  };
  if (usesLength(v.cond) && !measure("length", 10)) return null;
  // Côté 2 ouvert ici : sa profondeur part, même telle qu'affichée.
  if (cond2 === "borgne"
      && !measure("length2", 10, state.cond2 !== "borgne")) return null;
  const thin = feature.thin;
  if (thin) {
    if (!measure("thinT", thin.thickness)) return null;
    if (thin.type === "deux" && !measure("thinT2", thin.thickness2)) {
      return null;
    }
    if (thin.caps > 0 && !measure("thinCapT", thin.caps)) return null;
    if (thin.type !== "milieu" && !!v.thinReversed !== !!thin.reversed) {
      values.thinReversed = !!v.thinReversed;
    }
  }
  return values;
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

// ---------- perçage ----------

/** Cotes d'un perçage à l'ouverture du panneau : celles de la création. */
const HOLE_DEFAULTS = { diameter: 6, depth: 15, cutDiameter: 11, cutDepth: 3,
                        cutAngle: 90 };

/** Type et condition de fin d'un perçage, à la création comme à la
 *  réédition (`edit` : `holeEditInitial`). */
export function holeGroups(edit = null) {
  const v0 = edit ?? { cut: "none", cond: "travers", ...HOLE_DEFAULTS };
  const measure = (key, label, unit, min, showIf) => {
    const row = edit ? measureRow(key, label, v0[key], unit)
      : { type: "number", key, label, value: v0[key], unit, min };
    if (showIf) row.showIf = showIf;
    return row;
  };
  return [
    {
      label: "Type de perçage",
      rows: [
        { type: "select", key: "cut", value: v0.cut,
          options: [["none", "Perçage"], ["lamage", "Lamage"],
                    ["fraisage", "Fraisage"]] },
        measure("diameter", "Diamètre", "mm", 0.01),
        measure("cutDiameter", "Ø de tête", "mm", 0.01,
                (v) => v.cut !== "none"),
        measure("cutDepth", "Prof. lamage", "mm", 0.01,
                (v) => v.cut === "lamage"),
        measure("cutAngle", "Angle", "°", 1, (v) => v.cut === "fraisage"),
      ],
    },
    {
      label: "Condition de fin",
      rows: [
        { type: "select", key: "cond", value: v0.cond,
          options: [["travers", "À travers tout"],
                    ["borgne", "Borgne"]] },
        measure("depth", "Profondeur", "mm", 0.01,
                (v) => v.cond === "borgne"),
      ],
    },
  ];
}

/** Valeurs du panneau pour un perçage qu'on réédite : son type et sa
 *  condition (`feature.hole`), ses cotes (expressions comprises) ; une
 *  cote que son type ne prend pas reprend celle de la création. */
export function holeEditInitial(feature) {
  const hole = feature.hole;
  const initial = { cut: hole.cut, cond: hole.cond };
  for (const [key, fallback] of Object.entries(HOLE_DEFAULTS)) {
    const found = (feature.params ?? []).find((p) => p.key === key);
    initial[key] = found?.expr ?? found?.value ?? hole[key] ?? fallback;
  }
  return initial;
}

/**
 * Valeurs `set_params` d'un perçage réédité : `{}` si rien n'a changé,
 * null si une cote visible est invalide. FreeCAD remet les cotes de tête
 * à ses valeurs quand le type change : elles repartent alors toutes.
 */
export function holeEditValues(v, feature) {
  const hole = feature.hole;
  const initial = holeEditInitial(feature);
  const values = {};
  const retyped = v.cut !== hole.cut;
  if (retyped) values.cut = v.cut;
  if (v.cond !== hole.cond) values.cond = v.cond;
  const measure = (key, always = false) => {
    const stored = storedMeasure(feature.params, key, initial[key]);
    const read = readMeasure(v[key], stored, { min: 0, max: Infinity });
    if (read != null && (always || !sameMeasure(read, stored))) {
      values[key] = read;
    }
    return read;
  };
  const diameter = measure("diameter");
  if (diameter == null) return null;
  if (v.cond === "borgne"
      && measure("depth", hole.cond !== "borgne") == null) return null;
  if (v.cut !== "none") {
    const head = measure("cutDiameter", retyped);
    if (head == null) return null;
    // Le lamage englobe le trou — vérifié quand l'un des deux change.
    const resized = "cutDiameter" in values || "diameter" in values;
    if (resized && typeof head === "number" && typeof diameter === "number"
        && !(head > diameter)) return null;
    const extra = v.cut === "lamage" ? "cutDepth" : "cutAngle";
    if (measure(extra, retyped) == null) return null;
  }
  return values;
}

/** Ce qui manque à une réédition refusée (`extrudeEditValues` à null). */
export function extrudeEditProblem(v, feature) {
  const bad = (key) => key in v && readMeasure(
    v[key], storedMeasure(feature.params, key, 1),
    { min: 0, max: Infinity }) == null;
  return feature.thin && ["thinT", "thinT2", "thinCapT"].some(bad)
    ? "Épaisseur de paroi invalide" : "Profondeur invalide";
}

// ---------- fusionner ou non (extrusion, révolution, lissage, balayage) ----------
// Décochée : un nouveau corps. Cochée : le corps actif, et les corps qu'on
// clique dans la vue — la fonction les fond en un seul. Seulement quand
// la pièce a déjà un volume.

/** Groupe « Résultat » d'un volume, vide sans corps solide. `when` : le
 *  groupe ne s'affiche que si ces valeurs le veulent (pas pour un
 *  enlèvement de matière). */
export function mergeGroups(bodies, { when } = {}) {
  const solid = (bodies ?? []).filter((b) => b.has_solid === true);
  if (!solid.length) return [];
  const active = (bodies ?? []).find((b) => b.active && b.has_solid === true);
  return [{
    label: "Résultat",
    ...(when ? { showIf: when } : {}),
    rows: [
      { type: "check", key: "merge", label: "Fusionner", value: true },
      { type: "selection", key: "body", accepts: ["body"], label: "Corps",
        multiple: true, hint: "Cliquez des corps dans la vue",
        value: { kind: "body", items: active
          ? [{ kind: "body", name: active.name, label: active.label }] : [] },
        showIf: (v) => v.merge !== false },
    ],
  }];
}

const activeBodyName = (bodies) => (bodies ?? []).find((b) => b.active)?.name;

/** Les corps de la zone, dans l'ordre des clics, et celui où la fonction
 *  se range : le corps actif s'il y est, sinon le premier (zone vide : le
 *  corps actif). */
function mergeTargets(v, bodies) {
  const picks = v.body?.items ?? (v.body ? [v.body] : []);
  const names = [...new Set(picks.map((i) => i.name).filter(Boolean))];
  const active = activeBodyName(bodies);
  const target = !names.length || names.includes(active) ? active : names[0];
  return { target, others: names.filter((n) => n !== target) };
}

/** Ce que la fusion interdit, sinon null. */
export function mergeProblem(v, bodies) {
  if (v.merge === false) {
    const blind = v.cond === "milieu" || (v.cond === "borgne"
      && (!v.dir2 || v.cond2 === "borgne"));
    return blind ? null : "Nouveau corps : profondeur borgne ou plan milieu";
  }
  const { target } = mergeTargets(v, bodies);
  if (v.cond === "face" && target && target !== activeBodyName(bodies)) {
    return "Jusqu'à la face : fusionnez avec le corps actif";
  }
  return null;
}

/** Params moteur de la fusion : `merge: false`, ou le corps où ranger la
 *  fonction s'il n'est pas le corps actif, et les autres corps qu'elle y
 *  fond (`bodies`). */
export function mergeParams(v, bodies) {
  if (v.merge === false) return { merge: false };
  const { target, others } = mergeTargets(v, bodies);
  return { ...(target && target !== activeBodyName(bodies)
    ? { body: target } : {}),
           ...(others.length ? { bodies: others } : {}) };
}

// ---------- corps fondus, à la réédition ----------
// Un corps fondu ne se voit plus à part dans la vue : la réédition donne
// une case par corps — cochée pour ceux que la fonction fond, décochée
// pour les autres corps du dossier. Le corps de la fonction ne bouge pas.

const FUSING = ["pad", "revolution"];
const fuseKey = (name) => `fuse:${name}`;

/** Les cases de la réédition : les corps fondus, puis les autres corps
 *  solides du dossier, sauf celui de la fonction. */
export function fusedCandidates(feature, tree) {
  if (!FUSING.includes(feature?.type_key)) return [];
  const own = feature.body ?? activeBodyName(tree?.bodies);
  const fused = feature.fused ?? [];
  const others = (tree?.bodies ?? []).filter((b) => b.has_solid === true
    && b.name !== own && !fused.some((f) => f.name === b.name));
  return [...fused.map(({ name, label }) => ({ name, label, fused: true })),
          ...others.map(({ name, label }) => ({ name, label, fused: false }))];
}

/** Groupe « Corps fondus » de la réédition, vide sans autre corps. */
export function fusedGroups(feature, tree) {
  const candidates = fusedCandidates(feature, tree);
  if (!candidates.length) return [];
  return [{
    label: "Corps fondus",
    rows: candidates.map((c) => ({ type: "check", key: fuseKey(c.name),
                                   label: c.label, value: c.fused })),
  }];
}

/** `{ bodies }` quand les cases ont changé, sinon `{}`. */
export function fusedValues(v, feature, tree) {
  const candidates = fusedCandidates(feature, tree);
  const checked = candidates
    .filter((c) => v[fuseKey(c.name)] ?? c.fused).map((c) => c.name);
  const before = candidates.filter((c) => c.fused).map((c) => c.name);
  const same = checked.length === before.length
    && checked.every((name) => before.includes(name));
  return same ? {} : { bodies: checked };
}

// Lissage, balayage : un enlèvement creuse le corps actif, sans fusion.
const added = (v) => !v.subtractive;
const addedMergeParams = (v, ctx) => (added(v)
  ? mergeParams(v, ctx?.lastTree?.bodies) : {});

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
    op: "add_pad",
    icon: "nodes_extrude",
    title: "Extrusion",
    groups: (ctx) => [...extrudeGroups("pad"),
                      ...mergeGroups(ctx?.lastTree?.bodies)],
    build: (v, ctx) => {
      const bodies = ctx?.lastTree?.bodies;
      const built = extrudeBuild("add_pad", v);
      if (!built || mergeProblem(v, bodies)) return null;
      built.params = { ...built.params, ...mergeParams(v, bodies) };
      return built;
    },
    invalid: (v, ctx) => mergeProblem(v, ctx?.lastTree?.bodies)
      ?? extrudeInvalid(v),
    refresh: "part",
  }),
  withSketchProfile({
    button: "btn-pocket",
    op: "add_pocket",
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
    merge: true,
  }),
  revolved({
    button: "btn-groove",
    op: "add_groove",
    icon: "groove",
    title: "Enlèvement par révolution",
  }),
  {
    button: "btn-hole",
    op: "add_hole",
    icon: "hole",
    title: "Perçage",
    groups: () => [
      { label: "Positions",
        rows: [{ type: "selection", key: "pos", accepts: ["point"],
                 multiple: true,
                 hint: "Cliquez les centres des trous sur une face" }] },
      ...holeGroups(),
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
    op: "add_loft",
    icon: "loft",
    title: "Lissage",
    groups: (ctx) => [
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
      ...mergeGroups(ctx?.lastTree?.bodies, { when: added }),
    ],
    build: (v, ctx) => {
      const items = v.profiles?.items ?? [];
      if (items.length < 2) return null;
      return { op: "add_loft", params: {
        sketches: items.map((i) => i.name),
        subtractive: !!v.subtractive,
        ruled: !!v.ruled,
        closed: !!v.closed,
        ...addedMergeParams(v, ctx) } };
    },
    invalid: "Lissage : au moins deux profils",
    refresh: "part",
  },
  {
    button: "btn-sweep",
    op: "add_sweep",
    icon: "sweep",
    title: "Balayage",
    groups: (ctx) => [
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
      ...mergeGroups(ctx?.lastTree?.bodies, { when: added }),
    ],
    build: (v, ctx) => {
      if (!v.profile || !v.spine) return null;
      if (v.profile.name === v.spine.name) return null;
      return { op: "add_sweep", params: {
        profile: v.profile.name,
        spine: v.spine.name,
        subtractive: !!v.subtractive,
        ...addedMergeParams(v, ctx) } };
    },
    invalid: "Balayage : un profil puis une trajectoire (différents)",
    refresh: "part",
  },
  {
    button: "btn-helix",
    op: "add_helix",
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
    op: "add_text",
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
