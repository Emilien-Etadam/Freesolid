// FreeSolid app — M0. One part, one mesh, a SolidWorks-shaped tree,
// face picking by construction (each engine face is an index group).

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { createSketchMode } from "./sketch.js";
import { createPropertyPanel } from "./panel.js";

const statusEl = document.getElementById("status");
const pickEl = document.getElementById("pick");
const treeEl = document.getElementById("tree");

// ---------- api ----------

async function call(op, params = {}) {
  const response = await fetch("/api", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ op, params }),
  });
  const payload = await response.json();
  if (!payload.ok) throw new Error(payload.error + (payload.hint ? ` (${payload.hint})` : ""));
  return payload.result;
}

function say(text, isError = false) {
  statusEl.textContent = text;
  statusEl.className = isError ? "err" : "";
}

// PropertyManager-style side panel — feature options live there, not in
// prompt() dialogs. See panel.js for the SolidWorks anatomy. Closing the
// panel (OK or cancel) always clears the yellow ghost preview.
const panel = createPropertyPanel({ say, onClose: () => clearGhost() });

// ---------- viewport ----------

const container = document.getElementById("viewport");
const renderer = new THREE.WebGLRenderer({ antialias: true });
container.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x17191c);

const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 5000);
camera.position.set(160, -160, 120);
camera.up.set(0, 0, 1); // CAD is Z-up

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

scene.add(new THREE.HemisphereLight(0xdde4ec, 0x30343a, 1.0));
const keyLight = new THREE.DirectionalLight(0xffffff, 1.4);
keyLight.position.set(1, -0.7, 1.2);
scene.add(keyLight);

const grid = new THREE.GridHelper(400, 40, 0x3a4048, 0x262b31);
grid.rotation.x = Math.PI / 2; // into the XY plane, Z-up
scene.add(grid);

const baseMaterial = new THREE.MeshStandardMaterial({
  color: 0x9fb2c4, metalness: 0.15, roughness: 0.55,
  transparent: true, opacity: 1, // l'aperçu jaune estompe la pièce
  polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1,
});
const hoverMaterial = new THREE.MeshStandardMaterial({
  color: 0x4f8fdb, metalness: 0.15, roughness: 0.45,
  polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1,
});
const selectedMaterial = new THREE.MeshStandardMaterial({
  color: 0xd9924a, metalness: 0.15, roughness: 0.45,
  polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1,
});

// The picked face, sticky across renders: what Coque/Dépouille/Esquisse use.
let selectedFaceId = null;
// Picked edges (multi-select, Ctrl = ajouter) : what Congé/Chanfrein use.
let selectedEdges = new Set();

let partMesh = null;
let partEdges = null;
let othersMesh = null; // les corps non actifs, estompés
let meshGroups = [];
let edgeGroups = [];
let hoveredEdgeGroup = -1;

const othersMaterial = new THREE.MeshStandardMaterial({
  color: 0x5f6b78, metalness: 0.1, roughness: 0.7,
  transparent: true, opacity: 0.45, depthWrite: false,
});
// Surfaces : double face translucide sarcelle — lisibles des deux côtés.
const surfacesMaterial = new THREE.MeshStandardMaterial({
  color: 0x4fb8a8, metalness: 0.1, roughness: 0.6,
  transparent: true, opacity: 0.55, side: THREE.DoubleSide,
  depthWrite: false,
});
const curvesMaterial = new THREE.LineBasicMaterial({ color: 0x4fb8a8 });
let surfacesMesh = null;
let curvesLines = null;

// Qui alloue dispose. Les matériaux partagés (constantes de module) ne
// portent pas le flag et ne sont jamais disposés ; tout matériau créé
// par allocation pose `userData.own = true`.
function disposeSubtree(root) {
  root.traverse((obj) => {
    obj.geometry?.dispose();
    const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
    for (const m of mats) {
      if (m && m.userData?.own) { m.map?.dispose(); m.dispose(); }
    }
  });
}

let lastClearedSelections = false;

function showMesh(mesh) {
  if (partMesh) { scene.remove(partMesh); partMesh.geometry.dispose(); }
  if (othersMesh) { scene.remove(othersMesh); othersMesh.geometry.dispose(); }
  partMesh = othersMesh = null;
  meshGroups = mesh.groups;
  hoveredGroup = -1;
  selectedFaceId = null; // ids shift after every feature: stale picks lie
  const cleared = panel.invalidateSelections();
  lastClearedSelections = cleared > 0;
  if (lastClearedSelections) {
    say("Sélections réinitialisées — la géométrie a changé.");
  }
  if (surfacesMesh) {
    scene.remove(surfacesMesh);
    surfacesMesh.geometry.dispose();
    surfacesMesh = null;
  }
  if (curvesLines) {
    scene.remove(curvesLines);
    curvesLines.geometry.dispose();
    curvesLines = null;
  }
  if (mesh.others?.indices.length) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position",
      new THREE.Float32BufferAttribute(mesh.others.positions, 3));
    geometry.setIndex(mesh.others.indices);
    geometry.computeVertexNormals();
    othersMesh = new THREE.Mesh(geometry, othersMaterial);
    scene.add(othersMesh);
  }
  if (mesh.surfaces?.indices.length) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position",
      new THREE.Float32BufferAttribute(mesh.surfaces.positions, 3));
    geometry.setIndex(mesh.surfaces.indices);
    geometry.computeVertexNormals();
    surfacesMesh = new THREE.Mesh(geometry, surfacesMaterial);
    scene.add(surfacesMesh);
  }
  if (mesh.curves?.indices.length) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position",
      new THREE.Float32BufferAttribute(mesh.curves.positions, 3));
    geometry.setIndex(mesh.curves.indices);
    curvesLines = new THREE.LineSegments(geometry, curvesMaterial);
    scene.add(curvesLines);
  }
  if (!mesh.indices.length) return;

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position",
    new THREE.Float32BufferAttribute(mesh.positions, 3));
  geometry.setIndex(mesh.indices);
  for (const g of mesh.groups) geometry.addGroup(g.start, g.count, 0);
  geometry.computeVertexNormals();

  geometry.computeBoundingSphere(); // les vues standard cadrent dessus

  partMesh = new THREE.Mesh(geometry, [baseMaterial, hoverMaterial, selectedMaterial]);
  scene.add(partMesh);
  rebuildPlanes(); // les plans de base suivent la taille de la pièce
}

// Les vraies arêtes BREP du moteur (pas une silhouette approchée) :
// chaque arête OCCT est son propre groupe d'indices — picking par
// construction, exactement comme les faces.
const edgeBaseMaterial = new THREE.LineBasicMaterial({ color: 0x11141a });
const edgeHoverMaterial = new THREE.LineBasicMaterial({ color: 0x4f8fdb });
const edgeSelectedMaterial = new THREE.LineBasicMaterial({ color: 0xd9924a });

function showEdgeLines(data) {
  if (partEdges) { scene.remove(partEdges); partEdges.geometry.dispose(); }
  partEdges = null;
  edgeGroups = data.groups;
  hoveredEdgeGroup = -1;
  selectedEdges = new Set(); // ids shift after every rebuild, like faces
  if (!data.indices.length) return;
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position",
    new THREE.Float32BufferAttribute(data.positions, 3));
  geometry.setIndex(data.indices);
  for (const g of data.groups) geometry.addGroup(g.start, g.count, 0);
  partEdges = new THREE.LineSegments(geometry,
    [edgeBaseMaterial, edgeHoverMaterial, edgeSelectedMaterial]);
  scene.add(partEdges);
}

function repaintEdges() {
  if (!partEdges) return;
  partEdges.geometry.groups.forEach((g, i) => {
    const id = edgeGroups[i].edgeId;
    g.materialIndex = selectedEdges.has(id) ? 2
      : (i === hoveredEdgeGroup ? 1 : 0);
  });
}

// Jeton monotone : une réponse n'applique arbre/maillage que si elle
// est encore la plus récente (deux Ctrl+Z rapides, undo pendant un
// refresh). Jamais de booléen « busy » qui bloque l'utilisateur.
let viewGen = 0;

async function updateViewport(gen) {
  const mesh = await call("tessellate");
  if (gen !== viewGen) return;
  showMesh(mesh);
  const edges = await call("tessellate_edges");
  if (gen !== viewGen) return;
  showEdgeLines(edges);
}

// ---------- plans de base (Face / Dessus / Droite) ----------
// Toujours là, comme dans SolidWorks : visibles dans l'arbre, cliquables
// dans la zone graphique quand la commande Esquisse attend un plan.

const PLANE_ROTATIONS = {
  XY: [0, 0, 0],
  XZ: [Math.PI / 2, 0, 0],
  YZ: [0, Math.PI / 2, 0],
};
const planesGroup = new THREE.Group();
planesGroup.visible = false;
scene.add(planesGroup);
let planeMeshes = {};
let planePicking = false;
let selectedPlane = null;   // plan choisi dans l'arbre (sticky)
let hoverPlane = null;      // survol en zone graphique pendant le picking
let treeHoverPlane = null;  // survol d'une ligne de plan dans l'arbre

// Mêmes noms que vocab.ORIGIN_PLANES — affichés sur les plans eux-mêmes.
const PLANE_LABELS = {
  XY: "Plan de dessus", XZ: "Plan de face", YZ: "Plan de droite",
};

function makePlaneLabel(text) {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 44;
  const ctx = canvas.getContext("2d");
  ctx.font = "600 24px system-ui";
  ctx.fillStyle = "#7fc4ff";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, 128, 22);
  const material = new THREE.SpriteMaterial({
    map: new THREE.CanvasTexture(canvas),
    transparent: true, depthTest: false });
  material.userData.own = true;
  const sprite = new THREE.Sprite(material);
  sprite.renderOrder = 10;
  return sprite;
}

let lastPlanesSize = null;

function rebuildPlanes() {
  const { radius } = partCenterRadius();
  const size = Math.max(radius * 1.7, 80);
  if (lastPlanesSize === size && Object.keys(planeMeshes).length) {
    updatePlaneVisibility();
    return;
  }
  disposeSubtree(planesGroup);
  planesGroup.clear();
  planeMeshes = {};
  lastPlanesSize = size;
  for (const [id, rotation] of Object.entries(PLANE_ROTATIONS)) {
    const holder = new THREE.Group();
    holder.rotation.set(...rotation);
    const fillMaterial = new THREE.MeshBasicMaterial({
      color: 0x4f8fdb, transparent: true, opacity: 0.1,
      side: THREE.DoubleSide, depthWrite: false });
    fillMaterial.userData.own = true;
    const fill = new THREE.Mesh(
      new THREE.PlaneGeometry(size, size), fillMaterial);
    fill.userData.plane = id;
    const borderMaterial = new THREE.LineBasicMaterial(
      { color: 0x4f8fdb, transparent: true, opacity: 0.6 });
    borderMaterial.userData.own = true;
    const border = new THREE.LineSegments(
      new THREE.EdgesGeometry(fill.geometry), borderMaterial);
    const label = makePlaneLabel(PLANE_LABELS[id]);
    label.position.set(0, size * 0.46, 0);
    label.scale.set(size * 0.42, size * 0.42 * (44 / 256), 1);
    holder.add(fill, border, label);
    planesGroup.add(holder);
    planeMeshes[id] = fill;
  }
  updatePlaneVisibility();
}

function updatePlaneVisibility() {
  const single = planePicking ? null : (treeHoverPlane ?? selectedPlane);
  planesGroup.visible = planePicking || single !== null;
  for (const [id, mesh] of Object.entries(planeMeshes)) {
    mesh.parent.visible = planePicking || id === single;
    mesh.material.opacity =
      (planePicking && id === hoverPlane) || id === selectedPlane
        ? 0.28 : 0.1;
  }
}

function startPlanePick() {
  planePicking = true;
  hoverPlane = null;
  rebuildPlanes();
  say("Esquisse : cliquez un plan — dans la zone graphique ou dans " +
      "l'arbre (Échap pour annuler)");
}

function cancelPlanePick() {
  planePicking = false;
  hoverPlane = null;
  updatePlaneVisibility();
  say("Esquisse annulée.");
}

function pickPlane(id) {
  planePicking = false;
  hoverPlane = null;
  selectedPlane = null;
  updatePlaneVisibility();
  if (lastTree) renderTree(lastTree);
  sketchMode.enter(call("sketch_start", { plane: id }));
}

// ---------- aperçu jaune (le ghost du PropertyManager) ----------

const ghostMaterial = new THREE.MeshStandardMaterial({
  color: 0xf2c94c, metalness: 0.1, roughness: 0.5,
  transparent: true, opacity: 0.55, depthWrite: false,
});
let ghostMesh = null;
let previewTimer = null;
let previewGen = 0;

function clearGhost() {
  clearTimeout(previewTimer);
  previewTimer = null;
  if (ghostMesh) {
    scene.remove(ghostMesh);
    ghostMesh.geometry.dispose();
    ghostMesh = null;
  }
  baseMaterial.opacity = 1;
}

function showGhost(mesh) {
  if (ghostMesh) {
    scene.remove(ghostMesh);
    ghostMesh.geometry.dispose();
    ghostMesh = null;
  }
  if (!mesh.indices.length) return;
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position",
    new THREE.Float32BufferAttribute(mesh.positions, 3));
  geometry.setIndex(mesh.indices);
  geometry.computeVertexNormals();
  ghostMesh = new THREE.Mesh(geometry, ghostMaterial);
  scene.add(ghostMesh);
  baseMaterial.opacity = 0.15; // la pièce s'efface derrière le résultat
}

// Chaque frappe dans le panneau relance l'aperçu, débouncé — le serveur
// exécute la fonction dans une transaction puis l'annule (op "preview").
// previewGen s'incrémente à chaque appel (y compris built == null) : une
// réponse obsolète ne montre ni n'efface le fantôme.
function schedulePreview(built) {
  const gen = ++previewGen;
  clearTimeout(previewTimer);
  if (!built) { clearGhost(); return; }
  previewTimer = setTimeout(async () => {
    try {
      const mesh = await call("preview",
        { op: built.op, params: built.params });
      if (gen !== previewGen) return;
      if (!panel.active) return;
      showGhost(mesh);
    } catch (error) {
      if (gen !== previewGen) return;
      if (!panel.active) return;
      clearGhost();
      say("Aperçu — " + error.message);
    }
  }, 250);
}

// Face hover: triangle index -> group -> engine faceId. By construction.
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
let hoveredGroup = -1;

renderer.domElement.addEventListener("pointermove", (event) => {
  if (sketchMode.active) return;
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  if (planePicking) {
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects(Object.values(planeMeshes))[0];
    const id = hit?.object.userData.plane ?? null;
    if (id !== hoverPlane) {
      hoverPlane = id;
      updatePlaneVisibility();
    }
    renderer.domElement.style.cursor = id ? "pointer" : "";
    return;
  }
  if (!partMesh) return;
  raycaster.setFromCamera(pointer, camera);
  const faceHit = raycaster.intersectObject(partMesh)[0];

  // Les arêtes d'abord : plus précises sous le curseur. Une arête cachée
  // derrière une face plus proche perd — pas de sélection à travers la
  // matière.
  let edgeGroupIndex = -1;
  if (partEdges) {
    const { radius } = partCenterRadius();
    raycaster.params.Line.threshold =
      camera.position.distanceTo(controls.target) * 0.008;
    const edgeHit = raycaster.intersectObject(partEdges)[0];
    if (edgeHit && (!faceHit
        || edgeHit.distance <= faceHit.distance + radius * 0.02)) {
      edgeGroupIndex = edgeGroups.findIndex(
        (g) => edgeHit.index >= g.start
            && edgeHit.index < g.start + g.count);
    }
  }

  let groupIndex = -1;
  if (edgeGroupIndex < 0 && faceHit) {
    const indexPosition = faceHit.faceIndex * 3;
    groupIndex = meshGroups.findIndex(
      (g) => indexPosition >= g.start && indexPosition < g.start + g.count);
  }
  if (groupIndex !== hoveredGroup || edgeGroupIndex !== hoveredEdgeGroup) {
    hoveredGroup = groupIndex;
    hoveredEdgeGroup = edgeGroupIndex;
    renderer.domElement.style.cursor =
      groupIndex >= 0 || edgeGroupIndex >= 0 ? "pointer" : "";
    repaintGroups();
    repaintEdges();
  }
});

function repaintGroups() {
  if (!partMesh) return;
  partMesh.geometry.groups.forEach((g, i) => {
    const isSelected = meshGroups[i].faceId === selectedFaceId;
    g.materialIndex = isSelected ? 2 : (i === hoveredGroup ? 1 : 0);
  });
  const parts = [];
  if (hoveredEdgeGroup >= 0) {
    parts.push(`Arête ${edgeGroups[hoveredEdgeGroup].edgeId}`);
  } else if (hoveredGroup >= 0) {
    parts.push(`Face ${meshGroups[hoveredGroup].faceId}`);
  }
  if (selectedEdges.size) {
    parts.push(`sél. ${selectedEdges.size} arête(s) — Ctrl+clic : ajouter`);
  } else if (selectedFaceId !== null) {
    parts.push(`sél. Face ${selectedFaceId}`);
  }
  pickEl.textContent = parts.join(" · ");
}

// Click selects the hovered face (sticky); click in the void deselects.
// Guarded against orbit drags: a press that travels is navigation, not a pick.
let pressPosition = null;
renderer.domElement.addEventListener("pointerdown", (event) => {
  if (sketchMode.active) return;
  pressPosition = { x: event.clientX, y: event.clientY };
});
renderer.domElement.addEventListener("pointerup", (event) => {
  if (sketchMode.active || !pressPosition) return;
  const travel = Math.hypot(event.clientX - pressPosition.x,
                            event.clientY - pressPosition.y);
  pressPosition = null;
  if (travel > 5) return;
  if (assemblyState) {
    raycaster.setFromCamera(pointer, camera);
    const hit = asmGroup
      ? raycaster.intersectObjects(asmGroup.children, false)[0] : null;
    // Panneau Contrainte ouvert : le clic vise une FACE du composant.
    if (hit && panel.active) {
      const groups = hit.object.userData.groups ?? [];
      const indexPosition = hit.faceIndex * 3;
      const g = groups.find((grp) => indexPosition >= grp.start
        && indexPosition < grp.start + grp.count);
      if (g && panel.notifyPick("asmface", {
            kind: "asmface",
            component: hit.object.userData.component,
            componentLabel: hit.object.userData.componentLabel,
            face: g.faceId })) {
        selectComponent(hit.object.userData.component);
        return;
      }
    }
    selectComponent(hit ? hit.object.userData.component : null);
    return;
  }
  if (planePicking) {
    if (hoverPlane) pickPlane(hoverPlane);
    return;
  }

  if (measuring) {
    const pick = hoveredEdgeGroup >= 0
      ? { kind: "edge", id: edgeGroups[hoveredEdgeGroup].edgeId }
      : hoveredGroup >= 0
        ? { kind: "face", id: meshGroups[hoveredGroup].faceId }
        : null;
    if (!pick) return;
    const label = (p) => `${p.kind === "edge" ? "arête" : "face"} ${p.id}`;
    if (!measureFirst) {
      measureFirst = pick;
      say(`Mesurer : ${label(pick)} — cliquez le second élément`);
    } else {
      const first = measureFirst;
      measuring = false;
      measureFirst = null;
      call("measure", { a_kind: first.kind, a_id: first.id,
                        b_kind: pick.kind, b_id: pick.id })
        .then((r) => say(`Distance ${label(first)} ↔ ${label(pick)} : ` +
                         `${r.distance.toFixed(3)} mm`))
        .catch((error) => say(error.message, true));
    }
    return;
  }

  const clearPlaneChoice = () => {
    if (selectedPlane !== null || selectedDatumFeature !== null) {
      selectedPlane = null;
      selectedDatumFeature = null;
      refreshDatumGhost(null);
      updatePlaneVisibility();
      if (lastTree) renderTree(lastTree);
    }
  };

  if (hoveredEdgeGroup >= 0) {
    const id = edgeGroups[hoveredEdgeGroup].edgeId;
    if (event.ctrlKey || event.metaKey) {
      if (!selectedEdges.delete(id)) selectedEdges.add(id);
    } else {
      selectedEdges = new Set([id]);
    }
    selectedFaceId = null;
    clearPlaneChoice();
    repaintGroups();
    repaintEdges();
    panel.notifyPick("edges",
      { kind: "edges", edges: [...selectedEdges] });
    return;
  }

  selectedFaceId = hoveredGroup >= 0 ? meshGroups[hoveredGroup].faceId : null;
  selectedEdges = new Set(); // une face (ou le vide) remplace les arêtes
  repaintEdges();
  repaintGroups();
  if (selectedFaceId !== null) {
    clearPlaneChoice();
    // A command panel with a selection box absorbs the pick.
    panel.notifyPick("face", { kind: "face", face: selectedFaceId });
  }
});

function resize() {
  const w = container.clientWidth, h = container.clientHeight;
  renderer.setSize(w, h);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(container);

renderer.setAnimationLoop(() => {
  controls.update();
  if (explodeFactor !== explodeTarget) {
    const step = 0.06;
    explodeFactor += Math.sign(explodeTarget - explodeFactor)
      * Math.min(step, Math.abs(explodeTarget - explodeFactor));
    applyExplode();
  }
  renderer.render(scene, camera);
});

// ---------- standard views (SolidWorks: Ctrl+1/4/5/7, F) ----------

function partCenterRadius() {
  if (!partMesh || !partMesh.geometry.boundingSphere)
    return { center: new THREE.Vector3(0, 0, 20), radius: 90 };
  const sphere = partMesh.geometry.boundingSphere;
  return { center: sphere.center.clone(), radius: Math.max(sphere.radius, 1) };
}

// direction = d'où l'on regarde ; null = garder l'angle actuel (zoom au mieux).
function frameView(direction, up) {
  const { center, radius } = partCenterRadius();
  const distance =
    1.25 * radius / Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
  if (up) camera.up.set(...up);
  const dir = direction
    ? new THREE.Vector3(...direction).normalize()
    : camera.position.clone().sub(controls.target).normalize();
  controls.target.copy(center);
  camera.position.copy(center).addScaledVector(dir, distance);
  camera.lookAt(center);
}

// Vue de face = normale au Plan de face (XZ), etc. — mêmes plans que le vocab.
const VIEWS = {
  "view-iso":   { direction: [1, -1, 1], up: [0, 0, 1] },
  "view-front": { direction: [0, -1, 0], up: [0, 0, 1] },
  "view-top":   { direction: [0, 0, 1],  up: [0, 1, 0] },
  "view-right": { direction: [1, 0, 0],  up: [0, 0, 1] },
  "view-fit":   { direction: null,       up: null },
};
for (const [id, view] of Object.entries(VIEWS)) {
  document.getElementById(id).addEventListener("click", () => {
    if (sketchMode.active) return; // en esquisse, la caméra suit le plan
    frameView(view.direction, view.up);
  });
}

const VIEW_KEYS = { 1: "view-front", 4: "view-right", 5: "view-top", 7: "view-iso" };
document.addEventListener("keydown", (event) => {
  if (sketchMode.active) return;
  // Typing in a panel field must not trigger view shortcuts (F, Ctrl+1…).
  if (/^(INPUT|SELECT|TEXTAREA)$/.test(event.target.tagName)) return;
  if ((event.key === "f" || event.key === "F")
      && !event.ctrlKey && !event.metaKey && !event.altKey) {
    frameView(null, null);
  } else if ((event.ctrlKey || event.metaKey) && VIEW_KEYS[event.key]) {
    event.preventDefault();
    frameView(VIEWS[VIEW_KEYS[event.key]].direction,
              VIEWS[VIEW_KEYS[event.key]].up);
  } else if ((event.ctrlKey || event.metaKey)
             && (event.key === "z" || event.key === "y")) {
    event.preventDefault();
    refreshAny(call(event.key === "z" ? "undo" : "redo"));
  } else if (event.key === "Escape" && planePicking) {
    cancelPlanePick();
  } else if (event.key === "Escape" && measuring) {
    measuring = false;
    measureFirst = null;
    say("Mesure annulée.");
  }
});

// ---------- feature tree ----------

// FreeCAD's own icons (see app/icons/README.md) — the tree reads like
// SolidWorks' FeatureManager: icon + label, the kind lives in the tooltip.
const TREE_ICONS = {
  "Sketcher::SketchObject": "Sketcher_Sketch.svg",
  "PartDesign::Pad": "PartDesign_Pad.svg",
  "PartDesign::Pocket": "PartDesign_Pocket.svg",
  "PartDesign::Fillet": "PartDesign_Fillet.svg",
  "PartDesign::Chamfer": "PartDesign_Chamfer.svg",
  "PartDesign::Revolution": "PartDesign_Revolution.svg",
  "PartDesign::Groove": "PartDesign_Groove.svg",
  "PartDesign::Mirrored": "PartDesign_Mirrored.svg",
  "PartDesign::LinearPattern": "PartDesign_LinearPattern.svg",
  "PartDesign::PolarPattern": "PartDesign_PolarPattern.svg",
  "PartDesign::Thickness": "PartDesign_Thickness.svg",
  "PartDesign::Draft": "PartDesign_Draft.svg",
  "PartDesign::Hole": "PartDesign_Hole.svg",
  "PartDesign::Plane": "PartDesign_Plane.svg",
  "PartDesign::AdditiveLoft": "PartDesign_AdditiveLoft.svg",
  "PartDesign::SubtractiveLoft": "PartDesign_SubtractiveLoft.svg",
  "PartDesign::AdditivePipe": "PartDesign_AdditivePipe.svg",
  "PartDesign::SubtractivePipe": "PartDesign_SubtractivePipe.svg",
  "PartDesign::AdditiveHelix": "PartDesign_AdditiveHelix.svg",
};

// ---------- plans de référence (fantôme + sélection d'esquisse) ----------

let datumGhost = null;
let selectedDatumFeature = null; // { name, placement }

function refreshDatumGhost(hoverFeature) {
  if (datumGhost) {
    disposeSubtree(datumGhost);
    scene.remove(datumGhost);
    datumGhost = null;
  }
  const feature = hoverFeature ?? selectedDatumFeature;
  if (!feature?.placement) return;
  const { radius } = partCenterRadius();
  const size = Math.max(radius * 1.4, 60);
  const holder = new THREE.Group();
  holder.matrixAutoUpdate = false;
  holder.matrix.set(...feature.placement);
  const fillMaterial = new THREE.MeshBasicMaterial({
    color: 0x4f8fdb, transparent: true, opacity: 0.14,
    side: THREE.DoubleSide, depthWrite: false });
  fillMaterial.userData.own = true;
  const fill = new THREE.Mesh(
    new THREE.PlaneGeometry(size, size), fillMaterial);
  const borderMaterial = new THREE.LineBasicMaterial(
    { color: 0x4f8fdb, transparent: true, opacity: 0.7 });
  borderMaterial.userData.own = true;
  const border = new THREE.LineSegments(
    new THREE.EdgesGeometry(fill.geometry), borderMaterial);
  holder.add(fill, border);
  scene.add(holder);
  datumGhost = holder;
}

function onDatumRow(feature) {
  selectedDatumFeature =
    selectedDatumFeature?.name === feature.name
      ? null
      : { name: feature.name, placement: feature.placement };
  if (selectedDatumFeature) {
    selectedPlane = null;
    selectedFaceId = null;
    repaintGroups();
    updatePlaneVisibility();
  }
  refreshDatumGhost(null);
  if (lastTree) renderTree(lastTree);
  say(selectedDatumFeature
    ? `${feature.label} choisi — cliquez Esquisse pour dessiner dessus`
    : "Plan de référence désélectionné");
}

function treeIcon(file) {
  const img = document.createElement("img");
  img.src = "icons/" + file;
  img.alt = "";
  return img;
}

let lastTree = null;
const expandedFeatures = new Set(); // les fonctions dépliées (persiste)

function onPlaneRow(id) {
  if (planePicking) { pickPlane(id); return; }
  selectedPlane = selectedPlane === id ? null : id;
  if (selectedPlane !== null) {
    selectedDatumFeature = null;
    refreshDatumGhost(null);
    if (selectedFaceId !== null) {
      selectedFaceId = null;
      repaintGroups();
    }
  }
  updatePlaneVisibility();
  if (lastTree) renderTree(lastTree);
  say(selectedPlane
    ? "Plan choisi — cliquez Esquisse pour dessiner dessus"
    : "Plan désélectionné");
}

function renderTree(tree) {
  clearAssemblyView(); // un arbre de pièce = le mode assemblage s'efface
  lastTree = tree;
  treeHoverPlane = null;
  treeEl.innerHTML = "";

  // Tous les corps de la pièce ; clic sur un corps inactif = l'activer.
  const bodies = tree.bodies
    ?? [{ name: null, label: tree.body, active: true, count: 0 }];
  for (const bodyInfo of bodies) {
    const bodyItem = document.createElement("li");
    bodyItem.className = "body" + (bodyInfo.active ? " active" : "");
    bodyItem.appendChild(treeIcon("PartDesign_Body.svg"));
    bodyItem.appendChild(document.createTextNode(
      bodyInfo.label
      + (bodyInfo.active ? "" : ` — ${bodyInfo.count} élément(s)`)));
    if (!bodyInfo.active && bodyInfo.name) {
      bodyItem.title = "Clic : activer ce corps";
      bodyItem.addEventListener("click", () =>
        refresh(call("set_active_body", { body: bodyInfo.name })));
    }
    if (bodyInfo.name) {
      bodyItem.addEventListener("contextmenu",
        (e) => openMenu(e, bodyInfo));
    }
    treeEl.appendChild(bodyItem);
    if (!bodyInfo.active) continue;
    renderActiveBodyContents(tree);
  }
  // Les surfaces vivent hors des corps — section à part, cliquable pour
  // alimenter Coudre / Épaissir / Balayage.
  for (const surface of tree.surfaces ?? []) {
    const item = document.createElement("li");
    item.appendChild(treeIcon("Part_3D_object.svg"));
    item.appendChild(document.createTextNode(surface.label));
    item.title = "Surface / courbe — clic : sélectionner pour une " +
      "commande · clic droit : renommer, supprimer";
    item.addEventListener("click", () => panel.notifyPick("surface",
      { kind: "surface", name: surface.name, label: surface.label }));
    item.addEventListener("contextmenu", (e) => openMenu(e, surface));
    treeEl.appendChild(item);
  }
}

function renderActiveBodyContents(tree) {
  // Les trois plans de base, toujours là — comme dans SolidWorks.
  for (const plane of tree.planes ?? []) {
    const item = document.createElement("li");
    item.className = "plane" + (selectedPlane === plane.id ? " sel" : "");
    item.appendChild(treeIcon("Std_Plane.svg"));
    item.appendChild(document.createTextNode(plane.label));
    item.title = "Clic : choisir ce plan pour la prochaine esquisse";
    item.addEventListener("click", () => onPlaneRow(plane.id));
    item.addEventListener("mouseenter", () => {
      treeHoverPlane = plane.id;
      updatePlaneVisibility();
    });
    item.addEventListener("mouseleave", () => {
      treeHoverPlane = null;
      updatePlaneVisibility();
    });
    treeEl.appendChild(item);
  }

  for (const feature of tree.features) {
    const item = document.createElement("li");
    if (feature.error) item.className = "error";
    const hasChildren = !!feature.children?.length;
    const arrow = document.createElement("span");
    arrow.className = "arrow";
    arrow.textContent = hasChildren
      ? (expandedFeatures.has(feature.name) ? "▾" : "▸") : "";
    if (hasChildren) {
      arrow.addEventListener("click", (e) => {
        e.stopPropagation();
        if (!expandedFeatures.delete(feature.name)) {
          expandedFeatures.add(feature.name);
        }
        renderTree(lastTree);
      });
    }
    item.appendChild(arrow);
    const icon = TREE_ICONS[feature.type];
    if (icon) item.appendChild(treeIcon(icon));
    item.appendChild(document.createTextNode(feature.label));
    item.title = `${feature.kind} — double-clic : modifier · ` +
      "clic droit : barre de retour, supprimer";
    item.addEventListener("dblclick", () => editFeature(feature));
    item.addEventListener("contextmenu", (e) => openMenu(e, feature));
    if (feature.type === "PartDesign::Plane") {
      // Un plan de référence se choisit comme un plan d'origine.
      item.classList.add("plane");
      if (selectedDatumFeature?.name === feature.name) {
        item.classList.add("sel");
      }
      item.addEventListener("click", () => onDatumRow(feature));
      item.addEventListener("mouseenter", () => refreshDatumGhost(feature));
      item.addEventListener("mouseleave", () => refreshDatumGhost(null));
    }
    if (feature.type === "Sketcher::SketchObject") {
      // Un lissage/balayage ouvert dans le panneau absorbe le clic.
      item.addEventListener("click", () => panel.notifyPick("sketch",
        { kind: "sketch", name: feature.name, label: feature.label }));
    }
    treeEl.appendChild(item);

    // L'esquisse consommée vit sous sa fonction, à la SolidWorks.
    if (hasChildren && expandedFeatures.has(feature.name)) {
      for (const child of feature.children) {
        const row = document.createElement("li");
        row.className = "child" + (child.error ? " error" : "");
        row.appendChild(treeIcon("Sketcher_Sketch.svg"));
        row.appendChild(document.createTextNode(child.label));
        row.title = `${child.kind} — double-clic : modifier l'esquisse`;
        row.addEventListener("dblclick", () => editFeature(child));
        row.addEventListener("contextmenu", (e) => openMenu(e, child));
        row.addEventListener("click", () => panel.notifyPick("sketch",
          { kind: "sketch", name: child.name, label: child.label }));
        treeEl.appendChild(row);
      }
    }

    if (feature.name === tree.tip) {
      const bar = document.createElement("li");
      bar.className = "rollback";
      bar.textContent = "▲ barre de retour arrière ▲";
      bar.title = "Double-clic : revenir à l'état final";
      bar.addEventListener("dblclick", () => refresh(call("tip_to_end")));
      treeEl.appendChild(bar);
    }
  }
}
// (fin du rendu du corps actif)

// Property names -> designer-facing labels for the edit panel.
const PROP_LABELS = {
  Length: ["Profondeur", "mm"],
  Radius: ["Rayon", "mm"],
  Size: ["Distance", "mm"],
  Angle: ["Angle", "°"],
  Thickness: ["Épaisseur", "mm"],
  Value: ["Épaisseur", "mm"],
  Occurrences: ["Nombre d'occurrences", ""],
  Diameter: ["Diamètre", "mm"],
  Depth: ["Profondeur", "mm"],
  HoleCutDiameter: ["Ø lamage/fraisage", "mm"],
  HoleCutDepth: ["Profondeur du lamage", "mm"],
};

async function editFeature(feature) {
  if (feature.type === "Sketcher::SketchObject") {
    sketchMode.enter(call("sketch_edit", { feature: feature.name }));
    return;
  }
  try {
    const info = await call("get_params", { feature: feature.name });
    if (!info.params.length) {
      say(`${info.label} : aucun paramètre numérique éditable`);
      return;
    }
    // Champs texte : nombre OU expression (« 2*Variables.Largeur ») —
    // le moteur tranche. Σ marque les propriétés déjà pilotées.
    const collectChanged = (v) => {
      const values = {};
      for (const p of info.params) {
        const original = String(p.expr ?? p.value);
        const raw = String(v[p.prop] ?? "").trim();
        if (raw && raw !== original) values[p.prop] = raw;
      }
      return values;
    };
    panel.open({
      icon: TREE_ICONS[feature.type] ?? "PartDesign_Body.svg",
      title: info.label,
      groups: [{
        label: "Paramètres",
        rows: info.params.map((p) => {
          const [label, unit] = PROP_LABELS[p.prop] ?? [p.prop, "mm"];
          return { type: "text", key: p.prop,
                   label: (p.expr ? "Σ " : "") + label, unit,
                   value: String(p.expr ?? p.value) };
        }),
      }],
      // L'édition profite du même aperçu jaune que la création.
      onChange: (v) => {
        const values = collectChanged(v);
        schedulePreview(Object.keys(values).length
          ? { op: "set_params",
              params: { feature: feature.name, values } }
          : null);
      },
      onApply: (v) => {
        const values = collectChanged(v);
        if (!Object.keys(values).length) return;
        refresh(call("set_params",
          { feature: feature.name, values }));
      },
    });
  } catch (error) {
    say(error.message, true);
  }
}

// ---------- tree context menu ----------

const menuEl = document.getElementById("ctxmenu");
let menuFeature = null;

function openMenu(event, feature) {
  event.preventDefault();
  menuFeature = feature;
  menuEl.style.display = "block";
  menuEl.style.left = Math.min(event.clientX, window.innerWidth - 200) + "px";
  menuEl.style.top = event.clientY + "px";
}
document.addEventListener("click", () => { menuEl.style.display = "none"; });

document.getElementById("ctx-rename").addEventListener("click", () => {
  if (!menuFeature) return;
  const label = prompt("Nouveau nom :", menuFeature.label);
  if (label === null || !label.trim()) return;
  refreshAny(call("rename",
    { feature: menuFeature.name, label: label.trim() }));
});

document.getElementById("ctx-rollback").addEventListener("click", () => {
  if (menuFeature) refresh(call("set_tip", { feature: menuFeature.name }));
});
document.getElementById("ctx-end").addEventListener("click", () =>
  refresh(call("tip_to_end")));
document.getElementById("ctx-delete").addEventListener("click", () => {
  if (!menuFeature) return;
  if (confirm(`Supprimer « ${menuFeature.label} » ?`))
    refreshAny(call("delete_feature", { feature: menuFeature.name }));
});

// ---------- ruban à onglets (CommandManager) ----------

const RIBBONS = {
  features: "ribbon-features",
  sketch: "sketchbar",
  surfaces: "ribbon-surfaces",
  assembly: "ribbon-assembly",
};

function showTab(name) {
  for (const tab of document.querySelectorAll("header .tab")) {
    tab.classList.toggle("active", tab.dataset.tab === name);
  }
  for (const [key, id] of Object.entries(RIBBONS)) {
    document.getElementById(id).classList.toggle("active", key === name);
  }
}
for (const tab of document.querySelectorAll("header .tab")) {
  tab.addEventListener("click", () => showTab(tab.dataset.tab));
}
document.addEventListener("freesolid:sketch-enter", () => showTab("sketch"));
document.addEventListener("freesolid:sketch-exit", () => showTab("features"));

// Cliquer une fonction pendant une esquisse la termine d'abord — le
// réflexe SolidWorks : on dessine, puis on clique Bossage, sans passer
// par un bouton « quitter l'esquisse ».
async function featureCommand(openPanel) {
  if (assemblyState) {
    say("Les fonctions s'appliquent aux pièces — ouvrez ou créez une " +
        "pièce (un assemblage est en cours)", true);
    return;
  }
  if (sketchMode.active) await sketchMode.finish();
  openPanel();
}

// ---------- gravure de texte ----------

document.getElementById("btn-text").addEventListener("click", () =>
  featureCommand(() => dressupPanel({
    icon: "Draft_ShapeString.svg", title: "Texte",
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
      const size = parseFloat(v.size);
      const depth = parseFloat(v.depth);
      if (!content || !(size > 0) || !(depth > 0)) return null;
      return { op: "add_text", params: {
        text: content, face: v.sel.face, size, depth,
        x: parseFloat(v.x) || 0, y: parseFloat(v.y) || 0,
        emboss: !!v.emboss } };
    },
  })));

// ---------- plan de coupe visuel ----------

function setClip(axis, position, flip) {
  if (!axis || axis === "off") {
    renderer.clippingPlanes = [];
    say("Plan de coupe désactivé.");
    return;
  }
  const normals = { X: [1, 0, 0], Y: [0, 1, 0], Z: [0, 0, 1] };
  const n = new THREE.Vector3(...normals[axis]);
  if (flip) n.negate();
  renderer.clippingPlanes = [
    new THREE.Plane(n, flip ? position : -position)];
  say(`Coupe ${axis} à ${position} mm — purement visuelle.`);
}

document.getElementById("btn-clip").addEventListener("click", () => {
  const active = renderer.clippingPlanes.length > 0;
  panel.open({
    icon: "Std_ToggleClipPlane.svg",
    title: "Plan de coupe",
    groups: [{
      label: "Coupe visuelle",
      rows: [
        { type: "select", key: "axis", value: active ? "X" : "X",
          label: "Axe",
          options: [["off", "Aucune"], ["X", "X"], ["Y", "Y"],
                    ["Z", "Z"]] },
        { type: "number", key: "position", label: "Position", value: 0,
          unit: "mm", showIf: (v) => v.axis !== "off" },
        { type: "check", key: "flip", label: "Inverser le côté",
          value: false, showIf: (v) => v.axis !== "off" },
      ],
    }],
    note: "N'enlève pas de matière : la pièce est seulement montrée " +
          "coupée à l'écran.",
    onApply: (v) => setClip(v.axis, parseFloat(v.position) || 0, !!v.flip),
  });
});

// ---------- surfaces (phase D) ----------

function surfacePanel(id, { icon, title, rows, note, build }) {
  document.getElementById(id).addEventListener("click", () =>
    featureCommand(() => panel.open({
      icon, title,
      groups: [{ label: "Paramètres", rows }],
      note,
      onApply: (v) => {
        const built = build(v);
        if (!built) { say("Valeurs invalides", true); return; }
        refresh(call(built.op, built.params));
      },
    })));
}

surfacePanel("btn-surf-extrude", {
  icon: "Surface_Filling.svg", title: "Surface extrudée",
  rows: [{ type: "number", key: "length", label: "Longueur", value: 20,
           unit: "mm" }],
  note: "Utilise la dernière esquisse — le profil peut être OUVERT.",
  build: (v) => {
    const length = parseFloat(v.length);
    return length ? { op: "surface_extrude", params: { length } } : null;
  },
});

surfacePanel("btn-surf-revolve", {
  icon: "PartDesign_Revolution.svg", title: "Surface de révolution",
  rows: [{ type: "number", key: "angle", label: "Angle", value: 360,
           unit: "°", min: 0.01 }],
  note: "Autour de l'axe vertical de la dernière esquisse.",
  build: (v) => {
    const angle = parseFloat(v.angle);
    return angle ? { op: "surface_revolve", params: { angle } } : null;
  },
});

document.getElementById("btn-surf-loft").addEventListener("click", () =>
  featureCommand(() => panel.open({
    icon: "PartDesign_AdditiveLoft.svg",
    title: "Surface lissée",
    groups: [{ label: "Profils",
      rows: [{ type: "selection", key: "profiles", accepts: ["sketch"],
               multiple: true,
               hint: "Cliquez les esquisses dans l'arbre, dans l'ordre" }] }],
    onApply: (v) => {
      const items = v.profiles?.items ?? [];
      if (items.length < 2) {
        say("Surface lissée : au moins deux profils", true);
        return;
      }
      refresh(call("surface_loft",
        { sketches: items.map((i) => i.name) }));
    },
  })));

document.getElementById("btn-surf-sew").addEventListener("click", () =>
  featureCommand(() => panel.open({
    icon: "Part_3D_object.svg",
    title: "Coudre",
    groups: [{ label: "Surfaces",
      rows: [{ type: "selection", key: "surfaces", accepts: ["surface"],
               multiple: true,
               hint: "Cliquez les surfaces dans l'arbre" }] }],
    note: "Si la peau cousue est fermée, elle devient un solide.",
    onApply: (v) => {
      const items = v.surfaces?.items ?? [];
      if (items.length < 2) { say("Coudre : au moins deux surfaces", true); return; }
      refresh(call("surface_sew",
        { surfaces: items.map((i) => i.name) }));
    },
  })));

document.getElementById("btn-surf-thicken").addEventListener("click", () =>
  featureCommand(() => panel.open({
    icon: "PartDesign_Thickness.svg",
    title: "Épaissir",
    groups: [
      { label: "Surface",
        rows: [{ type: "selection", key: "surface", accepts: ["surface"],
                 hint: "Cliquez une surface dans l'arbre" }] },
      { label: "Paramètres",
        rows: [{ type: "number", key: "thickness", label: "Épaisseur",
                 value: 2, unit: "mm" }] },
    ],
    onApply: (v) => {
      const thickness = parseFloat(v.thickness);
      if (!v.surface || !thickness) {
        say("Épaissir : une surface et une épaisseur non nulle", true);
        return;
      }
      refresh(call("surface_thicken",
        { surface: v.surface.name, thickness }));
    },
  })));

document.getElementById("btn-curve3d").addEventListener("click", () =>
  featureCommand(() => {
    const raw = prompt(
      "Courbe 3D — points x,y,z séparés par « ; »\n" +
      "ex. : 0,0,0 ; 0,0,30 ; 20,0,50", "0,0,0 ; 0,0,30 ; 20,0,50");
    if (!raw) return;
    const points = raw.split(";").map((p) =>
      p.split(",").map((v) => parseFloat(v.trim())));
    if (points.length < 2
        || points.some((p) => p.length !== 3 || p.some(Number.isNaN))) {
      say("Courbe 3D : au moins deux points x,y,z valides", true);
      return;
    }
    refresh(call("add_curve3d", { points, spline: points.length >= 3 }));
  }));

document.getElementById("btn-drawing").addEventListener("click", async () => {
  const path = prompt("Mise en plan (chemin .dxf) :",
                      "~/piece-freesolid.dxf");
  if (!path) return;
  try {
    const out = await call("make_drawing", { path });
    say(`Mise en plan exportée : ${out.path} ` +
        `(${(out.size / 1024).toFixed(1)} Ko — Face, Dessus, Iso)`);
  } catch (error) {
    say(error.message, true);
  }
});

// ---------- assemblage v1 ----------

let assemblyState = null;      // dernier assembly_tree, ou null (mode pièce)
let selectedComponent = null;
let asmGroup = null;
const asmOutlineMaterial = new THREE.LineBasicMaterial({ color: 0x11141a });

function clearAssemblyView() {
  if (asmGroup) {
    scene.remove(asmGroup);
    asmGroup.traverse((o) => o.geometry?.dispose?.());
    asmGroup = null;
  }
  assemblyState = null;
  selectedComponent = null;
}

function showAssemblyMeshes(data) {
  if (asmGroup) {
    scene.remove(asmGroup);
    asmGroup.traverse((o) => o.geometry?.dispose?.());
  }
  // Le mode pièce s'efface : maillages, arêtes, corps estompés.
  showMesh({ positions: [], indices: [], groups: [] });
  showEdgeLines({ positions: [], indices: [], groups: [] });
  asmGroup = new THREE.Group();
  for (const comp of data.components) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position",
      new THREE.Float32BufferAttribute(comp.mesh.positions, 3));
    geometry.setIndex(comp.mesh.indices);
    geometry.computeVertexNormals();
    const mesh = new THREE.Mesh(geometry,
      comp.name === selectedComponent ? selectedMaterial : baseMaterial);
    mesh.userData.component = comp.name;
    mesh.userData.componentLabel = comp.label;
    mesh.userData.groups = comp.mesh.groups; // picking de faces (joints)
    const outline = new THREE.LineSegments(
      new THREE.EdgesGeometry(geometry, 25),
      asmOutlineMaterial);
    mesh.add(outline);
    asmGroup.add(mesh);
  }
  scene.add(asmGroup);
  computeExplodeDirs(); // la vue éclatée survit aux reconstructions
}

function selectComponent(name) {
  selectedComponent = name;
  if (asmGroup) {
    for (const mesh of asmGroup.children) {
      mesh.material = mesh.userData.component === name
        ? selectedMaterial : baseMaterial;
    }
  }
  if (assemblyState) renderAssemblyTree(assemblyState);
  pickEl.textContent = name
    ? `sél. ${assemblyState?.components.find(
        (c) => c.name === name)?.label ?? name}`
    : "";
}

async function refreshAssembly(treePromise) {
  const gen = ++viewGen;
  lastClearedSelections = false;
  try {
    assemblyState = await treePromise;
    if (gen !== viewGen) return;
    renderAssemblyTree(assemblyState);
    const meshes = await call("tessellate_assembly");
    if (gen !== viewGen) return;
    showAssemblyMeshes(meshes);
    if (!lastClearedSelections) say("Assemblage à jour.");
  } catch (error) {
    if (gen !== viewGen) return;
    say(error.message, true);
  }
}

// Rafraîchit dans le bon mode — les ops transverses (renommer,
// supprimer, annuler) renvoient l'arbre du mode courant.
async function refreshAny(treePromise) {
  const gen = ++viewGen;
  lastClearedSelections = false;
  try {
    const tree = await treePromise;
    if (gen !== viewGen) return;
    if (tree.assembly) {
      assemblyState = tree;
      renderAssemblyTree(tree);
      const meshes = await call("tessellate_assembly");
      if (gen !== viewGen) return;
      showAssemblyMeshes(meshes);
    } else {
      renderTree(tree);
      await updateViewport(gen);
      if (gen !== viewGen) return;
    }
    if (!lastClearedSelections) say("À jour.");
  } catch (error) {
    if (gen !== viewGen) return;
    say(error.message, true);
  }
}

function renderAssemblyTree(tree) {
  lastTree = null; // le mode pièce est inactif
  treeEl.innerHTML = "";
  const head = document.createElement("li");
  head.className = "body active";
  head.appendChild(treeIcon("Geoassembly.svg"));
  head.appendChild(document.createTextNode("Assemblage"));
  treeEl.appendChild(head);
  for (const comp of tree.components) {
    const item = document.createElement("li");
    if (comp.name === selectedComponent) item.className = "sel-comp";
    item.appendChild(treeIcon("Link.svg"));
    item.appendChild(document.createTextNode(
      comp.label + (comp.grounded ? " (fixé)" : "")));
    item.title = "Clic : sélectionner · double-clic : déplacer · " +
      "clic droit : renommer, supprimer";
    item.addEventListener("click", () => selectComponent(comp.name));
    item.addEventListener("dblclick", () => {
      selectComponent(comp.name);
      openMovePanel();
    });
    item.addEventListener("contextmenu", (e) => openMenu(e, comp));
    treeEl.appendChild(item);
  }
  if (!tree.components.length) {
    const empty = document.createElement("li");
    empty.textContent = "— insérez une pièce (.FCStd) —";
    treeEl.appendChild(empty);
  }
  for (const joint of tree.joints ?? []) {
    const row = document.createElement("li");
    row.className = "child";
    row.appendChild(treeIcon("Geoassembly.svg"));
    row.appendChild(document.createTextNode(joint.label));
    row.title = `${joint.type} — clic droit : renommer, supprimer`;
    row.addEventListener("contextmenu", (e) => openMenu(e, joint));
    treeEl.appendChild(row);
  }
}

function openMovePanel() {
  const comp = assemblyState?.components.find(
    (c) => c.name === selectedComponent);
  if (!comp) {
    say("Déplacer : cliquez d'abord un composant", true);
    return;
  }
  const [x, y, z] = comp.position;
  const [yaw, pitch, roll] = comp.rotation;
  panel.open({
    icon: "Link.svg",
    title: `Déplacer — ${comp.label}`,
    groups: [
      { label: "Translation",
        rows: [
          { type: "number", key: "x", label: "X", value: +x.toFixed(3), unit: "mm" },
          { type: "number", key: "y", label: "Y", value: +y.toFixed(3), unit: "mm" },
          { type: "number", key: "z", label: "Z", value: +z.toFixed(3), unit: "mm" },
        ] },
      { label: "Rotation",
        rows: [
          { type: "number", key: "yaw", label: "Lacet (Z)", value: +yaw.toFixed(2), unit: "°" },
          { type: "number", key: "pitch", label: "Tangage (Y)", value: +pitch.toFixed(2), unit: "°" },
          { type: "number", key: "roll", label: "Roulis (X)", value: +roll.toFixed(2), unit: "°" },
        ] },
    ],
    note: "v1 sans contraintes : positionnement direct — le solveur " +
          "de contraintes d'assemblage viendra ensuite.",
    onApply: (v) => refreshAssembly(call("move_component", {
      component: comp.name,
      x: parseFloat(v.x) || 0, y: parseFloat(v.y) || 0,
      z: parseFloat(v.z) || 0,
      yaw: parseFloat(v.yaw) || 0, pitch: parseFloat(v.pitch) || 0,
      roll: parseFloat(v.roll) || 0,
    })),
  });
}

document.getElementById("btn-newasm").addEventListener("click", () => {
  clearGhost();
  refreshAssembly(call("new_assembly"));
});

document.getElementById("btn-insert").addEventListener("click", () => {
  if (!assemblyState) {
    say("Créez d'abord un assemblage (Nouvel assemblage)", true);
    return;
  }
  const path = prompt("Insérer une pièce (chemin .FCStd) :",
                      "~/piece-freesolid.FCStd");
  if (!path) return;
  refreshAssembly(call("insert_component", { path }));
});

document.getElementById("btn-move").addEventListener("click", openMovePanel);

document.getElementById("btn-joint").addEventListener("click", () => {
  if (!assemblyState) {
    say("Créez d'abord un assemblage", true);
    return;
  }
  if (assemblyState.components.length < 2) {
    say("Contrainte : insérez au moins deux composants", true);
    return;
  }
  const MECHANICAL = ["engrenages", "cremaillere", "vis", "courroie"];
  const build = (v) => {
    if (!v.a || !v.b || v.a.component === v.b.component) return null;
    const params = {
      component1: v.a.component, component2: v.b.component,
      sub1: `Face${v.a.face + 1}`, sub2: `Face${v.b.face + 1}`,
      type: v.type,
    };
    if (v.type === "distance" || MECHANICAL.includes(v.type)) {
      const d = parseFloat(v.distance);
      if (!(d >= 0)) return null;
      params.distance = d;
      if (["engrenages", "courroie"].includes(v.type)) {
        const d2 = parseFloat(v.distance2);
        if (!(d2 >= 0)) return null;
        params.distance2 = d2;
      }
    }
    // Limites optionnelles : champ vide = pas de limite.
    for (const [key, param] of [["angleMin", "angle_min"],
                                ["angleMax", "angle_max"],
                                ["lengthMin", "length_min"],
                                ["lengthMax", "length_max"]]) {
      const raw = String(v[key] ?? "").trim();
      if (raw) {
        const parsed = parseFloat(raw.replace(",", "."));
        if (!Number.isNaN(parsed)) params[param] = parsed;
      }
    }
    return params;
  };
  panel.open({
    icon: "Geoassembly.svg",
    title: "Contrainte d'assemblage",
    groups: [
      { label: "Type de contrainte",
        rows: [
          { type: "select", key: "type", value: "fixe",
            options: [["fixe", "Fixe"], ["pivot", "Pivot"],
                      ["cylindrique", "Cylindrique"],
                      ["glissiere", "Glissière"], ["rotule", "Rotule"],
                      ["distance", "Distance"],
                      ["engrenages", "Engrenages"],
                      ["cremaillere", "Crémaillère-pignon"],
                      ["vis", "Vis"], ["courroie", "Courroie"]] },
          { type: "number", key: "distance",
            label: "Distance / rayon 1 / pas", value: 10,
            unit: "mm", min: 0,
            showIf: (v) => v.type === "distance"
              || MECHANICAL.includes(v.type) },
          { type: "number", key: "distance2", label: "Rayon 2", value: 10,
            unit: "mm", min: 0,
            showIf: (v) => ["engrenages", "courroie"].includes(v.type) },
          { type: "note",
            text: "Mécaniques : posez d'abord les pivots des deux " +
                  "composants, la contrainte couple ensuite leurs " +
                  "mouvements.",
            showIf: (v) => MECHANICAL.includes(v.type) },
          { type: "text", key: "angleMin", label: "Angle min", unit: "°",
            placeholder: "aucune limite",
            showIf: (v) => ["pivot", "cylindrique"].includes(v.type) },
          { type: "text", key: "angleMax", label: "Angle max", unit: "°",
            placeholder: "aucune limite",
            showIf: (v) => ["pivot", "cylindrique"].includes(v.type) },
          { type: "text", key: "lengthMin", label: "Longueur min",
            unit: "mm", placeholder: "aucune limite",
            showIf: (v) => ["glissiere", "cylindrique"].includes(v.type) },
          { type: "text", key: "lengthMax", label: "Longueur max",
            unit: "mm", placeholder: "aucune limite",
            showIf: (v) => ["glissiere", "cylindrique"].includes(v.type) },
        ] },
      { label: "Élément 1",
        rows: [{ type: "selection", key: "a", accepts: ["asmface"],
                 hint: "Cliquez une face du premier composant" }] },
      { label: "Élément 2",
        rows: [{ type: "selection", key: "b", accepts: ["asmface"],
                 hint: "Puis une face du second composant" }] },
    ],
    note: "Le solveur natif repositionne les composants — le premier " +
          "inséré est fixé.",
    onApply: (v) => {
      const params = build(v);
      if (!params) {
        say("Contrainte : deux faces de deux composants différents", true);
        return;
      }
      refreshAssembly(call("add_joint", params));
    },
  });
});

document.getElementById("btn-solve").addEventListener("click", () => {
  if (!assemblyState) {
    say("Créez d'abord un assemblage", true);
    return;
  }
  refreshAssembly(call("solve_assembly"));
});

document.getElementById("btn-array-comp").addEventListener("click", () => {
  const comp = assemblyState?.components.find(
    (c) => c.name === selectedComponent);
  if (!comp) {
    say("Répéter : cliquez d'abord un composant", true);
    return;
  }
  panel.open({
    icon: "Link.svg",
    title: `Répéter — ${comp.label}`,
    groups: [{
      label: "Répétition",
      rows: [
        { type: "number", key: "count", label: "Occurrences", value: 3,
          min: 2, step: 1 },
        { type: "number", key: "dx", label: "Pas X", value: 30,
          unit: "mm" },
        { type: "number", key: "dy", label: "Pas Y", value: 0,
          unit: "mm" },
        { type: "number", key: "dz", label: "Pas Z", value: 0,
          unit: "mm" },
      ],
    }],
    onApply: (v) => {
      const count = parseInt(v.count, 10);
      if (!(count >= 2)) { say("Au moins 2 occurrences", true); return; }
      refreshAssembly(call("array_component", {
        component: comp.name, count,
        dx: parseFloat(v.dx) || 0, dy: parseFloat(v.dy) || 0,
        dz: parseFloat(v.dz) || 0 }));
    },
  });
});

document.getElementById("btn-interf").addEventListener("click", async () => {
  if (!assemblyState) {
    say("Créez d'abord un assemblage", true);
    return;
  }
  try {
    const result = await call("check_interference");
    if (!result.interferences.length) {
      say("Aucune interférence entre les composants ✓");
      return;
    }
    panel.open({
      icon: "Geoassembly.svg",
      title: "Interférences",
      groups: [{
        label: `${result.interferences.length} interférence(s)`,
        rows: [{ type: "list",
          items: result.interferences.map((p) => ({
            label: `${p.a} ↔ ${p.b} : ` +
              `${(p.volume_mm3 / 1000).toFixed(3)} cm³`,
          })) }],
      }],
      note: "Volume commun réel (booléen OCCT) — à résoudre avant " +
            "impression.",
      onApply: () => {},
    });
  } catch (error) {
    say(error.message, true);
  }
});

// ---------- vue éclatée (visuelle) ----------

let explodeFactor = 0;
let explodeTarget = 0;

function applyExplode() {
  if (!asmGroup) return;
  for (const mesh of asmGroup.children) {
    const dir = mesh.userData.explodeDir;
    if (dir) mesh.position.copy(dir).multiplyScalar(explodeFactor);
  }
}

function computeExplodeDirs() {
  if (!asmGroup || !asmGroup.children.length) return;
  const centers = asmGroup.children.map((mesh) => {
    mesh.geometry.computeBoundingSphere();
    return mesh.geometry.boundingSphere.center.clone();
  });
  const global = centers.reduce((a, c) => a.add(c),
    new THREE.Vector3()).divideScalar(centers.length);
  asmGroup.children.forEach((mesh, i) => {
    const dir = centers[i].clone().sub(global);
    if (dir.length() < 1e-6) dir.set(0, 0, 1); // composants superposés
    mesh.userData.explodeDir = dir.multiplyScalar(0.9);
  });
  applyExplode();
}

document.getElementById("btn-explode").addEventListener("click", () => {
  if (!assemblyState) {
    say("Créez d'abord un assemblage", true);
    return;
  }
  explodeTarget = explodeTarget ? 0 : 1;
  say(explodeTarget
    ? "Vue éclatée — purement visuelle, re-cliquez pour rassembler"
    : "Vue rassemblée.");
});

// ---------- actions ----------

async function refresh(treePromise) {
  const gen = ++viewGen;
  lastClearedSelections = false;
  try {
    const tree = await treePromise;
    if (gen !== viewGen) return;
    renderTree(tree);
    await updateViewport(gen);
    if (gen !== viewGen) return;
    if (!lastClearedSelections) say("À jour.");
  } catch (error) {
    if (gen !== viewGen) return;
    say(error.message, true);
  }
}

document.getElementById("btn-new").addEventListener("click", () =>
  refresh(call("new_part")));

document.getElementById("btn-undo").addEventListener("click", () =>
  refreshAny(call("undo")));
document.getElementById("btn-redo").addEventListener("click", () =>
  refreshAny(call("redo")));

// ---------- équations (variables globales) ----------

async function openEquationsPanel() {
  let variables = [];
  try {
    variables = (await call("list_variables")).variables;
  } catch (error) {
    say(error.message, true);
    return;
  }
  panel.open({
    icon: "VarSet.svg",
    title: "Équations",
    groups: [
      {
        label: "Variables globales",
        rows: [{
          type: "list",
          empty: "— aucune variable —",
          items: variables.map((variable) => ({
            label: `${variable.name} = ${variable.value}`,
            onDelete: async () => {
              try {
                await call("delete_variable", { name: variable.name });
                openEquationsPanel();
              } catch (error) {
                say(error.message, true);
              }
            },
          })),
        }],
      },
      {
        label: "Ajouter / modifier",
        rows: [
          { type: "text", key: "name", label: "Nom",
            placeholder: "Largeur" },
          { type: "text", key: "value", label: "Valeur",
            placeholder: "100" },
        ],
      },
    ],
    note: "Utilisez « Variables.Nom » dans toute cote ou propriété — " +
          "ex. Variables.Largeur / 2. Retaper un nom existant le modifie.",
    onApply: async (v) => {
      const name = (v.name ?? "").trim();
      const value = parseFloat(String(v.value ?? "").replace(",", "."));
      if (!name || Number.isNaN(value)) return;
      try {
        await call("set_variable", { name, value });
        say(`${name} = ${value}`);
        refresh(call("get_tree")); // les cotes pilotées se recalculent
      } catch (error) {
        say(error.message, true);
      }
    },
  });
}

document.getElementById("btn-equations")
  .addEventListener("click", openEquationsPanel);

// ---------- évaluer + mesurer ----------

let lastDensity = 1.24; // PLA — le défaut d'un atelier d'impression 3D

async function openEvaluatePanel() {
  let props;
  try {
    props = await call("mass_properties", { density: lastDensity });
  } catch (error) {
    say(error.message, true);
    return;
  }
  const fixed = (v, n = 1) => v.toFixed(n);
  panel.open({
    icon: "view-measurement.svg",
    title: "Évaluer",
    groups: [
      { label: "Propriétés de masse",
        rows: [{ type: "list", items: [
          { label: `Volume : ${fixed(props.volume_mm3 / 1000, 2)} cm³` },
          { label: `Masse : ${fixed(props.mass_g)} g ` +
                   `(à ${props.density} g/cm³)` },
          { label: `Surface : ${fixed(props.area_mm2 / 100)} cm²` },
          { label: "Centre de gravité : "
                   + props.center_of_mass.map((v) => fixed(v)).join(", ") },
          { label: "Encombrement : "
                   + props.bounding_box.map((v) => fixed(v)).join(" × ")
                   + " mm" },
        ] }] },
      { label: "Matière",
        rows: [{ type: "number", key: "density", label: "Densité",
                 value: lastDensity, unit: "g/cm³", min: 0.001 }] },
    ],
    note: "PLA ≈ 1,24 · PETG ≈ 1,27 · ABS ≈ 1,04 · Alu ≈ 2,70 · " +
          "Acier ≈ 7,85 — OK recalcule avec la densité saisie",
    onApply: (v) => {
      const density = parseFloat(v.density);
      if (density > 0) {
        lastDensity = density;
        openEvaluatePanel();
      }
    },
  });
}

document.getElementById("btn-evaluate")
  .addEventListener("click", openEvaluatePanel);

let measuring = false;
let measureFirst = null;

document.getElementById("btn-measure").addEventListener("click", () => {
  if (!lastTree) {
    say("Mesurer : ouvrez d'abord une pièce", true);
    return;
  }
  measuring = true;
  measureFirst = null;
  say("Mesurer : cliquez deux éléments (faces ou arêtes) — Échap pour " +
      "quitter");
});

document.getElementById("btn-sketch").addEventListener("click", () =>
  featureCommand(async () => {
    // Pas encore de pièce ? Elle se crée toute seule — cliquer Esquisse
    // est LE geste de départ, pas une erreur.
    if (!lastTree) {
      try {
        renderTree(await call("new_part"));
      } catch (error) {
        say(error.message, true);
        return;
      }
    }
    if (selectedFaceId !== null) {
      sketchMode.enter(call("sketch_start", { face: selectedFaceId }));
    } else if (selectedDatumFeature !== null) {
      const name = selectedDatumFeature.name;
      selectedDatumFeature = null;
      refreshDatumGhost(null);
      if (lastTree) renderTree(lastTree);
      sketchMode.enter(call("sketch_start", { datum: name }));
    } else if (selectedPlane !== null) {
      pickPlane(selectedPlane);
    } else {
      // Rien de choisi : les trois plans s'affichent avec leur nom,
      // à vous de cliquer — le geste SolidWorks exact.
      startPlanePick();
    }
  }));

function pocketBuild(v) {
  const reversed = !!v.reversed;
  if (v.cond === "travers") {
    return { op: "add_pocket", params: { through: true, reversed } };
  }
  const length = Math.abs(parseFloat(v.length));
  return length ? { op: "add_pocket", params: { length, reversed } } : null;
}

document.getElementById("btn-pocket").addEventListener("click", () =>
  featureCommand(() => panel.open({
    icon: "PartDesign_Pocket.svg",
    title: "Enlèvement de matière extrudé",
    groups: [{
      label: "Direction 1",
      rows: [
        { type: "select", key: "cond", value: "travers",
          options: [["travers", "À travers tout"], ["borgne", "Borgne"]] },
        { type: "number", key: "length", label: "Profondeur", value: 10,
          unit: "mm", min: 0.01, showIf: (v) => v.cond === "borgne" },
        { type: "check", key: "reversed", label: "Inverser la direction",
          value: false },
      ],
    }],
    onChange: (v) => schedulePreview(pocketBuild(v)),
    onApply: (v) => {
      const built = pocketBuild(v);
      if (!built) { say("Profondeur invalide", true); return; }
      refresh(call(built.op, built.params));
    },
  })));

// Habillages : la zone de sélection du panneau absorbe les clics de la
// zone graphique (arêtes ou face selon la commande) — on peut ouvrir la
// commande d'abord et cliquer ensuite, comme dans SolidWorks.
function currentSelection(accepts) {
  if (accepts.includes("edges") && selectedEdges.size) {
    return { kind: "edges", edges: [...selectedEdges] };
  }
  if (accepts.includes("face") && selectedFaceId !== null) {
    return { kind: "face", face: selectedFaceId };
  }
  return null;
}

function hasSelection(sel) {
  return !!sel && (sel.kind === "edges"
    ? sel.edges.length > 0 : sel.face != null);
}

function dressupPanel({ icon, title, selectionLabel, group, rows, build,
                        accepts = ["face"], hint }) {
  panel.open({
    icon, title,
    groups: [
      { label: selectionLabel,
        rows: [{ type: "selection", key: "sel", accepts, hint,
                 value: currentSelection(accepts) }] },
      { label: group, rows },
    ],
    onChange: (v) =>
      schedulePreview(hasSelection(v.sel) ? build(v) : null),
    onApply: (v) => {
      if (!hasSelection(v.sel)) {
        say(`${title} : cliquez d'abord dans la zone graphique`, true);
        return;
      }
      const built = build(v);
      if (!built) { say("Valeur invalide", true); return; }
      refresh(call(built.op, built.params));
    },
  });
}

// La sélection du panneau devient les params du moteur : arêtes précises
// ou face entière (= toutes ses arêtes), les deux gestes SolidWorks.
function dressupParams(sel) {
  return sel.kind === "edges"
    ? { edges: sel.edges } : { face: sel.face };
}

document.getElementById("btn-fillet").addEventListener("click", () =>
  featureCommand(() => dressupPanel({
    icon: "PartDesign_Fillet.svg", title: "Congé",
    selectionLabel: "Éléments à arrondir",
    accepts: ["edges", "face"],
    hint: "Cliquez des arêtes (Ctrl = ajouter) ou une face",
    group: "Paramètres du congé",
    rows: [{ type: "number", key: "radius", label: "Rayon", value: 3,
             unit: "mm", min: 0.01 }],
    build: (v) => {
      const radius = parseFloat(v.radius);
      return radius > 0
        ? { op: "add_fillet",
            params: { ...dressupParams(v.sel), radius } }
        : null;
    },
  })));

document.getElementById("btn-chamfer").addEventListener("click", () =>
  featureCommand(() => dressupPanel({
    icon: "PartDesign_Chamfer.svg", title: "Chanfrein",
    selectionLabel: "Éléments à chanfreiner",
    accepts: ["edges", "face"],
    hint: "Cliquez des arêtes (Ctrl = ajouter) ou une face",
    group: "Paramètres du chanfrein",
    rows: [{ type: "number", key: "size", label: "Distance", value: 2,
             unit: "mm", min: 0.01 }],
    build: (v) => {
      const size = parseFloat(v.size);
      return size > 0
        ? { op: "add_chamfer",
            params: { ...dressupParams(v.sel), size } }
        : null;
    },
  })));

document.getElementById("btn-shell").addEventListener("click", () =>
  featureCommand(() => dressupPanel({
    icon: "PartDesign_Thickness.svg", title: "Coque",
    selectionLabel: "Faces à supprimer",
    group: "Paramètres",
    rows: [{ type: "number", key: "thickness", label: "Épaisseur", value: 2,
             unit: "mm", min: 0.01 }],
    build: (v) => {
      const thickness = parseFloat(v.thickness);
      return thickness > 0
        ? { op: "add_thickness",
            params: { face: v.sel.face, thickness } }
        : null;
    },
  })));

document.getElementById("btn-draft").addEventListener("click", () =>
  featureCommand(() => dressupPanel({
    icon: "PartDesign_Draft.svg", title: "Dépouille",
    selectionLabel: "Faces à dépouiller",
    group: "Angle de dépouille",
    rows: [
      { type: "number", key: "angle", label: "Angle", value: 3,
        unit: "°", min: 0.01 },
      { type: "note", text: "Plan neutre : Plan de dessus" },
    ],
    build: (v) => {
      const angle = parseFloat(v.angle);
      return angle > 0
        ? { op: "add_draft", params: { face: v.sel.face, angle } } : null;
    },
  })));

function holeBuild(v) {
  const diameter = parseFloat(v.diameter);
  if (!(diameter > 0)) return null;
  const params = { diameter, cut: v.cut };
  if (v.cond === "borgne") {
    const depth = parseFloat(v.depth);
    if (!(depth > 0)) return null;
    params.depth = depth;
  } else {
    params.through = true;
  }
  if (v.cut !== "none") {
    const cutDiameter = parseFloat(v.cutDiameter);
    if (!(cutDiameter > diameter)) return null; // le lamage englobe le trou
    params.cut_diameter = cutDiameter;
    if (v.cut === "lamage") {
      const cutDepth = parseFloat(v.cutDepth);
      if (!(cutDepth > 0)) return null;
      params.cut_depth = cutDepth;
    } else {
      const cutAngle = parseFloat(v.cutAngle);
      if (cutAngle > 0) params.cut_angle = cutAngle;
    }
  }
  return { op: "add_hole", params };
}

document.getElementById("btn-hole").addEventListener("click", () =>
  featureCommand(() => panel.open({
    icon: "PartDesign_Hole.svg",
    title: "Assistant de perçage",
    groups: [
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
    note: "Position : la dernière esquisse (un cercle par perçage). " +
          "Le diamètre saisi remplace celui des cercles.",
    onChange: (v) => schedulePreview(holeBuild(v)),
    onApply: (v) => {
      const built = holeBuild(v);
      if (!built) { say("Valeurs du perçage invalides", true); return; }
      refresh(call(built.op, built.params));
    },
  })));

document.getElementById("btn-body").addEventListener("click", () =>
  featureCommand(() => {
    const name = prompt("Nom du nouveau corps :", "Corps");
    if (name === null) return;
    refresh(call("add_body", name.trim() ? { name: name.trim() } : {}));
  }));

document.getElementById("btn-boolean").addEventListener("click", () =>
  featureCommand(() => {
    const others = (lastTree?.bodies ?? []).filter((b) => !b.active);
    if (!others.length) {
      say("Combiner : créez d'abord un second corps", true);
      return;
    }
    const build = (v) => ({ op: "add_boolean",
      params: { tool: v.tool, type: v.type } });
    panel.open({
      icon: "PartDesign_Boolean.svg",
      title: "Combiner",
      groups: [{
        label: "Opération",
        rows: [
          { type: "select", key: "type", value: "cut",
            options: [["cut", "Soustraire"], ["fuse", "Ajouter"],
                      ["common", "Intersection"]] },
          { type: "select", key: "tool", value: others[0].name,
            label: "Corps outil",
            options: others.map((b) => [b.name, b.label]) },
        ],
      }],
      note: "S'applique au corps actif ; le corps outil est absorbé " +
            "par l'opération.",
      onChange: (v) => schedulePreview(build(v)),
      onApply: (v) => refresh(call("add_boolean", build(v).params)),
    });
  }));

document.getElementById("btn-datum").addEventListener("click", () =>
  featureCommand(() => panel.open({
    icon: "PartDesign_Plane.svg",
    title: "Plan de référence",
    groups: [
      {
        label: "Référence",
        rows: [
          { type: "selection", key: "sel", accepts: ["face"],
            hint: "Cliquez une face — ou choisissez un plan ci-dessous",
            value: currentSelection(["face"]) },
          { type: "select", key: "base", value: "XY", label: "Plan",
            options: [["XZ", "Plan de face"], ["XY", "Plan de dessus"],
                      ["YZ", "Plan de droite"]] },
        ],
      },
      {
        label: "Position",
        rows: [
          { type: "number", key: "offset", label: "Décalage", value: 20,
            unit: "mm" },
          { type: "number", key: "angle", label: "Angle", value: 0,
            unit: "°" },
        ],
      },
    ],
    onApply: (v) => {
      const params = {
        offset: parseFloat(v.offset) || 0,
        angle: parseFloat(v.angle) || 0,
      };
      if (v.sel && v.sel.face != null) params.face = v.sel.face;
      else params.base = v.base;
      refresh(call("add_datum_plane", params));
    },
  })));

function loftBuild(v) {
  const items = v.profiles?.items ?? [];
  if (items.length < 2) return null;
  return { op: "add_loft", params: {
    sketches: items.map((i) => i.name),
    subtractive: !!v.subtractive,
    ruled: !!v.ruled,
    closed: !!v.closed } };
}

document.getElementById("btn-loft").addEventListener("click", () =>
  featureCommand(() => panel.open({
    icon: "PartDesign_AdditiveLoft.svg",
    title: "Bossage/Base lissé",
    groups: [
      { label: "Profils",
        rows: [{ type: "selection", key: "profiles", accepts: ["sketch"],
                 multiple: true,
                 hint: "Cliquez les esquisses dans l'arbre, dans " +
                       "l'ordre du lissage" }] },
      { label: "Options",
        rows: [
          { type: "check", key: "subtractive",
            label: "Enlèvement de matière", value: false },
          { type: "check", key: "ruled", label: "Lissage droit (réglé)",
            value: false },
          { type: "check", key: "closed", label: "Boucle fermée",
            value: false },
        ] },
    ],
    onChange: (v) => schedulePreview(loftBuild(v)),
    onApply: (v) => {
      const built = loftBuild(v);
      if (!built) { say("Lissage : au moins deux profils", true); return; }
      refresh(call(built.op, built.params));
    },
  })));

function sweepBuild(v) {
  if (!v.profile || !v.spine) return null;
  if (v.profile.name === v.spine.name) return null;
  return { op: "add_sweep", params: {
    profile: v.profile.name,
    spine: v.spine.name,
    subtractive: !!v.subtractive } };
}

document.getElementById("btn-sweep").addEventListener("click", () =>
  featureCommand(() => panel.open({
    icon: "PartDesign_AdditivePipe.svg",
    title: "Bossage/Base balayé",
    groups: [
      { label: "Profil",
        rows: [{ type: "selection", key: "profile", accepts: ["sketch"],
                 hint: "Cliquez l'esquisse du profil dans l'arbre" }] },
      { label: "Trajectoire",
        rows: [{ type: "selection", key: "spine", accepts: ["sketch"],
                 hint: "Puis l'esquisse de la trajectoire" }] },
      { label: "Options",
        rows: [{ type: "check", key: "subtractive",
                 label: "Enlèvement de matière", value: false }] },
    ],
    onChange: (v) => schedulePreview(sweepBuild(v)),
    onApply: (v) => {
      const built = sweepBuild(v);
      if (!built) {
        say("Balayage : un profil puis une trajectoire (différents)", true);
        return;
      }
      refresh(call(built.op, built.params));
    },
  })));

function helixBuild(v) {
  const pitch = parseFloat(v.pitch);
  const height = parseFloat(v.height);
  return pitch > 0 && height > 0
    ? { op: "add_helix", params: { pitch, height } } : null;
}

document.getElementById("btn-helix").addEventListener("click", () =>
  featureCommand(() => panel.open({
    icon: "PartDesign_AdditiveHelix.svg",
    title: "Hélice",
    groups: [{
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
    onChange: (v) => schedulePreview(helixBuild(v)),
    onApply: (v) => {
      const built = helixBuild(v);
      if (!built) { say("Pas et hauteur doivent être positifs", true); return; }
      refresh(call(built.op, built.params));
    },
  })));

function revolvedPanel(op, icon, title) {
  const build = (v) => {
    const angle = parseFloat(v.angle);
    return angle ? { op, params: { angle } } : null;
  };
  panel.open({
    icon, title,
    groups: [{
      label: "Direction 1",
      rows: [
        { type: "number", key: "angle", label: "Angle", value: 360,
          unit: "°", min: 0.01 },
      ],
    }],
    note: "Axe de révolution : l'axe vertical de l'esquisse",
    onChange: (v) => schedulePreview(build(v)),
    onApply: (v) => {
      const built = build(v);
      if (!built) { say("Angle invalide", true); return; }
      refresh(call(built.op, built.params));
    },
  });
}

document.getElementById("btn-revolution").addEventListener("click", () =>
  featureCommand(() =>
    revolvedPanel("add_revolution", "PartDesign_Revolution.svg",
                  "Bossage/Base avec révolution")));

document.getElementById("btn-groove").addEventListener("click", () =>
  featureCommand(() =>
    revolvedPanel("add_groove", "PartDesign_Groove.svg",
                  "Enlèvement de matière avec révolution")));

document.getElementById("btn-mirror").addEventListener("click", () =>
  featureCommand(() => panel.open({
    icon: "PartDesign_Mirrored.svg",
    title: "Symétrie",
    groups: [{
      label: "Plan de symétrie",
      rows: [
        { type: "select", key: "plane", value: "YZ",
          options: [["YZ", "Plan de droite"], ["XZ", "Plan de face"],
                    ["XY", "Plan de dessus"]] },
      ],
    }],
    note: "S'applique à la dernière fonction (bossage ou enlèvement)",
    onChange: (v) =>
      schedulePreview({ op: "add_mirror", params: { plane: v.plane } }),
    onApply: (v) => refresh(call("add_mirror", { plane: v.plane })),
  })));

function linPatternBuild(v) {
  const length = parseFloat(v.length);
  const count = parseInt(v.count, 10);
  return length && count >= 2
    ? { op: "add_linear_pattern", params: { axis: v.axis, length, count } }
    : null;
}

document.getElementById("btn-linpattern").addEventListener("click", () =>
  featureCommand(() => panel.open({
    icon: "PartDesign_LinearPattern.svg",
    title: "Répétition linéaire",
    groups: [{
      label: "Direction 1",
      rows: [
        { type: "select", key: "axis", value: "X", label: "Direction",
          options: [["X", "Axe X"], ["Y", "Axe Y"], ["Z", "Axe Z"]] },
        { type: "number", key: "length", label: "Longueur totale",
          value: 40, unit: "mm", min: 0.01 },
        { type: "number", key: "count", label: "Nombre d'occurrences",
          value: 3, min: 2, step: 1 },
      ],
    }],
    note: "S'applique à la dernière fonction (bossage ou enlèvement)",
    onChange: (v) => schedulePreview(linPatternBuild(v)),
    onApply: (v) => {
      const built = linPatternBuild(v);
      if (!built) { say("Valeurs invalides", true); return; }
      refresh(call(built.op, built.params));
    },
  })));

function polPatternBuild(v) {
  const angle = parseFloat(v.angle);
  const count = parseInt(v.count, 10);
  return angle && count >= 2
    ? { op: "add_polar_pattern", params: { count, angle } } : null;
}

document.getElementById("btn-polpattern").addEventListener("click", () =>
  featureCommand(() => panel.open({
    icon: "PartDesign_PolarPattern.svg",
    title: "Répétition circulaire",
    groups: [{
      label: "Direction 1",
      rows: [
        { type: "number", key: "angle", label: "Angle", value: 360,
          unit: "°", min: 0.01 },
        { type: "number", key: "count", label: "Nombre d'occurrences",
          value: 4, min: 2, step: 1 },
      ],
    }],
    note: "Axe : Z — s'applique à la dernière fonction",
    onChange: (v) => schedulePreview(polPatternBuild(v)),
    onApply: (v) => {
      const built = polPatternBuild(v);
      if (!built) { say("Valeurs invalides", true); return; }
      refresh(call(built.op, built.params));
    },
  })));

document.getElementById("btn-open").addEventListener("click", async () => {
  const path = prompt("Ouvrir (.FCStd, .step, .iges) :",
                      "~/piece-freesolid.FCStd");
  if (!path) return;
  const gen = ++viewGen;
  try {
    const tree = await call("open_part", { path });
    if (gen !== viewGen) return;
    if (tree.assembly) {
      assemblyState = tree;
      renderAssemblyTree(tree);
      const meshes = await call("tessellate_assembly");
      if (gen !== viewGen) return;
      showAssemblyMeshes(meshes);
      showTab("assembly");
      say("Assemblage ouvert.");
      return;
    }
    renderTree(tree);
    await updateViewport(gen);
    if (gen !== viewGen) return;
    say(tree.imported_solids !== undefined
      ? `Importé — ${tree.imported_solids} solide(s), la forme est la ` +
        "base du corps."
      : tree.bodies_in_file > 1
        ? `Ouvert — ${tree.bodies_in_file} corps dans le fichier.`
        : "Ouvert.");
  } catch (error) {
    if (gen !== viewGen) return;
    say(error.message, true);
  }
});

document.getElementById("btn-save").addEventListener("click", async () => {
  const path = prompt("Enregistrer sous :", "~/piece-freesolid.FCStd");
  if (!path) return;
  try {
    const saved = await call("save_part", { path });
    say(`Enregistré : ${saved.path} — ouvrable dans FreeCAD standard.`);
  } catch (error) {
    say(error.message, true);
  }
});

document.getElementById("btn-export").addEventListener("click", async () => {
  const path = prompt(
    "Exporter (.stl / .3mf pour l'impression, .step pour l'échange) :",
    "~/piece-freesolid.stl");
  if (!path) return;
  try {
    const out = await call("export_part", { path });
    say(`Exporté : ${out.path} (${(out.size / 1024).toFixed(1)} Ko)`);
  } catch (error) {
    say(error.message, true);
  }
});

function padBuild(v) {
  const length = Math.abs(parseFloat(v.length));
  if (!length) return null;
  return { op: "add_pad",
           params: { length, reversed: !!v.reversed,
                     midplane: v.cond === "milieu" } };
}

document.getElementById("btn-pad").addEventListener("click", () =>
  featureCommand(() => panel.open({
    icon: "PartDesign_Pad.svg",
    title: "Bossage/Base extrudé",
    groups: [{
      label: "Direction 1",
      rows: [
        { type: "select", key: "cond", value: "borgne",
          options: [["borgne", "Borgne"], ["milieu", "Plan milieu"]] },
        { type: "number", key: "length", label: "Profondeur", value: 10,
          unit: "mm", min: 0.01 },
        { type: "check", key: "reversed", label: "Inverser la direction",
          value: false, showIf: (v) => v.cond !== "milieu" },
      ],
    }],
    onChange: (v) => schedulePreview(padBuild(v)),
    onApply: (v) => {
      const built = padBuild(v);
      if (!built) { say("Profondeur invalide", true); return; }
      refresh(call(built.op, built.params));
    },
  })));

document.getElementById("btn-selftest").addEventListener("click", async () => {
  const gen = ++viewGen;
  try {
    say("Selftest en cours…");
    const report = await call("selftest");
    if (gen !== viewGen) return;
    renderTree(report.tree_after_pad);
    await updateViewport(gen);
    if (gen !== viewGen) return;
    say(`Selftest OK — ${report.mesh_faces} faces, ` +
        `${report.mesh_triangles} triangles, reparam ${report.m0_reparam_ok ? "OK" : "ÉCHEC"}`);
    console.log("selftest", report);
  } catch (error) {
    if (gen !== viewGen) return;
    say("Selftest : " + error.message, true);
  }
});

// ---------- sketch mode ----------

const sketchMode = createSketchMode(
  { scene, camera, renderer, controls, call, say, refresh, panel });

// ---------- boot ----------

call("ping")
  .then(async (info) => {
    say(`Moteur prêt — FreeCAD ${info.freecad}`);
    // Resynchronise avec le moteur : après un rechargement de la page,
    // la pièce en cours réapparaît au lieu d'être écrasée au premier
    // clic sur Esquisse.
    try {
      const gen = ++viewGen;
      const tree = await call("get_tree");
      if (gen !== viewGen) return;
      renderTree(tree);
      await updateViewport(gen);
    } catch {
      try {
        // Peut-être un assemblage en cours dans le moteur.
        const gen = ++viewGen;
        assemblyState = await call("assembly_tree");
        if (gen !== viewGen) return;
        renderAssemblyTree(assemblyState);
        const meshes = await call("tessellate_assembly");
        if (gen !== viewGen) return;
        showAssemblyMeshes(meshes);
        showTab("assembly");
      } catch {
        // pas encore de document — Esquisse créera une pièce
      }
    }
  })
  .catch(() => say("Moteur injoignable — lancez engine/server.py avec freecadcmd", true));
