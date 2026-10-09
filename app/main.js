// FreeSolid app — M0. One part, one mesh, a SolidWorks-shaped tree,
// face picking by construction (each engine face is an index group).

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { createSketchMode, createDimSprite } from "./sketch.js";
import {
  dimEditPayload, dimLabel, openDimEditor, sketchDimAnchor,
} from "./dims.js";
import { createPropertyPanel } from "./panel.js";
import { num } from "./num.js";
import {
  readDisplay, writeDisplay, displayEffects,
} from "./display.js";
import {
  FEATURES, chamferRows, chamferFieldValue, chamferEditValues, chamferProblem,
  revolutionGroups, revolutionEditValues, revolutionProblem,
} from "./features.js";
import {
  formatProgressStatus,
  noteProgressForCalibration,
  rememberCombineFinished,
} from "./progress.js";
import { arcAngles } from "./geom2d.js";
import { sketchTreeLabel, splitHistoryAroundBar } from "./history.js";
import { contextToolbarKeys, viewMenuItems, viewMenuLabel } from "./viewmenu.js";
import { currentPaneIndex, layoutPanes, paneRect } from "./layouts.js";
import { createPluginApi, loadClientPlugins } from "./plugins.js";
import { createSettingsDialog, ISSUES_URL, readLang } from "./settings.js";
import { installMenuBar, menuBarModel } from "./menubar.js";
import {
  boxMode, isDrag, middleAction, normalizeRect, pickInBox,
  readReverseWheel, writeReverseWheel, zoomSpeedFor,
} from "./navigation.js";
import { currentLang, setLang, t, translateDom } from "./i18n.js";

// La langue avant tout rendu : ruban, panneaux et messages passent par t().
setLang(readLang((() => { try { return window.localStorage; } catch { return null; } })(),
  navigator.language));
document.documentElement.lang = currentLang();
translateDom(document.body);

// prompt()/confirm() natifs, message traduit : les appels gardent le texte
// source en français, le dictionnaire fait le reste.
const prompt = (message, fallback) => window.prompt(t(message), fallback);
const confirm = (message) => window.confirm(t(message));
import {
  buildRibbonElement, buildTabButton, installCoreRibbons, isPluginId,
} from "./ribbon.js";
import RIBBON_LAYOUT from "./ribbon.json" with { type: "json" };
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

// Le ruban du noyau est rendu depuis ribbon.json avant tout câblage :
// les getElementById("btn-…") plus bas supposent les boutons présents.
// La table onglet → bandeau est complétée par les plugins (addPluginRibbon).
const RIBBONS = installCoreRibbons(document, RIBBON_LAYOUT);

const statusEl = document.getElementById("status");
const pickEl = document.getElementById("pick");
const treeEl = document.getElementById("tree");

// ---------- api ----------

async function call(op, params = {}) {
  const response = await fetch("/api", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    // La langue de l'interface part avec chaque requête : le moteur nomme
    // ce qu'il crée et rédige ses erreurs dans cette langue.
    body: JSON.stringify({ op, params, lang: currentLang() }),
  });
  const text = await response.text();
  let payload = null;
  try {
    payload = JSON.parse(text);
  } catch {
    payload = null;
  }
  // {ok:false} (HTTP 200 ou 4xx protocole) : message moteur / protocole.
  if (payload && payload.ok === false) {
    throw new Error(payload.error + (payload.hint ? ` (${payload.hint})` : ""));
  }
  if (!response.ok || !payload || payload.ok !== true) {
    const excerpt = text.slice(0, 180).replace(/\s+/g, " ").trim();
    throw new Error(
      `HTTP ${response.status}${excerpt ? ` — ${excerpt}` : ""}`);
  }
  return payload.result;
}

const PROGRESS_MS = 300;
let progressTimer = null;
let progressWatchers = 0;
let progressGen = 0;
let statusSticky = false;

async function pollProgressOnce(gen) {
  if (gen !== progressGen || statusSticky) return;
  try {
    const progress = await call("progress");
    if (gen !== progressGen || statusSticky) return;
    const now = Date.now() / 1000;
    noteProgressForCalibration(progress, now);
    const text = formatProgressStatus(progress, now);
    if (text) say(text);
  } catch {
    // Le sondage ne doit jamais masquer l'op en cours ni son erreur.
  }
}

function startProgressWatch() {
  progressWatchers += 1;
  if (progressWatchers > 1) return;
  const gen = ++progressGen;
  document.body.classList.add("op-en-cours");
  document.body.setAttribute("aria-busy", "true");
  pollProgressOnce(gen);
  progressTimer = setInterval(() => pollProgressOnce(gen), PROGRESS_MS);
}

function stopProgressWatch() {
  progressWatchers = Math.max(0, progressWatchers - 1);
  if (progressWatchers > 0) return;
  progressGen += 1;
  if (progressTimer != null) {
    clearInterval(progressTimer);
    progressTimer = null;
  }
  document.body.classList.remove("op-en-cours");
  document.body.removeAttribute("aria-busy");
}

function say(text, isError = false) {
  if (statusSticky && !isError) return;
  if (!isError) statusSticky = false;
  statusEl.textContent = t(text);
  statusEl.className = isError ? "err" : "";
  if (statusSticky) statusEl.classList.add("sticky");
  statusEl.title = statusSticky ? t("Cliquer pour fermer") : "";
}

/** Erreur qui reste jusqu'à ce que l'utilisateur clique la barre d'état. */
function sayUntilAck(text) {
  statusSticky = true;
  say(text, true);
}

statusEl.addEventListener("click", () => {
  if (!statusSticky) return;
  statusSticky = false;
  statusEl.classList.remove("sticky");
  statusEl.title = "";
});

// PropertyManager-style side panel — feature options live there, not in
// prompt() dialogs. See panel.js for the SolidWorks anatomy. Closing the
// panel (OK or cancel) always clears the yellow ghost preview.
const panel = createPropertyPanel({
  say,
  onClose: () => {
    clearGhost();
    sketchInfoOpen = false;
  },
  onToggle: () => {
    updateConfirmCorner();
    updateTreeFlyout();
  },
});

// ---------- arbre en surimpression pendant une commande ----------
// Le panneau prend la place de l'arbre : l'arbre (le même élément, avec
// ses écouteurs) passe dans un volet en haut à gauche de la vue, pour y
// cliquer une fonction, une esquisse ou un plan pendant la commande.

const treeFlyout = document.getElementById("tree-flyout");
const treeFlyoutBody = document.getElementById("tree-flyout-body");
const TREE_FLYOUT_KEY = "freesolid.treeFlyoutOpen";

function updateTreeFlyout() {
  if (!treeFlyout) return;
  const tree = document.getElementById("tree");
  if (panel.active) {
    if (tree.parentElement !== treeFlyoutBody) treeFlyoutBody.appendChild(tree);
    treeFlyout.hidden = false;
  } else {
    const aside = document.querySelector("aside");
    if (tree.parentElement !== aside) {
      aside.insertBefore(tree, document.getElementById("panel"));
    }
    treeFlyout.hidden = true;
  }
}

function setTreeFlyoutOpen(open) {
  treeFlyout?.classList.toggle("collapsed", !open);
  try { localStorage.setItem(TREE_FLYOUT_KEY, open ? "1" : "0"); } catch { /* ok */ }
}

document.getElementById("tree-flyout-toggle")?.addEventListener("click", () =>
  setTreeFlyoutOpen(treeFlyout.classList.contains("collapsed")));
setTreeFlyoutOpen((() => {
  try { return localStorage.getItem(TREE_FLYOUT_KEY) !== "0"; } catch { return true; }
})());

// ---------- viewport ----------

const container = document.getElementById("viewport");
const renderer = new THREE.WebGLRenderer({ antialias: true });
// En tête du conteneur : les calques posés par-dessus (boîtes, barres)
// restent au-dessus des canvas des fenêtres multiples.
container.prepend(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x17191c);

// Hauteur du frustum (unités monde) à zoom = 1. Le zoom OrbitControls
// et « Zoom au mieux » ajustent camera.zoom, pas la distance.
const ORTHO_HEIGHT = 200;
const camera = new THREE.OrthographicCamera(
  -ORTHO_HEIGHT / 2, ORTHO_HEIGHT / 2,
  ORTHO_HEIGHT / 2, -ORTHO_HEIGHT / 2,
  0.1, 10000);
camera.position.set(160, -160, 120);
camera.up.set(0, 0, 1); // CAD is Z-up

// Dispositions multi-fenêtres (layouts.js). Le canvas principal, sa caméra
// et ses contrôles occupent toujours la fenêtre active : sélection, cotes
// et esquisse n'en savent rien. Les autres fenêtres sont dessinées par des
// canvas secondaires, chacune avec l'état de caméra qu'elle avait. Cliquer
// une fenêtre secondaire l'active : les états s'échangent, rien ne saute.
let panes = layoutPanes("single");
let activePane = 0;
const extraViews = [];   // { renderer, pane } — pane : index, ou -1
const paneCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 10000);

/** Taille en pixels de la fenêtre active. */
function viewSize() {
  const width = container.clientWidth, height = container.clientHeight;
  if (panes.length < 2) return { width, height };
  return paneRect(panes[activePane], width, height);
}

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

// Navigation (navigation.js) : le milieu tourne, Ctrl + milieu déplace,
// Maj + milieu zoome, la molette zoome vers le curseur ; le bouton gauche
// sélectionne (clic ou cadre), le droit reste au menu contextuel.
const localStore = (() => { try { return window.localStorage; } catch { return null; } })();
controls.mouseButtons = { LEFT: null, MIDDLE: THREE.MOUSE.ROTATE, RIGHT: null };
controls.zoomToCursor = true;
controls.zoomSpeed = zoomSpeedFor(readReverseWheel(localStore));

// OrbitControls inverse lui-même ROTATE/PAN quand Ctrl ou Maj est tenu :
// on lui donne le bouton qui, avec ces touches, produit le bon geste.
function orbitButtonFor(action, event) {
  const mod = event.ctrlKey || event.metaKey || event.shiftKey;
  if (action === "dolly") return THREE.MOUSE.DOLLY;
  if (action === "pan") return mod ? THREE.MOUSE.ROTATE : THREE.MOUSE.PAN;
  return mod ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE;
}
// Capture : passe avant le pointerdown d'OrbitControls, qui lit
// mouseButtons à l'appui.
renderer.domElement.addEventListener("pointerdown", (event) => {
  if (event.button !== 1) return;
  controls.mouseButtons.MIDDLE = orbitButtonFor(
    middleAction(event, { rotateLocked: !controls.enableRotate }), event);
}, { capture: true });
// Pas de défilement automatique du navigateur au clic milieu.
renderer.domElement.addEventListener("mousedown", (event) => {
  if (event.button === 1) event.preventDefault();
});

// Centre de rotation : un clic milieu (sans glisser) sur la pièce pose le
// centre, un clic milieu dans le vide le retire. Avec un centre posé, le
// glisser milieu tourne la vue autour de lui (il reste fixe à l'écran) ;
// OrbitControls, qui ne sait tourner qu'autour du centre de la vue, est
// mis de côté le temps du glisser.
let rotationPivot = null;
let pivotDrag = null;
const pivotMarker = new THREE.Points(
  new THREE.BufferGeometry().setFromPoints([new THREE.Vector3()]),
  new THREE.PointsMaterial({ color: 0xd9924a, size: 10,
    sizeAttenuation: false, depthTest: false }));
pivotMarker.visible = false;
pivotMarker.renderOrder = 30;
scene.add(pivotMarker);

function pickPivot(event) {
  const rect = renderer.domElement.getBoundingClientRect();
  const at = new THREE.Vector2(
    ((event.clientX - rect.left) / rect.width) * 2 - 1,
    -((event.clientY - rect.top) / rect.height) * 2 + 1);
  raycaster.setFromCamera(at, camera);
  const targets = [partMesh, ...othersMeshes, ...surfaceMeshes,
    ...(asmGroup ? asmGroup.children : [])].filter(Boolean);
  return raycaster.intersectObjects(targets, false)[0]?.point ?? null;
}

function setRotationPivot(point) {
  rotationPivot = point ? point.clone() : null;
  pivotMarker.visible = !!rotationPivot;
  if (rotationPivot) pivotMarker.position.copy(rotationPivot);
  say(rotationPivot
    ? "Centre de rotation posé — clic milieu dans le vide pour le retirer."
    : "Centre de rotation : centre de la vue.");
}

/** Tourne caméra et cible autour du centre : lacet autour de l'axe haut de
 *  la caméra (Z, ou Y après une vue de dessus), tangage autour de
 *  l'horizontale de l'écran. Même axe haut que lookAt : pas de saut. */
function orbitAroundPivot(dx, dy) {
  const height = renderer.domElement.clientHeight || 1;
  const yaw = -2 * Math.PI * dx / height;
  const pitch = -2 * Math.PI * dy / height;
  const view = new THREE.Vector3().subVectors(controls.target, camera.position)
    .normalize();
  const right = new THREE.Vector3().crossVectors(view, camera.up).normalize();
  const up = camera.up.clone().normalize();
  const q = new THREE.Quaternion().setFromAxisAngle(up, yaw);
  const qPitch = new THREE.Quaternion().setFromAxisAngle(right, pitch);
  const tilted = view.clone().applyQuaternion(qPitch);
  if (Math.abs(tilted.dot(up)) < 0.995) q.multiply(qPitch); // pas de bascule au pôle
  for (const point of [camera.position, controls.target]) {
    point.sub(rotationPivot).applyQuaternion(q).add(rotationPivot);
  }
  camera.lookAt(controls.target);
}

renderer.domElement.addEventListener("pointerdown", (event) => {
  if (event.button !== 1) return;
  pivotDrag = { x: event.clientX, y: event.clientY, last: null,
    custom: !!rotationPivot && controls.enableRotate
      && !event.ctrlKey && !event.metaKey && !event.shiftKey };
  if (pivotDrag.custom) {
    controls.enabled = false;
    pivotDrag.last = { x: event.clientX, y: event.clientY };
  }
}, { capture: true });

renderer.domElement.addEventListener("pointermove", (event) => {
  if (!pivotDrag?.custom || !pivotDrag.last) return;
  orbitAroundPivot(event.clientX - pivotDrag.last.x,
                   event.clientY - pivotDrag.last.y);
  pivotDrag.last = { x: event.clientX, y: event.clientY };
});

window.addEventListener("pointerup", (event) => {
  if (!pivotDrag || event.button !== 1) return;
  const drag = pivotDrag;
  pivotDrag = null;
  if (drag.custom) controls.enabled = true;
  if (Math.hypot(event.clientX - drag.x, event.clientY - drag.y) > 4) return;
  if (sketchMode?.active) return;
  setRotationPivot(pickPivot(event));
});

function setReverseWheel(reversed) {
  writeReverseWheel(localStore, reversed);
  controls.zoomSpeed = zoomSpeedFor(reversed);
}

// Cadre de sélection : un rectangle HTML posé sur la vue. Trait plein en
// fenêtre (gauche → droite), tirets en capture (droite → gauche).
const boxEl = document.createElement("div");
boxEl.id = "box-select";
boxEl.hidden = true;
const boxOverlay = {
  show(start, end) {
    const host = container.getBoundingClientRect();
    const r = normalizeRect(start, end);
    boxEl.hidden = false;
    boxEl.className = boxMode(start, end);
    boxEl.style.left = `${r.left - host.left}px`;
    boxEl.style.top = `${r.top - host.top}px`;
    boxEl.style.width = `${r.right - r.left}px`;
    boxEl.style.height = `${r.bottom - r.top}px`;
  },
  hide() { boxEl.hidden = true; },
};
container.appendChild(boxEl);

// Maillages volumiques (corps, autres corps, surfaces, arêtes, aperçu).
// La pièce reste visible pendant l'esquisse (on dessine en s'appuyant sur
// elle, l'esquisse se lit par-dessus) ; seules les cotes de fonction,
// propres au mode 3D, se masquent. (Revient sur P023, décision Q1.)
const volumesGroup = new THREE.Group();
volumesGroup.name = "volumes";
scene.add(volumesGroup);
let inSketchMode = false;

function applyVolumeVisibility() {
  volumesGroup.visible = true;
  featureDimsGroup.visible = !inSketchMode;
  applyDisplay();
}

function volumeVisibleCount() {
  if (!volumesGroup.visible) return 0;
  let n = 0;
  volumesGroup.traverse((obj) => {
    if (obj !== volumesGroup && (obj.isMesh || obj.isLineSegments)
        && obj.visible) {
      n += 1;
    }
  });
  return n;
}

function sketchScreenPoint() {
  const lines = sketchLineMeshes[0];
  if (!lines) return null;
  const pos = lines.geometry.getAttribute("position");
  if (!pos || pos.count < 2) return null;
  const a = new THREE.Vector3().fromBufferAttribute(pos, 0);
  const b = new THREE.Vector3().fromBufferAttribute(pos, 1);
  const mid = a.add(b).multiplyScalar(0.5);
  mid.project(camera);
  const rect = renderer.domElement.getBoundingClientRect();
  return {
    name: lines.userData.sketch?.name ?? null,
    label: lines.userData.sketch?.label ?? null,
    x: (mid.x * 0.5 + 0.5) * rect.width + rect.left,
    y: (-mid.y * 0.5 + 0.5) * rect.height + rect.top,
  };
}

function surfaceScreenPoint() {
  const mesh = surfaceMeshes[0];
  if (!mesh) return null;
  mesh.geometry.computeBoundingSphere();
  const center = mesh.geometry.boundingSphere?.center;
  if (!center) return null;
  const projected = center.clone().project(camera);
  const rect = renderer.domElement.getBoundingClientRect();
  return {
    name: mesh.userData.surface?.name ?? null,
    label: mesh.userData.surface?.label ?? null,
    x: (projected.x * 0.5 + 0.5) * rect.width + rect.left,
    y: (-projected.y * 0.5 + 0.5) * rect.height + rect.top,
  };
}

/** Centre du premier volume visible, en coordonnées écran — pour que le
 *  smoke clique la pièce là où elle est, pas là où il l'espère. */
function volumeScreenPoint() {
  let mesh = null;
  volumesGroup.traverse((obj) => {
    if (!mesh && obj.isMesh && obj.visible) mesh = obj;
  });
  if (!mesh) return null;
  mesh.geometry.computeBoundingSphere();
  const center = mesh.geometry.boundingSphere?.center;
  if (!center) return null;
  const projected = mesh.localToWorld(center.clone()).project(camera);
  const rect = renderer.domElement.getBoundingClientRect();
  return {
    x: (projected.x * 0.5 + 0.5) * rect.width + rect.left,
    y: (-projected.y * 0.5 + 0.5) * rect.height + rect.top,
  };
}

window.__freesolidDebug = {
  get volumeVisibleCount() { return volumeVisibleCount(); },
  get volumeScreenPoint() { return volumeScreenPoint(); },
  get isOrthographic() { return camera.isOrthographicCamera === true; },
  get sketchLineCount() { return sketchLineMeshes.length; },
  get sketchScreenPoint() { return sketchScreenPoint(); },
  get surfaceMeshCount() { return surfaceMeshes.length; },
  get surfaceScreenPoint() { return surfaceScreenPoint(); },
  get gemHudText() {
    const hud = document.getElementById("gem-hud");
    if (!hud || hud.hidden) return "";
    return hud.innerText.replace(/\s+/g, " ").trim();
  },
  get featureDimCount() { return featureDimSprites.length; },
  /** Centre de rotation projeté à l'écran, ou null. */
  get rotationPivotScreen() {
    if (!rotationPivot) return null;
    camera.updateMatrixWorld();
    const p = rotationPivot.clone().project(camera);
    const rect = renderer.domElement.getBoundingClientRect();
    return { x: (p.x * 0.5 + 0.5) * rect.width + rect.left,
             y: (-p.y * 0.5 + 0.5) * rect.height + rect.top };
  },
  get selectedFeatureName() { return selectedFeatureName; },
  refresh: () => refresh(call("get_tree")),
  get graphFeatureActive() { return graphFn.active; },
  get graphFeatureKind() { return graphFn.kind; },
  get graphFeatureErrorNode() { return graphFn.errorNode; },
  get graphFeatureOutput() { return graphFn.draft?.output ?? null; },
  get graphFeatureNodeIds() {
    return (graphFn.draft?.nodes ?? []).map((node) => String(node.id));
  },
};

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
let othersMeshes = []; // corps non actifs, un mesh chacun
let partBaseMaterial = null; // clone possédé — couleur du corps actif
let meshGroups = [];
let edgeGroups = [];
let hoveredEdgeGroup = -1;

const othersMaterial = new THREE.MeshStandardMaterial({
  color: 0x5f6b78, metalness: 0.1, roughness: 0.7,
  transparent: true, opacity: 0.45, depthWrite: false,
});
// Surfaces : même teinte que le solide, DoubleSide (peau ouverte).
const surfaceHoverMaterial = hoverMaterial.clone();
surfaceHoverMaterial.side = THREE.DoubleSide;
const surfaceSelectedMaterial = selectedMaterial.clone();
surfaceSelectedMaterial.side = THREE.DoubleSide;
const curvesMaterial = new THREE.LineBasicMaterial({ color: 0x4fb8a8 });
const sketchesMaterial = new THREE.LineBasicMaterial({ color: 0x8fa8c8 });
let surfaceMeshes = []; // un mesh par surface, sélectionnable
let curvesLines = null;
let sketchLineMeshes = []; // esquisses libres, un LineSegments chacune
let hoveredSketch = null;  // { name, label } | null
let hoveredSurface = null; // { name, label } | null
let selectedSurface = null; // { name, label } | null
let lastFaceHit = null; // { face, x, y, z } du dernier clic face
let selectedFeatureName = null;
const featureDimsGroup = new THREE.Group();
featureDimsGroup.renderOrder = 24;
scene.add(featureDimsGroup);
let featureDimSprites = [];
let featureDimContext = null; // { feature, hit }
let lastFaceMatch = null; // { matched, faces } du dernier tessellate
let pluginRuntime = null;

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

function applyPackedGeometry(geometry, packed) {
  geometry.setAttribute("position",
    new THREE.Float32BufferAttribute(packed.positions, 3));
  if (packed.indices) geometry.setIndex(packed.indices);
  if (packed.normals && packed.normals.length === packed.positions.length) {
    geometry.setAttribute("normal",
      new THREE.Float32BufferAttribute(packed.normals, 3));
  } else {
    geometry.computeVertexNormals();
  }
}


function hexColor(value) {
  return typeof value === "string" && /^#[0-9a-fA-F]{6}$/.test(value)
    ? value : null;
}

function ownedMaterial(source, color) {
  const material = source.clone();
  material.userData.own = true;
  if (color) material.color.set(color);
  return material;
}

function detachMesh(mesh) {
  if (!mesh) return;
  mesh.removeFromParent();
  disposeSubtree(mesh);
}

function detachSurfaceMeshes() {
  for (const mesh of surfaceMeshes) {
    mesh.removeFromParent();
    mesh.geometry.dispose();
    const base = mesh.userData.baseMaterial;
    if (base?.userData?.own) base.dispose();
  }
  surfaceMeshes = [];
}

let lastClearedSelections = false;

function showMesh(mesh) {
  detachMesh(partMesh);
  for (const extra of othersMeshes) detachMesh(extra);
  othersMeshes = [];
  partMesh = partBaseMaterial = null;
  meshGroups = mesh.groups;
  lastFaceMatch = mesh.face_match ?? null;
  hoveredGroup = -1;
  selectedFaceId = null; // ids shift after every feature: stale picks lie
  const cleared = panel.invalidateSelections();
  lastClearedSelections = cleared > 0;
  // Les noms/labels d'esquisse bougent aussi après une fonction.
  clearSketchSelection({ quiet: true });
  cancelPendingSurfaceClick();
  selectedSurface = null;
  if (lastClearedSelections) {
    say("Sélections réinitialisées — la géométrie a changé.");
  }
  detachSurfaceMeshes();
  hoveredSurface = null;
  if (curvesLines) {
    scene.remove(curvesLines);
    curvesLines.geometry.dispose();
    curvesLines = null;
  }
  for (const lines of sketchLineMeshes) detachMesh(lines);
  sketchLineMeshes = [];
  hoveredSketch = null;
  const othersList = mesh.other_bodies?.length
    ? mesh.other_bodies
    : (mesh.others?.indices.length
      ? [{ color: null, positions: mesh.others.positions,
           indices: mesh.others.indices }]
      : []);
  for (const extra of othersList) {
    if (!extra.indices.length) continue;
    const geometry = new THREE.BufferGeometry();
    applyPackedGeometry(geometry, extra);
    const otherMesh = new THREE.Mesh(
      geometry, ownedMaterial(othersMaterial, hexColor(extra.color)));
    otherMesh.raycast = () => {};
    volumesGroup.add(otherMesh);
    othersMeshes.push(otherMesh);
  }
  for (const surface of Array.isArray(mesh.surfaces) ? mesh.surfaces : []) {
    if (!surface.indices?.length) continue;
    const geometry = new THREE.BufferGeometry();
    applyPackedGeometry(geometry, surface);
    const material = ownedMaterial(baseMaterial);
    material.side = THREE.DoubleSide;
    material.transparent = false;
    material.opacity = 1;
    const surfMesh = new THREE.Mesh(geometry, material);
    surfMesh.userData.surface = { name: surface.name, label: surface.label };
    surfMesh.userData.baseMaterial = material;
    volumesGroup.add(surfMesh);
    surfaceMeshes.push(surfMesh);
  }
  if (mesh.curves?.indices.length) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position",
      new THREE.Float32BufferAttribute(mesh.curves.positions, 3));
    geometry.setIndex(mesh.curves.indices);
    curvesLines = new THREE.LineSegments(geometry, curvesMaterial);
    scene.add(curvesLines);
  }
  for (const sketch of mesh.sketches ?? []) {
    if (!sketch.indices?.length) continue;
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position",
      new THREE.Float32BufferAttribute(sketch.positions, 3));
    geometry.setIndex(sketch.indices);
    const lines = new THREE.LineSegments(geometry, sketchesMaterial);
    lines.userData.sketch = { name: sketch.name, label: sketch.label };
    volumesGroup.add(lines);
    sketchLineMeshes.push(lines);
  }
  pluginRuntime?.applyViewport(mesh, {
    volumesGroup, applyPackedGeometry, ownedMaterial, scene, camera,
  }, detachMesh);
  if (!mesh.indices.length) {
    applyVolumeVisibility();
    rebuildPlanes();
    repaintGroups();
    return;
  }

  const geometry = new THREE.BufferGeometry();
  applyPackedGeometry(geometry, mesh);
  for (const g of mesh.groups) geometry.addGroup(g.start, g.count, 0);

  geometry.computeBoundingSphere(); // les vues standard cadrent dessus

  partBaseMaterial = ownedMaterial(baseMaterial, hexColor(mesh.color));
  partMesh = new THREE.Mesh(geometry,
    [partBaseMaterial, hoverMaterial, selectedMaterial]);
  volumesGroup.add(partMesh);
  applyVolumeVisibility();
  rebuildPlanes(); // les plans de base suivent la taille de la pièce
  repaintGroups();
}

// Les vraies arêtes BREP du moteur (pas une silhouette approchée) :
// chaque arête OCCT est son propre groupe d'indices — picking par
// construction, exactement comme les faces.
const edgeBaseMaterial = new THREE.LineBasicMaterial({ color: 0x11141a });
const edgeHoverMaterial = new THREE.LineBasicMaterial({ color: 0x4f8fdb });
const edgeSelectedMaterial = new THREE.LineBasicMaterial({ color: 0xd9924a });
const hiddenEdgeMaterial = new THREE.LineBasicMaterial({
  color: 0x7d8792,
  depthFunc: THREE.GreaterEqualDepth,
});
const maskMaterial = new THREE.MeshBasicMaterial({
  color: 0x17191c,
  polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1,
});
let hiddenEdgeLines = null;

function showEdgeLines(data) {
  if (partEdges) {
    partEdges.removeFromParent();
    partEdges.geometry.dispose();
  }
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
  volumesGroup.add(partEdges);
  applyVolumeVisibility();
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
let selectedSketch = null;  // { name, label } | null — esquisse sélectionnée
let sketchHighlightGroup = null;
const sketchHighlightMaterial = new THREE.LineBasicMaterial({
  color: 0xd9924a, depthTest: false,
});

// Mêmes noms que vocab.ORIGIN_PLANES — affichés sur les plans eux-mêmes.
const PLANE_LABELS = {
  XY: t("Plan de dessus"), XZ: t("Plan de face"), YZ: t("Plan de droite"),
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
    // Décalée vers un coin : au centre du bord, les étiquettes du plan de
    // dessus et du plan de droite tombaient au même endroit.
    label.position.set(-size * 0.3, size * 0.46, 0);
    label.scale.set(size * 0.42, size * 0.42 * (44 / 256), 1);
    holder.add(fill, border, label);
    planesGroup.add(holder);
    planeMeshes[id] = fill;
  }
  updatePlaneVisibility();
  if (originShown) rebuildOrigin();
}

// Origine de la pièce : trois axes courts depuis (0, 0, 0), affichés à la
// demande (ligne « Origine » de l'arbre), à la taille de la pièce.
const originGroup = new THREE.Group();
originGroup.visible = false;
originGroup.renderOrder = 12;
scene.add(originGroup);
let displayState = readDisplay(localStore);
let originShown = displayState.origin;

function rebuildOrigin() {
  disposeSubtree(originGroup);
  originGroup.clear();
  const { radius } = partCenterRadius();
  const length = Math.max(radius * 0.35, 12);
  const axes = [[1, 0, 0, 0xe06666], [0, 1, 0, 0x6aa84f], [0, 0, 1, 0x4b9bd5]];
  for (const [x, y, z, color] of axes) {
    const arrow = new THREE.ArrowHelper(
      new THREE.Vector3(x, y, z), new THREE.Vector3(0, 0, 0),
      length, color, length * 0.2, length * 0.1);
    arrow.traverse((obj) => {
      if (obj.material) {
        // Passe transparente : dessinée après la pièce, qui l'est aussi.
        obj.material.transparent = true;
        obj.material.depthTest = false;
        obj.material.userData.own = true;
      }
      obj.renderOrder = 12;
    });
    originGroup.add(arrow);
  }
  originGroup.visible = originShown;
}

function toggleOrigin() {
  setOriginShown(!originShown);
  say(originShown ? "Origine affichée." : "Origine masquée.");
}

function setOriginShown(shown) {
  originShown = !!shown;
  displayState = { ...displayState, origin: originShown };
  writeDisplay(localStore, displayState);
  rebuildOrigin();
  if (lastTree) renderTree(lastTree);
  syncVisibilityMenu();
}

function updatePlaneVisibility() {
  const showAll = displayEffects(displayState).planes;
  const single = planePicking ? null : (treeHoverPlane ?? selectedPlane);
  planesGroup.visible = planePicking || showAll || single !== null;
  for (const [id, mesh] of Object.entries(planeMeshes)) {
    mesh.parent.visible = planePicking || showAll || id === single;
    mesh.material.opacity =
      (planePicking && id === hoverPlane) || id === selectedPlane
        ? 0.28 : 0.1;
  }
}

function applyDisplay() {
  const fx = displayEffects(displayState);
  const meshes = [partMesh, ...othersMeshes, ...surfaceMeshes].filter(Boolean);
  for (const mesh of meshes) {
    if (fx.mask) {
      if (!mesh.userData.savedMaterial) mesh.userData.savedMaterial = mesh.material;
      mesh.material = maskMaterial;
    } else if (mesh.userData.savedMaterial) {
      mesh.material = mesh.userData.savedMaterial;
      delete mesh.userData.savedMaterial;
    }
    mesh.visible = fx.faces;
    if (fx.mask) mesh.renderOrder = 0;
  }
  if (partEdges) {
    partEdges.visible = fx.edges;
    partEdges.renderOrder = 2;
    // Sur le solide clair, les arêtes sont sombres. Sur le fond, elles
    // doivent rester lisibles (filaire, lignes cachées).
    edgeBaseMaterial.color.setHex(
      fx.faces && !fx.mask ? 0x11141a : 0xd5dde6);
  }
  if (hiddenEdgeLines) {
    hiddenEdgeLines.removeFromParent();
    hiddenEdgeLines = null;
  }
  if (fx.ghostEdges && partEdges) {
    hiddenEdgeLines = new THREE.LineSegments(
      partEdges.geometry, hiddenEdgeMaterial);
    hiddenEdgeLines.renderOrder = 1;
    hiddenEdgeLines.raycast = () => {};
    volumesGroup.add(hiddenEdgeLines);
  }
  for (const lines of sketchLineMeshes) lines.visible = fx.sketches;
  if (sketchHighlightGroup) sketchHighlightGroup.visible = fx.sketches;
  originGroup.visible = !!displayState.origin;
}

function closeViewMenus() {
  const style = document.getElementById("style-menu");
  const visibility = document.getElementById("visibility-menu");
  const open = (style && !style.hidden) || (visibility && !visibility.hidden);
  if (style) style.hidden = true;
  if (visibility) visibility.hidden = true;
  return open;
}

function syncStyleMenu() {
  const menu = document.getElementById("style-menu");
  if (!menu) return;
  for (const button of menu.querySelectorAll("[data-style]")) {
    button.classList.toggle("on", button.dataset.style === displayState.style);
  }
}

function syncVisibilityMenu() {
  const menu = document.getElementById("visibility-menu");
  if (!menu) return;
  for (const input of menu.querySelectorAll("[data-vis]")) {
    input.checked = !!displayState[input.dataset.vis];
  }
}

function setDisplay(patch) {
  displayState = { ...displayState, ...patch };
  if ("origin" in patch) originShown = !!patch.origin;
  writeDisplay(localStore, displayState);
  if ("origin" in patch) rebuildOrigin();
  applyDisplay();
  syncStyleMenu();
  syncVisibilityMenu();
  if ("origin" in patch && lastTree) renderTree(lastTree);
}

{
  const styleButton = document.getElementById("btn-style");
  const styleMenu = document.getElementById("style-menu");
  const visibilityButton = document.getElementById("btn-visibility");
  const visibilityMenu = document.getElementById("visibility-menu");
  styleButton?.addEventListener("click", (event) => {
    event.stopPropagation();
    const open = styleMenu.hidden;
    closeViewMenus();
    styleMenu.hidden = !open;
    syncStyleMenu();
  });
  visibilityButton?.addEventListener("click", (event) => {
    event.stopPropagation();
    const open = visibilityMenu.hidden;
    closeViewMenus();
    visibilityMenu.hidden = !open;
    syncVisibilityMenu();
  });
  styleMenu?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-style]");
    if (!button) return;
    setDisplay({ style: button.dataset.style });
    closeViewMenus();
  });
  visibilityMenu?.addEventListener("change", (event) => {
    const input = event.target.closest("[data-vis]");
    if (!input) return;
    const key = input.dataset.vis;
    if (key === "origin") setOriginShown(input.checked);
    else setDisplay({ [key]: input.checked });
  });
  visibilityMenu?.addEventListener("click", (event) => event.stopPropagation());
  document.addEventListener("click", () => closeViewMenus());
  syncStyleMenu();
  syncVisibilityMenu();
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
    ghostMesh.removeFromParent();
    ghostMesh.geometry.dispose();
    ghostMesh = null;
  }
  baseMaterial.opacity = 1;
  if (partBaseMaterial) partBaseMaterial.opacity = 1;
}

function showGhost(mesh) {
  if (ghostMesh) {
    ghostMesh.removeFromParent();
    ghostMesh.geometry.dispose();
    ghostMesh = null;
  }
  if (!mesh.indices.length) return;
  const geometry = new THREE.BufferGeometry();
  applyPackedGeometry(geometry, mesh);
  ghostMesh = new THREE.Mesh(geometry, ghostMaterial);
  volumesGroup.add(ghostMesh);
  applyVolumeVisibility();
  baseMaterial.opacity = 0.15; // la pièce s'efface derrière le résultat
  if (partBaseMaterial) partBaseMaterial.opacity = 0.15;
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

function linePickThreshold() {
  return ORTHO_HEIGHT / (camera.zoom * Math.max(viewSize().height, 1)) * 8;
}

function pickHoveredSketch() {
  if (!sketchLineMeshes.length) return null;
  raycaster.params.Line.threshold = linePickThreshold();
  const hit = raycaster.intersectObjects(sketchLineMeshes, false)[0];
  return hit?.object.userData.sketch ?? null;
}

function pickHoveredSurfaceHit() {
  if (!surfaceMeshes.length) return null;
  return raycaster.intersectObjects(surfaceMeshes, false)[0] ?? null;
}

function repaintSurfaces() {
  for (const mesh of surfaceMeshes) {
    const name = mesh.userData.surface?.name;
    if (selectedSurface?.name === name) {
      mesh.material = surfaceSelectedMaterial;
    } else if (hoveredSurface?.name === name) {
      mesh.material = surfaceHoverMaterial;
    } else {
      mesh.material = mesh.userData.baseMaterial;
    }
  }
}

// Face hover: triangle index -> group -> engine faceId. By construction.
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
let hoveredGroup = -1;

function setPointerFromEvent(event) {
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
}

function pointerCtx() {
  raycaster.setFromCamera(pointer, camera);
  return {
    raycaster, pointer, partMesh, scene, camera, controls, meshGroups,
    get faceHit() {
      return partMesh ? raycaster.intersectObject(partMesh)[0] : undefined;
    },
  };
}

function pluginSeesPointer() {
  return !assemblyState && !planePicking && !measuring;
}

renderer.domElement.addEventListener("pointermove", (event) => {
  if (sketchMode.active) return;
  if (boxStart && isDrag(boxStart, { x: event.clientX, y: event.clientY })) {
    boxOverlay.show(boxStart, { x: event.clientX, y: event.clientY });
  }
  setPointerFromEvent(event);
  if (pluginSeesPointer()
      && pluginRuntime?.dispatchPointer("move", event, pointerCtx())) {
    return;
  }
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
  if (!partMesh && !sketchLineMeshes.length && !surfaceMeshes.length) return;
  raycaster.setFromCamera(pointer, camera);

  // L'esquisse libre gagne sur la face (et l'arête) derrière elle :
  // le geste vise le profil, pas le solide. Priorité en pixels, inchangée.
  const sketchHit = pickHoveredSketch();

  let edgeGroupIndex = -1;
  let groupIndex = -1;
  let surfaceHit = null;
  if (!sketchHit) {
    const faceHit = partMesh
      ? raycaster.intersectObject(partMesh)[0] : undefined;
    let edgeHit;
    if (partMesh && partEdges) {
      const { radius } = partCenterRadius();
      raycaster.params.Line.threshold = linePickThreshold();
      edgeHit = raycaster.intersectObject(partEdges)[0];
      if (edgeHit && (!faceHit
          || edgeHit.distance <= faceHit.distance + radius * 0.02)) {
        edgeGroupIndex = edgeGroups.findIndex(
          (g) => edgeHit.index >= g.start
              && edgeHit.index < g.start + g.count);
      }
    }
    if (edgeGroupIndex < 0 && faceHit) {
      const indexPosition = faceHit.faceIndex * 3;
      groupIndex = meshGroups.findIndex(
        (g) => indexPosition >= g.start && indexPosition < g.start + g.count);
    }
    const surfHit = pickHoveredSurfaceHit();
    if (surfHit) {
      const solidHit = edgeGroupIndex >= 0 ? edgeHit : faceHit;
      if (!solidHit || surfHit.distance < solidHit.distance) {
        surfaceHit = surfHit.object.userData.surface;
        groupIndex = -1;
        edgeGroupIndex = -1;
      }
    }
  }
  const surfaceName = surfaceHit?.name ?? null;
  if (groupIndex !== hoveredGroup || edgeGroupIndex !== hoveredEdgeGroup
      || sketchHit?.name !== hoveredSketch?.name
      || surfaceName !== hoveredSurface?.name) {
    hoveredGroup = groupIndex;
    hoveredEdgeGroup = edgeGroupIndex;
    hoveredSketch = sketchHit;
    hoveredSurface = surfaceHit;
    renderer.domElement.style.cursor =
      groupIndex >= 0 || edgeGroupIndex >= 0 || sketchHit || surfaceHit
        ? "pointer" : "";
    repaintGroups();
    repaintEdges();
    repaintSurfaces();
  }
});

function repaintGroups() {
  if (partMesh) {
    partMesh.geometry.groups.forEach((g, i) => {
      const isSelected = meshGroups[i].faceId === selectedFaceId;
      g.materialIndex = isSelected ? 2 : (i === hoveredGroup ? 1 : 0);
    });
  }
  const parts = [];
  if (hoveredSketch) {
    parts.push(hoveredSketch.label);
  } else if (hoveredSurface) {
    parts.push(hoveredSurface.label);
  } else if (hoveredEdgeGroup >= 0) {
    parts.push(t("Arête {n}", { n: edgeGroups[hoveredEdgeGroup].edgeId }));
  } else if (hoveredGroup >= 0) {
    parts.push(t("Face {n}", { n: meshGroups[hoveredGroup].faceId }));
  }
  if (selectedEdges.size) {
    parts.push(t("sél. {n} arête(s) — Ctrl+clic : ajouter",
      { n: selectedEdges.size }));
  } else if (selectedFaceId !== null) {
    parts.push(t("sél. Face {n}", { n: selectedFaceId }));
  } else if (selectedSurface) {
    parts.push(t("sél. {s}", { s: selectedSurface.label }));
  }
  pickEl.textContent = parts.join(" · ");
}

// Click selects the hovered face (sticky); click in the void deselects.
// Guarded against orbit drags: a press that travels is navigation, not a pick.
let pressPosition = null;
let boxStart = null; // appui gauche dans le vide : peut devenir un cadre

/** Arêtes du corps actif retenues par le cadre (fenêtre ou capture). */
function selectEdgesInBox(start, end, additive) {
  if (!partEdges) return;
  const rect = normalizeRect(start, end);
  const host = renderer.domElement.getBoundingClientRect();
  const pos = partEdges.geometry.getAttribute("position");
  const index = partEdges.geometry.getIndex();
  const v = new THREE.Vector3();
  const items = edgeGroups.map((g) => {
    const points = [];
    for (let k = g.start; k < g.start + g.count; k++) {
      v.fromBufferAttribute(pos, index.getX(k)).project(camera);
      points.push({
        x: (v.x * 0.5 + 0.5) * host.width + host.left,
        y: (-v.y * 0.5 + 0.5) * host.height + host.top,
      });
    }
    return { id: g.edgeId, points };
  });
  const ids = pickInBox(items, rect, boxMode(start, end));
  selectedEdges = additive ? new Set([...selectedEdges, ...ids]) : new Set(ids);
  selectedFaceId = null;
  cancelPendingSurfaceClick();
  clearSketchSelection({ quiet: true });
  clearSurfaceSelection({ quiet: true });
  repaintGroups();
  repaintEdges();
  if (lastTree) renderTree(lastTree);
  panel.notifyPick("edges", { kind: "edges", edges: [...selectedEdges] });
}

renderer.domElement.addEventListener("pointerdown", (event) => {
  if (sketchMode.active) return;
  pressPosition = { x: event.clientX, y: event.clientY };
  const nothingHovered = hoveredGroup < 0 && hoveredEdgeGroup < 0
    && !hoveredSketch && !hoveredSurface;
  boxStart = event.button === 0 && nothingHovered && !assemblyState
    && !planePicking && !measuring && partEdges
    ? { x: event.clientX, y: event.clientY } : null;
  if (!pluginSeesPointer()) return;
  setPointerFromEvent(event);
  pluginRuntime?.dispatchPointer("down", event, pointerCtx());
});
renderer.domElement.addEventListener("pointerup", (event) => {
  if (sketchMode.active) return;
  if (pluginSeesPointer()) {
    setPointerFromEvent(event);
    if (pluginRuntime?.dispatchPointer("up", event, pointerCtx())) {
      pressPosition = null;
      return;
    }
  }
  const box = boxStart;
  boxStart = null;
  boxOverlay.hide();
  if (box && isDrag(box, { x: event.clientX, y: event.clientY })) {
    pressPosition = null;
    selectEdgesInBox(box, { x: event.clientX, y: event.clientY },
      event.ctrlKey || event.metaKey);
    return;
  }
  if (!pressPosition) return;
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
    const label = (p) => (p.kind === "edge"
      ? t("arête {n}", { n: p.id }) : t("face {n}", { n: p.id }));
    if (!measureFirst) {
      measureFirst = pick;
      say(t("Mesurer : {a} — cliquez le second élément", { a: label(pick) }));
    } else {
      const first = measureFirst;
      measuring = false;
      measureFirst = null;
      call("measure", { a_kind: first.kind, a_id: first.id,
                        b_kind: pick.kind, b_id: pick.id })
        .then((r) => say(t("Distance {a} ↔ {b} : {d} mm",
          { a: label(first), b: label(pick), d: r.distance.toFixed(3) })))
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

  if (hoveredSketch) {
    selectedFaceId = null;
    selectedEdges = new Set();
    clearPlaneChoice();
    cancelPendingSurfaceClick();
    clearSurfaceSelection({ quiet: true });
    repaintGroups();
    repaintEdges();
    selectSketch(hoveredSketch);
    if (event.button === 0) showContextToolbar(event);
    return;
  }

  if (hoveredSurface) {
    selectedFaceId = null;
    selectedEdges = new Set();
    clearPlaneChoice();
    clearSketchSelection({ quiet: true });
    repaintGroups();
    repaintEdges();
    onSurfaceClick(hoveredSurface);
    return;
  }

  if (hoveredEdgeGroup >= 0) {
    const id = edgeGroups[hoveredEdgeGroup].edgeId;
    if (event.ctrlKey || event.metaKey) {
      if (!selectedEdges.delete(id)) selectedEdges.add(id);
    } else {
      selectedEdges = new Set([id]);
    }
    selectedFaceId = null;
    clearPlaneChoice();
    cancelPendingSurfaceClick();
    clearSketchSelection({ quiet: true });
    clearSurfaceSelection({ quiet: true });
    if (lastTree) renderTree(lastTree);
    repaintGroups();
    repaintEdges();
    panel.notifyPick("edges",
      { kind: "edges", edges: [...selectedEdges] });
    if (event.button === 0) showContextToolbar(event);
    return;
  }

  selectedFaceId = hoveredGroup >= 0 ? meshGroups[hoveredGroup].faceId : null;
  selectedEdges = new Set(); // une face (ou le vide) remplace les arêtes
  cancelPendingSurfaceClick();
  clearSketchSelection({ quiet: true });
  clearSurfaceSelection({ quiet: true });
  repaintEdges();
  repaintGroups();
  if (selectedFaceId !== null) {
    clearPlaneChoice();
    raycaster.setFromCamera(pointer, camera);
    const faceHit = partMesh
      ? raycaster.intersectObject(partMesh)[0] : null;
    if (faceHit) {
      // La normale sert à « Normal à » (Ctrl+8).
      const normal = faceHit.face
        ? faceHit.face.normal.clone()
          .transformDirection(faceHit.object.matrixWorld)
        : null;
      lastFaceHit = {
        face: selectedFaceId,
        x: faceHit.point.x, y: faceHit.point.y, z: faceHit.point.z,
        normal: normal ? [normal.x, normal.y, normal.z] : null,
      };
    }
    // A command panel with a selection box absorbs the pick.
    panel.notifyPick("face", { kind: "face", face: selectedFaceId });
    if (event.button === 0) showContextToolbar(event);
  } else {
    lastFaceHit = null;
    clearPlaneChoice();
    clearFeatureDims();
    pluginRuntime?.runPointerIdle(pointerCtx());
  }
  if (lastTree) renderTree(lastTree);
});

function findFeatureInTree(tree, name) {
  if (!name || !tree) return null;
  for (const feature of tree.features ?? []) {
    if (feature.name === name) return feature;
    for (const child of feature.children ?? []) {
      if (child.name === name) return child;
    }
  }
  for (const surface of tree.surfaces ?? []) {
    if (surface.name === name) return surface;
  }
  return null;
}

function disposeFeatureDimSprites() {
  for (const sprite of featureDimSprites) {
    sprite.material?.map?.dispose();
    sprite.material?.dispose();
  }
  featureDimsGroup.clear();
  featureDimSprites = [];
}

function clearFeatureDims() {
  disposeFeatureDimSprites();
  featureDimContext = null;
  if (selectedFeatureName) {
    selectedFeatureName = null;
    if (lastTree) renderTree(lastTree);
  }
}

function sketchWorldPoint(placement, x, y) {
  const matrix = new THREE.Matrix4().set(...placement);
  return new THREE.Vector3(x, y, 0).applyMatrix4(matrix);
}

function featureParamWorldPos(param, feature, hit, sketchState) {
  if (sketchState?.placement
      && (param.prop === "Length" || param.prop === "LengthFwd")) {
    const matrix = new THREE.Matrix4().set(...sketchState.placement);
    const origin = new THREE.Vector3().setFromMatrixPosition(matrix);
    const normal = new THREE.Vector3(0, 0, 1).transformDirection(matrix);
    return origin.add(normal.normalize().multiplyScalar(param.value / 2));
  }
  if (hit) return hit.clone().add(new THREE.Vector3(0, 0, 3));
  return new THREE.Vector3(0, 0, 8);
}

async function showFeatureDims(featureName, hit) {
  if (!featureName) {
    const match = lastFaceMatch;
    const detail = match && match.faces
      ? " " + t("({m}/{n} face(s) appariée(s) à une fonction)",
        { m: match.matched, n: match.faces })
      : "";
    say(t("cette face n'a pas de fonction associée") + detail, true);
    clearFeatureDims();
    return;
  }
  const feature = findFeatureInTree(lastTree, featureName);
  if (!feature) {
    say("cette face n'appartient à aucune fonction éditable");
    clearFeatureDims();
    return;
  }
  selectedFeatureName = feature.name;
  featureDimContext = {
    feature: feature.name,
    hit: hit ? hit.clone() : null,
  };
  disposeFeatureDimSprites();
  const sketches = (feature.children ?? []).filter(
    (child) => child.type === "Sketcher::SketchObject");
  if (feature.type === "Sketcher::SketchObject") sketches.push(feature);
  const params = feature.params?.length
    ? feature.params
    : ((await call("get_params", { feature: feature.name })).params ?? []);
  let firstSketchState = null;
  for (const sketch of sketches) {
    let state;
    try {
      state = await call("sketch_state", { sketch: sketch.name });
    } catch (error) {
      say(error.message, true);
      continue;
    }
    if (!firstSketchState) firstSketchState = state;
    for (const dim of state.dims ?? []) {
      const anchor = sketchDimAnchor(dim, state.entities);
      if (!anchor) continue;
      const world = sketchWorldPoint(state.placement, anchor.x, anchor.y);
      const sprite = createDimSprite(dimLabel(dim), world.x, world.y, world.z);
      sprite.userData.dim = { ...dim, kind: "sketch", sketch: sketch.name };
      sprite.renderOrder = 24;
      featureDimsGroup.add(sprite);
      featureDimSprites.push(sprite);
    }
  }
  for (const param of params) {
    const [label, unit] = PROP_LABELS[param.prop] ?? [param.prop, "mm"];
    const dim = {
      kind: "param",
      name: label,
      value: param.value,
      expr: param.expr || "",
      unit,
      feature: feature.name,
      prop: param.prop,
      type: param.prop === "Angle" ? "Angle" : "Distance",
    };
    const world = featureParamWorldPos(
      param, feature, hit, firstSketchState);
    const sprite = createDimSprite(dimLabel({
      ...dim,
      type: dim.unit === "°" ? "Angle" : dim.type,
      value: dim.unit === "°" ? dim.value * Math.PI / 180 : dim.value,
    }), world.x, world.y, world.z);
    sprite.userData.dim = dim;
    sprite.renderOrder = 24;
    featureDimsGroup.add(sprite);
    featureDimSprites.push(sprite);
  }
  if (!featureDimSprites.length) {
    say(t("{f} : aucune cote à afficher", { f: feature.label }));
    return;
  }
  if (lastTree) renderTree(lastTree);
  say(t("{f} : {n} cote(s) — double-clic une cote pour la changer",
    { f: feature.label, n: featureDimSprites.length }));
}

function pickFeatureDim(event) {
  if (!featureDimSprites.length) return false;
  const rect = renderer.domElement.getBoundingClientRect();
  for (const sprite of featureDimSprites) {
    const projected = sprite.position.clone().project(camera);
    const sx = (projected.x * 0.5 + 0.5) * rect.width + rect.left;
    const sy = (-projected.y * 0.5 + 0.5) * rect.height + rect.top;
    if (Math.hypot(sx - event.clientX, sy - event.clientY) < 22) {
      editFeatureDim(sprite.userData.dim);
      return true;
    }
  }
  return false;
}

function editFeatureDim(dim) {
  if (!dim) return;
  openDimEditor({
    panel,
    dim,
    onApply: (values, meta) => {
      const extra = dimEditPayload(values, dim, meta);
      if (dim.kind === "sketch") {
        if (extra.name === undefined && extra.value === undefined
            && extra.expr === undefined) return;
        refreshFeatureDimEdit(call("sketch_set_dim", {
          sketch: dim.sketch, dim: dim.id, ...extra,
        }).then(() => call("get_tree")));
        return;
      }
      if (extra.value === undefined && extra.expr === undefined) return;
      const raw = extra.expr ?? extra.value;
      refreshFeatureDimEdit(call("set_params", {
        feature: dim.feature,
        values: { [dim.prop]: raw },
      }));
    },
  });
}

function refreshFeatureDimEdit(treePromise) {
  const ctx = featureDimContext;
  refresh(treePromise).then(() => {
    if (ctx) return showFeatureDims(ctx.feature, ctx.hit);
  });
}

renderer.domElement.addEventListener("dblclick", (event) => {
  if (sketchMode.active || assemblyState || planePicking || measuring) return;
  if (hoveredSurface) {
    onSurfaceDblClick(hoveredSurface);
    return;
  }
  if (pickFeatureDim(event)) return;
  if (hoveredGroup < 0) {
    clearFeatureDims();
    return;
  }
  const group = meshGroups[hoveredGroup];
  const hit = lastFaceHit && lastFaceHit.face === group.faceId
    ? new THREE.Vector3(lastFaceHit.x, lastFaceHit.y, lastFaceHit.z)
    : null;
  showFeatureDims(group.feature, hit);
});

/** Frustum orthographique pour un rapport largeur / hauteur. */
function setOrthoFrustum(cam, width, height) {
  const aspect = height > 0 ? width / height : 1;
  cam.left = -ORTHO_HEIGHT * aspect / 2;
  cam.right = ORTHO_HEIGHT * aspect / 2;
  cam.top = ORTHO_HEIGHT / 2;
  cam.bottom = -ORTHO_HEIGHT / 2;
  cam.updateProjectionMatrix();
}

/** Canvas dans une fenêtre (rectangle en pixels), ou plein cadre. */
function placeCanvas(canvas, rect) {
  canvas.classList.toggle("fs-pane", !!rect);
  for (const key of ["left", "top", "width", "height"]) {
    canvas.style[key] = rect ? `${rect[key]}px` : "";
  }
}

function resize() {
  const { width: w, height: h } = viewSize();
  const multi = panes.length > 1;
  // updateStyle=false : le CSS (100 %) fait suivre le canvas à sa cellule,
  // setSize ne règle que le tampon de rendu.
  renderer.setSize(w, h, false);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  placeCanvas(renderer.domElement, multi
    ? paneRect(panes[activePane], container.clientWidth, container.clientHeight)
    : null);
  renderer.domElement.classList.toggle("active", multi);
  setOrthoFrustum(camera, w, h);
  const others = panes.map((_, i) => i).filter((i) => i !== activePane);
  while (extraViews.length < others.length) extraViews.push(createExtraView());
  extraViews.forEach((view, k) => {
    view.pane = others[k] ?? -1;
    view.renderer.domElement.hidden = view.pane < 0;
    if (view.pane < 0) return;
    const rect = paneRect(panes[view.pane], container.clientWidth,
                          container.clientHeight);
    view.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    view.renderer.setSize(rect.width, rect.height, false);
    placeCanvas(view.renderer.domElement, rect);
  });
}
new ResizeObserver(resize).observe(container);

/** Canvas secondaire : il dessine une fenêtre inactive ; un appui dessus
 *  l'active. */
function createExtraView() {
  const view = { renderer: new THREE.WebGLRenderer({ antialias: true }),
                 pane: -1 };
  renderer.domElement.after(view.renderer.domElement);
  view.renderer.domElement.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    activatePane(view.pane);
  });
  // La molette aussi : les crans suivants zooment la fenêtre activée.
  view.renderer.domElement.addEventListener("wheel",
    () => activatePane(view.pane), { passive: true });
  return view;
}

function cameraState() {
  return { position: camera.position.clone(), up: camera.up.clone(),
           zoom: camera.zoom, target: controls.target.clone() };
}

function applyCameraState(state) {
  camera.up.copy(state.up);
  camera.position.copy(state.position);
  camera.zoom = state.zoom;
  controls.target.copy(state.target);
  camera.lookAt(state.target);
  camera.updateProjectionMatrix();
}

function activatePane(index) {
  if (index < 0 || index === activePane || index >= panes.length) return;
  if (sketchMode.active) {
    say("En esquisse, la fenêtre active reste celle de l'esquisse.");
    return;
  }
  hideContextToolbar();
  panes[activePane].state = cameraState();
  activePane = index;
  applyCameraState(panes[index].state);
  resize();
}

/** Une, deux ou quatre fenêtres. La vue en cours garde sa fenêtre ; les
 *  autres partent d'une vue standard cadrée sur la pièce. */
function setLayout(name) {
  if (sketchMode.active) {
    say("Terminez l'esquisse avant de changer de disposition.");
    return;
  }
  const current = cameraState();
  panes = layoutPanes(name);
  for (const [index, pane] of panes.entries()) {
    if (pane.view === "current" || !VIEWS[pane.view]) {
      pane.state = current;
      continue;
    }
    activePane = index;   // le cadrage se règle sur cette fenêtre
    frameView(VIEWS[pane.view].direction, VIEWS[pane.view].up);
    pane.state = cameraState();
  }
  activePane = currentPaneIndex(panes);
  applyCameraState(current);
  resize();
}

function renderExtraViews() {
  for (const view of extraViews) {
    const state = panes[view.pane]?.state;
    if (view.pane < 0 || !state) continue;
    const { width, height } = paneRect(panes[view.pane],
      container.clientWidth, container.clientHeight);
    setOrthoFrustum(paneCamera, width, height);
    paneCamera.up.copy(state.up);
    paneCamera.position.copy(state.position);
    paneCamera.zoom = state.zoom;
    paneCamera.lookAt(state.target);
    paneCamera.updateProjectionMatrix();
    view.renderer.render(scene, paneCamera);
  }
}

renderer.setAnimationLoop(() => {
  controls.update();
  if (explodeFactor !== explodeTarget) {
    const step = 0.06;
    explodeFactor += Math.sign(explodeTarget - explodeFactor)
      * Math.min(step, Math.abs(explodeTarget - explodeFactor));
    applyExplode();
  }
  renderer.render(scene, camera);
  renderExtraViews();
});

// ---------- vues standard (Ctrl+1 à Ctrl+8, F) ----------

function partCenterRadius() {
  if (!partMesh || !partMesh.geometry.boundingSphere)
    return { center: new THREE.Vector3(0, 0, 20), radius: 90 };
  const sphere = partMesh.geometry.boundingSphere;
  return { center: sphere.center.clone(), radius: Math.max(sphere.radius, 1) };
}

function fitOrthoZoom(radius) {
  const w = viewSize().width || 1;
  const h = viewSize().height || 1;
  const aspect = w / h;
  const needed = 2 * Math.max(radius, 1) * 1.25;
  camera.zoom = Math.min(ORTHO_HEIGHT * aspect, ORTHO_HEIGHT) / needed;
  camera.updateProjectionMatrix();
}

// direction = d'où l'on regarde ; null = garder l'angle actuel (zoom au mieux).
function frameView(direction, up) {
  const { center, radius } = partCenterRadius();
  if (up) camera.up.set(...up);
  const dir = direction
    ? new THREE.Vector3(...direction).normalize()
    : camera.position.clone().sub(controls.target).normalize();
  if (dir.lengthSq() < 1e-12) dir.set(1, -1, 1).normalize();
  // Distance : near/far et orbite uniquement — la taille vient du zoom.
  const distance = Math.max(radius * 2.5, 80);
  controls.target.copy(center);
  camera.position.copy(center).addScaledVector(dir, distance);
  camera.lookAt(center);
  fitOrthoZoom(radius);
}

// Vue de face = normale au Plan de face (XZ), etc. — mêmes plans que le vocab.
const VIEWS = {
  "view-iso":    { direction: [1, -1, 1], up: [0, 0, 1] },
  // Dimétrique : deux axes raccourcis pareil ; trimétrique : trois différents.
  "view-dimetric":  { direction: [1, -1, 0.55], up: [0, 0, 1] },
  "view-trimetric": { direction: [1, -0.62, 0.5], up: [0, 0, 1] },
  "view-front":  { direction: [0, -1, 0], up: [0, 0, 1] },
  "view-back":   { direction: [0, 1, 0],  up: [0, 0, 1] },
  "view-left":   { direction: [-1, 0, 0], up: [0, 0, 1] },
  "view-right":  { direction: [1, 0, 0],  up: [0, 0, 1] },
  "view-top":    { direction: [0, 0, 1],  up: [0, 1, 0] },
  // Vue de dessous : l'avant de la pièce passe en haut de l'écran.
  "view-bottom": { direction: [0, 0, -1], up: [0, -1, 0] },
  "view-fit":    { direction: null,       up: null },
};
for (const [id, view] of Object.entries(VIEWS)) {
  document.getElementById(id)?.addEventListener("click", () => {
    if (sketchMode.active) return; // en esquisse, la caméra suit le plan
    frameView(view.direction, view.up);
  });
}

// Normale des plans d'origine, côté d'où on les regarde (même sens que
// les vues Face / Dessus / Droite).
const PLANE_VIEW_NORMALS = { XY: [0, 0, 1], XZ: [0, -1, 0], YZ: [1, 0, 0] };

/** « Normal à » : la face ou le plan sélectionné face à l'écran. Un second
 *  appui, alors qu'on regarde déjà dans cet axe, passe de l'autre côté. */
function viewNormalTo() {
  let normal = null;
  if (selectedFaceId !== null && lastFaceHit?.face === selectedFaceId
      && lastFaceHit.normal) {
    normal = new THREE.Vector3(...lastFaceHit.normal);
  } else if (selectedPlane !== null && PLANE_VIEW_NORMALS[selectedPlane]) {
    normal = new THREE.Vector3(...PLANE_VIEW_NORMALS[selectedPlane]);
  }
  if (!normal || normal.lengthSq() < 1e-12) {
    say("Normal à : sélectionnez d'abord une face plane ou un plan.");
    return;
  }
  normal.normalize();
  const looking = camera.position.clone().sub(controls.target).normalize();
  if (looking.dot(normal) > 0.999) normal.negate();
  // Haut de l'écran : Z, sauf si on regarde le long de Z.
  const up = Math.abs(normal.z) > 0.9 ? [0, 1, 0] : [0, 0, 1];
  frameView([normal.x, normal.y, normal.z], up);
}

const VIEW_KEYS = {
  1: "view-front", 2: "view-back", 3: "view-left", 4: "view-right",
  5: "view-top", 6: "view-bottom", 7: "view-iso",
};

// ---------- boîte d'orientation (barre d'espace) ----------
// Les vues standard dépliées en croix autour de la face, plus iso,
// dimétrique, trimétrique et « Normal à ». Elle s'ouvre sous le curseur ;
// l'épingle la garde ouverte après un choix.

const orientBox = document.getElementById("orient-box");
let orientPinned = false;
let lastViewportPointer = null;

container.addEventListener("pointermove", (event) => {
  lastViewportPointer = { x: event.clientX, y: event.clientY };
});

function openOrientBox() {
  if (!orientBox) return;
  const host = container.getBoundingClientRect();
  const at = lastViewportPointer ?? {
    x: host.left + host.width / 2, y: host.top + host.height / 2 };
  orientBox.hidden = false;
  const box = orientBox.getBoundingClientRect();
  const left = Math.min(Math.max(at.x - host.left - box.width / 2, 4),
    host.width - box.width - 4);
  const top = Math.min(Math.max(at.y - host.top - box.height / 2, 4),
    host.height - box.height - 4);
  orientBox.style.left = `${left}px`;
  orientBox.style.top = `${top}px`;
}

function closeOrientBox() {
  if (orientBox) orientBox.hidden = true;
}

orientBox?.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  const view = button.dataset.view;
  if (button.dataset.action === "pin") {
    orientPinned = !orientPinned;
    button.classList.toggle("on", orientPinned);
    return;
  }
  if (button.dataset.action === "close") {
    closeOrientBox();
    return;
  }
  if (button.dataset.layout) setLayout(button.dataset.layout);
  else if (view === "normal") viewNormalTo();
  else if (VIEWS[view]) frameView(VIEWS[view].direction, VIEWS[view].up);
  if (!orientPinned) closeOrientBox();
});
document.addEventListener("keydown", (event) => {
  if (sketchMode.active) return;
  // Typing in a panel field must not trigger view shortcuts (F, Ctrl+1…).
  if (/^(INPUT|SELECT|TEXTAREA)$/.test(event.target.tagName)) return;
  if (event.key !== "Escape" && pluginRuntime?.dispatchKey(event)) return;
  if (event.key === " " && !event.ctrlKey && !event.metaKey && !event.altKey) {
    event.preventDefault();
    if (orientBox?.hidden === false) closeOrientBox();
    else openOrientBox();
    return;
  }
  if (event.key === "Escape" && orientBox?.hidden === false) {
    closeOrientBox();
    return;
  }
  if (event.key === "Escape" && closeViewMenus()) return;
  if ((event.key === "f" || event.key === "F")
      && !event.ctrlKey && !event.metaKey && !event.altKey) {
    frameView(null, null);
  } else if ((event.key === "z" || event.key === "Z")
             && !event.ctrlKey && !event.metaKey && !event.altKey) {
    // Z : zoom arrière, Maj+Z : zoom avant, autour du centre de la vue.
    camera.zoom *= event.shiftKey ? 1.25 : 0.8;
    camera.updateProjectionMatrix();
  } else if ((event.ctrlKey || event.metaKey) && event.key === "8") {
    event.preventDefault();
    viewNormalTo();
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
  } else if (event.key === "Escape"
      && !document.getElementById("script-trust")?.hidden) {
    event.preventDefault();
    document.getElementById("script-trust-deny")?.click();
  } else if (event.key === "Escape" && graphFn.active) {
    event.preventDefault();
    if (literalEditEl.style.display === "block") closeLiteralEditor();
    else if (graphPalette.style.display === "block") closeGraphPalette();
    else if (graphWiring) cancelGraphWire();
    else exitGraphFeature();
  } else if (event.key === "Escape" && graphOpen) {
    event.preventDefault();
    if (graphPalette.style.display === "block") closeGraphPalette();
    else if (paramPickEl.style.display === "block") closeParamPicker();
    else if (graphWiring) cancelGraphWire();
    else closeGraph();
  } else if (pluginRuntime?.dispatchKey(event)) {
    return;
  } else if (graphOpen && (event.key === "Delete" || event.key === "Suppr")) {
    event.preventDefault();
    if (graphPalette.style.display === "block") return;
    if (graphFn.active) deleteGraphFnSelection();
    else if (graphSelectedEdge) unlinkParamEdge(graphSelectedEdge);
    else deleteSelectedGraphNode();
  }
});

installMenuBar(document, menuBarModel(RIBBON_LAYOUT), {
  onAction(name) {
    if (name === "delete") {
      const feature = findFeatureInTree(lastTree, selectedFeatureName);
      if (!feature) {
        say("Sélectionnez une fonction à supprimer.");
        return;
      }
      deleteFeatureWithConfirm(feature);
    } else if (name === "orient") {
      openOrientBox();
    } else if (name === "origin") {
      toggleOrigin();
    } else if (name === "report") {
      window.open(ISSUES_URL, "_blank", "noopener");
    }
  },
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
  "PartDesign::Boolean": "PartDesign_Boolean.svg",
  "PartDesign::Body": "PartDesign_Body.svg",
  "Part::Extrusion": "Part_3D_object.svg",
  "Part::Revolution": "Part_3D_object.svg",
  "Part::Loft": "Part_3D_object.svg",
  "Part::Feature": "Part_3D_object.svg",
  "Part::Offset": "Part_3D_object.svg",
  "App::Link": "LinkArray.svg",
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
  cancelPendingSurfaceClick();
  clearSketchSelection({ quiet: true });
  clearSurfaceSelection({ quiet: true });
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
    ? t("{f} choisi — cliquez Esquisse pour dessiner dessus",
      { f: feature.label })
    : "Plan de référence désélectionné");
}

function treeIcon(file) {
  const img = document.createElement("img");
  img.src = "icons/" + file;
  img.alt = "";
  return img;
}

function graphIconFile(node) {
  if (node?.icon) return node.icon;
  if (node?.spec?.icon) return node.spec.icon;
  if (node?.role === "compute" || node?.role === "shape") {
    if (node.type === "cylindre") return "nodes_cylinder.svg";
    if (node.type === "boite") return "nodes_box.svg";
    if (node.type === "serie") return "nodes_number_range.svg";
    if (node.type === "variable") return "VarSet.svg";
    if (node.type === "vecteur" || node.type === "point") return "nodes_vect.svg";
    return "nodes_wb_icon.svg";
  }
  if (node?.type && TREE_ICONS[node.type]) return TREE_ICONS[node.type];
  if (node?.role === "sketch") return TREE_ICONS["Sketcher::SketchObject"];
  if (node?.role === "datum") return TREE_ICONS["PartDesign::Plane"];
  if (node?.role === "plane") return "Std_Plane.svg";
  if (node?.role === "surface") return "Part_3D_object.svg";
  if (node?.role === "variable") return "VarSet.svg";
  if (node?.role === "body") return TREE_ICONS["PartDesign::Body"];
  return TREE_ICONS["PartDesign::Body"];
}

function svgGraphIcon(file, x, y) {
  return svgEl("image", {
    href: "icons/" + file,
    x, y, width: 16, height: 16,
  });
}

let lastTree = null;
const expandedFeatures = new Set(); // les fonctions dépliées (persiste)
const folderState = Object.create(null); // dossiers tête, mémoire de session
const folderPrevCounts = Object.create(null); // compteurs du rendu précédent
let sketchInfoOpen = false;
let sketchClickTimer = null;
let surfaceClickTimer = null;

/** Clic simple (éventuellement différé pour laisser passer le double-clic). */
function onSketchRowClick(feature) {
  clearTimeout(sketchClickTimer);
  sketchClickTimer = setTimeout(() => selectSketch(feature), 280);
}

function onSketchRowDblClick(feature) {
  clearTimeout(sketchClickTimer);
  sketchClickTimer = null;
  // Entrer en édition sans passer par le toggle de sélection.
  clearSketchSelection({ quiet: true });
  if (lastTree) renderTree(lastTree);
  editFeature(feature);
}

function clearSketchHighlight() {
  if (!sketchHighlightGroup) return;
  scene.remove(sketchHighlightGroup);
  disposeSubtree(sketchHighlightGroup);
  sketchHighlightGroup = null;
}

function drawSketchHighlight(state) {
  clearSketchHighlight();
  if (!state?.entities?.length) return;
  const group = new THREE.Group();
  group.renderOrder = 25;
  group.matrixAutoUpdate = false;
  group.matrix.set(...state.placement);
  for (const entity of state.entities) {
    let points = null;
    if (entity.type === "line") {
      points = [
        new THREE.Vector3(entity.p1[0], entity.p1[1], 0),
        new THREE.Vector3(entity.p2[0], entity.p2[1], 0)];
    } else if (entity.type === "circle") {
      points = [];
      for (let i = 0; i <= 48; i++) {
        const a = (i / 48) * Math.PI * 2;
        points.push(new THREE.Vector3(
          entity.c[0] + entity.r * Math.cos(a),
          entity.c[1] + entity.r * Math.sin(a), 0));
      }
    } else if (entity.type === "arc") {
      const { a1, a2 } = arcAngles(entity);
      points = [];
      for (let i = 0; i <= 32; i++) {
        const a = a1 + (i / 32) * (a2 - a1);
        points.push(new THREE.Vector3(
          entity.c[0] + entity.r * Math.cos(a),
          entity.c[1] + entity.r * Math.sin(a), 0));
      }
    } else if (entity.type === "poly" && entity.points?.length > 1) {
      points = entity.points.map((p) => new THREE.Vector3(p[0], p[1], 0));
    }
    if (!points) continue;
    const line = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(points),
      sketchHighlightMaterial);
    line.renderOrder = 25;
    group.add(line);
  }
  scene.add(group);
  sketchHighlightGroup = group;
}

function sketchConsumerLabel(tree, sketchName) {
  for (const feature of tree?.features ?? []) {
    for (const child of feature.children ?? []) {
      if (child.name === sketchName) return feature.label;
    }
  }
  return null;
}

function clearSketchSelection({ quiet = false } = {}) {
  const had = selectedSketch !== null || sketchHighlightGroup
    || sketchInfoOpen;
  selectedSketch = null;
  clearSketchHighlight();
  if (sketchInfoOpen) {
    sketchInfoOpen = false;
    if (panel.active) panel.close({ silent: true });
  }
  if (!had) return;
  if (!quiet && lastTree) renderTree(lastTree);
}

function cancelPendingSurfaceClick() {
  clearTimeout(surfaceClickTimer);
  surfaceClickTimer = null;
}

function surfaceRecord(ref) {
  const name = ref?.name;
  if (!name) return null;
  return (lastTree?.surfaces ?? []).find((s) => s.name === name) ?? ref;
}

function onSurfaceClick(surface) {
  clearTimeout(surfaceClickTimer);
  const target = { name: surface.name, label: surface.label };
  surfaceClickTimer = setTimeout(() => selectSurface(target), 280);
}

function onSurfaceDblClick(ref) {
  cancelPendingSurfaceClick();
  const surface = surfaceRecord(ref);
  if (!surface) return;
  clearSurfaceSelection({ quiet: true });
  if (lastTree) renderTree(lastTree);
  editSurface(surface);
}

function clearSurfaceSelection({ quiet = false } = {}) {
  const had = selectedSurface !== null;
  selectedSurface = null;
  repaintSurfaces();
  if (!had) return;
  if (!quiet && lastTree) renderTree(lastTree);
}

function selectSurface(surface) {
  const pick = { kind: "surface", name: surface.name, label: surface.label };
  if (panel.notifyPick("surface", pick)) return;
  if (selectedSurface?.name === surface.name) {
    clearSurfaceSelection();
    say("Surface désélectionnée");
    return;
  }
  selectedPlane = null;
  selectedDatumFeature = null;
  refreshDatumGhost(null);
  updatePlaneVisibility();
  selectedFaceId = null;
  selectedEdges = new Set();
  clearSketchSelection({ quiet: true });
  selectedSurface = { name: surface.name, label: surface.label };
  if (lastTree) renderTree(lastTree);
  repaintGroups();
  repaintEdges();
  repaintSurfaces();
  say(surface.label);
}

async function selectSketch(feature) {
  const pick = { kind: "sketch", name: feature.name, label: feature.label };
  if (panel.notifyPick("sketch", pick)) return; // loft/sweep absorbe
  if (selectedSketch?.name === feature.name) {
    clearSketchSelection();
    say("Esquisse désélectionnée");
    return;
  }
  // Autre sélection d'arbre : un seul focus à la fois.
  selectedPlane = null;
  selectedDatumFeature = null;
  refreshDatumGhost(null);
  updatePlaneVisibility();
  cancelPendingSurfaceClick();
  clearSurfaceSelection({ quiet: true });
  selectedSketch = { name: feature.name, label: feature.label };
  if (lastTree) renderTree(lastTree);
  try {
    const state = await call("sketch_state", { sketch: feature.name });
    if (selectedSketch?.name !== feature.name) return; // course
    drawSketchHighlight(state);
    openSketchInfoPanel(state, feature);
  } catch (error) {
    say(error.message, true);
    clearSketchSelection();
  }
}

function openSketchInfoPanel(state, feature) {
  const usedBy = sketchConsumerLabel(lastTree, feature.name);
  const nEnt = state.entities?.length ?? 0;
  const nCon = state.constraints?.length ?? 0;
  const dof = state.dof;
  const status = state.fullyConstrained
    ? t("totalement contrainte")
    : dof !== null && dof !== undefined
      ? t("{n} degré(s) de liberté", { n: dof })
      : t("état inconnu");
  sketchInfoOpen = true;
  panel.open({
    icon: "Sketcher_Sketch.svg",
    title: state.label || feature.label,
    noApply: true,
    groups: [{
      label: t("Propriétés"),
      rows: [
        { type: "note",
          text: t("Support : {s}", { s: state.support || "—" }) },
        { type: "note",
          text: t("Entités : {e} — Contraintes : {c}", { e: nEnt, c: nCon }) },
        { type: "note", text: t("État : {s}", { s: status }) },
        { type: "note",
          text: t("Utilisée par : {f}", { f: usedBy ?? t("libre") }) },
      ],
    }],
    actions: [{
      label: t("Modifier"),
      title: t("Modifier l'esquisse"),
      className: "paction",
      onClick: () => {
        sketchInfoOpen = false;
        const target = {
          type: "Sketcher::SketchObject",
          name: feature.name,
          label: feature.label,
        };
        selectedSketch = null;
        clearSketchHighlight();
        if (lastTree) renderTree(lastTree);
        editFeature(target);
      },
    }],
    onCancel: () => {
      // Fermer / Échap uniquement (open() remplace en silencieux).
      sketchInfoOpen = false;
      selectedSketch = null;
      clearSketchHighlight();
      if (lastTree) renderTree(lastTree);
    },
  });
}

function onPlaneRow(id) {
  if (planePicking) { pickPlane(id); return; }
  cancelPendingSurfaceClick();
  clearSketchSelection({ quiet: true });
  clearSurfaceSelection({ quiet: true });
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

function dropRolledBackSelection(tree) {
  let dropped = false;
  if (selectedSurface) {
    const surf = (tree.surfaces ?? []).find(
      (item) => item.name === selectedSurface.name);
    if (!surf || surf.rolled_back) {
      selectedSurface = null;
      dropped = true;
    }
  }
  if (selectedSketch) {
    const feat = (tree.features ?? []).find(
      (item) => item.name === selectedSketch.name);
    if (feat?.type === "Sketcher::SketchObject" && feat.rolled_back) {
      selectedSketch = null;
      clearSketchHighlight();
      dropped = true;
    }
  }
  if (dropped) {
    hoveredSurface = null;
    hoveredSketch = null;
    repaintGroups();
  }
}

function rememberFolderCount(key, count) {
  const prev = folderPrevCounts[key];
  if (typeof prev === "number" && count > prev) {
    folderState[key] = true;
  }
  folderPrevCounts[key] = count;
}

function folderIsOpen(key, defaultOpen) {
  return Object.prototype.hasOwnProperty.call(folderState, key)
    ? folderState[key]
    : defaultOpen;
}

function toggleFolder(key, defaultOpen) {
  folderState[key] = !folderIsOpen(key, defaultOpen);
  if (lastTree) renderTree(lastTree);
}

function appendFolder(key, label, count, icon, defaultOpen, extra = {}) {
  const open = folderIsOpen(key, defaultOpen);
  const item = document.createElement("li");
  item.className = "folder" + (count === 0 ? " empty" : "");
  item.dataset.folder = key;
  const arrow = document.createElement("span");
  arrow.className = "arrow";
  arrow.textContent = open ? "▾" : "▸";
  arrow.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleFolder(key, defaultOpen);
  });
  item.appendChild(arrow);
  item.appendChild(treeIcon(icon));
  item.appendChild(document.createTextNode(`${label} (${count})`));
  if (extra.title) item.title = extra.title;
  if (extra.clickToggles !== false) {
    item.addEventListener("click", () => toggleFolder(key, defaultOpen));
  }
  if (extra.onDblClick) {
    item.addEventListener("dblclick", (event) => {
      event.stopPropagation();
      extra.onDblClick();
    });
  }
  treeEl.appendChild(item);
  return open;
}

function appendBodyRow(bodyInfo) {
  const bodyItem = document.createElement("li");
  const empty = bodyInfo.has_solid !== true;
  bodyItem.className = "body in-folder"
    + (bodyInfo.active ? " active" : "")
    + (empty ? " empty" : "");
  bodyItem.appendChild(treeIcon("PartDesign_Body.svg"));
  if (hexColor(bodyInfo.color)) {
    const swatch = document.createElement("span");
    swatch.className = "swatch";
    swatch.style.background = bodyInfo.color;
    bodyItem.appendChild(swatch);
  }
  const suffix = empty
    ? " — " + t("vide")
    : (bodyInfo.active ? ""
      : " — " + t("{n} élément(s)", { n: bodyInfo.count }));
  bodyItem.appendChild(document.createTextNode(bodyInfo.label + suffix));
  if (!bodyInfo.active && bodyInfo.name) {
    bodyItem.title = t("Clic : activer ce corps");
    bodyItem.addEventListener("click", () =>
      refresh(call("set_active_body", { body: bodyInfo.name })));
  }
  if (bodyInfo.name) {
    bodyItem.addEventListener("contextmenu",
      (event) => openMenu(event, bodyInfo));
  }
  treeEl.appendChild(bodyItem);
}

function appendSurfaceRow(surface, { inFolder = true, rolledBack = false } = {}) {
  const item = document.createElement("li");
  item.className = "surface" + (inFolder ? " in-folder" : "")
    + (selectedSurface?.name === surface.name ? " sel" : "")
    + (rolledBack ? " rolled-back" : "");
  if (!inFolder) item.dataset.hist = surface.name;
  const children = surface.children ?? [];
  const hasChildren = children.length > 0;
  const arrow = document.createElement("span");
  arrow.className = "arrow";
  arrow.textContent = hasChildren
    ? (expandedFeatures.has(surface.name) ? "▾" : "▸") : "";
  if (hasChildren) {
    arrow.addEventListener("click", (event) => {
      event.stopPropagation();
      if (!expandedFeatures.delete(surface.name)) {
        expandedFeatures.add(surface.name);
      }
      renderTree(lastTree);
    });
  }
  item.appendChild(arrow);
  item.appendChild(treeIcon(
    isGraphFeature(surface) ? "Geoassembly.svg" : "Part_3D_object.svg"));
  item.appendChild(document.createTextNode(surface.label));
  item.title = t("Surface / courbe — clic : sélectionner pour une " +
    "commande · double-clic : modifier · clic droit : modifier, " +
    "renommer, supprimer");
  item.addEventListener("click", () => onSurfaceClick(surface));
  item.addEventListener("dblclick", () => onSurfaceDblClick(surface));
  item.addEventListener("contextmenu", (event) => openMenu(event, surface));
  treeEl.appendChild(item);
  if (hasChildren && expandedFeatures.has(surface.name)) {
    for (const child of children) {
      const row = document.createElement("li");
      row.className = "child" + (inFolder ? " in-folder" : "")
        + (child.error ? " error" : "")
        + (rolledBack ? " rolled-back" : "");
      row.appendChild(treeIcon("Sketcher_Sketch.svg"));
      row.appendChild(document.createTextNode(child.label));
      row.title = `${child.kind} — `
        + t("double-clic : modifier l'esquisse · clic droit : modifier");
      row.addEventListener("dblclick", () => onSketchRowDblClick(child));
      row.addEventListener("contextmenu", (event) => openMenu(event, child));
      row.addEventListener("click", () => onSketchRowClick(child));
      treeEl.appendChild(row);
    }
  }
}

function appendRollbackBar(tree) {
  const bar = document.createElement("li");
  bar.className = "rollback";
  bar.textContent = t("▲ barre de retour arrière ▲");
  bar.title = t("Glisser pour déplacer · double-clic : revenir à l'état final");
  bar.addEventListener("dblclick", () => refresh(call("tip_to_end")));
  bindRollbackDrag(bar, tree);
  treeEl.appendChild(bar);
}

// Glisser-déposer d'une fonction dans l'arbre : le repère d'insertion de
// la barre de retour montre où elle ira ; le moteur la déplace avec ses
// esquisses, et refuse si l'arbre ne se reconstruit plus.
let suppressTreeClick = false;
treeEl.addEventListener("click", (event) => {
  if (!suppressTreeClick) return;
  suppressTreeClick = false;
  event.stopPropagation();
  event.preventDefault();
}, true);

function bindFeatureDrag(row, feature) {
  row.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || panel.active || sketchMode.active) return;
    const start = { x: event.clientX, y: event.clientY };
    let dragging = false;
    const onMove = (moveEvent) => {
      if (!dragging && Math.hypot(moveEvent.clientX - start.x,
                                  moveEvent.clientY - start.y) < 6) return;
      dragging = true;
      row.classList.add("dragging");
      const slots = rollbackSlotPositions();
      if (slots.length) showInsertMark(nearestRollbackSlot(moveEvent.clientY, slots));
    };
    const onUp = (upEvent) => {
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerup", onUp);
      hideInsertMark();
      row.classList.remove("dragging");
      if (!dragging) return;
      // Le clic qui suit le lâcher ne doit pas sélectionner ; s'il ne vient
      // pas (lâcher hors de la ligne), le drapeau retombe aussitôt.
      suppressTreeClick = true;
      setTimeout(() => { suppressTreeClick = false; }, 0);
      const rows = [...treeEl.querySelectorAll("li[data-hist]")];
      const slots = rollbackSlotPositions();
      if (!slots.length) return;
      const slot = nearestRollbackSlot(upEvent.clientY, slots);
      const own = rows.indexOf(row);
      if (slot.index === own || slot.index === own + 1) return;
      const params = slot.index < rows.length
        ? { feature: feature.name, target: rows[slot.index].dataset.hist,
            after: false }
        : { feature: feature.name, target: rows[rows.length - 1].dataset.hist,
            after: true };
      refresh(call("reorder_feature", params));
    };
    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", onUp);
  });
}

function applyRollbackSlot(index, history) {
  if (index <= 0) {
    refresh(call("set_tip", {}));
    return;
  }
  if (index >= history.length) {
    refresh(call("tip_to_end"));
    return;
  }
  const target = history[index - 1];
  refresh(call("set_tip", { feature: target.item.name }));
}

function rollbackSlotPositions() {
  const rows = [...treeEl.querySelectorAll("li[data-hist]")];
  if (!rows.length) return [];
  const slots = [{ y: rows[0].getBoundingClientRect().top, index: 0 }];
  for (let i = 0; i < rows.length; i++) {
    slots.push({
      y: rows[i].getBoundingClientRect().bottom,
      index: i + 1,
    });
  }
  return slots;
}

function nearestRollbackSlot(clientY, slots) {
  let best = slots[0];
  let bestDist = Infinity;
  for (const slot of slots) {
    const dist = Math.abs(clientY - slot.y);
    if (dist < bestDist) {
      bestDist = dist;
      best = slot;
    }
  }
  return best;
}

function showInsertMark(slot) {
  let mark = treeEl.querySelector("li.insert-mark");
  if (!mark) {
    mark = document.createElement("li");
    mark.className = "insert-mark";
    treeEl.appendChild(mark);
  }
  const treeRect = treeEl.getBoundingClientRect();
  mark.style.top = `${slot.y - treeRect.top}px`;
}

function hideInsertMark() {
  treeEl.querySelector("li.insert-mark")?.remove();
}

function bindRollbackDrag(bar, tree) {
  bar.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    event.preventDefault();
    const startX = event.clientX;
    const startY = event.clientY;
    const split = splitHistoryAroundBar(
      tree.features ?? [], tree.surfaces ?? [], tree.tip);
    const history = split.before.concat(split.after);
    const currentSlot = split.before.length;
    let dragging = false;
    try {
      bar.setPointerCapture(event.pointerId);
    } catch {
      // Capture indisponible (pointeur déjà relâché) : le drag s'arrête.
    }

    const onMove = (moveEvent) => {
      const dist = Math.hypot(
        moveEvent.clientX - startX, moveEvent.clientY - startY);
      if (!dragging && dist < 5) return;
      dragging = true;
      bar.classList.add("dragging");
      const slots = rollbackSlotPositions();
      if (!slots.length) return;
      showInsertMark(nearestRollbackSlot(moveEvent.clientY, slots));
    };
    const onUp = (upEvent) => {
      bar.removeEventListener("pointermove", onMove);
      bar.removeEventListener("pointerup", onUp);
      bar.removeEventListener("pointercancel", onUp);
      hideInsertMark();
      bar.classList.remove("dragging");
      if (!dragging) return;
      const slots = rollbackSlotPositions();
      if (!slots.length) return;
      const slot = nearestRollbackSlot(upEvent.clientY, slots);
      if (slot.index === currentSlot) return;
      applyRollbackSlot(slot.index, history);
    };
    bar.addEventListener("pointermove", onMove);
    bar.addEventListener("pointerup", onUp);
    bar.addEventListener("pointercancel", onUp);
  });
}

function renderTree(tree) {
  clearAssemblyView(); // un arbre de pièce = le mode assemblage s'efface
  dropRolledBackSelection(tree);
  lastTree = tree;
  treeHoverPlane = null;
  treeEl.innerHTML = "";

  const bodies = tree.bodies
    ?? [{ name: null, label: tree.body, active: true, count: 0 }];
  const surfaces = tree.surfaces ?? [];
  const variables = tree.variables ?? [];
  const solidCount = bodies.filter((body) => body.has_solid === true).length;
  const bodiesDefaultOpen = bodies.length > 1
    || bodies.some((body) => body.error);
  const surfacesDefaultOpen = surfaces.some((surface) => surface.error
    || (surface.children ?? []).some((child) => child.error));

  rememberFolderCount("bodies", solidCount);
  rememberFolderCount("surfaces", surfaces.length);
  rememberFolderCount("equations", variables.length);

  // Ordre SolidWorks : dossiers en tête, puis plans, puis fonctions.
  const bodiesOpen = appendFolder(
    "bodies", t("Corps volumiques"), solidCount, "PartDesign_Body.svg",
    bodiesDefaultOpen,
    { title: t("Corps de la pièce — clic : déplier") });
  if (bodiesOpen) {
    for (const bodyInfo of bodies) appendBodyRow(bodyInfo);
  }

  const surfacesOpen = appendFolder(
    "surfaces", t("Corps surfaciques"), surfaces.length, "Part_3D_object.svg",
    surfacesDefaultOpen,
    { title: t("Surfaces et courbes — clic : déplier") });
  if (surfacesOpen) {
    for (const surface of surfaces) appendSurfaceRow(surface);
  }

  const equationsOpen = appendFolder(
    "equations", t("Équations"), variables.length, "VarSet.svg", false,
    {
      clickToggles: false,
      title: t("Double-clic : ouvrir les équations"),
      onDblClick: openEquationsPanel,
    });
  if (equationsOpen) {
    for (const variable of variables) {
      const row = document.createElement("li");
      row.className = "in-folder";
      row.appendChild(treeIcon("VarSet.svg"));
      row.appendChild(document.createTextNode(
        `${variable.name} = ${variable.value}`));
      row.title = t("Double-clic : ouvrir les équations");
      row.addEventListener("dblclick", openEquationsPanel);
      treeEl.appendChild(row);
    }
  }

  renderActiveBodyContents(tree);
  pluginRuntime?.renderTreeRows(tree, {
    treeIcon, openMenu, append: (row) => treeEl.appendChild(row),
  });
  syncGraphFromTree();
}

function renderActiveBodyContents(tree) {
  // Les trois plans de base, toujours là — comme dans SolidWorks.
  for (const plane of tree.planes ?? []) {
    const item = document.createElement("li");
    item.className = "plane" + (selectedPlane === plane.id ? " sel" : "");
    item.appendChild(treeIcon("Std_Plane.svg"));
    item.appendChild(document.createTextNode(plane.label));
    item.title = t("Clic : choisir ce plan pour la prochaine esquisse");
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
  // L'origine ferme le groupe des références, comme d'habitude en CAO.
  const origin = document.createElement("li");
  origin.className = "plane origin" + (originShown ? " sel" : "");
  origin.appendChild(treeIcon("FreeSolid_Origin.svg"));
  origin.appendChild(document.createTextNode(t("Origine")));
  origin.title = t("Clic : afficher ou masquer l'origine");
  origin.addEventListener("click", toggleOrigin);
  treeEl.appendChild(origin);

  const features = tree.features ?? [];
  const split = splitHistoryAroundBar(features, tree.surfaces ?? [], tree.tip);
  if (split.bar !== "none") {
    for (const row of split.before) {
      if (row.surface) {
        appendSurfaceRow(row.item, {
          inFolder: false, rolledBack: !!row.item.rolled_back,
        });
      } else {
        appendFeatureHistoryRow(row.item, false);
      }
    }
    appendRollbackBar(tree);
    for (const row of split.after) {
      if (row.surface) {
        appendSurfaceRow(row.item, {
          inFolder: false, rolledBack: true,
        });
      } else {
        appendFeatureHistoryRow(row.item, true);
      }
    }
  }
}

function appendFeatureHistoryRow(feature, rolledBack) {
  const row = document.createElement("li");
  row.classList.add("feat");
  row.dataset.feat = feature.name;
  row.dataset.hist = feature.name;
  if (feature.error) row.classList.add("error");
  if (rolledBack) row.classList.add("rolled-back");
  if (selectedFeatureName === feature.name) row.classList.add("sel");
  const hasChildren = !!feature.children?.length;
  const arrow = document.createElement("span");
  arrow.className = "arrow";
  arrow.textContent = hasChildren
    ? (expandedFeatures.has(feature.name) ? "▾" : "▸") : "";
  if (hasChildren) {
    arrow.addEventListener("click", (event) => {
      event.stopPropagation();
      if (!expandedFeatures.delete(feature.name)) {
        expandedFeatures.add(feature.name);
      }
      renderTree(lastTree);
    });
  }
  row.appendChild(arrow);
  const icon = isGraphFeature(feature)
    ? "Geoassembly.svg"
    : isRepeatFeature(feature)
      ? "PartDesign_LinearPattern.svg"
      : TREE_ICONS[feature.type];
  if (icon) row.appendChild(treeIcon(icon));
  row.appendChild(document.createTextNode(
    feature.type === "Sketcher::SketchObject"
      ? sketchTreeLabel(feature.label, sketchDefinitionOf(feature))
      : feature.label));
  if (sketchMode.editing === feature.name) row.classList.add("editing");
  row.title = `${feature.kind} — `
    + t("double-clic : modifier · clic droit : modifier, barre de retour, supprimer · glisser : réordonner");
  row.addEventListener("dblclick", () => {
    if (feature.type === "Sketcher::SketchObject") {
      onSketchRowDblClick(feature);
    } else {
      editFeature(feature);
    }
  });
  row.addEventListener("contextmenu", (event) => openMenu(event, feature));
  bindFeatureDrag(row, feature);
  if (feature.type === "PartDesign::Plane") {
    // Un plan de référence se choisit comme un plan d'origine.
    row.classList.add("plane");
    if (selectedDatumFeature?.name === feature.name) {
      row.classList.add("sel");
    }
    row.addEventListener("click", () => onDatumRow(feature));
    row.addEventListener("mouseenter", () => refreshDatumGhost(feature));
    row.addEventListener("mouseleave", () => refreshDatumGhost(null));
  }
  if (feature.type === "Sketcher::SketchObject") {
    if (selectedSketch?.name === feature.name) row.classList.add("sel");
    row.addEventListener("click", () => onSketchRowClick(feature));
  } else if (feature.type !== "PartDesign::Plane") {
    row.addEventListener("click", () => {
      panel.notifyPick("feature", {
        kind: "feature", name: feature.name, label: feature.label,
      });
    });
  }
  treeEl.appendChild(row);

  // L'esquisse consommée vit sous sa fonction, à la SolidWorks.
  if (hasChildren && expandedFeatures.has(feature.name)) {
    for (const child of feature.children) {
      const childRow = document.createElement("li");
      childRow.className = "child" + (child.error ? " error" : "");
      if (rolledBack) childRow.classList.add("rolled-back");
      if (selectedSketch?.name === child.name) childRow.classList.add("sel");
      childRow.appendChild(treeIcon("Sketcher_Sketch.svg"));
      childRow.appendChild(document.createTextNode(
        sketchTreeLabel(child.label, sketchDefinitionOf(child))));
      if (sketchMode.editing === child.name) childRow.classList.add("editing");
      childRow.title = `${child.kind} — `
        + t("double-clic : modifier l'esquisse · clic droit : modifier");
      childRow.addEventListener("dblclick", () => onSketchRowDblClick(child));
      childRow.addEventListener("contextmenu", (event) => openMenu(event, child));
      childRow.addEventListener("click", () => onSketchRowClick(child));
      treeEl.appendChild(childRow);
    }
  }
}
// (fin du rendu du corps actif)

/** En cours d'édition, l'état vient du solveur de l'esquisse ouverte. */
function sketchDefinitionOf(item) {
  if (sketchMode.editing === item.name && sketchMode.definition) {
    return sketchMode.definition;
  }
  return item.definition;
}

// Property names -> designer-facing labels for the edit panel.
const PROP_LABELS = {
  Length: ["Profondeur", "mm"],
  LengthFwd: ["Longueur", "mm"],
  Radius: ["Rayon", "mm"],
  Size: ["Distance", "mm"],
  Angle: ["Angle", "°"],
  Thickness: ["Épaisseur", "mm"],
  Thickness2: ["Épaisseur côté 2", "mm"],
  Value: ["Épaisseur", "mm"],
  Occurrences: ["Nombre d'occurrences", ""],
  Diameter: ["Diamètre", "mm"],
  Depth: ["Profondeur", "mm"],
  HoleCutDiameter: ["Ø lamage/fraisage", "mm"],
  HoleCutDepth: ["Profondeur du lamage", "mm"],
};

async function editSurface(surface) {
  if (isGraphFeature(surface) || isRepeatFeature(surface)) {
    enterGraphFeature(surface);
    return;
  }
  if (surface.static || surface.type === "Part::Feature") {
    say("Surface figée — non éditable");
    return;
  }
  await editFeature({
    name: surface.name,
    label: surface.label,
    type: surface.type,
  });
}

function findSketch(tree, name) {
  const stack = [...(tree?.features ?? [])];
  while (stack.length) {
    const item = stack.pop();
    if (!item) continue;
    if (item.name === name) return item;
    if (item.children) stack.push(...item.children);
  }
  return null;
}

function editRevolved(feature) {
  const spec = feature.revolution;
  const sketch = findSketch(lastTree, spec.profile);
  panel.open({
    icon: TREE_ICONS[feature.type] ?? "PartDesign_Revolution.svg",
    title: feature.label,
    groups: revolutionGroups(sketch, {
      angle: chamferFieldValue(feature.params, "Angle", spec.angle),
      axis: spec.axis,
      reversed: spec.reversed,
      midplane: spec.midplane,
    }),
    onChange: (v) => {
      const values = revolutionEditValues(v, spec, feature.params);
      schedulePreview(values && Object.keys(values).length
        ? { op: "set_params",
            params: { feature: feature.name, values } }
        : null);
    },
    onApply: (v) => {
      const values = revolutionEditValues(v, spec, feature.params);
      if (values === null) {
        say(revolutionProblem(), true);
        return;
      }
      if (!Object.keys(values).length) return;
      refresh(call("set_params", { feature: feature.name, values }));
    },
  });
}

function editChamfer(feature) {
  const spec = feature.chamfer;
  panel.open({
    icon: "PartDesign_Chamfer.svg",
    title: feature.label,
    groups: [{
      label: "Paramètres du chanfrein",
      rows: chamferRows({
        kind: spec.type,
        size: chamferFieldValue(feature.params, "Size", spec.size),
        size2: chamferFieldValue(feature.params, "Size2", spec.size2),
        angle: chamferFieldValue(feature.params, "Angle", spec.angle),
        flip: spec.flip,
      }),
    }],
    onChange: (v) => {
      const values = chamferEditValues(v, spec, feature.params);
      schedulePreview(values && Object.keys(values).length
        ? { op: "set_params",
            params: { feature: feature.name, values } }
        : null);
    },
    onApply: (v) => {
      const values = chamferEditValues(v, spec, feature.params);
      if (values === null) {
        say(chamferProblem(v), true);
        return;
      }
      if (!Object.keys(values).length) return;
      refresh(call("set_params", { feature: feature.name, values }));
    },
  });
}

async function editFeature(feature) {
  if (isGraphFeature(feature) || isRepeatFeature(feature)) {
    enterGraphFeature(feature);
    return;
  }
  if (feature.type === "Sketcher::SketchObject") {
    closeGraph();
    sketchMode.enter(call("sketch_edit", { feature: feature.name }));
    return;
  }
  if (feature.text) {
    // Gravure rééditable (P032) : panneau dédié -> edit_text.
    const txt = feature.text;
    panel.open({
      icon: TREE_ICONS[feature.type] ?? "PartDesign_Body.svg",
      title: feature.label,
      groups: [{
        label: t("Gravure"),
        rows: [
          { type: "text", key: "text", label: t("Texte"), value: txt.text },
          { type: "number", key: "size", label: t("Taille"), unit: "mm",
            value: txt.size },
          { type: "number", key: "depth", label: t("Profondeur"), unit: "mm",
            value: txt.depth },
          { type: "number", key: "x", label: t("X"), unit: "mm", value: txt.x },
          { type: "number", key: "y", label: t("Y"), unit: "mm", value: txt.y },
        ],
      }],
      onApply: (v) => {
        refresh(call("edit_text", {
          feature: feature.name,
          text: String(v.text ?? txt.text),
          size: num(v.size) ?? txt.size,
          depth: num(v.depth) ?? txt.depth,
          x: num(v.x) ?? txt.x,
          y: num(v.y) ?? txt.y,
        }));
      },
    });
    return;
  }
  if (feature.type === "PartDesign::Chamfer" && feature.chamfer) {
    editChamfer(feature);
    return;
  }
  if ((feature.type === "PartDesign::Revolution"
       || feature.type === "PartDesign::Groove") && feature.revolution) {
    editRevolved(feature);
    return;
  }
  try {
    const info = await call("get_params", { feature: feature.name });
    if (!info.params.length) {
      say(t("{f} : aucun paramètre numérique éditable", { f: info.label }));
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
        label: t("Paramètres"),
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

function isBodyMenuTarget(feature) {
  return feature != null && typeof feature.active === "boolean";
}

function isFrozenSurface(feature) {
  if (isGraphFeature(feature) || isRepeatFeature(feature)) return false;
  return !!(feature?.static || feature?.type === "Part::Feature");
}

function canModifyMenuTarget(feature) {
  if (!feature || isBodyMenuTarget(feature)) return false;
  const type = feature.type;
  if (!type || type === "PartDesign::Plane") return false;
  if (isFrozenSurface(feature)) return false;
  if (type === "Sketcher::SketchObject") return true;
  return type.startsWith("PartDesign::")
    || type.startsWith("Part::")
    || type.startsWith("Surface::");
}

function modifyMenuTarget(feature) {
  if (feature.type === "Sketcher::SketchObject") {
    onSketchRowDblClick(feature);
  } else if (feature.type.startsWith("Part::")
             || feature.type.startsWith("Surface::")) {
    editSurface(feature);
  } else {
    editFeature(feature);
  }
}

function openMenu(event, feature) {
  event.preventDefault();
  menuFeature = feature;
  const onBody = isBodyMenuTarget(feature);
  // Un composant d'assemblage : fixer / libérer, pas de barre de retour.
  const onComponent = !!assemblyState && typeof feature.grounded === "boolean";
  document.getElementById("ctx-modify").hidden = !canModifyMenuTarget(feature);
  document.getElementById("ctx-color").hidden = !onBody;
  document.getElementById("ctx-color-reset").hidden = !onBody;
  const ground = document.getElementById("ctx-ground");
  ground.hidden = !onComponent;
  ground.textContent = t(feature.grounded ? "Libérer" : "Fixer");
  document.getElementById("ctx-rollback").hidden = !!assemblyState;
  document.getElementById("ctx-end").hidden = !!assemblyState;
  menuEl.style.display = "block";
  menuEl.style.left = Math.min(event.clientX, window.innerWidth - 200) + "px";
  menuEl.style.top = event.clientY + "px";
}
document.addEventListener("click", () => { menuEl.style.display = "none"; });

document.getElementById("ctx-modify").addEventListener("click", () => {
  if (!menuFeature || !canModifyMenuTarget(menuFeature)) return;
  modifyMenuTarget(menuFeature);
});

document.getElementById("ctx-rename").addEventListener("click", () => {
  if (!menuFeature) return;
  const label = prompt("Nouveau nom :", menuFeature.label);
  if (label === null || !label.trim()) return;
  refreshAny(call("rename",
    { feature: menuFeature.name, label: label.trim() }));
});

document.getElementById("ctx-color").addEventListener("click", () => {
  if (!menuFeature) return;
  const bodyName = menuFeature.name;
  const picker = document.getElementById("body-color-picker");
  picker.value = hexColor(menuFeature.color) || "#9fb2c4";
  picker.addEventListener("change", () => {
    refresh(call("set_body_color", { body: bodyName, color: picker.value }));
  }, { once: true });
  picker.click();
});

document.getElementById("ctx-color-reset").addEventListener("click", () => {
  if (!menuFeature) return;
  refresh(call("set_body_color", { body: menuFeature.name, color: null }));
});

document.getElementById("ctx-ground").addEventListener("click", () => {
  if (!menuFeature || typeof menuFeature.grounded !== "boolean") return;
  refreshAssembly(call("set_component_grounded", {
    component: menuFeature.name, grounded: !menuFeature.grounded,
  }));
});

document.getElementById("ctx-rollback").addEventListener("click", () => {
  if (menuFeature) refresh(call("set_tip", { feature: menuFeature.name }));
});
document.getElementById("ctx-end").addEventListener("click", () =>
  refresh(call("tip_to_end")));
document.getElementById("ctx-delete").addEventListener("click", () => {
  if (!menuFeature) return;
  if (confirm(t("Supprimer « {f} » ?", { f: menuFeature.label })))
    refreshAny(call("delete_feature", { feature: menuFeature.name }));
});

// ---------- menu contextuel de la zone graphique ----------
// Clic droit : ce qui est visé (face, arête, esquisse, surface) décide
// des entrées (viewmenu.js) ; le clic droit a déjà sélectionné l'élément.

const viewMenuEl = document.createElement("div");
viewMenuEl.id = "view-menu";
document.body.appendChild(viewMenuEl);
let viewMenuHit = null;

function viewMenuContext() {
  if (sketchMode.active) return { mode: "sketch" };
  let hit = null;
  if (hoveredEdgeGroup >= 0) {
    hit = { kind: "edge", edge: edgeGroups[hoveredEdgeGroup].edgeId };
  } else if (hoveredSketch) {
    hit = { kind: "sketch", sketch: hoveredSketch, label: hoveredSketch.label };
  } else if (hoveredSurface) {
    hit = { kind: "surface", surface: hoveredSurface, label: hoveredSurface.label };
  } else if (hoveredGroup >= 0) {
    const group = meshGroups[hoveredGroup];
    const feature = findFeatureInTree(lastTree, group.feature);
    const sketch = (feature?.children ?? [])
      .find((child) => child.type === "Sketcher::SketchObject");
    hit = {
      kind: "face",
      face: group.faceId,
      feature: feature ? {
        name: feature.name, label: feature.label, sketch: sketch?.name,
        item: feature, sketchItem: sketch,
      } : null,
    };
  }
  return { hit, originShown };
}

function clickButton(id) {
  document.getElementById(id)?.click();
}

function sketchTool(tool) {
  document.querySelector(`#sketchbar [data-tool="${tool}"]`)?.click();
}

async function withSketchSelected(hit, buttonId) {
  if (selectedSketch?.name !== hit.sketch.name) await selectSketch(hit.sketch);
  clickButton(buttonId);
}

const VIEW_MENU_ACTIONS = {
  "zoom-fit": () => frameView(null, null),
  orient: () => openOrientBox(),
  origin: () => toggleOrigin(),
  undo: () => refreshAny(call("undo")),
  redo: () => refreshAny(call("redo")),
  rebuild: () => clickButton("btn-rebuild"),
  "sketch-on-face": () => clickButton("btn-sketch"),
  "normal-to": () => viewNormalTo(),
  fillet: () => clickButton("btn-fillet"),
  chamfer: () => clickButton("btn-chamfer"),
  shell: () => clickButton("btn-shell"),
  measure: () => clickButton("btn-measure"),
  "edit-feature": (hit) => editFeature(hit.feature.item),
  "edit-sketch": (hit) => onSketchRowDblClick(hit.kind === "sketch"
    ? { name: hit.sketch.name, label: hit.sketch.label,
        type: "Sketcher::SketchObject" }
    : hit.feature.sketchItem),
  rollback: (hit) => refresh(call("set_tip", { feature: hit.feature.name })),
  "delete-feature": (hit) => {
    if (confirm(t("Supprimer « {f} » ?", { f: hit.feature.label }))) {
      refreshAny(call("delete_feature", { feature: hit.feature.name }));
    }
  },
  pad: (hit) => withSketchSelected(hit, "btn-pad"),
  pocket: (hit) => withSketchSelected(hit, "btn-pocket"),
  revolve: (hit) => withSketchSelected(hit, "btn-revolution"),
  "edit-surface": (hit) => onSurfaceDblClick(hit.surface),
  "sk-select": () => sketchTool("select"),
  "sk-line": () => sketchTool("line"),
  "sk-rect": () => sketchTool("rect"),
  "sk-circle": () => sketchTool("circle"),
  "sk-dim": () => sketchTool("dim"),
  "sk-trim": () => sketchTool("trim"),
  "sk-finish": () => sketchMode.finish(),
  "sk-cancel": () => sketchMode.cancel(),
};

function hideViewMenu() {
  viewMenuEl.style.display = "none";
}

// Barre d'icônes contextuelle : après un clic gauche sur une face, une
// arête ou une esquisse, les actions courantes s'offrent près du curseur ;
// elle s'efface quand la souris s'éloigne.
const ctxBarEl = document.createElement("div");
ctxBarEl.id = "ctx-toolbar";
ctxBarEl.hidden = true;
container.appendChild(ctxBarEl);
let ctxBarAnchor = null;
let ctxBarHit = null;

const CTX_BAR_ICONS = {
  "sketch-on-face": "Sketcher_NewSketch.svg", "normal-to": "view-front.svg",
  fillet: "PartDesign_Fillet.svg", chamfer: "PartDesign_Chamfer.svg",
  shell: "PartDesign_Thickness.svg", measure: "view-measurement.svg",
  "edit-feature": "Sketcher_EditSketch.svg",
  "edit-sketch": "Sketcher_EditSketch.svg", pad: "PartDesign_Pad.svg",
  pocket: "PartDesign_Pocket.svg", revolve: "PartDesign_Revolution.svg",
};

function hideContextToolbar() {
  ctxBarEl.hidden = true;
  ctxBarAnchor = null;
}

function showContextToolbar(event) {
  if (panel.active || measuring || assemblyState) return;
  const ctx = viewMenuContext();
  const keys = contextToolbarKeys(ctx.hit);
  if (!keys.length) { hideContextToolbar(); return; }
  ctxBarHit = ctx.hit;
  ctxBarEl.innerHTML = "";
  for (const key of keys) {
    const button = document.createElement("button");
    const icon = document.createElement("img");
    icon.src = "icons/" + CTX_BAR_ICONS[key];
    icon.alt = "";
    button.appendChild(icon);
    button.title = t(viewMenuLabel(key, ctx));
    button.addEventListener("click", (clickEvent) => {
      clickEvent.stopPropagation();
      hideContextToolbar();
      VIEW_MENU_ACTIONS[key]?.(ctxBarHit);
    });
    ctxBarEl.appendChild(button);
  }
  const host = container.getBoundingClientRect();
  ctxBarEl.hidden = false;
  ctxBarEl.style.left = `${Math.min(event.clientX - host.left + 14,
    host.width - ctxBarEl.offsetWidth - 4)}px`;
  ctxBarEl.style.top = `${Math.max(event.clientY - host.top - 46, 4)}px`;
  ctxBarAnchor = { x: event.clientX, y: event.clientY };
}

renderer.domElement.addEventListener("pointermove", (event) => {
  if (ctxBarAnchor && Math.hypot(event.clientX - ctxBarAnchor.x,
                                 event.clientY - ctxBarAnchor.y) > 160) {
    hideContextToolbar();
  }
});
renderer.domElement.addEventListener("pointerdown", hideContextToolbar);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") hideContextToolbar();
});

renderer.domElement.addEventListener("contextmenu", (event) => {
  event.preventDefault();
  if (assemblyState || planePicking || measuring) return;
  menuEl.style.display = "none";
  const ctx = viewMenuContext();
  viewMenuHit = ctx.hit;
  viewMenuEl.innerHTML = "";
  for (const item of viewMenuItems(ctx)) {
    const row = document.createElement("div");
    if (item.separator) {
      row.className = "sep";
    } else if (item.header) {
      row.className = "head";
      row.textContent = t(item.header);
    } else {
      row.textContent = t(item.label);
      if (item.danger) row.classList.add("danger");
      row.addEventListener("click", () => {
        hideViewMenu();
        VIEW_MENU_ACTIONS[item.key]?.(viewMenuHit);
      });
    }
    viewMenuEl.appendChild(row);
  }
  viewMenuEl.style.display = "block";
  const { offsetWidth: w, offsetHeight: h } = viewMenuEl;
  viewMenuEl.style.left = `${Math.min(event.clientX, window.innerWidth - w - 4)}px`;
  viewMenuEl.style.top = `${Math.min(event.clientY, window.innerHeight - h - 4)}px`;
});
document.addEventListener("click", hideViewMenu);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") hideViewMenu();
});

// ---------- ruban à onglets (CommandManager) ----------

function showTab(name) {
  for (const tab of document.querySelectorAll("header .tab")) {
    tab.classList.toggle("active", tab.dataset.tab === name);
  }
  for (const [key, id] of Object.entries(RIBBONS)) {
    const ribbon = document.getElementById(id);
    if (ribbon) ribbon.classList.toggle("active", key === name);
  }
}
for (const tab of document.querySelectorAll("header .tab")) {
  tab.addEventListener("click", () => showTab(tab.dataset.tab));
}

function addPluginRibbon(spec) {
  if (!isPluginId(spec.id) || RIBBONS[spec.id]) return;
  const tab = buildTabButton(document, spec.id, spec.libelle);
  const push = document.querySelector("#topbar .push");
  if (push) push.parentElement.insertBefore(tab, push);
  tab.addEventListener("click", () => showTab(spec.id));

  const ribbon = buildRibbonElement(document, spec.id, spec.groupes);
  const sketchbar = document.getElementById("sketchbar");
  sketchbar.parentElement.insertBefore(ribbon, sketchbar);
  RIBBONS[spec.id] = ribbon.id;
}

function addPluginFeature(entry) {
  FEATURES.push(entry);
  bindFeature(entry);
}

function addPluginHud(node) {
  if (!(node instanceof Node)) return;
  const viewbar = document.getElementById("viewbar");
  if (viewbar) viewbar.after(node);
  else document.getElementById("viewport")?.appendChild(node);
}

// ---------- coin de confirmation ----------
// En haut à droite de la vue : ✓ valide, ✗ abandonne. Il agit sur la
// commande ouverte, sinon sur l'esquisse en cours ; caché le reste du temps.

const confirmCorner = document.getElementById("confirm-corner");
const confirmOk = document.getElementById("confirm-ok");
const confirmCancel = document.getElementById("confirm-cancel");

function confirmTarget() {
  if (panel.applicable) return "panel";
  if (sketchMode?.active) return "sketch";
  return null;
}

function updateConfirmCorner() {
  if (!confirmCorner) return;
  // sketchMode n'existe pas encore pendant le chargement du module.
  let target = null;
  try { target = confirmTarget(); } catch { target = null; }
  confirmCorner.hidden = target === null;
  if (target === "sketch") {
    confirmOk.title = t("Fermer l'esquisse en gardant les modifications");
    confirmCancel.title = t("Quitter l'esquisse sans garder les modifications");
  } else {
    confirmOk.title = t("OK (Entrée)");
    confirmCancel.title = t("Annuler (Échap)");
  }
}

confirmOk?.addEventListener("click", () => {
  const target = confirmTarget();
  if (target === "panel") panel.apply();
  else if (target === "sketch") sketchMode.finish();
});
confirmCancel?.addEventListener("click", () => {
  const target = confirmTarget();
  if (target === "panel") panel.close();
  else if (target === "sketch") sketchMode.cancel();
});

document.addEventListener("freesolid:sketch-enter", () => {
  updateConfirmCorner();
  inSketchMode = true;
  applyVolumeVisibility();
  showTab("sketch");
  // L'esquisse ouverte apparaît dans l'arbre dès sa création.
  call("get_tree").then((tree) => renderTree(tree)).catch(() => {});
});
// À chaque calcul de l'esquisse ouverte, son préfixe (-)/(+) suit.
document.addEventListener("freesolid:sketch-state", () => {
  if (lastTree) renderTree(lastTree);
});
document.addEventListener("freesolid:sketch-exit", () => {
  updateConfirmCorner();
  inSketchMode = false;
  applyVolumeVisibility();
  showTab("features");
});

// ---------- réglages du ruban (libellés) ----------

const RIBBON_LABELS_KEY = "freesolid.ribbonLabels";
const RIBBON_LABELS_DEFAULT = "icons-and-text";

function readRibbonLabels() {
  try {
    const stored = localStorage.getItem(RIBBON_LABELS_KEY);
    if (stored === "icons-only" || stored === "icons-and-text") return stored;
  } catch {
    // localStorage peut être indisponible (mode privé strict).
  }
  return RIBBON_LABELS_DEFAULT;
}

function applyRibbonLabels(mode) {
  const iconsOnly = mode === "icons-only";
  document.body.classList.toggle("ribbon-icons-only", iconsOnly);
  try {
    localStorage.setItem(RIBBON_LABELS_KEY, mode);
  } catch {
    // même repli que la lecture : le réglage tient pour la session.
  }
}

applyRibbonLabels(readRibbonLabels());

// ---------- panneau Paramètres ----------

const settingsDialog = createSettingsDialog({
  root: document.getElementById("settings-dialog"),
  doc: document,
  win: window,
  call,
  ribbonLabels: { read: readRibbonLabels, apply: applyRibbonLabels },
  wheel: { read: () => readReverseWheel(localStore), apply: setReverseWheel },
  storage: (() => { try { return window.localStorage; } catch { return null; } })(),
  navigatorLang: navigator.language,
});
document.getElementById("btn-settings").addEventListener("click", () => {
  settingsDialog.toggle();
});

// Cliquer une fonction pendant une esquisse la termine d'abord — le
// réflexe SolidWorks : on dessine, puis on clique Bossage, sans passer
// par un bouton « quitter l'esquisse ».
async function featureCommand(openPanel) {
  if (assemblyState) {
    say("Les fonctions s'appliquent aux pièces — ouvrez ou créez une " +
        "pièce (un assemblage est en cours)", true);
    return;
  }
  if (graphFn.active) {
    say("Fermez d'abord la fonction graphe (Échap ou Fermer)", true);
    return;
  }
  if (sketchMode.active) await sketchMode.finish();
  openPanel();
}

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
  say(t("Coupe {axis} à {position} mm — purement visuelle.", { axis, position }));
}

document.getElementById("btn-clip").addEventListener("click", () => {
  const active = renderer.clippingPlanes.length > 0;
  panel.open({
    icon: "Std_ToggleClipPlane.svg",
    title: t("Plan de coupe"),
    groups: [{
      label: t("Coupe visuelle"),
      rows: [
        { type: "select", key: "axis", value: active ? "X" : "X",
          label: t("Axe"),
          options: [["off", "Aucune"], ["X", "X"], ["Y", "Y"],
                    ["Z", "Z"]] },
        { type: "number", key: "position", label: t("Position"), value: 0,
          unit: "mm", showIf: (v) => v.axis !== "off" },
        { type: "check", key: "flip", label: t("Inverser le côté"),
          value: false, showIf: (v) => v.axis !== "off" },
      ],
    }],
    note: t("N'enlève pas de matière : la pièce est seulement montrée " +
          "coupée à l'écran."),
    onApply: (v) => setClip(v.axis, num(v.position) ?? 0, !!v.flip),
  });
});

// ---------- vue en graphe (depuis lastTree) ----------

const SVG_NS = "http://www.w3.org/2000/svg";
const graphView = document.getElementById("graph-view");
const graphSvg = document.getElementById("graph-svg");
const graphWorld = document.getElementById("graph-world");
const graphEmpty = document.getElementById("graph-empty");
const graphCap = document.getElementById("graph-cap");
const graphBtn = document.getElementById("btn-graph");
const graphAddBtn = document.getElementById("btn-graph-add");
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

let graphOpen = false;
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
let graphFn = {
  active: false,
  kind: "graphe",
  feature: null,
  draft: null,
  saved: null,
  vocabulary: [],
  errorNode: null,
  selected: null,
  draggingNode: null,
};

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

function graphLabelText(text) {
  const label = String(text ?? "");
  return label.length > 16 ? `${label.slice(0, 15)}…` : label;
}

function isGraphNodeSelected(node) {
  if (graphFn.active) return graphFn.selected === node.name;
  if (graphSelectedName && node.name === graphSelectedName) return true;
  if (selectedSketch?.name === node.name) return true;
  if (selectedDatumFeature?.name === node.name) return true;
  if (selectedSurface?.name === node.name) return true;
  if (selectedPlane != null) {
    const plane = (lastTree?.planes ?? [])
      .find((item) => item.id === selectedPlane);
    if (plane?.name === node.name) return true;
  }
  return false;
}

function lookupGraphTarget(name) {
  if (!lastTree || !name) return null;
  for (const plane of lastTree.planes ?? []) {
    if (plane.name === name) return { kind: "plane", plane };
  }
  for (const feature of lastTree.features ?? []) {
    if (feature.name === name) {
      if (feature.type === "Sketcher::SketchObject") {
        return { kind: "sketch", feature };
      }
      if (feature.type === "PartDesign::Plane") {
        return { kind: "datum", feature };
      }
      return { kind: "feature", feature };
    }
    for (const child of feature.children ?? []) {
      if (child.name === name) return { kind: "sketch", feature: child };
    }
  }
  for (const surface of lastTree.surfaces ?? []) {
    if (surface.name === name) return { kind: "surface", surface };
    for (const child of surface.children ?? []) {
      if (child.name === name) return { kind: "sketch", feature: child };
    }
  }
  for (const body of lastTree.bodies ?? []) {
    if (body.name === name) return { kind: "body", body };
  }
  for (const variable of lastTree.variables ?? []) {
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
  if (graphFn.active) {
    graphFn.selected = name;
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
  if (graphFn.active) {
    graphFn.draft.output = name;
    graphFn.selected = name;
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
    lastTree,
    selectedSketch: profileOverride ?? selectedSketch,
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
      graphFn.draft, wiring.from, port.dataset.node, port.dataset.key,
      graphFn.vocabulary);
    if (!result.ok) {
      graphFn.errorNode = result.node;
      say(result.error, true);
      renderGraphFunction();
      return;
    }
    graphFn.draft = result.draft;
    graphFn.errorNode = null;
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
  const pad = graphFn.active ? 88 : 56;
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
  const fn = graphFn.active;
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
        if (fn) graphFn.selected = null;
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
      "data-type": node.type || "",
    });
    if (isGraphNodeSelected(node)) group.classList.add("sel");
    if (!fn && node.afterBar) group.classList.add("rolled-back");
    if (fn && node.output) group.classList.add("output");
    if (fn && graphFn.errorNode === node.name) group.classList.add("error");
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
  if (!graphFn.active || !graphFn.draft) return;
  renderGraph(layoutFunctionGraph(graphFn.draft, graphFn.vocabulary));
}

function applyGraphNodeSelection() {
  for (const node of graphWorld.querySelectorAll(".graph-node")) {
    node.classList.toggle("sel",
      isGraphNodeSelected({ name: node.dataset.name }));
  }
}

function syncGraphFromTree() {
  if (!graphOpen) return;
  if (graphFn.active) return;
  const data = buildGraph(lastTree);
  renderGraph(data);
  const names = data.nodes.map((node) => node.name).join("\0");
  if (names !== graphFitNames) {
    graphFitNames = names;
    fitGraphView(data);
  }
}

function startFunctionNodeDrag(node, event) {
  graphFn.draggingNode = node.name;
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
  if (!graphFn.draggingNode || !graphFn.draft) return;
  const dx = (event.clientX - graphDragX) / graphZoom;
  const dy = (event.clientY - graphDragY) / graphZoom;
  if (!graphMoved && Math.hypot(event.clientX - graphDragX,
      event.clientY - graphDragY) < 4) return;
  graphMoved = true;
  graphDragX = event.clientX;
  graphDragY = event.clientY;
  const raw = graphFn.draft.nodes.find(
    (item) => String(item.id) === graphFn.draggingNode);
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
  if (!graphFn.active) return;
  if (graphSelectedEdge?.kind === "data") {
    graphFn.draft = disconnectGraphEdge(
      graphFn.draft, graphSelectedEdge.from, graphSelectedEdge.to,
      graphSelectedEdge.input);
    graphSelectedEdge = null;
    renderGraphFunction();
    return;
  }
  if (graphFn.selected) {
    graphFn.draft = removeGraphNode(graphFn.draft, graphFn.selected);
    graphFn.selected = null;
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

  if (graphFn.active) {
    const heading = document.createElement("div");
    heading.className = "menu-label";
    heading.textContent = t("Nœud à poser");
    graphPalette.appendChild(heading);
    for (const group of graphNodePaletteGroups(graphFn.vocabulary)) {
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
          img.src = "icons/" + item.icon;
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
          const offset = (graphFn.draft.nodes.length) * 36;
          world.x += offset;
          world.y += offset;
          const id = nextGraphNodeId(graphFn.draft.nodes);
          graphFn.draft.nodes.push(newGraphNode(item.spec, id, world));
          if (!graphFn.draft.output
              && (item.spec.shape || item.spec.type === "instance")) {
            graphFn.draft.output = id;
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
    : (selectedSketch?.name
      ? { name: selectedSketch.name, label: selectedSketch.label }
      : null);
  const ctx = graphPlacementCtx(graphPaletteProfile);
  const items = graphPaletteItems(FEATURES, ctx);

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
    img.src = "icons/" + item.icon;
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
  const raw = graphFn.draft.nodes.find((item) => String(item.id) === nodeId);
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
    const spec = graphFn.vocabulary.find((item) => item.type === raw.type);
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
  if (graphFn.active && graphFn.feature?.name === feature.name) return;
  if (graphFn.active && !exitGraphFeature()) return;
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
  graphFn.active = true;
  graphFn.kind = kind;
  graphFn.feature = { name: feature.name, label: feature.label };
  graphFn.vocabulary = vocabulary;
  graphFn.draft = cloneGraphDraft(graph);
  graphFn.saved = cloneGraphDraft(graph);
  graphFn.errorNode = null;
  graphFn.selected = null;
  graphOpen = true;
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
  const data = layoutFunctionGraph(graphFn.draft, graphFn.vocabulary);
  renderGraph(data);
  fitGraphView(data);
  say(kind === "repetition" ? REPEAT_FN_HINT : GRAPH_FN_HINT);
}

function exitGraphFeature({ force = false } = {}) {
  if (!graphFn.active) return true;
  if (!force && !graphDraftsEqual(graphFn.draft, graphFn.saved)) {
    if (!confirm("Le graphe n'a pas été appliqué. Quitter sans appliquer ?")) {
      return false;
    }
  }
  graphFn.active = false;
  graphFn.kind = "graphe";
  graphFn.feature = null;
  graphFn.draft = null;
  graphFn.saved = null;
  graphFn.errorNode = null;
  graphFn.selected = null;
  graphFn.draggingNode = null;
  graphFnBar.hidden = true;
  graphView.classList.remove("fn");
  closeGraphPalette();
  closeLiteralEditor();
  cancelGraphWire();
  if (graphOpen && lastTree) {
    const data = buildGraph(lastTree);
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
  if (!graphFn.active || !graphFn.feature) return;
  const composed = composeGraphPayload(graphFn.draft, graphFn.vocabulary);
  if (!composed.ok) {
    graphFn.errorNode = composed.node;
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
    const op = graphFn.kind === "repetition"
      ? "edit_repeat_feature" : "edit_graph_feature";
    const tree = await call(op, {
      feature: graphFn.feature.name,
      graph: composed.graph,
    });
    graphFn.errorNode = null;
    graphFn.saved = cloneGraphDraft(graphFn.draft);
    lastTree = tree;
    renderTree(tree);
    const gen = ++viewGen;
    await updateViewport(gen);
    renderGraphFunction();
    say(graphFn.kind === "repetition"
      ? "Réseau variable appliqué."
      : "Fonction graphe appliquée.");
  } catch (error) {
    graphFn.errorNode = nodeIdFromGraphError(error.message);
    say(error.message, true);
    renderGraphFunction();
  }
}

window.__freesolidDebug.setGraphLiteral = (id, key, value) => {
  if (!graphFn.draft) return false;
  const node = graphFn.draft.nodes.find(
    (item) => String(item.id) === String(id));
  if (!node) return false;
  node[key] = value;
  renderGraphFunction();
  return true;
};
window.__freesolidDebug.wireGraph = (from, to, input) => {
  if (!graphFn.draft) return { ok: false, error: "pas de brouillon" };
  const result = connectGraphEdge(
    graphFn.draft, from, to, input, graphFn.vocabulary);
  if (result.ok) {
    graphFn.draft = result.draft;
    graphFn.errorNode = null;
    renderGraphFunction();
  }
  return result;
};
window.__freesolidDebug.graphFeatureEdges = () =>
  (graphFn.draft?.edges ?? []).map((edge) => ({
    from: edge.from, to: edge.to, input: edge.input,
  }));
window.__freesolidDebug.applyGraphFeature = () => applyGraphFeature();

function closeGraph() {
  if (graphFn.active && !exitGraphFeature()) return;
  if (!graphOpen) return;
  cancelGraphWire();
  closeParamPicker();
  closeGraphEdgeMenu();
  closeGraphPalette();
  closeLiteralEditor();
  graphSelectedEdge = null;
  graphSelectedName = null;
  graphFitNames = "";
  graphOpen = false;
  graphView.classList.remove("open", "dragging", "wiring", "fn");
  graphBtn.classList.remove("on");
  graphFnBar.hidden = true;
  graphWorld.replaceChildren();
  graphEmpty.hidden = true;
  graphCap.hidden = true;
}

function openGraph() {
  if (!lastTree) {
    say("Vue en graphe : ouvrez d'abord une pièce", true);
    return;
  }
  if (graphFn.active) return;
  graphOpen = true;
  graphView.classList.add("open");
  graphBtn.classList.add("on");
  const data = buildGraph(lastTree);
  graphFitNames = data.nodes.map((node) => node.name).join("\0");
  renderGraph(data);
  fitGraphView(data);
  say(data.nodes.length
    ? "Vue en graphe — double-clic : poser une fonction. "
      + "Fil depuis une esquisse ou une variable. Échap pour fermer."
    : "Vue en graphe — aucun nœud. Échap pour fermer.");
}

graphBtn.addEventListener("click", () => {
  if (graphOpen) closeGraph();
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
  if (graphFn.draggingNode) {
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
  graphFn.draggingNode = null;
  if (graphWiring) finishGraphWire(event);
};
graphView.addEventListener("pointerup", endGraphDrag);
graphView.addEventListener("pointercancel", (event) => {
  graphDragging = false;
  graphFn.draggingNode = null;
  graphView.classList.remove("dragging");
  cancelGraphWire();
});

graphView.addEventListener("click", () => {
  if (graphMoved) return;
  selectGraphEdge(null);
  if (graphFn.active) {
    graphFn.selected = null;
    renderGraphFunction();
  }
});

graphView.addEventListener("dblclick", (event) => {
  if (!graphFn.active) return;
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
    graphFn.draft = disconnectGraphEdge(
      graphFn.draft, graphSelectedEdge.from, graphSelectedEdge.to,
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

document.getElementById("btn-curve3d").addEventListener("click", () =>
  featureCommand(() => {
    const raw = prompt(
      "Courbe 3D — points x,y,z séparés par « ; »\n" +
      "ex. : 0,0,0 ; 0,0,30 ; 20,0,50", "0,0,0 ; 0,0,30 ; 20,0,50");
    if (!raw) return;
    const points = raw.split(";").map((p) =>
      p.split(",").map((v) => num(v.trim())));
    if (points.length < 2
        || points.some((p) => p.length !== 3 || p.some((n) => n === null))) {
      say("Courbe 3D : au moins deux points x,y,z valides", true);
      return;
    }
    refresh(call("add_curve3d", { points, spline: points.length >= 3 }));
  }));

document.getElementById("btn-drawing").addEventListener("click", () => {
  panel.open({
    icon: "TechDraw_PageDefault.svg",
    title: t("Mise en plan"),
    groups: [
      {
        label: t("Fichier"),
        rows: [
          { type: "text", key: "path", label: t("Chemin"),
            value: "~/piece-freesolid.dxf" },
          { type: "number", key: "scale", label: t("Échelle"), value: "",
            min: 0.01 },
        ],
      },
      {
        label: t("Annotations"),
        rows: [
          { type: "check", key: "dims", label: t("Cotes d'encombrement"),
            value: true },
          { type: "select", key: "section", value: "", label: t("Coupe"),
            options: [["", "Aucune"], ["X", "X"], ["Y", "Y"],
                      ["Z", "Z"]] },
        ],
      },
    ],
    note: t("Trois vues (Face, Dessus, Iso) exportées en DXF."),
    onApply: (v) => {
      const path = (v.path ?? "").trim();
      if (!path) {
        say("Mise en plan : chemin du fichier requis", true);
        return;
      }
      const params = { path, dims: !!v.dims };
      const scale = num(v.scale);
      if (scale) params.scale = scale;
      if (v.section) params.section = v.section;
      (async () => {
        try {
          const out = await call("make_drawing", params);
          let extra = "";
          if (params.dims && out.dims_ok === false) extra += t(" (sans cotes)");
          if (params.section && out.section_ok === false) extra += t(" (sans coupe)");
              say(t("Mise en plan exportée : {path} ({size} Ko — Face, Dessus, Iso)",
            { path: out.path, size: (out.size / 1024).toFixed(1) }) + extra);
        } catch (error) {
          say(error.message, true);
        }
      })();
    },
  });
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
  startProgressWatch();
  let ok = false;
  try {
    assemblyState = await treePromise;
    if (gen !== viewGen) return;
    renderAssemblyTree(assemblyState);
    const meshes = await call("tessellate_assembly");
    if (gen !== viewGen) return;
    showAssemblyMeshes(meshes);
    ok = !lastClearedSelections;
  } catch (error) {
    if (gen !== viewGen) return;
    sayUntilAck(error.message);
  } finally {
    stopProgressWatch();
  }
  if (ok) say("Assemblage à jour.");
}

// Rafraîchit dans le bon mode — les ops transverses (renommer,
// supprimer, annuler) renvoient l'arbre du mode courant.
async function refreshAny(treePromise) {
  const gen = ++viewGen;
  lastClearedSelections = false;
  startProgressWatch();
  let ok = false;
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
    ok = !lastClearedSelections;
  } catch (error) {
    if (gen !== viewGen) return;
    sayUntilAck(error.message);
  } finally {
    stopProgressWatch();
  }
  if (ok) say("À jour.");
}

function renderAssemblyTree(tree) {
  lastTree = null; // le mode pièce est inactif
  closeGraph();
  treeEl.innerHTML = "";
  const head = document.createElement("li");
  head.className = "body active";
  head.appendChild(treeIcon("Geoassembly.svg"));
  head.appendChild(document.createTextNode(t("Assemblage")));
  treeEl.appendChild(head);
  for (const comp of tree.components) {
    const item = document.createElement("li");
    if (comp.name === selectedComponent) item.className = "sel-comp";
    item.appendChild(treeIcon("Link.svg"));
    item.appendChild(document.createTextNode(
      comp.label + (comp.grounded ? " " + t("(fixé)") : "")));
    item.title = t("Clic : sélectionner · double-clic : déplacer · " +
      "clic droit : renommer, supprimer");
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
    empty.textContent = t("— insérez une pièce (.FCStd) —");
    treeEl.appendChild(empty);
  }
  for (const joint of tree.joints ?? []) {
    const row = document.createElement("li");
    row.className = "child";
    row.appendChild(treeIcon("Geoassembly.svg"));
    row.appendChild(document.createTextNode(joint.label));
    row.title = `${joint.type} — ` + t("clic droit : renommer, supprimer");
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
    title: t("Déplacer — {c}", { c: comp.label }),
    groups: [
      { label: t("Translation"),
        rows: [
          { type: "number", key: "x", label: t("X"), value: +x.toFixed(3), unit: "mm" },
          { type: "number", key: "y", label: t("Y"), value: +y.toFixed(3), unit: "mm" },
          { type: "number", key: "z", label: t("Z"), value: +z.toFixed(3), unit: "mm" },
        ] },
      { label: t("Rotation"),
        rows: [
          { type: "number", key: "yaw", label: t("Lacet (Z)"), value: +yaw.toFixed(2), unit: "°" },
          { type: "number", key: "pitch", label: t("Tangage (Y)"), value: +pitch.toFixed(2), unit: "°" },
          { type: "number", key: "roll", label: t("Roulis (X)"), value: +roll.toFixed(2), unit: "°" },
        ] },
    ],
    note: t("Avec des contraintes posées, le solveur repositionne le "
          + "composant après le déplacement. Astuce : glissez un composant "
          + "libre directement dans la vue."),
    onApply: (v) => refreshAssembly(call("move_component", {
      component: comp.name,
      x: num(v.x) ?? 0, y: num(v.y) ?? 0,
      z: num(v.z) ?? 0,
      yaw: num(v.yaw) ?? 0, pitch: num(v.pitch) ?? 0,
      roll: num(v.roll) ?? 0,
    })),
  });
}

// Un assemblage neuf enchaîne sur l'insertion du premier composant
// (fixé à l'origine), puis propose d'en insérer d'autres.
document.getElementById("btn-newasm").addEventListener("click", async () => {
  clearGhost();
  await refreshAssembly(call("new_assembly"));
  if (assemblyState) insertComponents();
});

async function insertComponents() {
  for (;;) {
    const first = !assemblyState?.components.length;
    const path = prompt(first
      ? "Premier composant (chemin .FCStd) — il sera fixé à l'origine :"
      : "Composant suivant (chemin .FCStd) — Annuler pour terminer :",
    "~/piece-freesolid.FCStd");
    if (!path) return;
    await refreshAssembly(call("insert_component", { path }));
  }
}

document.getElementById("btn-insert").addEventListener("click", () => {
  if (!assemblyState) {
    say("Créez d'abord un assemblage (Nouvel assemblage)", true);
    return;
  }
  insertComponents();
});

// ---------- déplacer un composant à la souris ----------
// Bouton gauche glissé sur un composant libre : il suit le curseur dans le
// plan de l'écran ; au lâcher, sa position part au moteur (qui résout les
// contraintes posées, comme un glisser de modeleur).

let asmDrag = null; // { comp, mesh, plane, from, start }

renderer.domElement.addEventListener("pointerdown", (event) => {
  if (!assemblyState || !asmGroup || event.button !== 0 || panel.active) return;
  raycaster.setFromCamera(pointer, camera);
  const hit = raycaster.intersectObjects(asmGroup.children, false)[0];
  if (!hit) return;
  const comp = assemblyState.components.find(
    (c) => c.name === hit.object.userData.component);
  if (!comp || comp.grounded) return;
  const normal = camera.getWorldDirection(new THREE.Vector3());
  asmDrag = {
    comp, mesh: hit.object,
    plane: new THREE.Plane().setFromNormalAndCoplanarPoint(normal, hit.point),
    from: hit.point.clone(),
    start: { x: event.clientX, y: event.clientY },
    moved: false,
  };
});

renderer.domElement.addEventListener("pointermove", (event) => {
  if (!asmDrag) return;
  if (Math.hypot(event.clientX - asmDrag.start.x,
                 event.clientY - asmDrag.start.y) > 5) asmDrag.moved = true;
  if (!asmDrag.moved) return;
  setPointerFromEvent(event);
  raycaster.setFromCamera(pointer, camera);
  const at = new THREE.Vector3();
  if (!raycaster.ray.intersectPlane(asmDrag.plane, at)) return;
  asmDrag.mesh.position.copy(at.sub(asmDrag.from));
});

renderer.domElement.addEventListener("pointerup", () => {
  const drag = asmDrag;
  asmDrag = null;
  if (!drag?.moved) return;
  const d = drag.mesh.position;
  const [x, y, z] = drag.comp.position;
  const [yaw, pitch, roll] = drag.comp.rotation;
  refreshAssembly(call("move_component", {
    component: drag.comp.name,
    x: x + d.x, y: y + d.y, z: z + d.z, yaw, pitch, roll,
  }));
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
    if (v.flip) params.flip = true;
    if (v.type === "angle") {
      const a = num(v.angle);
      if (a === null) return null;
      params.angle = a;
    }
    if (v.type === "distance" || MECHANICAL.includes(v.type)) {
      const d = num(v.distance);
      if (d === null || d < 0) return null;
      params.distance = d;
      if (["engrenages", "courroie"].includes(v.type)) {
        const d2 = num(v.distance2);
        if (d2 === null || d2 < 0) return null;
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
        const parsed = num(raw);
        if (parsed !== null) params[param] = parsed;
      }
    }
    return params;
  };
  panel.open({
    icon: "Geoassembly.svg",
    title: t("Contrainte d'assemblage"),
    groups: [
      { label: t("Type de contrainte"),
        rows: [
          // Standard d'abord (les gestes courants), puis les liaisons
          // cinématiques et mécaniques.
          { type: "select", key: "type", value: "coincidente",
            options: [["coincidente", "Coïncidente"],
                      ["concentrique", "Concentrique"],
                      ["parallele", "Parallèle"],
                      ["perpendiculaire", "Perpendiculaire"],
                      ["tangente", "Tangente"],
                      ["distance", "Distance"], ["angle", "Angle"],
                      ["verrouillage", "Verrouillage"],
                      ["pivot", "Pivot"],
                      ["cylindrique", "Cylindrique"],
                      ["glissiere", "Glissière"], ["rotule", "Rotule"],
                      ["engrenages", "Engrenages"],
                      ["cremaillere", "Crémaillère-pignon"],
                      ["vis", "Vis"], ["courroie", "Courroie"]] },
          { type: "number", key: "angle", label: t("Angle"), value: 90,
            unit: "°", showIf: (v) => v.type === "angle" },
          { type: "check", key: "flip", label: t("Opposé (retourner l'alignement)"),
            value: false,
            showIf: (v) => ["coincidente", "concentrique", "parallele",
              "distance", "tangente", "pivot", "cylindrique",
              "glissiere"].includes(v.type) },
          { type: "number", key: "distance",
            label: t("Distance / rayon 1 / pas"), value: 10,
            unit: "mm", min: 0,
            showIf: (v) => v.type === "distance"
              || MECHANICAL.includes(v.type) },
          { type: "number", key: "distance2", label: t("Rayon 2"), value: 10,
            unit: "mm", min: 0,
            showIf: (v) => ["engrenages", "courroie"].includes(v.type) },
          { type: "note",
            text: "Mécaniques : posez d'abord les pivots des deux " +
                  "composants, la contrainte couple ensuite leurs " +
                  "mouvements.",
            showIf: (v) => MECHANICAL.includes(v.type) },
          { type: "text", key: "angleMin", label: t("Angle min"), unit: "°",
            placeholder: t("aucune limite"),
            showIf: (v) => ["pivot", "cylindrique"].includes(v.type) },
          { type: "text", key: "angleMax", label: t("Angle max"), unit: "°",
            placeholder: t("aucune limite"),
            showIf: (v) => ["pivot", "cylindrique"].includes(v.type) },
          { type: "text", key: "lengthMin", label: t("Longueur min"),
            unit: "mm", placeholder: t("aucune limite"),
            showIf: (v) => ["glissiere", "cylindrique"].includes(v.type) },
          { type: "text", key: "lengthMax", label: t("Longueur max"),
            unit: "mm", placeholder: t("aucune limite"),
            showIf: (v) => ["glissiere", "cylindrique"].includes(v.type) },
        ] },
      { label: t("Élément 1"),
        rows: [{ type: "selection", key: "a", accepts: ["asmface"],
                 hint: t("Cliquez une face du premier composant") }] },
      { label: t("Élément 2"),
        rows: [{ type: "selection", key: "b", accepts: ["asmface"],
                 hint: t("Puis une face du second composant") }] },
    ],
    note: t("Le solveur natif repositionne les composants — le premier " +
          "inséré est fixé."),
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
    title: t("Répéter — {c}", { c: comp.label }),
    groups: [{
      label: t("Répétition"),
      rows: [
        { type: "number", key: "count", label: t("Occurrences"), value: 3,
          min: 2, step: 1 },
        { type: "number", key: "dx", label: t("Pas X"), value: 30,
          unit: "mm" },
        { type: "number", key: "dy", label: t("Pas Y"), value: 0,
          unit: "mm" },
        { type: "number", key: "dz", label: t("Pas Z"), value: 0,
          unit: "mm" },
      ],
    }],
    onApply: (v) => {
      const count = parseInt(v.count, 10);
      if (!(count >= 2)) { say("Au moins 2 occurrences", true); return; }
      refreshAssembly(call("array_component", {
        component: comp.name, count,
        dx: num(v.dx) ?? 0, dy: num(v.dy) ?? 0,
        dz: num(v.dz) ?? 0 }));
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
      title: t("Interférences"),
      groups: [{
        label: t("{n} interférence(s)", { n: result.interferences.length }),
        rows: [{ type: "list",
          items: result.interferences.map((p) => ({
            label: `${p.a} ↔ ${p.b} : ` +
              `${(p.volume_mm3 / 1000).toFixed(3)} cm³`,
          })) }],
      }],
      note: t("Volume commun réel (booléen OCCT) — à résoudre avant " +
            "impression."),
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
  startProgressWatch();
  let ok = false;
  try {
    const tree = await treePromise;
    if (gen !== viewGen) return;
    renderTree(tree);
    await updateViewport(gen);
    if (gen !== viewGen) return;
    ok = !lastClearedSelections;
  } catch (error) {
    if (gen !== viewGen) return;
    sayUntilAck(error.message);
  } finally {
    stopProgressWatch();
  }
  if (ok) say("À jour.");
}

document.getElementById("btn-new").addEventListener("click", () => {
  clearFeatureDims();
  refresh(call("new_part"));
});

document.getElementById("btn-undo").addEventListener("click", () =>
  refreshAny(call("undo")));
document.getElementById("btn-redo").addEventListener("click", () =>
  refreshAny(call("redo")));
document.getElementById("btn-rebuild").addEventListener("click", () => {
  clearFeatureDims();
  refresh(call("rebuild"));
});

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
    title: t("Équations"),
    groups: [
      {
        label: t("Variables globales"),
        rows: [{
          type: "list",
          empty: t("— aucune variable —"),
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
        label: t("Ajouter / modifier"),
        rows: [
          { type: "text", key: "name", label: t("Nom"),
            placeholder: t("Largeur") },
          { type: "text", key: "value", label: t("Valeur"),
            placeholder: "100" },
        ],
      },
    ],
    note: t("Utilisez « Variables.Nom » dans toute cote ou propriété — " +
          "ex. Variables.Largeur / 2. Retaper un nom existant le modifie."),
    onApply: async (v) => {
      const name = (v.name ?? "").trim();
      const value = num(v.value);
      if (!name || value === null) return;
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
    title: t("Évaluer"),
    groups: [
      { label: t("Propriétés de masse"),
        rows: [{ type: "list", items: [
          { label: t("Volume : {v} cm³",
            { v: fixed(props.volume_mm3 / 1000, 2) }) },
          { label: t("Masse : {m} g (à {d} g/cm³)",
            { m: fixed(props.mass_g), d: props.density }) },
          { label: t("Surface : {s} cm²", { s: fixed(props.area_mm2 / 100) }) },
          { label: t("Centre de gravité : ")
                   + props.center_of_mass.map((v) => fixed(v)).join(", ") },
          { label: t("Encombrement : ")
                   + props.bounding_box.map((v) => fixed(v)).join(" × ")
                   + " mm" },
        ] }] },
      { label: t("Matière"),
        rows: [{ type: "number", key: "density", label: t("Densité"),
                 value: lastDensity, unit: "g/cm³", min: 0.001 }] },
    ],
    note: t("PLA ≈ 1,24 · PETG ≈ 1,27 · ABS ≈ 1,04 · Alu ≈ 2,70 · " +
          "Acier ≈ 7,85 — OK recalcule avec la densité saisie"),
    onApply: (v) => {
      const density = num(v.density);
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

// Registry : un bind unique pour tous les panneaux « ouvrir → éditer →
// aperçu → OK ». Les panneaux bespoke (équations, assemblage, datum…)
// restent plus bas.
/** Panneau d'une fonction de `FEATURES` — ruban et palette du graphe.
 *  `sketchOverride` : profil imposé par la palette, sinon la sélection. */
function openFeaturePanel(entry, sketchOverride) {
  const ctx = {
    lastTree,
    selection: currentSelection,
    selectedSketch: sketchOverride ?? selectedSketch,
  };
  Object.defineProperty(ctx, "lastFaceHit", {
    get: () => lastFaceHit,
  });
  const blocked = entry.guard?.(ctx);
  if (blocked) { say(blocked, true); return; }
  const spline = selectedFaceId != null && meshGroups.some(
    (g) => g.faceId === selectedFaceId && g.spline);
  const spec = {
    icon: entry.icon,
    title: entry.title,
    groups: entry.groups(ctx),
    note: typeof entry.noteFn === "function"
      ? entry.noteFn(ctx, { spline })
      : entry.note,
    onApply: (v) => {
      const built = entry.build(v, ctx);
      if (!built) {
        const msg = typeof entry.invalid === "function"
          ? entry.invalid(v, ctx)
          : (entry.invalid ?? "Valeurs invalides");
        say(msg, true);
        return;
      }
      if (typeof entry.confirm === "function") {
        const question = entry.confirm(v, ctx);
        if (question && !confirm(question)) return;
      }
      const run = entry.refresh === "any" ? refreshAny : refresh;
      const gem = (ctx.lastTree?.gems ?? []).find(
        (item) => item.name === built.params?.tool);
      const stoneCount = gem?.count;
      const started = Date.now();
      const promise = call(built.op, built.params).then((tree) => {
        if (built.op === "add_boolean" && stoneCount) {
          rememberCombineFinished(stoneCount, (Date.now() - started) / 1000);
        }
        return tree;
      });
      if (entry.openGraphEditor) {
        run(promise.then((tree) => {
          queueMicrotask(() => {
            const created = latestGraphOrRepeat(tree);
            if (created) enterGraphFeature(created);
          });
          return tree;
        }));
      } else {
        run(promise);
      }
    },
  };
  if (entry.preview !== false) {
    spec.onChange = (v) => schedulePreview(entry.build(v, ctx));
  }
  panel.open(spec);
}

function bindFeature(entry) {
  const ids = entry.buttons ?? [entry.button];
  for (const id of ids) {
    const el = document.getElementById(id);
    if (!el || el.dataset.boundFeature) continue;
    el.dataset.boundFeature = "1";
    el.addEventListener("click", () =>
      featureCommand(() => openFeaturePanel(entry)));
  }
}

for (const entry of FEATURES) bindFeature(entry);

document.getElementById("btn-body").addEventListener("click", () =>
  featureCommand(() => {
    const name = prompt("Nom du nouveau corps :", "Corps");
    if (name === null) return;
    refresh(call("add_body", name.trim() ? { name: name.trim() } : {}));
  }));

document.getElementById("btn-datum").addEventListener("click", () =>
  featureCommand(() => panel.open({
    icon: "PartDesign_Plane.svg",
    title: t("Plan de référence"),
    groups: [
      {
        label: t("Référence"),
        rows: [
          { type: "selection", key: "sel", accepts: ["face"],
            hint: t("Cliquez une face — ou choisissez un plan ci-dessous"),
            value: currentSelection(["face"]) },
          { type: "select", key: "base", value: "XY", label: t("Plan"),
            options: [["XZ", "Plan de face"], ["XY", "Plan de dessus"],
                      ["YZ", "Plan de droite"]] },
        ],
      },
      {
        label: t("Position"),
        rows: [
          { type: "number", key: "offset", label: t("Décalage"), value: 20,
            unit: "mm" },
          { type: "number", key: "angle", label: t("Angle"), value: 0,
            unit: "°" },
        ],
      },
    ],
    onApply: (v) => {
      const params = {
        offset: num(v.offset) ?? 0,
        angle: num(v.angle) ?? 0,
      };
      if (v.sel && v.sel.face != null) params.face = v.sel.face;
      else params.base = v.base;
      refresh(call("add_datum_plane", params));
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
      ? t("Importé — {n} solide(s), la forme est la base du corps.",
        { n: tree.imported_solids })
      : tree.bodies_in_file > 1
        ? t("Ouvert — {n} corps dans le fichier.", { n: tree.bodies_in_file })
        : t("Ouvert."));
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
    say(t("Enregistré : {path} — ouvrable dans FreeCAD standard.", { path: saved.path }));
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
    say(t("Exporté : {path} ({size} Ko)", { path: out.path, size: (out.size / 1024).toFixed(1) }));
  } catch (error) {
    say(error.message, true);
  }
});

document.getElementById("btn-selftest").addEventListener("click", async () => {
  const gen = ++viewGen;
  try {
    say("Autotest en cours…");
    const report = await call("selftest");
    if (gen !== viewGen) return;
    renderTree(report.tree_after_pad);
    await updateViewport(gen);
    if (gen !== viewGen) return;
    const bilan = report.bilan;
    const echecs = Array.isArray(bilan?.echecs) ? bilan.echecs : [];
    if (bilan && typeof bilan.verifications === "number"
        && typeof bilan.ok === "number") {
      const failed = echecs.length > 0;
      const nSteps = Array.isArray(report.steps) ? report.steps.length : 0;
      say(t("Autotest : {n} étapes, {ok}/{total} vérifications — {result}",
        { n: nSteps, ok: bilan.ok, total: bilan.verifications,
          result: failed ? t("ÉCHEC") : "OK" }), failed);
      if (failed) {
        panel.open({
          icon: "view-measurement.svg",
          title: t("Autotest"),
          noApply: true,
          groups: [{
            label: t("Indicateurs en échec"),
            rows: echecs.map((name) => ({ type: "note", text: name })),
          }],
        });
      }
    } else {
      say(t("Autotest OK — {faces} faces, {tris} triangles, reparam {result}",
        { faces: report.mesh_faces, tris: report.mesh_triangles,
          result: report.m0_reparam_ok ? "OK" : t("ÉCHEC") }));
    }
    console.log("selftest", report);
  } catch (error) {
    if (gen !== viewGen) return;
    say(t("Autotest : ") + error.message, true);
  }
});

// ---------- sketch mode ----------

const sketchMode = createSketchMode(
  { scene, camera, renderer, controls, call, say, refresh, panel, boxOverlay });

pluginRuntime = createPluginApi({
  call, refresh, say,
  tree: () => lastTree,
  scene, camera, controls, renderer,
  addRibbon: addPluginRibbon,
  addFeature: addPluginFeature,
  addHud: addPluginHud,
});

// ---------- boot ----------

call("ping")
  .then(async (info) => {
    await loadClientPlugins(call, pluginRuntime.api);
    for (const entry of FEATURES) bindFeature(entry);
    say(t("Moteur prêt — FreeCAD {v}", { v: info.freecad }));
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
