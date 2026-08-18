// Graphe de dépendances du FeatureManager — module pur.
// Pas de DOM, pas de window, pas de réseau. Entrée : l'arbre `get_tree`.
//
// Disposition : couche = plus long chemin depuis les racines ; à
// l'intérieur d'une couche, ordre par le champ `order` de l'arbre.
// Pas de minimisation de croisements en v1 — manque assumé, pas un oubli.

const COL_GAP = 200;
const ROW_GAP = 72;
const ORIGIN_X = 48;
const ORIGIN_Y = 48;

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

function addNode(nodes, item, role, fallbackOrder) {
  const name = item.name;
  if (!name || typeof name !== "string" || nodes.has(name)) return;
  const order = typeof item.order === "number" ? item.order : fallbackOrder;
  nodes.set(name, {
    name,
    label: item.label || name,
    kind: kindOf(item, role),
    role,
    type: item.type,
    order,
    layer: 0,
    x: 0,
    y: 0,
  });
}

function edgeKey(from, to, kind) {
  return `${kind}\0${from}\0${to}`;
}

function collectEdges(tree, variableNames) {
  const edges = [];
  const seen = new Set();
  const push = (from, to, kind) => {
    if (!from || !to || from === to) return;
    const key = edgeKey(from, to, kind);
    if (seen.has(key)) return;
    seen.add(key);
    edges.push({ from, to, kind });
  };

  walkEntries(tree, (item) => {
    const source = item.name;
    if (!source) return;
    for (const dep of listOf(item.deps)) {
      if (typeof dep === "string") push(dep, source, "geom");
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

/**
 * Construit le graphe positionné d'un arbre `get_tree`.
 * @param {object|null|undefined} tree
 * @returns {{ nodes: object[], edges: object[] }}
 */
export function buildGraph(tree) {
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
    const bucket = byLayer.get(layer);
    bucket.sort((a, b) => {
      if (a.order !== b.order) return a.order - b.order;
      if (a.name < b.name) return -1;
      if (a.name > b.name) return 1;
      return 0;
    });
    for (const [index, node] of bucket.entries()) {
      node.x = ORIGIN_X + layer * COL_GAP;
      node.y = ORIGIN_Y + index * ROW_GAP;
    }
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
