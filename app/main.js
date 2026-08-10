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

let partMesh = null;
let partEdges = null;
let meshGroups = [];

function showMesh(mesh) {
  if (partMesh) { scene.remove(partMesh); partMesh.geometry.dispose(); }
  if (partEdges) { scene.remove(partEdges); partEdges.geometry.dispose(); }
  partMesh = partEdges = null;
  meshGroups = mesh.groups;
  if (!mesh.indices.length) return;

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position",
    new THREE.Float32BufferAttribute(mesh.positions, 3));
  geometry.setIndex(mesh.indices);
  for (const g of mesh.groups) geometry.addGroup(g.start, g.count, 0);
  geometry.computeVertexNormals();

  partMesh = new THREE.Mesh(geometry, [baseMaterial, hoverMaterial]);
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
    partMesh.geometry.groups.forEach((g, i) => {
      g.materialIndex = i === groupIndex ? 1 : 0;
    });
    pickEl.textContent =
      groupIndex >= 0 ? `Face ${meshGroups[groupIndex].faceId}` : "";
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
    item.title = "Double-clic : modifier";
    item.addEventListener("dblclick", () => editFeature(feature));
    treeEl.appendChild(item);
    if (feature.name === tree.tip) {
      const bar = document.createElement("li");
      bar.className = "rollback";
      bar.textContent = "▲ barre de retour arrière ▲";
      treeEl.appendChild(bar);
    }
  }
}

async function editFeature(feature) {
  if (feature.type !== "PartDesign::Pad") {
    say("édition M0 : seul le bossage est éditable pour l'instant");
    return;
  }
  const value = prompt("Profondeur du bossage (mm) :", "10");
  if (value === null) return;
  await refresh(call("set_param",
    { feature: feature.name, prop: "Length", value: parseFloat(value) }));
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

document.getElementById("btn-sketch").addEventListener("click", () => {
  const w = parseFloat(prompt("Largeur (mm) :", "100") ?? "");
  const h = parseFloat(prompt("Hauteur (mm) :", "60") ?? "");
  if (!w || !h) return;
  refresh(call("add_rect_sketch", { width: w, height: h }));
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
        `${report.mesh_triangles} triangles, reparam ${report.reparam_ok ? "OK" : "ÉCHEC"}`);
    console.log("selftest", report);
  } catch (error) {
    say("Selftest : " + error.message, true);
  }
});

// ---------- boot ----------

call("ping")
  .then((info) => say(`Moteur prêt — FreeCAD ${info.freecad}`))
  .catch(() => say("Moteur injoignable — lancez engine/server.py avec freecadcmd", true));
