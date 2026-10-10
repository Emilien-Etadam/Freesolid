// Registry déclaratif des panneaux de fonctions mécaniques.
// Le branchement (clic → featureCommand → panel.open) vit dans main.js.
//
// Chaque entrée décrit un panneau « ouvrir → éditer → aperçu → OK ».
// build(v, ctx) rend { op, params } ou null (aperçu éteint, OK bloqué).

import { t } from "./i18n.js";
import { num, plainNumber } from "./num.js";
import { minimalGraphCurve, minimalGraphFeature, minimalRepeatGraph } from "./graph.js";
import { combineConfirmMessage } from "./progress.js";

/** Message moteur quand aucune esquisse libre n'est disponible (d'un
 *  seul tenant : c'est aussi la clé de traduction). */
export const NO_SKETCH_AVAILABLE =
  "aucune esquisse disponible — les esquisses existantes sont déjà utilisées par des fonctions, dessinez-en une nouvelle";

/** Esquisses libres (non consommées) dans l'ordre du corps — comme
 *  `_latest_sketch` côté moteur. */
export function availableSketches(tree) {
  return (tree?.features ?? []).filter(
    (f) => f.type === "Sketcher::SketchObject" && !f.rolled_back);
}

function latestAvailableSketch(tree) {
  const sketches = availableSketches(tree);
  return sketches.length ? sketches[sketches.length - 1] : null;
}

/** Corps inactifs + semis non vides : les outils que Combiner accepte. */
function booleanToolOptions(ctx) {
  const others = (ctx.lastTree?.bodies ?? []).filter((b) => !b.active);
  const gems = (ctx.lastTree?.gems ?? []).filter((g) => (g.count || 0) > 0);
  return [
    ...others.map((b) => [b.name, b.label]),
    ...gems.map((g) => [g.name, g.label]),
  ];
}

/** Profil affiché / utilisé : sélection d'arbre sinon dernière libre. */
export function resolveProfileSketch(ctx) {
  if (ctx.selectedSketch?.name) return ctx.selectedSketch;
  return latestAvailableSketch(ctx.lastTree);
}

export function hasSelection(sel) {
  return !!sel && (sel.kind === "edges"
    ? sel.edges.length > 0 : sel.face != null);
}

/** Consigne : rien n'est encore choisi. Ce n'est pas une erreur. */
function clickFirst(title) {
  return {
    text: t("{f} : cliquez d'abord dans la zone graphique", { f: t(title) }),
    tone: "guide",
  };
}

function dressupParams(sel) {
  return sel.kind === "edges"
    ? { edges: sel.edges } : { face: sel.face };
}

export function dressup({ button, icon, title, selectionLabel, group, rows, build,
                   accepts = ["face"], hint, note, noteFn, invalid }) {
  return {
    button, icon, title,
    dressup: true,
    note,
    noteFn,
    groups: (ctx) => [
      { label: selectionLabel,
        rows: [{ type: "selection", key: "sel", accepts, hint,
                 value: ctx.selection(accepts) }] },
      { label: group, rows },
    ],
    build: (v, ctx) => hasSelection(v.sel) ? build(v, ctx) : null,
    invalid: (v, ctx) => {
      if (!hasSelection(v.sel)) return clickFirst(title);
      if (typeof invalid === "function") return invalid(v, ctx);
      return invalid ?? "Valeur invalide";
    },
    refresh: "part",
  };
}

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

/** Coque : faces à ouvrir (une ou plusieurs), épaisseur, sens. */
export function shellBuild(v) {
  const faces = (v.faces?.items ?? []).map((item) => item.face)
    .filter((face) => face != null);
  const thickness = num(v.thickness);
  if (!faces.length || !(thickness > 0)) return null;
  return { op: "add_thickness",
           params: { faces, thickness, outward: !!v.outward } };
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
      return [
        { label: "Profil",
          rows: [{ type: "note",
            text: t("Profil : {p}", { p: profile ? profile.label : "—" }) }] },
        ...groups,
      ];
    },
    build: (v, ctx) => {
      const built = entry.build(v, ctx);
      if (!built) return null;
      if (ctx.selectedSketch?.name) {
        built.params = { ...built.params, sketch: ctx.selectedSketch.name };
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

/** Rangée « esquisse » préremplie : la sélection, sinon (``latest``) la
 *  dernière esquisse libre. */
function sketchRow(ctx, key, hint, { latest = true } = {}) {
  const sketch = latest ? resolveProfileSketch(ctx) : ctx.selectedSketch;
  return { type: "selection", key, accepts: ["sketch"], hint,
           value: sketch ? { kind: "sketch", name: sketch.name,
                             label: sketch.label } : null };
}

/** Un choix de la zone « Contour » → paramètre de surface_fill. */
export function boundaryParam(item) {
  if (item.kind !== "boundary") return { name: item.name };
  return item.body ? { body: true, edge: item.edge }
    : { name: item.name, edge: item.edge };
}

/** Faces cliquées d'une même surface → paramètres, ou null. */
export function deleteFacesParams(items) {
  if (!items?.length) return null;
  const name = items[0].name;
  if (items.some((i) => i.name !== name)) return null;
  return { surface: name, faces: items.map((i) => i.face) };
}

/** Faces cliquées : du solide (add_delete_face) ou d'une surface. */
export function deleteFacesBuild(items) {
  if (!items?.length) return null;
  if (items.every((i) => i.kind === "face")) {
    return { op: "add_delete_face",
             params: { faces: items.map((i) => i.face) } };
  }
  if (items.some((i) => i.kind !== "surfface")) return null;
  const params = deleteFacesParams(items);
  return params ? { op: "surface_delete_faces", params } : null;
}

/** Arêtes cliquées d'une même surface → paramètres du congé, ou null. */
export function surfaceFilletParams(items, radius) {
  const edges = (items ?? []).filter((i) => i.kind === "boundary"
    && !i.body && !i.curve);
  if (!edges.length || !(radius > 0)) return null;
  const name = edges[0].name;
  if (edges.some((i) => i.name !== name)) return null;
  return { surface: name, edges: edges.map((i) => i.edge), radius };
}

/** Ajuster (et ajustement mutuel) → paramètres, ou null. */
export function trimParams(v) {
  if (!v.tool || !v.keep || v.keep.name === v.tool.name) return null;
  const params = { surface: v.keep.name, tool: v.tool.name,
                   point: [v.keep.x, v.keep.y, v.keep.z] };
  if (!v.mutual) return { op: "surface_trim", params };
  if (v.toolKeep?.name !== v.tool.name) return null;
  params.tool_point = [v.toolKeep.x, v.toolKeep.y, v.toolKeep.z];
  return { op: "surface_trim", params };
}

/** Paramètres de surface_extend, ou null (bord de courbe, de solide). */
export function extendParams(target, distance) {
  if (!target || !(distance > 0)) return null;
  if (target.kind === "boundary") {
    if (target.curve || target.body) return null;
    return { surface: target.name, distance, edge: target.edge };
  }
  return { surface: target.name, distance };
}

function surface({ button, icon, title, groups, note, build, invalid }) {
  return {
    button, icon, title,
    groups: typeof groups === "function" ? groups : () => groups,
    note,
    build,
    // Une consigne, pas une erreur : tant qu'une case de sélection est
    // vide, elle dit déjà quoi cliquer et le bandeau s'efface.
    invalid: () => ({ text: invalid ?? "Valeurs invalides", tone: "guide" }),
    // Les ops surfaciques ne sont pas dans _PREVIEWABLE : pas d'aperçu
    // aujourd'hui, donc pas d'onChange (zéro changement de comportement).
    preview: false,
    refresh: "part",
  };
}

/** Combiner : même panneau sous `btn-boolean` (groupe Corps) et
 *  `btn-gem-combine` (onglet Bijouterie). Un seul objet, deux ids. */
const COMBINE_FEATURE = {
  icon: "boolean",
  title: "Combiner",
  guard: (ctx) => {
    const options = booleanToolOptions(ctx);
    return options.length ? null
      : "Combiner : créez d'abord un second corps, ou posez un semis de pierres";
  },
  groups: (ctx) => {
    const options = booleanToolOptions(ctx);
    return [{
      label: "Opération",
      rows: [
        { type: "select", key: "type", value: "cut",
          options: [["cut", "Soustraire"], ["fuse", "Ajouter"],
                    ["common", "Intersection"]] },
        { type: "select", key: "tool", value: options[0]?.[0] ?? "",
          label: "Corps outil",
          options },
      ],
    }];
  },
  note: "S'applique au corps actif. Un second corps est absorbé ; "
        + "un semis de pierres reste dans l'arbre, et l'empreinte "
        + "se recalcule à chaque reconstruction.",
  // Un booléen de semis peut durer des dizaines de secondes : l'aperçu
  // jaune le lancerait à l'ouverture du panneau, avant la confirmation.
  preview: false,
  confirm: (v, ctx) => combineConfirmMessage(ctx.lastTree, v.tool),
  build: (v) => ({ op: "add_boolean",
    params: { tool: v.tool, type: v.type } }),
  refresh: "part",
};


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

export function patternDirectionParams(v) {
  const params = { reversed: !!v.reversed };
  const edge = v.edge?.edges?.[0];
  if (v.dirKind === "edge" && edge != null) params.edge = edge;
  else params.axis = v.axis;
  return params;
}

function expressionText(raw) {
  const text = String(raw ?? "").trim();
  return text.length > 0 && plainNumber(text) == null;
}

function measureRow(key, label, value, unit, showIf) {
  const parsed = plainNumber(value);
  const row = parsed == null
    ? { type: "text", key, label, unit, value: String(value ?? "") }
    : { type: "number", key, label, unit, value: parsed, min: 0.01 };
  if (showIf) row.showIf = showIf;
  return row;
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

/** Valeur affichée : l'expression si la cote en a une, sinon le nombre. */
export function chamferFieldValue(params, prop, fallback) {
  const found = (params ?? []).find((item) => item.prop === prop);
  if (found?.expr) return found.expr;
  if (found && found.value != null) return found.value;
  return fallback;
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

function storedMeasure(params, prop, fallback) {
  const found = (params ?? []).find((item) => item.prop === prop);
  if (found?.expr) return { expr: String(found.expr) };
  if (found && found.value != null) return { numeric: Number(found.value) };
  const parsed = plainNumber(fallback);
  return parsed == null
    ? { expr: String(fallback ?? "") }
    : { numeric: parsed };
}

function readMeasure(raw, stored, bounds) {
  const text = typeof raw === "string" ? raw.trim() : raw;
  if (stored.expr && String(text ?? "").trim() === stored.expr) return stored.expr;
  const parsed = plainNumber(text);
  if (parsed == null) {
    const expr = String(text ?? "").trim();
    return expr ? expr : null;
  }
  if (!(parsed > bounds.min) || !(parsed < bounds.max)) return null;
  return parsed;
}

function sameMeasure(value, stored) {
  if (typeof value === "string") return stored.expr === value;
  return stored.numeric != null && Math.abs(value - stored.numeric) < 1e-9;
}

/**
 * Valeurs `set_params` pour rééditer un chanfrein.
 * `{}` si rien n'a changé, `null` si la saisie est invalide.
 */
export function chamferEditValues(v, chamfer, params) {
  const kind = v.kind || "egale";
  if (!CHAMFER_KINDS.has(kind)) return null;
  const sizeStored = storedMeasure(params, "Size", chamfer.size);
  const size = readMeasure(v.size, sizeStored, { min: 0, max: Infinity });
  if (size == null) return null;
  const values = { ChamferType: kind, Size: size };
  const flip = kind === "egale" ? false : !!v.flip;
  let secondSame = true;
  if (kind === "deux") {
    const stored = storedMeasure(params, "Size2", chamfer.size2);
    const size2 = readMeasure(v.size2, stored, { min: 0, max: Infinity });
    if (size2 == null) return null;
    values.Size2 = size2;
    values.FlipDirection = flip;
    secondSame = sameMeasure(size2, stored);
  } else if (kind === "angle") {
    const stored = storedMeasure(params, "Angle", chamfer.angle);
    const angle = readMeasure(v.angle, stored, { min: 0, max: 90 });
    if (angle == null) return null;
    values.Angle = angle;
    values.FlipDirection = flip;
    secondSame = sameMeasure(angle, stored);
  } else {
    values.FlipDirection = false;
  }
  const unchanged = kind === chamfer.type
    && flip === !!chamfer.flip
    && sameMeasure(size, sizeStored)
    && secondSame;
  return unchanged ? {} : values;
}

export const FEATURES = [
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
  dressup({
    button: "btn-fillet",
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
    button: "btn-shell",
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
  {
    button: "btn-linpattern",
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
    ],
    build: (v) => {
      const length = num(v.length);
      const count = parseInt(v.count, 10);
      return length && count >= 2
        ? { op: "add_linear_pattern",
            params: { ...patternDirectionParams(v), length, count,
                      spacing: v.mode === "spacing",
                      ...patternFeaturesParams(v) } }
        : null;
    },
    invalid: "Valeurs invalides",
    refresh: "part",
  },
  {
    button: "btn-polpattern",
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
  {
    button: "btn-boolean",
    buttons: ["btn-boolean", "btn-gem-combine"],
    ...COMBINE_FEATURE,
  },
  surface({
    button: "btn-surf-extrude",
    icon: "surface_extrude", title: "Surface extrudée",
    groups: [{ label: "Paramètres", rows: [
      { type: "number", key: "length", label: "Longueur", value: 20,
        unit: "mm" },
    ] }],
    note: "Utilise la dernière esquisse — le profil peut être OUVERT.",
    build: (v) => {
      const length = num(v.length);
      return length ? { op: "surface_extrude", params: { length } } : null;
    },
  }),
  surface({
    button: "btn-surf-revolve",
    icon: "surface_revolve", title: "Surface de révolution",
    groups: [{ label: "Paramètres", rows: [
      { type: "number", key: "angle", label: "Angle", value: 360,
        unit: "°", min: 0.01 },
    ] }],
    note: "Autour de l'axe vertical de la dernière esquisse.",
    build: (v) => {
      const angle = num(v.angle);
      return angle ? { op: "surface_revolve", params: { angle } } : null;
    },
  }),
  surface({
    button: "btn-surf-loft",
    icon: "surface_loft",
    title: "Surface lissée",
    groups: [{ label: "Profils",
      rows: [{ type: "selection", key: "profiles", accepts: ["sketch"],
               multiple: true,
               hint: "Cliquez les esquisses dans l'arbre, dans l'ordre" }] }],
    build: (v) => {
      const items = v.profiles?.items ?? [];
      if (items.length < 2) return null;
      return { op: "surface_loft",
               params: { sketches: items.map((i) => i.name) } };
    },
    invalid: "Surface lissée : au moins deux profils",
  }),
  surface({
    button: "btn-surf-sew",
    icon: "sew",
    title: "Coudre",
    groups: [{ label: "Surfaces",
      rows: [{ type: "selection", key: "surfaces", accepts: ["surface"],
               multiple: true,
               hint: "Cliquez les surfaces dans l'arbre" }] }],
    note: "Si la peau cousue est fermée, elle devient un solide.",
    build: (v) => {
      const items = v.surfaces?.items ?? [];
      if (items.length < 2) return null;
      return { op: "surface_sew",
               params: { surfaces: items.map((i) => i.name) } };
    },
    invalid: "Coudre : au moins deux surfaces",
  }),
  surface({
    button: "btn-surf-thicken",
    icon: "thicken",
    title: "Épaissir",
    groups: [
      { label: "Surface",
        rows: [{ type: "selection", key: "surface", accepts: ["surface"],
                 hint: "Cliquez une surface dans l'arbre" }] },
      { label: "Paramètres",
        rows: [{ type: "number", key: "thickness", label: "Épaisseur",
                 value: 2, unit: "mm" }] },
    ],
    build: (v) => {
      const thickness = num(v.thickness);
      if (!v.surface || !thickness) return null;
      return { op: "surface_thicken",
               params: { surface: v.surface.name, thickness } };
    },
    invalid: "Épaissir : une surface et une épaisseur non nulle",
  }),
  {
    button: "btn-surf-cut",
    icon: "surface_cut",
    title: "Couper avec une surface",
    groups: (ctx) => [
      { label: "Surface",
        rows: [{ type: "selection", key: "surface", accepts: ["surface"],
                 hint: "Cliquez la surface qui traverse le solide",
                 value: ctx.selection(["surface"]) }] },
      { label: "Options",
        rows: [{ type: "check", key: "flip", label: "Inverser le côté",
                 value: false }] },
    ],
    note: "L'aperçu montre ce qui reste. La surface doit traverser le "
      + "solide de part en part.",
    build: (v) => (v.surface ? { op: "add_surface_cut",
      params: { surface: v.surface.name, flip: !!v.flip } } : null),
    invalid: () => ({ text: "Couper : cliquez une surface",
                      tone: "guide" }),
    refresh: "part",
  },
  surface({
    button: "btn-surf-planar",
    icon: "surface_planar",
    title: "Surface plane",
    groups: (ctx) => [{ label: "Contour", rows: [sketchRow(ctx, "profile",
      "Cliquez l'esquisse du contour fermé")] }],
    note: "Le contour doit être fermé et plan.",
    build: (v) => (v.profile
      ? { op: "surface_planar", params: { sketch: v.profile.name } } : null),
    invalid: "Surface plane : une esquisse au contour fermé",
  }),
  surface({
    button: "btn-surf-sweep",
    icon: "surface_sweep",
    title: "Surface balayée",
    groups: (ctx) => [
      // Pas de « dernière esquisse » d'office : elle pourrait être la
      // trajectoire, et le clic suivant tomberait dans la mauvaise case.
      { label: "Profil", rows: [sketchRow(ctx, "profile",
        "Cliquez l'esquisse du profil — ouvert ou fermé",
        { latest: false })] },
      { label: "Trajectoire",
        rows: [{ type: "selection", key: "spine",
                 accepts: ["sketch", "surface"],
                 hint: "Puis la trajectoire : une esquisse ou une spline 3D" }] },
    ],
    build: (v) => {
      if (!v.profile || !v.spine || v.profile.name === v.spine.name) return null;
      return { op: "surface_sweep",
               params: { profile: v.profile.name, spine: v.spine.name } };
    },
    invalid: "Surface balayée : un profil puis une trajectoire (différents)",
  }),
  surface({
    button: "btn-surf-offset",
    icon: "surface_offset",
    title: "Surface décalée",
    groups: (ctx) => [
      { label: "Surface",
        rows: [{ type: "selection", key: "surface", accepts: ["surface"],
                 hint: "Cliquez la surface à décaler",
                 value: ctx.selection(["surface"]) }] },
      { label: "Paramètres",
        rows: [
          { type: "number", key: "distance", label: "Distance", value: 5,
            unit: "mm" },
          { type: "check", key: "flip", label: "Inverser le côté",
            value: false },
        ] },
    ],
    note: "Distance 0 : une copie de la surface.",
    build: (v) => {
      const distance = num(v.distance);
      if (!v.surface || distance === null) return null;
      return { op: "surface_offset", params: {
        surface: v.surface.name, distance: v.flip ? -distance : distance } };
    },
    invalid: "Surface décalée : une surface et une distance",
  }),
  surface({
    button: "btn-surf-fill",
    icon: "surface_fill",
    title: "Surface de remplissage",
    groups: [{ label: "Contour",
      rows: [{ type: "selection", key: "boundary",
               accepts: ["boundary", "sketch", "surface"], multiple: true,
               hint: "Cliquez les arêtes d'un contour fermé : bords de "
                 + "surface, courbes 3D, arêtes du solide ou esquisse" }] },
      { label: "Options",
        rows: [{ type: "check", key: "tangent",
                 label: "Tangent aux faces voisines", value: false }] }],
    note: "Sans tangence, la surface touche seulement le contour. Avec, "
      + "elle prolonge en douceur les faces que bordent les arêtes.",
    build: (v) => {
      const items = v.boundary?.items ?? [];
      if (!items.length) return null;
      return { op: "surface_fill", params: {
        boundary: items.map(boundaryParam), tangent: !!v.tangent } };
    },
    invalid: "Remplissage : sélectionnez un contour fermé",
  }),
  surface({
    button: "btn-surf-boundary",
    icon: "surface_boundary",
    title: "Surface frontière",
    groups: [{ label: "Courbes",
      rows: [{ type: "selection", key: "boundary",
               accepts: ["boundary", "sketch", "surface"], multiple: true,
               hint: "Cliquez deux à quatre courbes : bout à bout pour un "
                 + "contour, ou deux courbes opposées" }] }],
    build: (v) => {
      const items = v.boundary?.items ?? [];
      if (items.length < 2 || items.length > 4) return null;
      return { op: "surface_boundary",
               params: { boundary: items.map(boundaryParam) } };
    },
    invalid: "Surface frontière : deux à quatre courbes",
  }),
  surface({
    button: "btn-surf-radiate",
    icon: "surface_radiate",
    title: "Surface radiée",
    groups: [
      { label: "Contour plan",
        rows: [{ type: "selection", key: "boundary",
                 accepts: ["boundary", "sketch", "surface"], multiple: true,
                 hint: "Cliquez les arêtes d'un contour plan : solide, "
                   + "surface ou esquisse" }] },
      { label: "Paramètres",
        rows: [
          { type: "number", key: "distance", label: "Distance", value: 5,
            unit: "mm" },
          { type: "check", key: "inside", label: "Vers l'intérieur",
            value: false },
        ] },
    ],
    note: "Une bande plane part du contour, dans son plan (une collerette).",
    build: (v) => {
      const items = v.boundary?.items ?? [];
      const distance = num(v.distance);
      if (!items.length || !distance) return null;
      return { op: "surface_radiate", params: {
        boundary: items.map(boundaryParam),
        distance: v.inside ? -Math.abs(distance) : Math.abs(distance) } };
    },
    invalid: "Radiée : un contour plan et une distance",
  }),
  {
    button: "btn-surf-mid",
    icon: "surface_mid",
    title: "Surface médiane",
    preview: false,
    groups: () => [{ label: "Paroi",
      rows: [{ type: "selection", key: "faces", accepts: ["face"],
               multiple: true,
               hint: "Cliquez les deux faces en vis-à-vis de la paroi" }] }],
    note: "Faces planes parallèles ou cylindres concentriques : la peau "
      + "passe à mi-épaisseur et suit les cotes de la pièce.",
    build: (v) => {
      const items = v.faces?.items ?? [];
      if (items.length !== 2) return null;
      return { op: "surface_mid",
               params: { faces: items.map((i) => i.face) } };
    },
    invalid: () => ({ text: "Médiane : les deux faces d'une paroi",
                      tone: "guide" }),
    refresh: "part",
  },
  surface({
    button: "btn-surf-ruled",
    icon: "surface_ruled",
    title: "Surface réglée",
    groups: [{ label: "Courbes",
      rows: [{ type: "selection", key: "boundary",
               accepts: ["boundary", "sketch", "surface"], multiple: true,
               hint: "Cliquez les deux courbes à relier" }] }],
    note: "Des segments droits relient les deux courbes.",
    build: (v) => {
      const items = v.boundary?.items ?? [];
      if (items.length !== 2) return null;
      return { op: "surface_ruled",
               params: { boundary: items.map(boundaryParam) } };
    },
    invalid: "Surface réglée : exactement deux courbes",
  }),
  surface({
    button: "btn-surf-split",
    icon: "surface_split",
    title: "Ligne de séparation",
    groups: (ctx) => [
      { label: "Surface à scinder",
        rows: [{ type: "selection", key: "surface", accepts: ["surface"],
                 hint: "Cliquez la surface",
                 value: ctx.selection(["surface"]) }] },
      { label: "Courbe",
        rows: [{ type: "selection", key: "tool",
                 accepts: ["boundary", "surface", "sketch"],
                 hint: "Puis la courbe posée dessus (projetée, "
                   + "d'intersection, spline 3D)" }] },
    ],
    note: "Chaque morceau se supprime ou se remplit ensuite à part.",
    build: (v) => {
      if (!v.surface || !v.tool || v.tool.name === v.surface.name) return null;
      return { op: "surface_split",
               params: { surface: v.surface.name, tool: v.tool.name } };
    },
    invalid: "Scinder : une surface puis une courbe posée dessus",
  }),
  {
    button: "btn-replace-face",
    icon: "replace_face",
    title: "Remplacer la face",
    groups: (ctx) => [
      { label: "Face du solide",
        rows: [{ type: "selection", key: "face", accepts: ["face"],
                 hint: "Cliquez la face à remplacer",
                 value: ctx.selection(["face"]) }] },
      { label: "Surface de remplacement",
        rows: [{ type: "selection", key: "surface", accepts: ["surface"],
                 hint: "Puis la surface, qui doit couvrir toute la face" }] },
    ],
    note: "La matière s'étend ou se retire jusqu'à la surface ; l'aperçu "
      + "montre le résultat.",
    build: (v) => (v.face && v.surface ? { op: "add_replace_face",
      params: { face: v.face.face, surface: v.surface.name } } : null),
    invalid: () => ({ text: "Remplacer : une face du solide, puis une "
      + "surface", tone: "guide" }),
    refresh: "part",
  },
  {
    button: "btn-surf-delete-face",
    icon: "surface_delete_face",
    title: "Supprimer des faces",
    groups: () => [{ label: "Faces",
      rows: [{ type: "selection", key: "faces",
               accepts: ["face", "surfface"], multiple: true,
               hint: "Cliquez les faces à supprimer : sur le solide, ou "
                 + "sur une même surface" }] }],
    note: "Sur le solide, les faces voisines referment le trou (perçage, "
      + "congé, bossage retirés). Sur une surface, le trou reste ouvert : "
      + "il se bouche ensuite par un remplissage.",
    build: (v) => deleteFacesBuild(v.faces?.items),
    invalid: () => ({ text: "Supprimer : des faces du solide, ou d'une "
      + "même surface", tone: "guide" }),
    refresh: "part",
  },
  surface({
    button: "btn-surf-untrim",
    icon: "surface_untrim",
    title: "Désajuster la surface",
    groups: (ctx) => [{ label: "Face",
      rows: [{ type: "selection", key: "target",
               accepts: ["surfface", "surface"],
               hint: "Cliquez la face à rendre entière",
               value: ctx.selection(["surface"]) }] }],
    note: "La face retrouve les bords naturels de sa surface : trous "
      + "bouchés, contour d'origine.",
    build: (v) => (v.target ? { op: "surface_untrim", params: {
      surface: v.target.name, face: v.target.face ?? 0 } } : null),
    invalid: "Désajuster : cliquez une face de surface",
  }),
  surface({
    button: "btn-surf-fillet",
    icon: "surface_fillet",
    title: "Congé de surface",
    groups: [
      { label: "Arêtes",
        rows: [{ type: "selection", key: "edges", accepts: ["boundary"],
                 multiple: true,
                 hint: "Cliquez les arêtes entre deux faces d'une surface" }] },
      { label: "Paramètres",
        rows: [{ type: "number", key: "radius", label: "Rayon", value: 3,
                 unit: "mm", min: 0.01 }] },
    ],
    note: "Deux surfaces séparées se cousent d'abord (Coudre).",
    build: (v) => {
      const params = surfaceFilletParams(v.edges?.items, num(v.radius));
      return params ? { op: "surface_fillet", params } : null;
    },
    invalid: "Congé : des arêtes d'une même surface et un rayon",
  }),
  surface({
    button: "btn-curve-intersection",
    icon: "curve_intersection",
    title: "Courbe d'intersection",
    groups: (ctx) => [
      { label: "Surfaces",
        rows: [
          { type: "selection", key: "first", accepts: ["surface"],
            hint: "Cliquez une surface", value: ctx.selection(["surface"]) },
          { type: "selection", key: "second", accepts: ["surface"],
            hint: "Puis la seconde surface",
            showIf: (v) => !v.body },
        ] },
      { label: "Options",
        rows: [{ type: "check", key: "body", label: "Avec le solide",
                 value: false }] },
    ],
    build: (v) => {
      if (!v.first) return null;
      if (v.body) {
        return { op: "curve_intersection",
                 params: { first: v.first.name, body: true } };
      }
      if (!v.second || v.second.name === v.first.name) return null;
      return { op: "curve_intersection",
               params: { first: v.first.name, second: v.second.name } };
    },
    invalid: "Intersection : deux surfaces, ou une surface et le solide",
  }),
  surface({
    button: "btn-curve-project",
    icon: "curve_project",
    title: "Courbe projetée",
    groups: (ctx) => [
      { label: "Esquisse", rows: [sketchRow(ctx, "sketch",
        "Cliquez l'esquisse à projeter", { latest: false })] },
      { label: "Face cible",
        rows: [{ type: "selection", key: "target",
                 accepts: ["surfface", "surface"],
                 hint: "Puis la face de surface où projeter" }] },
    ],
    note: "Les traits se projettent selon la normale de l'esquisse.",
    build: (v) => {
      if (!v.sketch || !v.target) return null;
      return { op: "curve_project", params: { sketch: v.sketch.name,
        surface: v.target.name, face: v.target.face ?? 0 } };
    },
    invalid: "Projeter : une esquisse puis une face de surface",
  }),
  surface({
    button: "btn-curve-helix",
    icon: "nodes_helix",
    title: "Hélice",
    groups: [{ label: "Paramètres", rows: [
      { type: "number", key: "pitch", label: "Pas", value: 5, unit: "mm",
        min: 0.01 },
      { type: "number", key: "height", label: "Hauteur", value: 30,
        unit: "mm", min: 0.01 },
      { type: "number", key: "radius", label: "Rayon", value: 10, unit: "mm",
        min: 0.01 },
      { type: "number", key: "angle", label: "Conicité", value: 0, unit: "°" },
      { type: "select", key: "axis", label: "Axe", value: "Z",
        options: [["Z", "Axe Z"], ["Y", "Axe Y"], ["X", "Axe X"]] },
      { type: "check", key: "left", label: "Pas à gauche", value: false },
    ] }],
    note: "Une courbe : trajectoire d'une surface balayée ou d'un "
      + "balayage (ressort, filet). Conicité ≠ 0 : spirale conique.",
    build: (v) => {
      const pitch = num(v.pitch);
      const height = num(v.height);
      const radius = num(v.radius);
      if (!(pitch > 0 && height > 0 && radius > 0)) return null;
      return { op: "curve_helix", params: { pitch, height, radius,
        angle: num(v.angle) ?? 0, axis: v.axis, left: !!v.left } };
    },
    invalid: "Hélice : pas, hauteur et rayon positifs",
  }),
  surface({
    button: "btn-curve-composite",
    icon: "curve_composite",
    title: "Courbe composite",
    groups: [{ label: "Courbes et arêtes",
      rows: [{ type: "selection", key: "boundary",
               accepts: ["boundary", "sketch", "surface"], multiple: true,
               hint: "Cliquez les courbes et arêtes, bout à bout" }] }],
    note: "Une seule trajectoire, pour un balayage par exemple.",
    build: (v) => {
      const items = v.boundary?.items ?? [];
      if (!items.length) return null;
      return { op: "curve_composite",
               params: { boundary: items.map(boundaryParam) } };
    },
    invalid: "Composite : cliquez des courbes bout à bout",
  }),
  surface({
    button: "btn-surf-extend",
    icon: "surface_extend",
    title: "Prolonger la surface",
    groups: (ctx) => [
      { label: "Bord à prolonger",
        rows: [{ type: "selection", key: "target",
                 accepts: ["boundary", "surface"],
                 hint: "Cliquez un bord de la surface — ou la surface "
                   + "entière pour tous ses bords",
                 value: ctx.selection(["surface"]) }] },
      { label: "Paramètres",
        rows: [{ type: "number", key: "distance", label: "Distance",
                 value: 10, unit: "mm", min: 0.01 }] },
    ],
    build: (v) => {
      const params = extendParams(v.target, num(v.distance));
      return params ? { op: "surface_extend", params } : null;
    },
    invalid: "Prolonger : un bord de surface et une distance positive",
  }),
  surface({
    button: "btn-surf-trim",
    icon: "surface_trim",
    title: "Ajuster la surface",
    groups: (ctx) => [
      { label: "Outil de coupe",
        rows: [{ type: "selection", key: "tool", accepts: ["surface"],
                 hint: "Cliquez la surface qui coupe",
                 value: ctx.selection(["surface"]) }] },
      { label: "Partie à garder",
        rows: [
          { type: "selection", key: "keep", accepts: ["surfpoint"],
            hint: "Puis cliquez, sur la surface à ajuster, la partie "
              + "à garder" },
          { type: "check", key: "mutual", label: "Ajustement mutuel",
            value: false },
          { type: "selection", key: "toolKeep", accepts: ["surfpoint"],
            hint: "Et la partie de l'outil à garder",
            showIf: (v) => !!v.mutual },
        ] },
    ],
    build: (v) => trimParams(v),
    invalid: "Ajuster : l'outil, puis la partie à garder d'une autre surface",
  }),
  {
    button: "btn-graph-feature",
    icon: "graph_feature",
    title: "Fonction graphe",
    preview: false,
    groups: () => [{
      label: "Opération",
      rows: [
        { type: "select", key: "mode", value: "fuse",
          options: [
            ["fuse", "Solide — Ajouter"],
            ["cut", "Solide — Soustraire"],
            ["curve", "Courbe ou surface"],
          ] },
      ],
    }],
    note: "La géométrie produite est figée : changer une variable globale "
      + "ne recalcule pas la fonction — il faut la rouvrir et appliquer. "
      + "Le résultat est une forme combinée par un booléen, pas une "
      + "chaîne de fonctions.",
    build: (v) => {
      if (v.mode === "curve") {
        return {
          op: "add_graph_feature",
          params: { graph: minimalGraphCurve() },
        };
      }
      return {
        op: "add_graph_feature",
        params: { graph: minimalGraphFeature(), mode: v.mode },
      };
    },
    refresh: "part",
    openGraphEditor: true,
  },
  {
    button: "btn-repeat-variable",
    icon: "variable_pattern",
    title: "Réseau variable",
    preview: false,
    groups: (ctx) => [
      { label: "Fonctions",
        rows: [{ type: "selection", key: "features", accepts: ["feature"],
                 multiple: true, value: ctx?.selection?.(["feature"]) ?? null,
                 hint: "Cliquez les fonctions dans l'arbre, dans "
                       + "l'ordre du groupe" }] },
      { label: "Opération",
        rows: [
          { type: "select", key: "mode", value: "fuse",
            options: [["fuse", "Ajouter"], ["cut", "Soustraire"]] },
        ] },
    ],
    note: "Rejoue un groupe de fonctions avec des cotes différentes. "
      + "Si la topologie d'une instance ne correspond plus, la "
      + "répétition s'arrête plutôt que de produire.",
    build: (v) => {
      const items = v.features?.items ?? [];
      if (!items.length) return null;
      return {
        op: "add_repeat_feature",
        params: {
          features: items.map((item) => item.name),
          graph: minimalRepeatGraph(),
          mode: v.mode,
        },
      };
    },
    invalid: "Réseau variable : cliquez au moins une fonction dans l'arbre",
    refresh: "part",
    openGraphEditor: true,
  },
];
