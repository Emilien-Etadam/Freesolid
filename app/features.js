// Registry déclaratif des panneaux de fonctions mécaniques.
// Le branchement (clic → featureCommand → panel.open) vit dans main.js.
//
// Chaque entrée décrit un panneau « ouvrir → éditer → aperçu → OK ».
// build(v, ctx) rend { op, params } ou null (aperçu éteint, OK bloqué).

import { num } from "./num.js";
import { minimalGraphCurve, minimalGraphFeature, minimalRepeatGraph } from "./graph.js";
import { resolveProfileSketch } from "./features/commun.js";
import { VOLUMES } from "./features/volumes.js";
import { HABILLAGE } from "./features/habillage.js";
import { REPETITIONS } from "./features/repetitions.js";
import { COMBINER } from "./features/combiner.js";

export {
  availableSketches,
  dressup,
  hasSelection,
  NO_SKETCH_AVAILABLE,
  resolveProfileSketch,
} from "./features/commun.js";
export {
  checkedContours,
  contourLabel,
  contourRows,
  extrudeBuild,
  extrudeGroups,
  extrudeInvalid,
  holePositions,
  revolutionAxisOptions,
  revolutionCreationParams,
  revolutionEditValues,
  revolutionGroups,
  revolutionProblem,
} from "./features/volumes.js";
export {
  chamferCreationParams,
  chamferEditValues,
  chamferFieldValue,
  chamferProblem,
  chamferRows,
  shellBuild,
  vertexChamferDistances,
  vertexChamferRows,
} from "./features/habillage.js";
export {
  linearSecondDirection,
  patternDirectionParams,
  patternDirectionRows,
  patternFeaturesGroup,
  patternFeaturesParams,
} from "./features/repetitions.js";

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

/** Surface médiane : deux faces cliquées, ou toutes les parois. */
export function midParams(v) {
  if (v.auto) {
    const thickness = num(v.thickness);
    return thickness > 0
      ? { op: "surface_mid", params: { thickness } } : null;
  }
  const items = v.faces?.items ?? [];
  if (items.length !== 2) return null;
  return { op: "surface_mid", params: { faces: items.map((i) => i.face) } };
}

/** Couper avec une surface — tout un côté, ou une bande épaisse. */
export function surfaceCutParams(v) {
  if (!v.surface) return null;
  const params = { surface: v.surface.name, flip: !!v.flip };
  if (v.thick) {
    const thickness = num(v.thickness);
    if (!(thickness > 0)) return null;
    params.thickness = thickness;
  }
  return { op: "add_surface_cut", params };
}

/** Forme libre : surface, points poussés [x, y, z, h], rayon. */
export function freeformParams(v) {
  const radius = num(v.radius);
  const pushes = (v.pushes ?? []).filter((p) => p.length === 4 && p[3]);
  if (!v.surface || !pushes.length || !(radius > 0)) return null;
  return { op: "surface_freeform", params: {
    surface: v.surface.name, radius, pushes, keep_edges: !!v.keepEdges } };
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

export const FEATURES = [
  ...VOLUMES,
  ...HABILLAGE,
  ...REPETITIONS,
  ...COMBINER,
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
        rows: [
          { type: "check", key: "flip", label: "Inverser le côté",
            value: false },
          { type: "check", key: "thick", label: "Enlever une bande épaisse",
            value: false },
          { type: "number", key: "thickness", label: "Épaisseur", value: 2,
            unit: "mm", min: 0.01, showIf: (v) => v.thick },
        ] },
    ],
    note: "L'aperçu montre ce qui reste. La surface doit traverser le "
      + "solide de part en part ; en bande épaisse, seule la matière "
      + "qu'elle occupe part.",
    build: (v) => surfaceCutParams(v),
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
      rows: [
        { type: "check", key: "auto", label: "Toutes les parois de la pièce",
          value: false },
        { type: "selection", key: "faces", accepts: ["face"],
          multiple: true, showIf: (v) => !v.auto,
          hint: "Cliquez les deux faces en vis-à-vis de la paroi" },
        { type: "number", key: "thickness", label: "Épaisseur maximale",
          value: 3, unit: "mm", min: 0.01, showIf: (v) => !!v.auto },
      ] }],
    note: "La peau passe à mi-épaisseur et suit les cotes de la pièce. "
      + "Plans parallèles et cylindres concentriques : exact ; faces "
      + "inclinées ou courbes : surface passant par les milieux.",
    build: (v) => midParams(v),
    invalid: () => ({ text: "Médiane : les deux faces d'une paroi, ou "
      + "toutes les parois et une épaisseur", tone: "guide" }),
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
    button: "btn-surf-flatten",
    icon: "surface_flatten",
    title: "Aplatir la surface",
    groups: (ctx) => [{ label: "Face",
      rows: [{ type: "selection", key: "target",
               accepts: ["surfface", "surface"],
               hint: "Cliquez la face de surface à aplatir",
               value: ctx.selection(["surface"]) }] }],
    note: "Le patron à plat se pose sur le plan de dessus, à droite de la "
      + "pièce. Exact pour une face développable (cylindre, cône), "
      + "approché sinon.",
    build: (v) => (v.target ? { op: "surface_flatten", params: {
      surface: v.target.name, face: v.target.face ?? 0 } } : null),
    invalid: "Aplatir : cliquez une face de surface",
  }),
  surface({
    button: "btn-surf-freeform",
    icon: "surface_freeform",
    title: "Forme libre",
    groups: (ctx) => [
      { label: "Surface",
        rows: [{ type: "selection", key: "surface", accepts: ["surface"],
                 hint: "Cliquez la surface à déformer",
                 value: ctx.selection(["surface"]) }] },
      { label: "Points à pousser",
        rows: [{ type: "points", key: "pushes", value: [],
                 extra: { label: "Hauteur", value: 5 },
                 empty: "Puis cliquez les points à pousser, sur la "
                   + "surface" }] },
      { label: "Paramètres",
        rows: [
          { type: "number", key: "radius", label: "Rayon d'influence",
            value: 15, unit: "mm", min: 0.01 },
          { type: "check", key: "keepEdges", label: "Bords fixes",
            value: false },
        ] },
    ],
    note: "Chaque point bombe la surface selon sa normale, de sa hauteur "
      + "(4e colonne ; négative : un creux).",
    build: (v) => freeformParams(v),
    invalid: "Forme libre : une surface, des points à pousser, un rayon",
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
