// Graphe de dépendances du FeatureManager — module pur.
// Pas de DOM, pas de window, pas de réseau. Entrée : l'arbre `get_tree`.
//
// Disposition : couches par plus long chemin (Sugiyama, étape 1), puis
// réduction de croisements par barycentre (étapes 2–3). Dagre a été
// écarté : son ESM CDN ne s'importe pas sous node --test (pas d'https:).

import { splitHistoryAroundBar } from "./history.js";
import {
  hasSelection,
  NO_SKETCH_AVAILABLE,
  resolveProfileSketch,
} from "./features.js";

const COL_GAP = 200;
const ROW_GAP = 72;
const ORIGIN_X = 48;
const ORIGIN_Y = 48;
const CROSSING_PASSES = 8;
const NODE_HALF_W = 74;
const VAR_HALF_W = 54;
const NODE_BASE_H = 32;
const GRAPH_PARAM_MAX = 1;

const IDENTIFIER = /[A-Za-z_][A-Za-z0-9_]*/g;

function listOf(section) {
  return Array.isArray(section) ? section : [];
}

function identifiersIn(expression) {
  if (typeof expression !== "string") return [];
  return expression.match(IDENTIFIER) ?? [];
}

function citedVariables(expression, variableNames) {
  const found = new Set(identifiersIn(expression));
  const cited = [];
  for (const name of variableNames) {
    if (found.has(name)) cited.push(name);
  }
  return cited;
}

function walkEntries(tree, visit) {
  const walk = (items) => {
    for (const item of listOf(items)) {
      if (!item || typeof item !== "object") continue;
      visit(item);
      walk(item.children);
    }
  };
  walk(tree.features);
  walk(tree.surfaces);
  walk(tree.planes);
  walk(tree.bodies);
}

function roleOf(item, fallback) {
  if (fallback) return fallback;
  if (item.type === "Sketcher::SketchObject") return "sketch";
  if (item.type === "PartDesign::Plane") return "datum";
  if (item.type === "PartDesign::Body") return "body";
  return "feature";
}

function kindOf(item, role) {
  if (typeof item.kind === "string" && item.kind) return item.kind;
  if (role === "plane") return item.label || "Plan de référence";
  if (role === "variable") return "Variable";
  if (role === "body") return "Corps";
  if (role === "surface") return "Surface";
  if (role === "sketch" || item.type === "Sketcher::SketchObject") {
    return "Esquisse";
  }
  if (role === "datum" || item.type === "PartDesign::Plane") {
    return "Plan de référence";
  }
  return item.label || item.name || "";
}

function featureParams(item) {
  return listOf(item.params).filter(
    (param) => param && typeof param === "object" && typeof param.prop === "string");
}

function addNode(nodes, item, role, fallbackOrder) {
  const name = item.name;
  if (!name || typeof name !== "string" || nodes.has(name)) return;
  const order = typeof item.order === "number" ? item.order : fallbackOrder;
  const params = featureParams(item);
  nodes.set(name, {
    name,
    label: item.label || name,
    kind: kindOf(item, role),
    role,
    type: item.type,
    order,
    afterBar: false,
    layer: 0,
    x: 0,
    y: 0,
    params,
    height: NODE_BASE_H,
  });
}

/** Noms des fonctions (et esquisses enfants) situés après la barre de reprise. */
function namesAfterBar(tree) {
  const split = splitHistoryAroundBar(
    listOf(tree.features), listOf(tree.surfaces), tree.tip);
  const names = new Set();
  for (const row of split.after) {
    const item = row?.item;
    if (item?.name) names.add(item.name);
    for (const child of listOf(item?.children)) {
      if (child?.name) names.add(child.name);
    }
  }
  return names;
}

function edgeKey(from, to, kind) {
  return `${kind}\0${from}\0${to}`;
}

function collectEdges(tree, variableNames) {
  const edges = [];
  const seen = new Set();
  const push = (from, to, kind, subs) => {
    if (!from || !to || from === to) return;
    const key = edgeKey(from, to, kind);
    if (seen.has(key)) return;
    seen.add(key);
    const edge = { from, to, kind };
    if (kind === "geom" && subs && subs.length) edge.subs = subs;
    edges.push(edge);
  };

  walkEntries(tree, (item) => {
    const source = item.name;
    if (!source) return;
    const depSubs = item.dep_subs && typeof item.dep_subs === "object"
      && !Array.isArray(item.dep_subs) ? item.dep_subs : {};
    for (const dep of listOf(item.deps)) {
      if (typeof dep !== "string") continue;
      const subs = listOf(depSubs[dep]).filter(
        (name) => typeof name === "string" && name);
      push(dep, source, "geom", subs);
    }
    const driven = item.driven;
    if (!driven || typeof driven !== "object" || Array.isArray(driven)) return;
    const cited = new Set();
    for (const expression of Object.values(driven)) {
      for (const name of citedVariables(expression, variableNames)) {
        cited.add(name);
      }
    }
    for (const name of variableNames) {
      if (cited.has(name)) push(name, source, "param");
    }
  });
  return edges;
}

function longestLayers(names, incoming) {
  const memo = new Map();
  const visiting = new Set();

  const layerOf = (name) => {
    if (memo.has(name)) return memo.get(name);
    if (visiting.has(name)) return 0;
    visiting.add(name);
    let layer = 0;
    for (const pred of incoming.get(name) ?? []) {
      layer = Math.max(layer, layerOf(pred) + 1);
    }
    visiting.delete(name);
    memo.set(name, layer);
    return layer;
  };

  for (const name of names) layerOf(name);
  return memo;
}

function compareNodes(a, b) {
  if (a.order !== b.order) return a.order - b.order;
  if (a.name < b.name) return -1;
  if (a.name > b.name) return 1;
  return 0;
}

function barycenterOf(neighbors, indexOf, fallback) {
  let sum = 0;
  let count = 0;
  for (const name of neighbors) {
    const index = indexOf.get(name);
    if (index === undefined) continue;
    sum += index;
    count += 1;
  }
  return count ? sum / count : fallback;
}

function indexInBucket(bucket) {
  const indexOf = new Map();
  for (const [index, node] of bucket.entries()) {
    indexOf.set(node.name, index);
  }
  return indexOf;
}

function sortLayerByBarycenter(bucket, neighborMap, neighborIndex) {
  const keyed = bucket.map((node, index) => ({
    node,
    index,
    bary: barycenterOf(neighborMap.get(node.name) ?? [], neighborIndex, index),
  }));
  keyed.sort((a, b) => {
    if (a.bary !== b.bary) return a.bary - b.bary;
    return a.index - b.index;
  });
  return keyed.map((item) => item.node);
}

function reduceCrossings(byLayer, layerIds, edges) {
  const preds = new Map();
  const succs = new Map();
  for (const layer of layerIds) {
    for (const node of byLayer.get(layer)) {
      preds.set(node.name, []);
      succs.set(node.name, []);
    }
  }
  for (const edge of edges) {
    if (!preds.has(edge.to) || !succs.has(edge.from)) continue;
    succs.get(edge.from).push(edge.to);
    preds.get(edge.to).push(edge.from);
  }

  for (let pass = 0; pass < CROSSING_PASSES; pass++) {
    for (let i = 1; i < layerIds.length; i++) {
      const prev = byLayer.get(layerIds[i - 1]);
      const cur = byLayer.get(layerIds[i]);
      byLayer.set(layerIds[i],
        sortLayerByBarycenter(cur, preds, indexInBucket(prev)));
    }
    for (let i = layerIds.length - 2; i >= 0; i--) {
      const next = byLayer.get(layerIds[i + 1]);
      const cur = byLayer.get(layerIds[i]);
      byLayer.set(layerIds[i],
        sortLayerByBarycenter(cur, succs, indexInBucket(next)));
    }
  }
}

function assignCoordinates(byLayer, layerIds) {
  for (const layer of layerIds) {
    const bucket = byLayer.get(layer);
    for (const [index, node] of bucket.entries()) {
      node.x = ORIGIN_X + layer * COL_GAP;
      node.y = ORIGIN_Y + index * ROW_GAP;
    }
  }
}

function orientation(p, q, r) {
  const value = (q.y - p.y) * (r.x - q.x) - (q.x - p.x) * (r.y - q.y);
  if (Math.abs(value) < 1e-9) return 0;
  return value > 0 ? 1 : 2;
}

function segmentsCross(p1, q1, p2, q2) {
  const o1 = orientation(p1, q1, p2);
  const o2 = orientation(p1, q1, q2);
  const o3 = orientation(p2, q2, p1);
  const o4 = orientation(p2, q2, q1);
  if (o1 === 0 || o2 === 0 || o3 === 0 || o4 === 0) return false;
  return o1 !== o2 && o3 !== o4;
}

/**
 * Nombre de paires d'arêtes qui se coupent (segments entre centres).
 * Les arêtes qui partagent une extrémité ne comptent pas.
 */
export function countEdgeCrossings(graph) {
  const byName = new Map((graph?.nodes ?? []).map((node) => [node.name, node]));
  const segs = [];
  for (const edge of graph?.edges ?? []) {
    const a = byName.get(edge.from);
    const b = byName.get(edge.to);
    if (!a || !b) continue;
    segs.push({ from: edge.from, to: edge.to, a, b });
  }
  let count = 0;
  for (let i = 0; i < segs.length; i++) {
    for (let j = i + 1; j < segs.length; j++) {
      const p = segs[i];
      const q = segs[j];
      if (p.from === q.from || p.from === q.to
          || p.to === q.from || p.to === q.to) continue;
      if (segmentsCross(p.a, p.b, q.a, q.b)) count += 1;
    }
  }
  return count;
}

/**
 * Courbe de Bézier cubique à poignées horizontales.
 * `d` suit l'écart horizontal, borné pour éviter les boucles.
 */
export function edgeCurvePath(x1, y1, x2, y2) {
  const span = x2 - x1;
  const sign = span < 0 ? -1 : 1;
  const d = sign * Math.min(Math.max(Math.abs(span) * 0.45, 16), 90);
  return `M ${x1},${y1} C ${x1 + d},${y1} ${x2 - d},${y2} ${x2},${y2}`;
}

export function edgeAttachX(role, goingRight) {
  const half = role === "variable" ? VAR_HALF_W : NODE_HALF_W;
  return goingRight ? half : -half;
}

/**
 * Construit le graphe positionné d'un arbre `get_tree`.
 * @param {object|null|undefined} tree
 * @param {{ reduceCrossings?: boolean }} [options]
 * @returns {{ nodes: object[], edges: object[] }}
 */
export function buildGraph(tree, options = {}) {
  if (tree == null || typeof tree !== "object") {
    return { nodes: [], edges: [] };
  }

  const nodes = new Map();

  for (const [index, item] of listOf(tree.features).entries()) {
    const role = roleOf(item);
    addNode(nodes, item, role, 1e5 + index);
    for (const [childIndex, child] of listOf(item.children).entries()) {
      addNode(nodes, child, roleOf(child, "sketch"), 1e5 + index + childIndex + 1);
    }
  }
  for (const [index, item] of listOf(tree.surfaces).entries()) {
    addNode(nodes, item, "surface", 1e5 + index);
    for (const [childIndex, child] of listOf(item.children).entries()) {
      addNode(nodes, child, roleOf(child, "sketch"), 1e5 + index + childIndex + 1);
    }
  }
  for (const [index, item] of listOf(tree.planes).entries()) {
    addNode(nodes, item, "plane", -300 + index);
  }

  const variables = listOf(tree.variables).filter(
    (item) => item && typeof item.name === "string" && item.name);
  const variableNames = variables.map((item) => item.name);
  for (const [index, item] of variables.entries()) {
    addNode(nodes, item, "variable", -200 + index);
  }

  const edges = collectEdges(tree, variableNames);

  const referenced = new Set();
  for (const edge of edges) {
    referenced.add(edge.from);
    referenced.add(edge.to);
  }
  for (const [index, item] of listOf(tree.bodies).entries()) {
    if (item?.name && referenced.has(item.name) && !nodes.has(item.name)) {
      addNode(nodes, item, "body", 1e6 + index);
    }
  }

  const kept = [];
  const known = new Set(nodes.keys());
  for (const edge of edges) {
    if (known.has(edge.from) && known.has(edge.to)) kept.push(edge);
  }

  const incoming = new Map();
  for (const name of known) incoming.set(name, []);
  for (const edge of kept) {
    incoming.get(edge.to).push(edge.from);
  }
  const layers = longestLayers([...known], incoming);

  const byLayer = new Map();
  for (const node of nodes.values()) {
    node.layer = layers.get(node.name) ?? 0;
    const bucket = byLayer.get(node.layer);
    if (bucket) bucket.push(node);
    else byLayer.set(node.layer, [node]);
  }
  const layerIds = [...byLayer.keys()].sort((a, b) => a - b);
  for (const layer of layerIds) {
    byLayer.get(layer).sort(compareNodes);
  }
  const reduce = options.reduceCrossings !== false;
  if (reduce && layerIds.length > 1) {
    reduceCrossings(byLayer, layerIds, kept);
  }
  assignCoordinates(byLayer, layerIds);

  const afterBar = namesAfterBar(tree);
  for (const node of nodes.values()) {
    node.afterBar = afterBar.has(node.name);
  }

  const orderedNodes = [];
  for (const layer of layerIds) {
    orderedNodes.push(...byLayer.get(layer));
  }
  kept.sort((a, b) => {
    if (a.kind !== b.kind) return a.kind < b.kind ? -1 : 1;
    if (a.from !== b.from) return a.from < b.from ? -1 : 1;
    if (a.to !== b.to) return a.to < b.to ? -1 : 1;
    return 0;
  });

  return { nodes: orderedNodes, edges: kept };
}

/** Un fil paramétrique part d'une variable — pas d'une arête géométrique. */
export function isParamWireSource(role) {
  return role === "variable";
}

/** Un fil constructif part d'une esquisse vers le fond (palette). */
export function isConstructWireSource(role) {
  return role === "sketch";
}

/** Habillage : il faut une face ou des arêtes prises dans le viewport. */
export const GRAPH_DRESSUP_REASON =
  "sélectionnez d'abord une face ou une arête dans la zone graphique";

/**
 * Profil qui partira avec la création : esquisse sélectionnée, sinon
 * dernière libre — le même `resolveProfileSketch` que le ruban.
 * @param {{ selectedSketch?: { name?: string }|null, lastTree?: object|null }} [ctx]
 * @returns {{ name: string, label?: string }|null}
 */
export function graphCreateProfile(ctx) {
  return resolveProfileSketch(ctx ?? {}) ?? null;
}

/**
 * Une entrée de `FEATURES` est-elle posable depuis le graphe, dans ce
 * contexte ? Les habillages réclament une face ; les fonctions à profil
 * réclament une esquisse. Le reste est posable (la garde du panneau tranche).
 * @param {object|null|undefined} entry
 * @param {{ selectedSketch?: object|null, lastTree?: object|null, selection?: object|null }} [ctx]
 * @returns {{ enabled: boolean, reason: string|null, profile: object|null }}
 */
export function graphFeaturePlaceable(entry, ctx = {}) {
  if (!entry || typeof entry !== "object") {
    return { enabled: false, reason: "", profile: null };
  }
  if (entry.dressup) {
    if (!hasSelection(ctx.selection)) {
      return { enabled: false, reason: GRAPH_DRESSUP_REASON, profile: null };
    }
    return { enabled: true, reason: null, profile: null };
  }
  if (entry.sketchProfile) {
    const profile = graphCreateProfile(ctx);
    if (!profile) {
      return { enabled: false, reason: NO_SKETCH_AVAILABLE, profile: null };
    }
    return { enabled: true, reason: null, profile };
  }
  return { enabled: true, reason: null, profile: graphCreateProfile(ctx) };
}

/**
 * Palette du graphe : une ligne par entrée de `FEATURES`, icône et titre
 * repris tels quels. `enabled` / `reason` portent les murs visibles.
 * @param {object[]|null|undefined} features
 * @param {{ selectedSketch?: object|null, lastTree?: object|null, selection?: object|null }} [ctx]
 */
export function graphPaletteItems(features, ctx = {}) {
  const list = Array.isArray(features) ? features : [];
  return list.map((entry) => {
    const placed = graphFeaturePlaceable(entry, ctx);
    return {
      button: entry.button,
      icon: entry.icon,
      title: entry.title,
      dressup: !!entry.dressup,
      sketchProfile: !!entry.sketchProfile,
      enabled: placed.enabled,
      reason: placed.reason,
      profile: placed.profile,
    };
  });
}

/**
 * Palette de la fonction graphe : tout le catalogue, groupé par
 * catégorie. Un nœud non implémenté reste visible, grisé, avec sa raison.
 * @param {object[]|null|undefined} vocabulary
 */
export function graphNodePaletteGroups(vocabulary) {
  const groups = [];
  const byCat = new Map();
  for (const spec of listOfSpec(vocabulary)) {
    if (!spec || typeof spec.type !== "string") continue;
    const category = spec.category || "";
    if (!byCat.has(category)) {
      const group = {
        category,
        label: spec.category_label || category,
        items: [],
      };
      byCat.set(category, group);
      groups.push(group);
    }
    const implemented = spec.implemented !== false;
    byCat.get(category).items.push({
      type: spec.type,
      title: spec.label || spec.type,
      icon: spec.icon || "",
      enabled: implemented,
      reason: implemented
        ? null
        : (spec.reason || "pas encore implémenté"),
      spec,
    });
  }
  return groups;
}

/**
 * Arrivée d'un fil paramétrique : une fonction aux cotes éditables.
 * Esquisse, plan, surface, corps : visibles comme non cibles, pas après coup.
 */
export function isParamWireTarget(role) {
  return role === "feature";
}

/**
 * Expression envoyée à `set_params` pour lier une cote à une variable.
 * Le moteur d'expressions FreeCAD résout le VarSet (`Variables.nom`), pas
 * l'identifiant nu — c'est le même préfixe que le panneau Équations.
 */
export function expressionForVariable(name) {
  if (typeof name !== "string" || !name) return "";
  return `Variables.${name}`;
}

/**
 * Valeurs numériques qui figent une coupure : les cotes de `get_params`
 * dont l'expression cite `variableName`. La géométrie ne bouge pas —
 * on écrit la valeur courante, on ne remet pas à zéro.
 * @param {object[]|null|undefined} params
 * @param {string} variableName
 * @returns {Record<string, number>}
 */
export function freezeDrivenValues(params, variableName) {
  if (typeof variableName !== "string" || !variableName) return {};
  const values = {};
  const names = [variableName];
  for (const param of listOf(params)) {
    if (!param || typeof param !== "object") continue;
    if (typeof param.prop !== "string" || !param.prop) continue;
    if (typeof param.expr !== "string" || !param.expr) continue;
    if (!citedVariables(param.expr, names).length) continue;
    if (typeof param.value !== "number" || !Number.isFinite(param.value)) {
      continue;
    }
    values[param.prop] = param.value;
  }
  return values;
}

/**
 * Libellé d'une cote dans le sélecteur au dépôt du fil.
 * `labels` est `PROP_LABELS` du client — on n'en tient pas une seconde table.
 * @param {object|null|undefined} param
 * @param {Record<string, [string, string]>|null|undefined} labels
 */
export function paramChoiceCaption(param, labels) {
  if (!param || typeof param !== "object" || typeof param.prop !== "string") {
    return "";
  }
  const pair = labels && typeof labels === "object" ? labels[param.prop] : null;
  const label = Array.isArray(pair) && pair[0] ? pair[0] : param.prop;
  const unit = Array.isArray(pair) ? (pair[1] ?? "") : "mm";
  const withUnit = unit ? `${label} (${unit})` : label;
  if (typeof param.expr === "string" && param.expr) {
    return `${withUnit} — déjà « ${param.expr} »`;
  }
  return withUnit;
}

/**
 * Libellé compact d'une cote dans le nœud du graphe.
 * `labels` est `PROP_LABELS` — pas de seconde table. Σ comme dans l'arbre.
 */
export function graphParamLine(param, labels) {
  if (!param || typeof param !== "object" || typeof param.prop !== "string") {
    return "";
  }
  const pair = labels && typeof labels === "object" ? labels[param.prop] : null;
  const label = Array.isArray(pair) && pair[0] ? pair[0] : param.prop;
  const driven = typeof param.expr === "string" && param.expr;
  const prefix = driven ? "Σ " : "";
  const value = typeof param.value === "number" && Number.isFinite(param.value)
    ? String(param.value)
    : "";
  return `${prefix}${label} ${value}`.trim();
}

/** Premières cotes visibles dans le nœud ; le reste va en infobulle. */
export function graphVisibleParams(params) {
  return listOf(params).slice(0, GRAPH_PARAM_MAX);
}

/**
 * Sous-élément affiché sur une arête : « Face3 », ou « Edge3 +1 »
 * quand il y en a plusieurs.
 */
export function edgeSubCaption(subs) {
  const names = listOf(subs).filter((name) => typeof name === "string" && name);
  if (!names.length) return "";
  if (names.length === 1) return names[0];
  return `${names[0]} +${names.length - 1}`;
}

/** Milieu de la Bézier à poignées horizontales (t = 0,5). */
export function edgeMidpoint(x1, y1, x2, y2) {
  return { x: (x1 + x2) / 2, y: (y1 + y2) / 2 };
}

const FN_COL_GAP = 220;
const FN_ROW_GAP = 110;
const FN_ORIGIN_X = 56;
const FN_ORIGIN_Y = 72;
const FN_NODE_WIDTH = 168;
const FN_HEADER = 28;
const FN_ROW = 22;

function listOfSpec(value) {
  return Array.isArray(value) ? value : [];
}

function specByType(vocabulary) {
  const map = new Map();
  for (const spec of listOfSpec(vocabulary)) {
    if (spec && typeof spec.type === "string") map.set(spec.type, spec);
  }
  return map;
}

function isPointLiteral(value) {
  return !!value && typeof value === "object" && !Array.isArray(value)
    && Number.isFinite(Number(value.x))
    && Number.isFinite(Number(value.y))
    && Number.isFinite(Number(value.z));
}

function isNumberLiteral(value) {
  return typeof value === "number" && Number.isFinite(value);
}

/** Valeur initiale d'un port : point d'ancrage, liste, ou nombre. */
export function defaultPortLiteral(input) {
  if (input && (input.kind === "point" || input.kind === "vector")) {
    return { x: 0, y: 0, z: 0 };
  }
  if (input && input.kind === "list") return 1;
  return 1;
}

export const LIST_SOCKET_OPS = [
  { value: "flatten", label: "Aplatir" },
  { value: "simplify", label: "Simplifier" },
  { value: "graft", label: "Greffer" },
  { value: "unwrap", label: "Déplier" },
  { value: "wrap", label: "Envelopper" },
];

/** Valeur initiale d'un champ propre au nœud (valeur, nom, opération). */
export function defaultFieldValue(field) {
  const kind = field && field.kind;
  if (kind === "text" || kind === "code") return "";
  if (kind === "op") return "+";
  if (kind === "list_op") return "flatten";
  return 1;
}

/**
 * Graphe minimal valide — un cylindre — pour créer la fonction.
 * Ce n'est pas une table de types : une instance, prête à remplir.
 */
export function minimalGraphFeature() {
  return {
    nodes: [{
      id: "cyl",
      type: "cylindre",
      rayon: 10,
      hauteur: 20,
      ancrage: { x: 0, y: 0, z: 0 },
      pos: [240, 80],
    }],
    edges: [],
    output: "cyl",
  };
}

export function cloneGraphDraft(draft) {
  return JSON.parse(JSON.stringify(draft ?? { nodes: [], edges: [], output: "" }));
}

export function nextGraphNodeId(nodes) {
  const used = new Set(listOfSpec(nodes).map((node) => String(node.id)));
  let index = 1;
  while (used.has(`n${index}`)) index += 1;
  return `n${index}`;
}

export function newGraphNode(spec, id, pos) {
  const node = {
    id: String(id),
    type: spec.type,
    pos: [pos?.x ?? 0, pos?.y ?? 0],
  };
  for (const field of listOfSpec(spec.fields)) {
    node[field.key] = defaultFieldValue(field);
  }
  for (const input of listOfSpec(spec.inputs)) {
    if (input.kind === "any") continue;
    node[input.key] = defaultPortLiteral(input);
  }
  return node;
}

export function functionNodeSize(spec) {
  const rows = Math.max(
    listOfSpec(spec?.inputs).length,
    listOfSpec(spec?.fields).length,
    1,
  );
  return {
    width: FN_NODE_WIDTH,
    height: FN_HEADER + rows * FN_ROW + 8,
  };
}

export function functionPortLayout(spec, size) {
  const width = size?.width ?? FN_NODE_WIDTH;
  const height = size?.height ?? FN_HEADER + FN_ROW;
  const inputs = listOfSpec(spec?.inputs).map((input, index) => ({
    key: input.key,
    label: input.label,
    kind: input.kind,
    x: -width / 2,
    y: -height / 2 + FN_HEADER + index * FN_ROW,
  }));
  return {
    inputs,
    output: { x: width / 2, y: 0 },
  };
}

function wiredInputsOf(draft) {
  const map = new Map();
  for (const edge of listOfSpec(draft?.edges)) {
    if (!edge || typeof edge.to !== "string" || typeof edge.input !== "string") {
      continue;
    }
    if (!map.has(edge.to)) map.set(edge.to, new Set());
    map.get(edge.to).add(edge.input);
  }
  return map;
}

/**
 * JSON envoyé à `edit_graph_feature`.
 * Un fil vers un port inconnu est refusé ici, avant le moteur.
 * Un port sans fil prend le littéral du nœud. La sortie est unique.
 * `pos` est conservé : c'est le JSON persisté.
 * @returns {{ ok: true, graph: object } | { ok: false, error: string, node: string|null }}
 */
export function composeGraphPayload(draft, vocabulary) {
  const specs = specByType(vocabulary);
  const nodesIn = listOfSpec(draft?.nodes);
  const byId = new Map();
  for (const raw of nodesIn) {
    if (!raw || raw.id == null || typeof raw.type !== "string") {
      return { ok: false, error: "nœud invalide", node: null };
    }
    const ident = String(raw.id);
    if (byId.has(ident)) {
      return { ok: false, error: `nœud en double : « ${ident} »`, node: ident };
    }
    byId.set(ident, raw);
  }

  const output = draft?.output;
  if (output == null || output === "") {
    return { ok: false, error: "la sortie désignée est absente", node: null };
  }
  if (Array.isArray(output)) {
    return { ok: false, error: "la sortie désignée doit être unique", node: null };
  }
  const outputId = String(output);
  if (!byId.has(outputId)) {
    return {
      ok: false,
      error: `nœud de sortie inconnu « ${outputId} »`,
      node: outputId,
    };
  }

  const wired = wiredInputsOf(draft);
  const edges = [];
  const seenPorts = new Set();
  for (const edge of listOfSpec(draft?.edges)) {
    if (!edge || typeof edge !== "object") {
      return { ok: false, error: "arête invalide", node: null };
    }
    const src = String(edge.from ?? "");
    const dst = String(edge.to ?? "");
    const port = edge.input;
    if (!byId.has(src)) {
      return { ok: false, error: `arête depuis un nœud inconnu « ${src} »`, node: src };
    }
    if (!byId.has(dst)) {
      return { ok: false, error: `arête vers un nœud inconnu « ${dst} »`, node: dst };
    }
    const spec = specs.get(byId.get(dst).type);
    const allowed = new Set(listOfSpec(spec?.inputs).map((item) => item.key));
    if (typeof port !== "string" || !allowed.has(port)) {
      return {
        ok: false,
        error: `nœud « ${dst} » : entrée inconnue « ${port} »`,
        node: dst,
      };
    }
    const key = `${dst}\0${port}`;
    if (seenPorts.has(key)) {
      return {
        ok: false,
        error: `nœud « ${dst} » : entrée « ${port} » branchée deux fois`,
        node: dst,
      };
    }
    seenPorts.add(key);
    edges.push({ from: src, to: dst, input: port });
  }

  const nodes = [];
  for (const raw of nodesIn) {
    const ident = String(raw.id);
    const spec = specs.get(raw.type);
    if (!spec) {
      return {
        ok: false,
        error: `nœud « ${ident} » : type inconnu « ${raw.type} »`,
        node: ident,
      };
    }
    if (spec.implemented === false) {
      return {
        ok: false,
        error: spec.reason
          || `nœud « ${ident} » : pas encore implémenté`,
        node: ident,
      };
    }
    const node = { id: ident, type: raw.type };
    if (Array.isArray(raw.pos) && raw.pos.length === 2
        && Number.isFinite(Number(raw.pos[0]))
        && Number.isFinite(Number(raw.pos[1]))) {
      node.pos = [Number(raw.pos[0]), Number(raw.pos[1])];
    }
    for (const field of listOfSpec(spec.fields)) {
      if (raw[field.key] !== undefined) node[field.key] = raw[field.key];
    }
    const taken = wired.get(ident) ?? new Set();
    for (const input of listOfSpec(spec.inputs)) {
      if (taken.has(input.key)) continue;
      if (!(input.key in raw)) continue;
      const value = raw[input.key];
      if (input.kind === "point" || input.kind === "vector"
          || (input.kind === "any" && isPointLiteral(value))) {
        if (!isPointLiteral(value)) {
          return {
            ok: false,
            error: `nœud « ${ident} » : littéral invalide pour « ${input.key} »`,
            node: ident,
          };
        }
        node[input.key] = {
          x: Number(value.x), y: Number(value.y), z: Number(value.z),
        };
        continue;
      }
      if (input.kind === "list" || input.kind === "any") {
        if (Array.isArray(value)) {
          node[input.key] = value;
          continue;
        }
      }
      if (!isNumberLiteral(value) && typeof value !== "number") {
        const asNum = typeof value === "string" ? Number(value) : NaN;
        if (!Number.isFinite(asNum)) {
          return {
            ok: false,
            error: `nœud « ${ident} » : littéral invalide pour « ${input.key} »`,
            node: ident,
          };
        }
        node[input.key] = asNum;
        continue;
      }
      node[input.key] = Number(value);
    }
    nodes.push(node);
  }

  return { ok: true, graph: { nodes, edges, output: outputId } };
}

/**
 * Pose un fil sur un port nommé. Un port inconnu est refusé.
 * Un second fil sur le même port remplace le premier.
 */
export function connectGraphEdge(draft, from, to, input, vocabulary) {
  const specs = specByType(vocabulary);
  const dest = listOfSpec(draft?.nodes).find((node) => String(node.id) === String(to));
  if (!dest) {
    return { ok: false, error: `nœud inconnu « ${to} »`, node: String(to) };
  }
  const spec = specs.get(dest.type);
  const allowed = new Set(listOfSpec(spec?.inputs).map((item) => item.key));
  if (!allowed.has(input)) {
    return {
      ok: false,
      error: `nœud « ${to} » : entrée inconnue « ${input} »`,
      node: String(to),
    };
  }
  if (String(from) === String(to)) {
    return { ok: false, error: "un nœud ne se branche pas sur lui-même", node: String(to) };
  }
  const next = cloneGraphDraft(draft);
  next.edges = listOfSpec(next.edges).filter(
    (edge) => !(String(edge.to) === String(to) && edge.input === input));
  next.edges.push({ from: String(from), to: String(to), input });
  return { ok: true, draft: next };
}

export function disconnectGraphEdge(draft, from, to, input) {
  const next = cloneGraphDraft(draft);
  next.edges = listOfSpec(next.edges).filter((edge) => !(
    String(edge.from) === String(from)
    && String(edge.to) === String(to)
    && edge.input === input
  ));
  return next;
}

export function removeGraphNode(draft, id) {
  const ident = String(id);
  const next = cloneGraphDraft(draft);
  next.nodes = listOfSpec(next.nodes).filter((node) => String(node.id) !== ident);
  next.edges = listOfSpec(next.edges).filter((edge) =>
    String(edge.from) !== ident && String(edge.to) !== ident);
  if (String(next.output) === ident) {
    const fallback = next.nodes.find((node) => node.type === "cylindre"
      || node.type === "boite") ?? next.nodes[0];
    next.output = fallback ? String(fallback.id) : "";
  }
  return next;
}

export function graphDraftsEqual(a, b) {
  return JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
}

/**
 * Identifiant du nœud nommé par un GraphError français.
 * Le message est « nœud « id (type) » : … ».
 */
export function nodeIdFromGraphError(message) {
  const text = String(message ?? "");
  const labeled = text.match(/nœud « ([^»]+?) \(/);
  if (labeled) return labeled[1];
  const duplicate = text.match(/nœud en double : « ([^»]+) »/);
  if (duplicate) return duplicate[1];
  const unknownOut = text.match(/nœud de sortie inconnu « ([^»]+) »/);
  if (unknownOut) return unknownOut[1];
  return null;
}

export function isGraphFeature(item) {
  return !!(item && typeof item === "object" && item.graph
    && typeof item.graph === "object");
}

/** Le brouillon porte-t-il au moins un nœud Python ? */
export function graphHasScript(draft) {
  return listOfSpec(draft?.nodes).some((node) => node && node.type === "script");
}

/** Sources Python à montrer au consentement, dans l'ordre du graphe. */
export function graphScriptSources(draft) {
  const sources = [];
  for (const node of listOfSpec(draft?.nodes)) {
    if (!node || node.type !== "script") continue;
    sources.push({
      id: String(node.id),
      code: typeof node.code === "string" ? node.code : "",
    });
  }
  return sources;
}

/**
 * Disposition du graphe interne : `pos` persisté, sinon couches.
 * Les nœuds portent `name` (= id) pour le rendu partagé.
 */
export function layoutFunctionGraph(draft, vocabulary) {
  const specs = specByType(vocabulary);
  const rawNodes = listOfSpec(draft?.nodes);
  const wired = wiredInputsOf(draft);
  const incoming = new Map();
  const names = [];
  for (const raw of rawNodes) {
    const ident = String(raw.id);
    names.push(ident);
    incoming.set(ident, []);
  }
  for (const edge of listOfSpec(draft?.edges)) {
    const src = String(edge.from ?? "");
    const dst = String(edge.to ?? "");
    if (!incoming.has(dst) || !incoming.has(src)) continue;
    incoming.get(dst).push(src);
  }
  const layers = longestLayers(names, incoming);

  const placed = [];
  const byLayer = new Map();
  for (const raw of rawNodes) {
    const ident = String(raw.id);
    const spec = specs.get(raw.type) ?? {
      type: raw.type, label: raw.type, inputs: [], fields: [],
    };
    const size = functionNodeSize(spec);
    const ports = functionPortLayout(spec, size);
    const hasPos = Array.isArray(raw.pos) && raw.pos.length === 2
      && Number.isFinite(Number(raw.pos[0]))
      && Number.isFinite(Number(raw.pos[1]));
    const layer = layers.get(ident) ?? 0;
    const node = {
      name: ident,
      id: ident,
      type: raw.type,
      label: spec.label || raw.type,
      kind: spec.label || raw.type,
      role: spec.shape ? "shape" : "compute",
      shape: !!spec.shape,
      icon: spec.icon || "",
      output: String(draft?.output) === ident,
      spec,
      width: size.width,
      height: size.height,
      ports,
      layer,
      x: hasPos ? Number(raw.pos[0]) : FN_ORIGIN_X + layer * FN_COL_GAP,
      y: hasPos ? Number(raw.pos[1]) : 0,
      hasPos,
      literals: {},
      fields: {},
    };
    const taken = wired.get(ident) ?? new Set();
    node.inputs = ports.inputs.map((port) => ({
      ...port,
      wired: taken.has(port.key),
      value: raw[port.key],
    }));
    for (const field of listOfSpec(spec.fields)) {
      node.fields[field.key] = raw[field.key];
    }
    placed.push(node);
    if (!hasPos) {
      const bucket = byLayer.get(layer);
      if (bucket) bucket.push(node);
      else byLayer.set(layer, [node]);
    }
  }
  const layerIds = [...byLayer.keys()].sort((a, b) => a - b);
  for (const layer of layerIds) {
    const bucket = byLayer.get(layer);
    for (const [index, node] of bucket.entries()) {
      node.y = FN_ORIGIN_Y + index * FN_ROW_GAP;
    }
  }

  const edges = [];
  const known = new Set(placed.map((node) => node.name));
  for (const edge of listOfSpec(draft?.edges)) {
    const src = String(edge.from ?? "");
    const dst = String(edge.to ?? "");
    if (!known.has(src) || !known.has(dst)) continue;
    edges.push({
      from: src, to: dst, input: edge.input, kind: "data",
    });
  }
  return { nodes: placed, edges };
}

/** Attache d'un fil de fonction graphe : sortie → port d'entrée nommé. */
export function functionEdgeEnds(fromNode, toNode, input) {
  const start = fromNode.ports?.output ?? { x: (fromNode.width ?? 148) / 2, y: 0 };
  const port = (toNode.inputs ?? []).find((item) => item.key === input);
  const end = port ?? { x: -((toNode.width ?? 148) / 2), y: 0 };
  return {
    x1: fromNode.x + start.x,
    y1: fromNode.y + start.y,
    x2: toNode.x + end.x,
    y2: toNode.y + end.y,
  };
}
