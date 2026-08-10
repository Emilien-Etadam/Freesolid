// FreeSolid app — M0. One part, one mesh, a SolidWorks-shaped tree,
// face picking by construction (each engine face is an index group).

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

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

  partMesh = new THREE.Mesh(geometry, [baseMaterial, hoverMaterial, selectedMaterial]);
  scene.add(partMesh);

  // Plasticity-style crisp silhouette: hard edges over the shaded mesh.
  partEdges = new THREE.LineSegments(
    new THREE.EdgesGeometry(geometry, 25),
    new THREE.LineBasicMaterial({ color: 0x11141a }));
  scene.add(partEdges);
}

// Face hover: triangle index -> group -> engine faceId. By construction.
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
let hoveredGroup = -1;

renderer.domElement.addEventListener("pointermove", (event) => {
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
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
  pressPosition = { x: event.clientX, y: event.clientY };
});
renderer.domElement.addEventListener("pointerup", (event) => {
  if (!pressPosition) return;
  const travel = Math.hypot(event.clientX - pressPosition.x,
                            event.clientY - pressPosition.y);
  pressPosition = null;
  if (travel > 5) return;
  selectedFaceId = hoveredGroup >= 0 ? meshGroups[hoveredGroup].faceId : null;
  repaintGroups();
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

// ---------- feature tree ----------

function renderTree(tree) {
  treeEl.innerHTML = "";
  const bodyItem = document.createElement("li");
  bodyItem.className = "body";
  bodyItem.textContent = tree.body;
  treeEl.appendChild(bodyItem);

  for (const feature of tree.features) {
    const item = document.createElement("li");
    if (feature.error) item.className = "error";
    item.innerHTML =
      `<span class="kind">${feature.kind}</span> — ${feature.label}`;
    item.title = "Double-clic : modifier · clic droit : barre de retour, supprimer";
    item.addEventListener("dblclick", () => editFeature(feature));
    item.addEventListener("contextmenu", (e) => openMenu(e, feature));
    treeEl.appendChild(item);
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

async function editFeature(feature) {
  try {
    const info = await call("get_params", { feature: feature.name });
    if (!info.params.length) {
      say(`${info.label} : aucun paramètre numérique éditable`);
      return;
    }
    let touched = false;
    for (const p of info.params) {
      const raw = prompt(`${info.label} — ${p.prop} (mm) :`, p.value);
      if (raw === null) continue; // Annuler = garder cette valeur
      const value = parseFloat(raw);
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

document.getElementById("btn-sketch").addEventListener("click", () => {
  const w = parseFloat(prompt("Largeur (mm) :", "100") ?? "");
  const h = parseFloat(prompt("Hauteur (mm) :", "60") ?? "");
  if (!w || !h) return;
  const params = { width: w, height: h };
  if (selectedFaceId !== null) params.face = selectedFaceId;
  refresh(call("add_rect_sketch", params));
});

document.getElementById("btn-pocket").addEventListener("click", () => {
  const length = parseFloat(prompt("Profondeur de l'enlèvement (mm) :", "5") ?? "");
  if (!length) return;
  refresh(call("add_pocket", { length }));
});

function dressup(op, label, param, fallback) {
  if (selectedFaceId === null) {
    say(`${label} : cliquez d'abord une face de la pièce`, true);
    return;
  }
  const value = parseFloat(prompt(`${label} (mm) :`, fallback) ?? "");
  if (!value) return;
  refresh(call(op, { face: selectedFaceId, [param]: value }));
}

document.getElementById("btn-fillet").addEventListener("click", () =>
  dressup("add_fillet", "Rayon du congé", "radius", "3"));

document.getElementById("btn-chamfer").addEventListener("click", () =>
  dressup("add_chamfer", "Taille du chanfrein", "size", "2"));

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

document.getElementById("btn-pad").addEventListener("click", () => {
  const length = parseFloat(prompt("Profondeur (mm) :", "10") ?? "");
  if (!length) return;
  refresh(call("add_pad", { length }));
});

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

// ---------- boot ----------

call("ping")
  .then((info) => say(`Moteur prêt — FreeCAD ${info.freecad}`))
  .catch(() => say("Moteur injoignable — lancez engine/server.py avec freecadcmd", true));
