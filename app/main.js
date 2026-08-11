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

// The picked face, sticky across renders: what Congé/Chanfrein/Esquisse use.
let selectedFaceId = null;

let partMesh = null;
let partEdges = null;
let meshGroups = [];

function showMesh(mesh) {
  if (partMesh) { scene.remove(partMesh); partMesh.geometry.dispose(); }
  if (partEdges) { scene.remove(partEdges); partEdges.geometry.dispose(); }
  partMesh = partEdges = null;
  meshGroups = mesh.groups;
  hoveredGroup = -1;
  selectedFaceId = null; // ids shift after every feature: stale picks lie
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

  // Plasticity-style crisp silhouette: hard edges over the shaded mesh.
  partEdges = new THREE.LineSegments(
    new THREE.EdgesGeometry(geometry, 25),
    new THREE.LineBasicMaterial({ color: 0x11141a }));
  scene.add(partEdges);
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

function rebuildPlanes() {
  planesGroup.clear();
  planeMeshes = {};
  const { radius } = partCenterRadius();
  const size = Math.max(radius * 1.7, 80);
  for (const [id, rotation] of Object.entries(PLANE_ROTATIONS)) {
    const holder = new THREE.Group();
    holder.rotation.set(...rotation);
    const fill = new THREE.Mesh(
      new THREE.PlaneGeometry(size, size),
      new THREE.MeshBasicMaterial({
        color: 0x4f8fdb, transparent: true, opacity: 0.1,
        side: THREE.DoubleSide, depthWrite: false }));
    fill.userData.plane = id;
    const border = new THREE.LineSegments(
      new THREE.EdgesGeometry(fill.geometry),
      new THREE.LineBasicMaterial(
        { color: 0x4f8fdb, transparent: true, opacity: 0.6 }));
    holder.add(fill, border);
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
function schedulePreview(built) {
  clearTimeout(previewTimer);
  if (!built) { clearGhost(); return; }
  previewTimer = setTimeout(async () => {
    try {
      showGhost(await call("preview",
        { op: built.op, params: built.params }));
    } catch (error) {
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
  const hit = raycaster.intersectObject(partMesh)[0];
  let groupIndex = -1;
  if (hit) {
    const indexPosition = hit.faceIndex * 3;
    groupIndex = meshGroups.findIndex(
      (g) => indexPosition >= g.start && indexPosition < g.start + g.count);
  }
  if (groupIndex !== hoveredGroup) {
    hoveredGroup = groupIndex;
    renderer.domElement.style.cursor = groupIndex >= 0 ? "pointer" : "";
    repaintGroups();
  }
});

function repaintGroups() {
  if (!partMesh) return;
  partMesh.geometry.groups.forEach((g, i) => {
    const isSelected = meshGroups[i].faceId === selectedFaceId;
    g.materialIndex = isSelected ? 2 : (i === hoveredGroup ? 1 : 0);
  });
  const parts = [];
  if (hoveredGroup >= 0) parts.push(`Face ${meshGroups[hoveredGroup].faceId}`);
  if (selectedFaceId !== null) parts.push(`sél. Face ${selectedFaceId}`);
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
  if (planePicking) {
    if (hoverPlane) pickPlane(hoverPlane);
    return;
  }
  selectedFaceId = hoveredGroup >= 0 ? meshGroups[hoveredGroup].faceId : null;
  repaintGroups();
  if (selectedFaceId !== null && selectedPlane !== null) {
    selectedPlane = null; // une face remplace le plan choisi
    updatePlaneVisibility();
    if (lastTree) renderTree(lastTree);
  }
  // A command panel with a selection box absorbs the pick, SolidWorks-style.
  if (selectedFaceId !== null) panel.notifyFace(selectedFaceId);
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
    refresh(call(event.key === "z" ? "undo" : "redo"));
  } else if (event.key === "Escape" && planePicking) {
    cancelPlanePick();
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
};

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
  if (selectedPlane !== null && selectedFaceId !== null) {
    selectedFaceId = null;
    repaintGroups();
  }
  updatePlaneVisibility();
  if (lastTree) renderTree(lastTree);
  say(selectedPlane
    ? "Plan choisi — cliquez Esquisse pour dessiner dessus"
    : "Plan désélectionné");
}

function renderTree(tree) {
  lastTree = tree;
  treeHoverPlane = null;
  treeEl.innerHTML = "";
  const bodyItem = document.createElement("li");
  bodyItem.className = "body";
  bodyItem.appendChild(treeIcon("PartDesign_Body.svg"));
  bodyItem.appendChild(document.createTextNode(tree.body));
  treeEl.appendChild(bodyItem);

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

// Property names -> designer-facing labels for the edit panel.
const PROP_LABELS = {
  Length: ["Profondeur", "mm"],
  Radius: ["Rayon", "mm"],
  Size: ["Distance", "mm"],
  Angle: ["Angle", "°"],
  Thickness: ["Épaisseur", "mm"],
  Value: ["Épaisseur", "mm"],
  Occurrences: ["Nombre d'occurrences", ""],
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
    panel.open({
      icon: TREE_ICONS[feature.type] ?? "PartDesign_Body.svg",
      title: info.label,
      groups: [{
        label: "Paramètres",
        rows: info.params.map((p) => {
          const [label, unit] = PROP_LABELS[p.prop] ?? [p.prop, "mm"];
          return { type: "number", key: p.prop, label, unit,
                   value: p.value };
        }),
      }],
      onApply: async (v) => {
        try {
          let touched = false;
          for (const p of info.params) {
            const value = parseFloat(v[p.prop]);
            if (!Number.isNaN(value) && value !== p.value) {
              await call("set_param",
                { feature: feature.name, prop: p.prop, value });
              touched = true;
            }
          }
          if (touched) await refresh(call("get_tree"));
        } catch (error) {
          say(error.message, true);
        }
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

document.getElementById("ctx-rollback").addEventListener("click", () => {
  if (menuFeature) refresh(call("set_tip", { feature: menuFeature.name }));
});
document.getElementById("ctx-end").addEventListener("click", () =>
  refresh(call("tip_to_end")));
document.getElementById("ctx-delete").addEventListener("click", () => {
  if (!menuFeature) return;
  if (confirm(`Supprimer « ${menuFeature.label} » ?`))
    refresh(call("delete_feature", { feature: menuFeature.name }));
});

// ---------- ruban à onglets (CommandManager) ----------

function showTab(name) {
  for (const tab of document.querySelectorAll("header .tab")) {
    tab.classList.toggle("active", tab.dataset.tab === name);
  }
  document.getElementById("ribbon-features").classList
    .toggle("active", name === "features");
  document.getElementById("sketchbar").classList
    .toggle("active", name === "sketch");
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
  if (sketchMode.active) await sketchMode.finish();
  openPanel();
}

// ---------- actions ----------

async function refresh(treePromise) {
  try {
    const tree = await treePromise;
    renderTree(tree);
    showMesh(await call("tessellate"));
    say("À jour.");
  } catch (error) {
    say(error.message, true);
  }
}

document.getElementById("btn-new").addEventListener("click", () =>
  refresh(call("new_part")));

document.getElementById("btn-undo").addEventListener("click", () =>
  refresh(call("undo")));
document.getElementById("btn-redo").addEventListener("click", () =>
  refresh(call("redo")));

document.getElementById("btn-sketch").addEventListener("click", () =>
  featureCommand(() => {
    if (selectedFaceId !== null) {
      sketchMode.enter(call("sketch_start", { face: selectedFaceId }));
    } else if (selectedPlane !== null) {
      pickPlane(selectedPlane);
    } else {
      // Rien de choisi : les trois plans s'affichent, à vous de cliquer —
      // le geste SolidWorks exact.
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

// Habillages : la zone de sélection du panneau absorbe le clic de face —
// on peut ouvrir la commande d'abord et cliquer la face ensuite, comme
// dans SolidWorks.
function dressupPanel({ icon, title, selectionLabel, group, rows, build }) {
  panel.open({
    icon, title,
    groups: [
      { label: selectionLabel,
        rows: [{ type: "selection", key: "face", value: selectedFaceId }] },
      { label: group, rows },
    ],
    onChange: (v) =>
      schedulePreview(v.face === null || v.face === undefined
        ? null : build(v)),
    onApply: (v) => {
      if (v.face === null || v.face === undefined) {
        say(`${title} : cliquez une face de la pièce`, true);
        return;
      }
      const built = build(v);
      if (!built) { say("Valeur invalide", true); return; }
      refresh(call(built.op, built.params));
    },
  });
}

document.getElementById("btn-fillet").addEventListener("click", () =>
  featureCommand(() => dressupPanel({
    icon: "PartDesign_Fillet.svg", title: "Congé",
    selectionLabel: "Éléments à arrondir",
    group: "Paramètres du congé",
    rows: [{ type: "number", key: "radius", label: "Rayon", value: 3,
             unit: "mm", min: 0.01 }],
    build: (v) => {
      const radius = parseFloat(v.radius);
      return radius > 0
        ? { op: "add_fillet", params: { face: v.face, radius } } : null;
    },
  })));

document.getElementById("btn-chamfer").addEventListener("click", () =>
  featureCommand(() => dressupPanel({
    icon: "PartDesign_Chamfer.svg", title: "Chanfrein",
    selectionLabel: "Éléments à chanfreiner",
    group: "Paramètres du chanfrein",
    rows: [{ type: "number", key: "size", label: "Distance", value: 2,
             unit: "mm", min: 0.01 }],
    build: (v) => {
      const size = parseFloat(v.size);
      return size > 0
        ? { op: "add_chamfer", params: { face: v.face, size } } : null;
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
        ? { op: "add_thickness", params: { face: v.face, thickness } }
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
        ? { op: "add_draft", params: { face: v.face, angle } } : null;
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
  const path = prompt("Ouvrir (chemin .FCStd) :", "~/piece-freesolid.FCStd");
  if (!path) return;
  try {
    const tree = await call("open_part", { path });
    renderTree(tree);
    showMesh(await call("tessellate"));
    say(tree.bodies_in_file > 1
      ? `Ouvert — ${tree.bodies_in_file} corps dans le fichier, affichage du premier.`
      : "Ouvert.");
  } catch (error) {
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
    "Exporter (chemin .stl pour l'impression 3D, .step pour l'échange) :",
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
  try {
    say("Selftest en cours…");
    const report = await call("selftest");
    renderTree(report.tree_after_pad);
    showMesh(await call("tessellate"));
    say(`Selftest OK — ${report.mesh_faces} faces, ` +
        `${report.mesh_triangles} triangles, reparam ${report.m0_reparam_ok ? "OK" : "ÉCHEC"}`);
    console.log("selftest", report);
  } catch (error) {
    say("Selftest : " + error.message, true);
  }
});

// ---------- sketch mode ----------

const sketchMode = createSketchMode(
  { scene, camera, renderer, controls, call, say, refresh });

// ---------- boot ----------

call("ping")
  .then((info) => say(`Moteur prêt — FreeCAD ${info.freecad}`))
  .catch(() => say("Moteur injoignable — lancez engine/server.py avec freecadcmd", true));
