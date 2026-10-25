// Vue en graphe : dépendances de la pièce, et éditeur d'une fonction graphe.
// `graphOpen` et `graphFn` restent dans main.js (raccourcis, débogage,
// commandes) et sont mis à jour via ctx.

import { t } from "./i18n.js";
import { iconSrc } from "./icons.js";
import { FEATURES } from "./features.js";
import {
  buildGraph,
  cloneGraphDraft,
  composeGraphPayload,
  connectGraphEdge,
  disconnectGraphEdge,
  edgeAttachX,
  edgeCurvePath,
  edgeMidpoint,
  edgeSubCaption,
  expressionForVariable,
  freezeDrivenValues,
  functionEdgeEnds,
  graphDraftsEqual,
  graphHasScript,
  graphNodePaletteGroups,
  graphPaletteItems,
  graphParamLine,
  graphScriptSources,
  graphVisibleParams,
  isConstructWireSource,
  isGraphFeature,
  isRepeatFeature,
  latestGraphOrRepeat,
  isParamWireSource,
  isParamWireTarget,
  layoutFunctionGraph,
  LIST_SOCKET_OPS,
  newGraphNode,
  nextGraphNodeId,
  nodeIdFromGraphError,
  paramChoiceCaption,
  removeGraphNode,
} from "./graph.js";

/** Libellé d'un nœud : au-delà de 16 caractères, il est tronqué. */
export function graphLabelText(text) {
  const label = String(text ?? "");
  return label.length > 16 ? `${label.slice(0, 15)}…` : label;
}

/** Branche la vue en graphe. Les fonctions renvoyées sont celles que le
 *  reste de l'application appelle déjà. */
export function installGraphView(ctx) {
  const {
    say, call, refresh, refreshAny, confirm, PROP_LABELS,
    featureCommand, openMenu, editFeature, renderTree, updateViewport,
    onSketchRowClick, onDatumRow, onSurfaceClick, onPlaneRow,
    onSketchRowDblClick, onSurfaceDblClick,
    openEquationsPanel, openFeaturePanel, currentSelection,
  } = ctx;

  // Le graphe garde les fichiers d'avant. L'arbre, lui, prend le rôle
  // de la commande (TREE_ICONS).
  const GRAPH_TYPE_ICONS = {
    sketch: "Sketcher_Sketch",
    pad: "PartDesign_Pad",
    pocket: "PartDesign_Pocket",
    fillet: "PartDesign_Fillet",
    chamfer: "PartDesign_Chamfer",
    revolution: "PartDesign_Revolution",
    groove: "PartDesign_Groove",
    mirror: "PartDesign_Mirrored",
    linear_pattern: "PartDesign_LinearPattern",
    polar_pattern: "PartDesign_PolarPattern",
    thickness: "PartDesign_Thickness",
    draft: "PartDesign_Draft",
    hole: "PartDesign_Hole",
    datum_plane: "PartDesign_Plane",
    loft: "PartDesign_AdditiveLoft",
    loft_cut: "PartDesign_SubtractiveLoft",
    sweep: "PartDesign_AdditivePipe",
    sweep_cut: "PartDesign_SubtractivePipe",
    helix: "PartDesign_AdditiveHelix",
    boolean: "PartDesign_Boolean",
    body: "PartDesign_Body",
    surface_extrude: "Part_3D_object",
    surface_revolve: "Part_3D_object",
    surface_loft: "Part_3D_object",
    shape: "Part_3D_object",
    surface_offset: "Part_3D_object",
    component: "LinkArray",
  };

  function graphIconFile(node) {
    if (node?.icon) return node.icon;
    if (node?.spec?.icon) return node.spec.icon;
    if (node?.role === "compute" || node?.role === "shape") {
      if (node.type === "cylindre") return "nodes_cylinder";
      if (node.type === "boite") return "nodes_box";
      if (node.type === "serie") return "nodes_number_range";
      if (node.type === "variable") return "VarSet";
      if (node.type === "vecteur" || node.type === "point") return "nodes_vect";
      return "nodes_wb_icon";
    }
    const typed = node?.type_key ? GRAPH_TYPE_ICONS[node.type_key] : "";
    if (typed) return typed;
    if (node?.role === "sketch") return GRAPH_TYPE_ICONS.sketch;
    if (node?.role === "datum") return GRAPH_TYPE_ICONS.datum_plane;
    if (node?.role === "plane") return "Std_Plane";
    if (node?.role === "surface") return "Part_3D_object";
    if (node?.role === "variable") return "VarSet";
    if (node?.role === "body") return GRAPH_TYPE_ICONS.body;
    return GRAPH_TYPE_ICONS.body;
  }

  function svgGraphIcon(file, x, y) {
    return svgEl("image", {
      href: iconSrc(file),
      x, y, width: 16, height: 16,
    });
  }


  // ---------- vue en graphe (depuis lastTree) ----------

  const SVG_NS = "http://www.w3.org/2000/svg";
  const graphView = document.getElementById("graph-view");
  const graphSvg = document.getElementById("graph-svg");
  const graphWorld = document.getElementById("graph-world");
  const graphEmpty = document.getElementById("graph-empty");
  const graphCap = document.getElementById("graph-cap");
  const graphBtn = document.getElementById("btn-graph");
  const graphAddBtn = document.getElementById("btn-graph-add");
  const menuEl = document.getElementById("ctxmenu"); // menu de l'arbre, refermé ici
  const graphPalette = document.getElementById("graph-palette");
  const paramPickEl = document.getElementById("param-pick");
  const graphEdgeMenu = document.getElementById("graph-edge-menu");
  const literalEditEl = document.getElementById("graph-literal-edit");
  const graphFnBar = document.getElementById("graph-fn-bar");
  const GRAPH_HINT_AT = 60;
  const GRAPH_FN_HINT =
    "Fonction graphe — la géométrie produite est figée. Échap pour fermer.";
  const REPEAT_FN_HINT =
    "Réseau variable — le graphe produit les instances. "
    + "Si la topologie d'une instance ne correspond plus, la répétition "
    + "s'arrête plutôt que de produire. Échap pour fermer.";

  let graphPanX = 0;
  let graphPanY = 0;
  let graphZoom = 1;
  let graphDragging = false;
  let graphMoved = false;
  let graphDragX = 0;
  let graphDragY = 0;
  let graphWiring = null; // { from, kind, x, y, started, preview }
  let graphSelectedEdge = null; // { from, to, kind, input? }
  let graphSelectedName = null;
  let graphPaletteProfile = null;
  let graphFitNames = "";

  function svgEl(tag, attrs = {}) {
    const el = document.createElementNS(SVG_NS, tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (value != null) el.setAttribute(key, String(value));
    }
    return el;
  }

  function applyGraphTransform() {
    graphWorld.setAttribute(
      "transform",
      `translate(${graphPanX} ${graphPanY}) scale(${graphZoom})`);
  }


  function isGraphNodeSelected(node) {
    if (ctx.graphFn.active) return ctx.graphFn.selected === node.name;
    if (graphSelectedName && node.name === graphSelectedName) return true;
    if (ctx.selectedSketch?.name === node.name) return true;
    if (ctx.selectedDatumFeature?.name === node.name) return true;
    if (ctx.selectedSurface?.name === node.name) return true;
    if (ctx.selectedPlane != null) {
      const plane = (ctx.lastTree?.planes ?? [])
        .find((item) => item.id === ctx.selectedPlane);
      if (plane?.name === node.name) return true;
    }
    return false;
  }

  function lookupGraphTarget(name) {
    if (!ctx.lastTree || !name) return null;
    for (const plane of ctx.lastTree.planes ?? []) {
      if (plane.name === name) return { kind: "plane", plane };
    }
    for (const feature of ctx.lastTree.features ?? []) {
      if (feature.name === name) {
        if (feature.type_key === "sketch") {
          return { kind: "sketch", feature };
        }
        if (feature.type_key === "datum_plane") {
          return { kind: "datum", feature };
        }
        return { kind: "feature", feature };
      }
      for (const child of feature.children ?? []) {
        if (child.name === name) return { kind: "sketch", feature: child };
      }
    }
    for (const surface of ctx.lastTree.surfaces ?? []) {
      if (surface.name === name) return { kind: "surface", surface };
      for (const child of surface.children ?? []) {
        if (child.name === name) return { kind: "sketch", feature: child };
      }
    }
    for (const body of ctx.lastTree.bodies ?? []) {
      if (body.name === name) return { kind: "body", body };
    }
    for (const variable of ctx.lastTree.variables ?? []) {
      if (variable.name === name) return { kind: "variable", variable };
    }
    return null;
  }

  function graphMenuTarget(name) {
    const target = lookupGraphTarget(name);
    if (!target) return null;
    if (target.kind === "feature" || target.kind === "sketch"
        || target.kind === "datum") {
      return target.feature;
    }
    if (target.kind === "surface") return target.surface;
    if (target.kind === "body") return target.body;
    return null;
  }

  function onGraphNodeClick(name) {
    if (ctx.graphFn.active) {
      ctx.graphFn.selected = name;
      selectGraphEdge(null);
      renderGraphFunction();
      return;
    }
    const target = lookupGraphTarget(name);
    if (!target) return;
    if (target.kind === "sketch") onSketchRowClick(target.feature);
    else if (target.kind === "datum") onDatumRow(target.feature);
    else if (target.kind === "surface") onSurfaceClick(target.surface);
    else if (target.kind === "plane") onPlaneRow(target.plane.id);
  }

  function onGraphNodeDblClick(name) {
    if (ctx.graphFn.active) {
      ctx.graphFn.draft.output = name;
      ctx.graphFn.selected = name;
      renderGraphFunction();
      return;
    }
    const target = lookupGraphTarget(name);
    if (!target) return;
    if (target.kind === "sketch") onSketchRowDblClick(target.feature);
    else if (target.kind === "surface") onSurfaceDblClick(target.surface);
    else if (target.kind === "feature" || target.kind === "datum") {
      editFeature(target.feature);
    } else if (target.kind === "variable") {
      openEquationsPanel();
    }
  }

  function setGraphHover(name) {
    if (graphWiring) return;
    const incident = new Set();
    if (name) {
      incident.add(name);
      for (const edge of graphWorld.querySelectorAll(".graph-edge")) {
        if (edge.dataset.from === name) incident.add(edge.dataset.to);
        if (edge.dataset.to === name) incident.add(edge.dataset.from);
      }
    }
    for (const edge of graphWorld.querySelectorAll(".graph-edge")) {
      const hit = !!name && (edge.dataset.from === name
        || edge.dataset.to === name);
      edge.classList.toggle("lit", hit);
      edge.classList.toggle("dim", !!name && !hit);
    }
    for (const node of graphWorld.querySelectorAll(".graph-node")) {
      const hit = incident.has(node.dataset.name);
      node.classList.toggle("lit", hit);
      node.classList.toggle("dim", !!name && !hit);
    }
  }

  function clientToGraphWorld(clientX, clientY) {
    const rect = graphSvg.getBoundingClientRect();
    return {
      x: (clientX - rect.left - graphPanX) / graphZoom,
      y: (clientY - rect.top - graphPanY) / graphZoom,
    };
  }

  function graphNodeAt(clientX, clientY) {
    const hit = document.elementFromPoint(clientX, clientY);
    return hit?.closest?.(".graph-node") ?? null;
  }

  function placeGraphMenu(el, clientX, clientY) {
    el.style.display = "block";
    const pad = 8;
    const w = el.offsetWidth || 220;
    const h = el.offsetHeight || 80;
    const left = Math.min(Math.max(clientX, pad),
      Math.max(pad, window.innerWidth - w - pad));
    const top = Math.min(Math.max(clientY, pad),
      Math.max(pad, window.innerHeight - h - pad));
    el.style.left = `${left}px`;
    el.style.top = `${top}px`;
  }

  function closeParamPicker() {
    paramPickEl.style.display = "none";
    paramPickEl.replaceChildren();
  }

  function closeGraphEdgeMenu() {
    graphEdgeMenu.style.display = "none";
  }

  function graphPlacementCtx(profileOverride) {
    return {
      lastTree: ctx.lastTree,
      selectedSketch: profileOverride ?? ctx.selectedSketch,
      selection: currentSelection(["face", "edges"]),
    };
  }

  function selectGraphEdge(edge) {
    if (edge && (edge.kind === "param" || edge.kind === "data")) {
      graphSelectedEdge = {
        from: edge.from, to: edge.to, kind: edge.kind, input: edge.input,
      };
    } else {
      graphSelectedEdge = null;
    }
    applyGraphEdgeSelection();
  }

  function applyGraphEdgeSelection() {
    for (const edge of graphWorld.querySelectorAll(".graph-edge")) {
      const hit = !!graphSelectedEdge
        && edge.dataset.kind === graphSelectedEdge.kind
        && edge.dataset.from === graphSelectedEdge.from
        && edge.dataset.to === graphSelectedEdge.to
        && (graphSelectedEdge.input == null
            || edge.dataset.input === graphSelectedEdge.input);
      edge.classList.toggle("sel", hit);
    }
  }

  function clearParamDropHighlights() {
    graphView.classList.remove("wiring");
    for (const node of graphWorld.querySelectorAll(".graph-node")) {
      node.classList.remove("drop-ok", "drop-no", "drop-hover", "wiring-from");
    }
    for (const port of graphWorld.querySelectorAll(".graph-port")) {
      port.classList.remove("drop-ok", "drop-hover");
    }
  }

  function setParamDropHighlights(hoverName) {
    if (graphWiring?.kind === "port") {
      setDataDropHighlights(hoverName);
      return;
    }
    const source = graphWiring?.from;
    const construct = graphWiring?.kind === "construct";
    for (const node of graphWorld.querySelectorAll(".graph-node")) {
      const isSource = node.dataset.name === source;
      const valid = !construct && !isSource
        && isParamWireTarget(node.dataset.role);
      node.classList.toggle("wiring-from", isSource);
      node.classList.toggle("drop-ok", valid);
      node.classList.toggle("drop-no", !valid);
      node.classList.toggle("drop-hover",
        valid && hoverName != null && node.dataset.name === hoverName);
    }
  }

  function setDataDropHighlights(hoverPort) {
    const source = graphWiring?.from;
    for (const node of graphWorld.querySelectorAll(".graph-node")) {
      node.classList.toggle("wiring-from", node.dataset.name === source);
      node.classList.remove("drop-ok", "drop-no", "drop-hover");
    }
    for (const port of graphWorld.querySelectorAll(".graph-port.in")) {
      const key = `${port.dataset.node}:${port.dataset.key}`;
      port.classList.toggle("drop-ok", true);
      port.classList.toggle("drop-hover", hoverPort === key);
    }
  }

  function graphPortAt(clientX, clientY) {
    const hit = document.elementFromPoint(clientX, clientY);
    return hit?.closest?.(".graph-port") ?? null;
  }

  function cancelGraphWire() {
    if (graphWiring?.preview) graphWiring.preview.remove();
    graphWiring = null;
    graphView.classList.remove("wiring-construct");
    clearParamDropHighlights();
  }

  function startGraphWire(node, event, kind = "param") {
    cancelGraphWire();
    closeParamPicker();
    closeGraphEdgeMenu();
    closeGraphPalette();
    closeLiteralEditor();
    graphMoved = false;
    const origin = kind === "port" && node.ports?.output
      ? { x: node.x + node.ports.output.x, y: node.y + node.ports.output.y }
      : { x: node.x, y: node.y };
    graphWiring = {
      from: node.name,
      kind,
      x: origin.x,
      y: origin.y,
      started: false,
      preview: null,
    };
    try {
      graphView.setPointerCapture(event.pointerId);
    } catch {
      // Capture indisponible : le fil s'arrête au pointerup du nœud.
    }
  }

  function moveGraphWire(event) {
    if (!graphWiring) return;
    const origin = {
      x: graphWiring.x * graphZoom + graphPanX,
      y: graphWiring.y * graphZoom + graphPanY,
    };
    const rect = graphSvg.getBoundingClientRect();
    const screenX = origin.x + rect.left;
    const screenY = origin.y + rect.top;
    if (!graphWiring.started) {
      if (Math.hypot(event.clientX - screenX, event.clientY - screenY) < 4) {
        return;
      }
      graphWiring.started = true;
      graphMoved = true;
      graphView.classList.add("wiring");
      if (graphWiring.kind === "construct") {
        graphView.classList.add("wiring-construct");
      }
      const edgeKind = graphWiring.kind === "param" ? "param"
        : graphWiring.kind === "port" ? "data" : "geom";
      const preview = svgEl("g", { class: `graph-edge ${edgeKind} preview` });
      preview.appendChild(svgEl("path", {
        class: "graph-edge-line",
        d: edgeCurvePath(graphWiring.x, graphWiring.y,
                         graphWiring.x, graphWiring.y),
      }));
      graphWorld.insertBefore(preview, graphWorld.firstChild);
      graphWiring.preview = preview;
      setParamDropHighlights(null);
    }
    const world = clientToGraphWorld(event.clientX, event.clientY);
    const line = graphWiring.preview?.querySelector(".graph-edge-line");
    if (line) {
      line.setAttribute("d",
        edgeCurvePath(graphWiring.x, graphWiring.y, world.x, world.y));
    }
    if (graphWiring.kind === "port") {
      const port = graphPortAt(event.clientX, event.clientY);
      const key = port?.dataset.side === "in"
        ? `${port.dataset.node}:${port.dataset.key}` : null;
      setDataDropHighlights(key);
      return;
    }
    const hover = graphNodeAt(event.clientX, event.clientY);
    setParamDropHighlights(hover?.dataset.name ?? null);
  }

  async function finishGraphWire(event) {
    if (!graphWiring) return;
    const wiring = graphWiring;
    const started = wiring.started;
    if (wiring.kind === "port") {
      const port = graphPortAt(event.clientX, event.clientY);
      cancelGraphWire();
      if (!started) return;
      if (port?.dataset.side !== "in") return;
      const result = connectGraphEdge(
        ctx.graphFn.draft, wiring.from, port.dataset.node, port.dataset.key,
        ctx.graphFn.vocabulary);
      if (!result.ok) {
        ctx.graphFn.errorNode = result.node;
        say(result.error, true);
        renderGraphFunction();
        return;
      }
      ctx.graphFn.draft = result.draft;
      ctx.graphFn.errorNode = null;
      renderGraphFunction();
      return;
    }
    const hover = graphNodeAt(event.clientX, event.clientY);
    cancelGraphWire();
    if (!started) return;
    if (wiring.kind === "construct") {
      const droppedOn = hover?.dataset.name;
      if (droppedOn && droppedOn !== wiring.from) {
        say("On ne recâble pas une fonction existante — le profil se pose "
          + "à la création.");
        return;
      }
      const target = lookupGraphTarget(wiring.from);
      const profile = target?.kind === "sketch"
        ? { name: target.feature.name, label: target.feature.label }
        : null;
      openGraphPalette({
        profileSketch: profile,
        clientX: event.clientX,
        clientY: event.clientY,
      });
      return;
    }
    const role = hover?.dataset.role;
    const name = hover?.dataset.name;
    if (!name || !isParamWireTarget(role) || name === wiring.from) return;
    await openParamPicker(name, wiring.from, event.clientX, event.clientY);
  }

  async function openParamPicker(featureName, variableName, clientX, clientY) {
    closeParamPicker();
    let info;
    try {
      info = await call("get_params", { feature: featureName });
    } catch (error) {
      say(error.message, true);
      return;
    }
    const params = Array.isArray(info.params) ? info.params : [];
    if (!params.length) {
      say(t("{f} : aucune cote éditable", { f: info.label ?? featureName }), true);
      return;
    }
    const heading = document.createElement("div");
    heading.className = "menu-label";
    heading.textContent = t("Cote à piloter");
    paramPickEl.appendChild(heading);
    for (const param of params) {
      const item = document.createElement("div");
      item.className = "menu-item";
      item.dataset.prop = param.prop;
      item.textContent = paramChoiceCaption(param, PROP_LABELS);
      item.addEventListener("click", (event) => {
        event.stopPropagation();
        closeParamPicker();
        refresh(call("set_params", {
          feature: featureName,
          values: { [param.prop]: expressionForVariable(variableName) },
        }));
      });
      paramPickEl.appendChild(item);
    }
    placeGraphMenu(paramPickEl, clientX, clientY);
  }

  async function unlinkParamEdge(edge) {
    if (!edge || edge.kind !== "param") return;
    closeGraphEdgeMenu();
    let info;
    try {
      info = await call("get_params", { feature: edge.to });
    } catch (error) {
      say(error.message, true);
      return;
    }
    const values = freezeDrivenValues(info.params, edge.from);
    if (!Object.keys(values).length) {
      say("Aucune cote à délier sur cette liaison", true);
      return;
    }
    graphSelectedEdge = null;
    refresh(call("set_params", { feature: edge.to, values }));
  }

  function graphEdgeEnds(a, b, edge) {
    if (edge?.kind === "data") return functionEdgeEnds(a, b, edge.input);
    const goingRight = b.x >= a.x;
    return {
      x1: a.x + edgeAttachX(a.role, goingRight),
      y1: a.y,
      x2: b.x + edgeAttachX(b.role, !goingRight),
      y2: b.y,
    };
  }

  function formatLiteral(value) {
    if (isPointValue(value)) {
      return `${value.x}, ${value.y}, ${value.z}`;
    }
    if (typeof value === "number" && Number.isFinite(value)) return String(value);
    if (typeof value === "string") {
      const op = LIST_SOCKET_OPS.find((item) => item.value === value);
      if (op) return op.label;
      const compact = value.replace(/\s+/g, " ").trim();
      if (!compact) return "…";
      return compact.length > 22 ? `${compact.slice(0, 21)}…` : compact;
    }
    return "";
  }

  function isPointValue(value) {
    return !!value && typeof value === "object" && !Array.isArray(value)
      && value.x != null && value.y != null && value.z != null;
  }

  function appendGraphShape(group, node) {
    const role = node.role || "feature";
    group.classList.add(role);
    if (role === "compute" || role === "shape") {
      const w = node.width ?? 168;
      const h = node.height ?? 56;
      group.appendChild(svgEl("rect", {
        class: "shape", x: -w / 2, y: -h / 2, width: w, height: h, rx: 8,
      }));
      group.appendChild(svgGraphIcon(graphIconFile(node), -w / 2 + 8, -h / 2 + 6));
      return;
    }
    if (role === "variable") {
      group.appendChild(svgEl("ellipse", {
        class: "shape", cx: 0, cy: 0, rx: 54, ry: 20,
      }));
      group.appendChild(svgGraphIcon(graphIconFile(node), -42, -8));
    } else {
      const w = 148;
      const h = node.height ?? 32;
      group.appendChild(svgEl("rect", {
        class: "shape", x: -w / 2, y: -h / 2, width: w, height: h,
        rx: role === "body" ? 2 : 8,
      }));
      group.appendChild(svgGraphIcon(graphIconFile(node), -66, -h / 2 + 8));
    }
  }

  function appendFunctionPorts(group, node) {
    for (const port of node.inputs ?? []) {
      const circle = svgEl("circle", {
        class: `graph-port in${port.wired ? " wired" : ""}`,
        cx: port.x, cy: port.y, r: 5,
        "data-side": "in",
        "data-node": node.name,
        "data-key": port.key,
      });
      circle.appendChild(svgEl("title")).textContent = port.label;
      circle.addEventListener("click", (event) => {
        event.stopPropagation();
        if (graphMoved) return;
        if (port.wired) return;
        openLiteralEditor(node.name, port.key, event.clientX, event.clientY);
      });
      group.appendChild(circle);
      const caption = svgEl("text", {
        class: "graph-port-label",
        x: port.x + 10, y: port.y,
        "text-anchor": "start", "dominant-baseline": "middle",
      });
      caption.textContent = port.wired
        ? port.label
        : `${port.label} ${formatLiteral(port.value)}`;
      group.appendChild(caption);
    }
    const out = node.ports?.output;
    if (out) {
      const circle = svgEl("circle", {
        class: "graph-port out",
        cx: out.x, cy: out.y, r: 5,
        "data-side": "out",
        "data-node": node.name,
      });
      circle.appendChild(svgEl("title")).textContent = t("Sortie");
      circle.addEventListener("pointerdown", (event) => {
        if (event.button !== 0) return;
        event.stopPropagation();
        startGraphWire(node, event, "port");
      });
      group.appendChild(circle);
    }
  }

  function fitGraphView(data) {
    const width = graphSvg.clientWidth || 800;
    const height = graphSvg.clientHeight || 600;
    if (!data.nodes.length) {
      graphPanX = 0;
      graphPanY = 0;
      graphZoom = 1;
      applyGraphTransform();
      return;
    }
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const node of data.nodes) {
      const hw = (node.width ?? 160) / 2 + 12;
      const hh = (node.height ?? 32) / 2 + 12;
      minX = Math.min(minX, node.x - hw);
      maxX = Math.max(maxX, node.x + hw);
      minY = Math.min(minY, node.y - hh);
      maxY = Math.max(maxY, node.y + hh);
    }
    const gw = Math.max(maxX - minX, 1);
    const gh = Math.max(maxY - minY, 1);
    const pad = ctx.graphFn.active ? 88 : 56;
    graphZoom = Math.min((width - pad * 2) / gw, (height - pad * 2) / gh, 1.35);
    graphZoom = Math.max(graphZoom, 0.3);
    graphPanX = (width - gw * graphZoom) / 2 - minX * graphZoom;
    graphPanY = (height - gh * graphZoom) / 2 - minY * graphZoom;
    applyGraphTransform();
  }

  function renderGraph(data) {
    graphWorld.replaceChildren();
    const empty = data.nodes.length === 0;
    graphEmpty.hidden = !empty;
    const fn = ctx.graphFn.active;
    if (!fn && data.nodes.length >= GRAPH_HINT_AT) {
      graphCap.hidden = false;
      graphCap.textContent =
        `Graphe : ${data.nodes.length} nœuds — zoomez et faites glisser.`;
    } else {
      graphCap.hidden = true;
      graphCap.textContent = "";
    }

    const byName = new Map(data.nodes.map((node) => [node.name, node]));
    for (const edge of data.edges) {
      const a = byName.get(edge.from);
      const b = byName.get(edge.to);
      if (!a || !b) continue;
      const { x1, y1, x2, y2 } = graphEdgeEnds(a, b, edge);
      const d = edgeCurvePath(x1, y1, x2, y2);
      const group = svgEl("g", {
        class: `graph-edge ${edge.kind}`,
        "data-from": edge.from,
        "data-to": edge.to,
        "data-kind": edge.kind,
      });
      if (edge.input) group.setAttribute("data-input", edge.input);
      const subCaption = edge.kind === "geom" ? edgeSubCaption(edge.subs) : "";
      if (subCaption) group.setAttribute("data-subs", (edge.subs ?? []).join(","));
      group.appendChild(svgEl("path", {
        class: "graph-edge-hit", d,
      }));
      group.appendChild(svgEl("path", {
        class: "graph-edge-line", d,
      }));
      if (subCaption) {
        const mid = edgeMidpoint(x1, y1, x2, y2);
        const sub = svgEl("text", {
          class: "graph-edge-sub",
          x: mid.x, y: mid.y - 6,
          "text-anchor": "middle", "dominant-baseline": "middle",
        });
        sub.textContent = subCaption;
        group.appendChild(sub);
      }
      const geomTitle = subCaption
        ? t("Liaison géométrique — {s}", { s: subCaption })
        : t("Liaison géométrique — non modifiable pour l'instant");
      const title = edge.kind === "param"
        ? "Liaison paramétrique"
        : edge.kind === "data"
          ? `Fil → ${edge.input}`
          : geomTitle;
      group.appendChild(svgEl("title")).textContent = title;
      if (edge.kind === "param" || edge.kind === "data") {
        group.addEventListener("click", (event) => {
          event.stopPropagation();
          if (graphMoved) return;
          selectGraphEdge(edge);
          if (fn) ctx.graphFn.selected = null;
        });
        group.addEventListener("contextmenu", (event) => {
          event.preventDefault();
          event.stopPropagation();
          selectGraphEdge(edge);
          closeParamPicker();
          menuEl.style.display = "none";
          placeGraphMenu(graphEdgeMenu, event.clientX, event.clientY);
        });
      }
      graphWorld.appendChild(group);
    }

    for (const node of data.nodes) {
      const group = svgEl("g", {
        class: "graph-node",
        transform: `translate(${node.x} ${node.y})`,
        "data-name": node.name,
        "data-role": node.role || "feature",
        "data-type": node.type_key || node.type || "",
      });
      if (isGraphNodeSelected(node)) group.classList.add("sel");
      if (!fn && node.afterBar) group.classList.add("rolled-back");
      if (fn && node.output) group.classList.add("output");
      if (fn && ctx.graphFn.errorNode === node.name) group.classList.add("error");
      appendGraphShape(group, node);
      const isVar = node.role === "variable";
      const fnNode = node.role === "compute" || node.role === "shape";
      const shownParams = (!fn && !isVar)
        ? graphVisibleParams(node.params)
        : [];
      const label = svgEl("text", {
        x: fnNode ? -(node.width ?? 168) / 2 + 28 : (isVar ? -20 : -44),
        y: fnNode
          ? -(node.height ?? 56) / 2 + 16
          : (shownParams.length ? -7 : 0),
        "text-anchor": "start", "dominant-baseline": "middle",
      });
      label.textContent = graphLabelText(node.label);
      group.appendChild(label);
      const extraParams = (!fn && !isVar)
        ? (node.params ?? []).map((param) => graphParamLine(param, PROP_LABELS))
          .filter(Boolean)
        : [];
      for (const [index, param] of shownParams.entries()) {
        const line = graphParamLine(param, PROP_LABELS);
        if (!line) continue;
        const text = svgEl("text", {
          class: `graph-param${param.expr ? " driven" : ""}`,
          x: -44,
          y: 8,
          "text-anchor": "start", "dominant-baseline": "middle",
          "data-prop": param.prop,
        });
        text.textContent = line;
        text.addEventListener("click", (event) => {
          event.stopPropagation();
          if (graphMoved) return;
          const feature = graphMenuTarget(node.name);
          if (feature) editFeature(feature);
        });
        group.appendChild(text);
      }
      if (fnNode) {
        const fields = Object.entries(node.fields ?? {});
        for (const [index, [key, value]] of fields.entries()) {
          const field = svgEl("text", {
            class: "graph-literal",
            x: (node.width ?? 168) / 2 - 10,
            y: -(node.height ?? 56) / 2 + 16 + index * 14,
            "text-anchor": "end", "dominant-baseline": "middle",
          });
          field.textContent = formatLiteral(value);
          field.addEventListener("click", (event) => {
            event.stopPropagation();
            openLiteralEditor(node.name, key, event.clientX, event.clientY);
          });
          group.appendChild(field);
        }
        appendFunctionPorts(group, node);
      }
      const paramHint = extraParams.length
        ? extraParams.join(" · ")
        : "";
      group.appendChild(svgEl("title")).textContent = fn && node.output
        ? `${node.label} — sortie du graphe`
        : paramHint
          ? `${node.label} — ${node.kind}\n${paramHint}`
          : `${node.label} — ${node.kind}`;
      group.addEventListener("pointerenter", () => setGraphHover(node.name));
      group.addEventListener("pointerleave", () => setGraphHover(null));
      group.addEventListener("pointerdown", (event) => {
        if (event.button !== 0) return;
        if (event.target.closest(".graph-port")) return;
        if (fn) {
          event.stopPropagation();
          startFunctionNodeDrag(node, event);
          return;
        }
        if (isParamWireSource(node.role)) {
          event.stopPropagation();
          startGraphWire(node, event, "param");
          return;
        }
        if (isConstructWireSource(node.role)) {
          event.stopPropagation();
          startGraphWire(node, event, "construct");
        }
      });
      group.addEventListener("click", (event) => {
        event.stopPropagation();
        if (graphMoved) return;
        selectGraphEdge(null);
        if (!fn) graphSelectedName = node.name;
        onGraphNodeClick(node.name);
        if (!fn) applyGraphNodeSelection();
      });
      group.addEventListener("dblclick", (event) => {
        event.stopPropagation();
        onGraphNodeDblClick(node.name);
      });
      group.addEventListener("contextmenu", (event) => {
        event.preventDefault();
        event.stopPropagation();
        if (fn) return;
        const feature = graphMenuTarget(node.name);
        if (!feature) return;
        closeParamPicker();
        closeGraphEdgeMenu();
        openMenu(event, feature);
      });
      graphWorld.appendChild(group);
    }
    applyGraphTransform();
    applyGraphEdgeSelection();
  }

  function renderGraphFunction() {
    if (!ctx.graphFn.active || !ctx.graphFn.draft) return;
    renderGraph(layoutFunctionGraph(ctx.graphFn.draft, ctx.graphFn.vocabulary));
  }

  function applyGraphNodeSelection() {
    for (const node of graphWorld.querySelectorAll(".graph-node")) {
      node.classList.toggle("sel",
        isGraphNodeSelected({ name: node.dataset.name }));
    }
  }

  function syncGraphFromTree() {
    if (!ctx.graphOpen) return;
    if (ctx.graphFn.active) return;
    const data = buildGraph(ctx.lastTree);
    renderGraph(data);
    const names = data.nodes.map((node) => node.name).join("\0");
    if (names !== graphFitNames) {
      graphFitNames = names;
      fitGraphView(data);
    }
  }

  function startFunctionNodeDrag(node, event) {
    ctx.graphFn.draggingNode = node.name;
    graphMoved = false;
    graphDragX = event.clientX;
    graphDragY = event.clientY;
    try {
      graphView.setPointerCapture(event.pointerId);
    } catch {
      // Capture indisponible.
    }
  }

  function moveFunctionNode(event) {
    if (!ctx.graphFn.draggingNode || !ctx.graphFn.draft) return;
    const dx = (event.clientX - graphDragX) / graphZoom;
    const dy = (event.clientY - graphDragY) / graphZoom;
    if (!graphMoved && Math.hypot(event.clientX - graphDragX,
        event.clientY - graphDragY) < 4) return;
    graphMoved = true;
    graphDragX = event.clientX;
    graphDragY = event.clientY;
    const raw = ctx.graphFn.draft.nodes.find(
      (item) => String(item.id) === ctx.graphFn.draggingNode);
    if (!raw) return;
    const pos = Array.isArray(raw.pos) ? raw.pos : [0, 0];
    raw.pos = [pos[0] + dx, pos[1] + dy];
    renderGraphFunction();
  }

  function deleteFeatureWithConfirm(feature) {
    if (!feature) return;
    if (confirm(t("Supprimer « {f} » ?", { f: feature.label }))) {
      refreshAny(call("delete_feature", { feature: feature.name }));
    }
  }

  function deleteSelectedGraphNode() {
    if (!graphSelectedName) return;
    const feature = graphMenuTarget(graphSelectedName);
    if (!feature) return;
    deleteFeatureWithConfirm(feature);
  }

  function deleteGraphFnSelection() {
    if (!ctx.graphFn.active) return;
    if (graphSelectedEdge?.kind === "data") {
      ctx.graphFn.draft = disconnectGraphEdge(
        ctx.graphFn.draft, graphSelectedEdge.from, graphSelectedEdge.to,
        graphSelectedEdge.input);
      graphSelectedEdge = null;
      renderGraphFunction();
      return;
    }
    if (ctx.graphFn.selected) {
      ctx.graphFn.draft = removeGraphNode(ctx.graphFn.draft, ctx.graphFn.selected);
      ctx.graphFn.selected = null;
      renderGraphFunction();
    }
  }

  function closeGraphPalette() {
    graphPalette.style.display = "none";
    graphPalette.replaceChildren();
    graphPaletteProfile = null;
  }

  function closeLiteralEditor() {
    literalEditEl.style.display = "none";
    literalEditEl.replaceChildren();
  }

  function openGraphPalette({ profileSketch = null, clientX, clientY } = {}) {
    closeGraphPalette();
    closeLiteralEditor();
    closeParamPicker();
    closeGraphEdgeMenu();
    menuEl.style.display = "none";

    if (ctx.graphFn.active) {
      const heading = document.createElement("div");
      heading.className = "menu-label";
      heading.textContent = t("Nœud à poser");
      graphPalette.appendChild(heading);
      for (const group of graphNodePaletteGroups(ctx.graphFn.vocabulary)) {
        const cat = document.createElement("div");
        cat.className = "menu-label";
        cat.dataset.category = group.category;
        cat.textContent = group.label;
        graphPalette.appendChild(cat);
        for (const item of group.items) {
          const row = document.createElement("button");
          row.type = "button";
          row.className = "graph-palette-item"
            + (item.enabled ? "" : " disabled");
          row.dataset.type = item.type;
          if (!item.enabled) {
            row.setAttribute("aria-disabled", "true");
            row.title = item.reason;
          }
          if (item.icon) {
            const img = document.createElement("img");
            img.src = iconSrc(item.icon);
            img.alt = "";
            row.appendChild(img);
          }
          const body = document.createElement("span");
          body.className = "graph-palette-body";
          const title = document.createElement("span");
          title.className = "graph-palette-title";
          title.textContent = item.title;
          body.appendChild(title);
          if (!item.enabled && item.reason) {
            const why = document.createElement("span");
            why.className = "graph-palette-reason";
            why.textContent = item.reason;
            body.appendChild(why);
          }
          row.appendChild(body);
          row.addEventListener("click", (event) => {
            event.stopPropagation();
            if (!item.enabled) {
              say(item.reason, true);
              return;
            }
            closeGraphPalette();
            const world = clientToGraphWorld(clientX, clientY);
            const offset = (ctx.graphFn.draft.nodes.length) * 36;
            world.x += offset;
            world.y += offset;
            const id = nextGraphNodeId(ctx.graphFn.draft.nodes);
            ctx.graphFn.draft.nodes.push(newGraphNode(item.spec, id, world));
            if (!ctx.graphFn.draft.output
                && (item.spec.shape || item.spec.type === "instance")) {
              ctx.graphFn.draft.output = id;
            }
            renderGraphFunction();
          });
          graphPalette.appendChild(row);
        }
      }
      placeGraphMenu(graphPalette, clientX ?? 24, clientY ?? 56);
      return;
    }

    graphPaletteProfile = profileSketch?.name
      ? profileSketch
      : (ctx.selectedSketch?.name
        ? { name: ctx.selectedSketch.name, label: ctx.selectedSketch.label }
        : null);
    const placement = graphPlacementCtx(graphPaletteProfile);
    const items = graphPaletteItems(FEATURES, placement);

    const heading = document.createElement("div");
    heading.className = "menu-label";
    heading.textContent = t("Ajouter une fonction");
    graphPalette.appendChild(heading);
    if (graphPaletteProfile?.name) {
      const profile = document.createElement("div");
      profile.className = "menu-label";
      profile.textContent = `Profil : ${graphPaletteProfile.label
        ?? graphPaletteProfile.name}`;
      graphPalette.appendChild(profile);
    }

    for (const item of items) {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "graph-palette-item" + (item.enabled ? "" : " disabled");
      row.dataset.button = item.button;
      if (!item.enabled) {
        row.setAttribute("aria-disabled", "true");
        row.title = item.reason;
      }
      const img = document.createElement("img");
      img.src = iconSrc(item.icon);
      img.alt = "";
      row.appendChild(img);
      const body = document.createElement("span");
      body.className = "graph-palette-body";
      const title = document.createElement("span");
      title.className = "graph-palette-title";
      title.textContent = item.title;
      body.appendChild(title);
      if (!item.enabled && item.reason) {
        const why = document.createElement("span");
        why.className = "graph-palette-reason";
        why.textContent = item.reason;
        body.appendChild(why);
      }
      row.appendChild(body);
      row.addEventListener("click", (event) => {
        event.stopPropagation();
        if (!item.enabled) {
          say(item.reason, true);
          return;
        }
        const profile = graphPaletteProfile;
        const entry = FEATURES.find((feat) => feat.button === item.button);
        closeGraphPalette();
        if (!entry) return;
        featureCommand(() => openFeaturePanel(entry, profile));
      });
      graphPalette.appendChild(row);
    }

    const wall = document.createElement("div");
    wall.className = "menu-label graph-palette-wall";
    wall.textContent = t("L'historique est linéaire — la fonction se pose "
      + "à la barre de reprise.");
    graphPalette.appendChild(wall);

    placeGraphMenu(graphPalette, clientX ?? 24, clientY ?? 56);
  }

  function openLiteralEditor(nodeId, key, clientX, clientY) {
    closeLiteralEditor();
    const raw = ctx.graphFn.draft.nodes.find((item) => String(item.id) === nodeId);
    if (!raw) return;
    const value = raw[key];
    const applyValue = (next) => {
      raw[key] = next;
      closeLiteralEditor();
      renderGraphFunction();
    };
    if (isPointValue(value)) {
      for (const axis of ["x", "y", "z"]) {
        const input = document.createElement("input");
        input.type = "number";
        input.step = "any";
        input.value = value[axis];
        input.dataset.axis = axis;
        literalEditEl.appendChild(input);
      }
      const ok = document.createElement("button");
      ok.type = "button";
      ok.textContent = t("OK");
      ok.addEventListener("click", (event) => {
        event.stopPropagation();
        const axes = {};
        for (const input of literalEditEl.querySelectorAll("input")) {
          axes[input.dataset.axis] = Number(input.value);
        }
        applyValue(axes);
      });
      literalEditEl.appendChild(ok);
    } else if (key === "op") {
      const spec = ctx.graphFn.vocabulary.find((item) => item.type === raw.type);
      const field = (spec?.fields || []).find((item) => item.key === "op");
      const options = field?.kind === "list_op"
        ? LIST_SOCKET_OPS
        : ["+", "-", "*", "/"].map((op) => ({ value: op, label: op }));
      const select = document.createElement("select");
      for (const op of options) {
        const option = document.createElement("option");
        option.value = op.value;
        option.textContent = op.label;
        select.append(option);
      }
      select.value = value ?? options[0]?.value;
      select.addEventListener("change", () => applyValue(select.value));
      literalEditEl.appendChild(select);
    } else if (key === "code") {
      const area = document.createElement("textarea");
      area.rows = 10;
      area.cols = 48;
      area.value = value ?? "";
      area.spellcheck = false;
      area.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          closeLiteralEditor();
        }
      });
      const ok = document.createElement("button");
      ok.type = "button";
      ok.textContent = t("OK");
      ok.addEventListener("click", (event) => {
        event.stopPropagation();
        applyValue(area.value);
      });
      literalEditEl.appendChild(area);
      literalEditEl.appendChild(ok);
      area.focus();
    } else if (key === "name" || typeof value === "string") {
      const input = document.createElement("input");
      input.type = "text";
      input.value = value ?? "";
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          applyValue(input.value);
        }
      });
      literalEditEl.appendChild(input);
      input.focus();
    } else {
      const input = document.createElement("input");
      input.type = "number";
      input.step = "any";
      input.value = value ?? 1;
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          applyValue(Number(input.value));
        }
      });
      input.addEventListener("blur", () => {
        if (literalEditEl.style.display === "none") return;
        applyValue(Number(input.value));
      });
      literalEditEl.appendChild(input);
      input.focus();
      input.select();
    }
    literalEditEl.style.display = "block";
    literalEditEl.style.left = Math.min(clientX, window.innerWidth - 200) + "px";
    literalEditEl.style.top = Math.min(clientY, window.innerHeight - 80) + "px";
  }

  async function enterGraphFeature(feature) {
    const kind = isRepeatFeature(feature) ? "repetition" : "graphe";
    if (ctx.graphFn.active && ctx.graphFn.feature?.name === feature.name) return;
    if (ctx.graphFn.active && !exitGraphFeature()) return;
    let vocabulary;
    try {
      vocabulary = await call("graph_vocabulary");
    } catch (error) {
      say(error.message, true);
      return;
    }
    if (!Array.isArray(vocabulary)) {
      say("vocabulaire des nœuds illisible", true);
      return;
    }
    let graph = kind === "repetition" ? feature.repeat?.graph : feature.graph;
    if (!graph || typeof graph !== "object") {
      try {
        const op = kind === "repetition"
          ? "get_repeat_feature" : "get_graph_feature";
        const stored = await call(op, { feature: feature.name });
        graph = stored.graph;
      } catch (error) {
        say(error.message, true);
        return;
      }
    }
    if (!graph || typeof graph !== "object") {
      graph = { nodes: [], edges: [], output: "" };
    }
    ctx.graphFn.active = true;
    ctx.graphFn.kind = kind;
    ctx.graphFn.feature = { name: feature.name, label: feature.label };
    ctx.graphFn.vocabulary = vocabulary;
    ctx.graphFn.draft = cloneGraphDraft(graph);
    ctx.graphFn.saved = cloneGraphDraft(graph);
    ctx.graphFn.errorNode = null;
    ctx.graphFn.selected = null;
    ctx.graphOpen = true;
    graphView.classList.add("open", "fn");
    graphBtn.classList.add("on");
    graphFnBar.hidden = false;
    const hintEl = document.getElementById("graph-fn-hint");
    if (hintEl) {
      hintEl.textContent = kind === "repetition"
        ? "Le graphe produit les instances. Si la topologie d'une instance "
          + "ne correspond plus, la répétition s'arrête plutôt que de "
          + "produire."
        : "La géométrie produite est figée. Changer une variable globale ne "
          + "recalcule pas la fonction ; rouvrez-la et appliquez. Le résultat "
          + "est une forme, combinée par un booléen — pas une chaîne de "
          + "fonctions. Ce qui est calculé dedans n'apparaît pas dans l'arbre.";
    }
    const data = layoutFunctionGraph(ctx.graphFn.draft, ctx.graphFn.vocabulary);
    renderGraph(data);
    fitGraphView(data);
    say(kind === "repetition" ? REPEAT_FN_HINT : GRAPH_FN_HINT);
  }

  function exitGraphFeature({ force = false } = {}) {
    if (!ctx.graphFn.active) return true;
    if (!force && !graphDraftsEqual(ctx.graphFn.draft, ctx.graphFn.saved)) {
      if (!confirm("Le graphe n'a pas été appliqué. Quitter sans appliquer ?")) {
        return false;
      }
    }
    ctx.graphFn.active = false;
    ctx.graphFn.kind = "graphe";
    ctx.graphFn.feature = null;
    ctx.graphFn.draft = null;
    ctx.graphFn.saved = null;
    ctx.graphFn.errorNode = null;
    ctx.graphFn.selected = null;
    ctx.graphFn.draggingNode = null;
    graphFnBar.hidden = true;
    graphView.classList.remove("fn");
    closeGraphPalette();
    closeLiteralEditor();
    cancelGraphWire();
    if (ctx.graphOpen && ctx.lastTree) {
      const data = buildGraph(ctx.lastTree);
      renderGraph(data);
      say("Vue en graphe — Échap pour fermer.");
    }
    return true;
  }

  function requestScriptTrust(graph) {
    const dialog = document.getElementById("script-trust");
    const codeEl = document.getElementById("script-trust-code");
    const allowBtn = document.getElementById("script-trust-allow");
    const denyBtn = document.getElementById("script-trust-deny");
    const sources = graphScriptSources(graph);
    const blocks = sources.map((item) => {
      const body = item.code || "(vide)";
      return `# nœud ${item.id}\n${body}`;
    });
    codeEl.textContent = blocks.join("\n\n") || "(aucun code)";
    dialog.hidden = false;
    denyBtn.focus();
    return new Promise((resolve) => {
      const finish = (allowed) => {
        dialog.hidden = true;
        allowBtn.removeEventListener("click", onAllow);
        denyBtn.removeEventListener("click", onDeny);
        resolve(allowed);
      };
      const onAllow = (event) => {
        event.preventDefault();
        finish(true);
      };
      const onDeny = (event) => {
        event.preventDefault();
        finish(false);
      };
      allowBtn.addEventListener("click", onAllow);
      denyBtn.addEventListener("click", onDeny);
    });
  }

  async function applyGraphFeature() {
    if (!ctx.graphFn.active || !ctx.graphFn.feature) return;
    const composed = composeGraphPayload(ctx.graphFn.draft, ctx.graphFn.vocabulary);
    if (!composed.ok) {
      ctx.graphFn.errorNode = composed.node;
      say(composed.error, true);
      renderGraphFunction();
      return;
    }
    try {
      if (graphHasScript(composed.graph)) {
        let status = { authorized: false };
        try {
          status = await call("script_trust_status");
        } catch {
          status = { authorized: false };
        }
        if (!status.authorized) {
          const allowed = await requestScriptTrust(composed.graph);
          if (!allowed) {
            say("Python refusé — la pièce est intacte.");
            return;
          }
          await call("authorize_scripts");
        }
      }
      const op = ctx.graphFn.kind === "repetition"
        ? "edit_repeat_feature" : "edit_graph_feature";
      const tree = await call(op, {
        feature: ctx.graphFn.feature.name,
        graph: composed.graph,
      });
      ctx.graphFn.errorNode = null;
      ctx.graphFn.saved = cloneGraphDraft(ctx.graphFn.draft);
      ctx.lastTree = tree;
      renderTree(tree);
      const gen = ++ctx.viewGen;
      await updateViewport(gen);
      renderGraphFunction();
      say(ctx.graphFn.kind === "repetition"
        ? "Réseau variable appliqué."
        : "Fonction graphe appliquée.");
    } catch (error) {
      ctx.graphFn.errorNode = nodeIdFromGraphError(error.message);
      say(error.message, true);
      renderGraphFunction();
    }
  }

  window.__freesolidDebug.setGraphLiteral = (id, key, value) => {
    if (!ctx.graphFn.draft) return false;
    const node = ctx.graphFn.draft.nodes.find(
      (item) => String(item.id) === String(id));
    if (!node) return false;
    node[key] = value;
    renderGraphFunction();
    return true;
  };
  window.__freesolidDebug.wireGraph = (from, to, input) => {
    if (!ctx.graphFn.draft) return { ok: false, error: "pas de brouillon" };
    const result = connectGraphEdge(
      ctx.graphFn.draft, from, to, input, ctx.graphFn.vocabulary);
    if (result.ok) {
      ctx.graphFn.draft = result.draft;
      ctx.graphFn.errorNode = null;
      renderGraphFunction();
    }
    return result;
  };
  window.__freesolidDebug.graphFeatureEdges = () =>
    (ctx.graphFn.draft?.edges ?? []).map((edge) => ({
      from: edge.from, to: edge.to, input: edge.input,
    }));
  window.__freesolidDebug.applyGraphFeature = () => applyGraphFeature();

  function closeGraph() {
    if (ctx.graphFn.active && !exitGraphFeature()) return;
    if (!ctx.graphOpen) return;
    cancelGraphWire();
    closeParamPicker();
    closeGraphEdgeMenu();
    closeGraphPalette();
    closeLiteralEditor();
    graphSelectedEdge = null;
    graphSelectedName = null;
    graphFitNames = "";
    ctx.graphOpen = false;
    graphView.classList.remove("open", "dragging", "wiring", "fn");
    graphBtn.classList.remove("on");
    graphFnBar.hidden = true;
    graphWorld.replaceChildren();
    graphEmpty.hidden = true;
    graphCap.hidden = true;
  }

  function openGraph() {
    if (!ctx.lastTree) {
      say("Vue en graphe : ouvrez d'abord une pièce", true);
      return;
    }
    if (ctx.graphFn.active) return;
    ctx.graphOpen = true;
    graphView.classList.add("open");
    graphBtn.classList.add("on");
    const data = buildGraph(ctx.lastTree);
    graphFitNames = data.nodes.map((node) => node.name).join("\0");
    renderGraph(data);
    fitGraphView(data);
    say(data.nodes.length
      ? "Vue en graphe — double-clic : poser une fonction. "
        + "Fil depuis une esquisse ou une variable. Échap pour fermer."
      : "Vue en graphe — aucun nœud. Échap pour fermer.");
  }

  graphBtn.addEventListener("click", () => {
    if (ctx.graphOpen) closeGraph();
    else openGraph();
  });

  if (graphAddBtn) {
    graphAddBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      const rect = event.currentTarget.getBoundingClientRect();
      openGraphPalette({ clientX: rect.left, clientY: rect.bottom + 4 });
    });
  }

  document.getElementById("graph-fn-apply").addEventListener("click", (event) => {
    event.stopPropagation();
    applyGraphFeature();
  });
  document.getElementById("graph-fn-close").addEventListener("click", (event) => {
    event.stopPropagation();
    exitGraphFeature();
  });
  document.getElementById("graph-fn-palette").addEventListener("click", (event) => {
    event.stopPropagation();
    const rect = event.currentTarget.getBoundingClientRect();
    openGraphPalette({ clientX: rect.left, clientY: rect.bottom + 4 });
  });

  graphView.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    graphMoved = false;
    if (event.target.closest("#graph-fn-bar, #graph-bar, #graph-palette, #graph-literal-edit")) {
      return;
    }
    if (event.target.closest(".graph-node")) return;
    if (event.target.closest(".graph-port")) return;
    if (event.target.closest(".graph-edge.param")
        || event.target.closest(".graph-edge.data")) return;
    closeParamPicker();
    closeGraphEdgeMenu();
    closeGraphPalette();
    closeLiteralEditor();
    event.preventDefault();
    try {
      graphView.setPointerCapture(event.pointerId);
    } catch {
      // Capture indisponible (pointeur déjà relâché) : le drag s'arrête.
    }
    graphDragging = true;
    graphDragX = event.clientX;
    graphDragY = event.clientY;
    graphView.classList.add("dragging");
  });

  graphView.addEventListener("pointermove", (event) => {
    if (graphWiring) {
      moveGraphWire(event);
      return;
    }
    if (ctx.graphFn.draggingNode) {
      moveFunctionNode(event);
      return;
    }
    if (!graphDragging) return;
    const dx = event.clientX - graphDragX;
    const dy = event.clientY - graphDragY;
    if (!graphMoved && Math.hypot(dx, dy) < 4) return;
    graphMoved = true;
    graphPanX += dx;
    graphPanY += dy;
    graphDragX = event.clientX;
    graphDragY = event.clientY;
    applyGraphTransform();
  });

  const endGraphDrag = (event) => {
    graphDragging = false;
    graphView.classList.remove("dragging");
    ctx.graphFn.draggingNode = null;
    if (graphWiring) finishGraphWire(event);
  };
  graphView.addEventListener("pointerup", endGraphDrag);
  graphView.addEventListener("pointercancel", (event) => {
    graphDragging = false;
    ctx.graphFn.draggingNode = null;
    graphView.classList.remove("dragging");
    cancelGraphWire();
  });

  graphView.addEventListener("click", () => {
    if (graphMoved) return;
    selectGraphEdge(null);
    if (ctx.graphFn.active) {
      ctx.graphFn.selected = null;
      renderGraphFunction();
    }
  });

  graphView.addEventListener("dblclick", (event) => {
    if (!ctx.graphFn.active) return;
    if (event.target.closest(".graph-node")) return;
    event.stopPropagation();
    openGraphPalette(event.clientX, event.clientY);
  });

  graphView.addEventListener("contextmenu", (event) => {
    if (event.target.closest(".graph-node")
        || event.target.closest(".graph-edge.param")
        || event.target.closest(".graph-edge.data")) return;
    event.preventDefault();
  });

  document.getElementById("ctx-unlink").addEventListener("click", (event) => {
    event.stopPropagation();
    if (graphSelectedEdge?.kind === "data") {
      ctx.graphFn.draft = disconnectGraphEdge(
        ctx.graphFn.draft, graphSelectedEdge.from, graphSelectedEdge.to,
        graphSelectedEdge.input);
      graphSelectedEdge = null;
      closeGraphEdgeMenu();
      renderGraphFunction();
      return;
    }
    unlinkParamEdge(graphSelectedEdge);
  });

  paramPickEl.addEventListener("click", (event) => event.stopPropagation());
  graphEdgeMenu.addEventListener("click", (event) => event.stopPropagation());
  graphPalette.addEventListener("click", (event) => event.stopPropagation());
  literalEditEl.addEventListener("click", (event) => event.stopPropagation());
  document.addEventListener("click", () => {
    closeParamPicker();
    closeGraphEdgeMenu();
    closeGraphPalette();
  });

  graphView.addEventListener("wheel", (event) => {
    event.preventDefault();
    const rect = graphSvg.getBoundingClientRect();
    const px = event.clientX - rect.left;
    const py = event.clientY - rect.top;
    const wx = (px - graphPanX) / graphZoom;
    const wy = (py - graphPanY) / graphZoom;
    const factor = event.deltaY < 0 ? 1.12 : 1 / 1.12;
    graphZoom = Math.min(3, Math.max(0.25, graphZoom * factor));
    graphPanX = px - wx * graphZoom;
    graphPanY = py - wy * graphZoom;
    applyGraphTransform();
  }, { passive: false });


  function graphHandleEscape(event) {
    if (event.key === "Escape" && ctx.graphFn.active) {
      event.preventDefault();
      if (literalEditEl.style.display === "block") closeLiteralEditor();
      else if (graphPalette.style.display === "block") closeGraphPalette();
      else if (graphWiring) cancelGraphWire();
      else exitGraphFeature();
      return true;
    }
    if (event.key === "Escape" && ctx.graphOpen) {
      event.preventDefault();
      if (graphPalette.style.display === "block") closeGraphPalette();
      else if (paramPickEl.style.display === "block") closeParamPicker();
      else if (graphWiring) cancelGraphWire();
      else closeGraph();
      return true;
    }
    return false;
  }

  function graphHandleDelete(event) {
    if (!(ctx.graphOpen && (event.key === "Delete" || event.key === "Suppr"))) {
      return false;
    }
    event.preventDefault();
    if (graphPalette.style.display === "block") return true;
    if (ctx.graphFn.active) deleteGraphFnSelection();
    else if (graphSelectedEdge) unlinkParamEdge(graphSelectedEdge);
    else deleteSelectedGraphNode();
    return true;
  }

  return {
    closeGraph, enterGraphFeature, syncGraphFromTree,
    deleteFeatureWithConfirm, graphHandleEscape, graphHandleDelete,
  };
}
