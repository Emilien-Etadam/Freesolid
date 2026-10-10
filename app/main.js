// FreeSolid app — M0. One part, one mesh, a SolidWorks-shaped tree,
// face picking by construction (each engine face is an index group).

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { createSketchMode, createDimSprite } from "./sketch.js";
import {
  dimEditPayload, dimLabel, filletRadiusLabel, openDimEditor, sketchDimAnchor,
} from "./dims.js";
import { createPropertyPanel, panelNotice } from "./panel.js";
import { num } from "./num.js";
import { eventToNdc, ndcToScreen } from "./screen.js";
import { cssHex, readScene } from "./theme.js";
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
import { installContextMenu } from "./contextmenu.js";
import { installMeasure } from "./measure.js";
import { VIEW_KEYS, VIEWS, installViewCube } from "./viewcube.js";
import { installAssembly } from "./assembly.js";
import { installGraphView } from "./graphview.js";
import { currentPaneIndex, layoutPanes, paneRect } from "./layouts.js";
import { perspectiveFrustum } from "./projection.js";
import { createSceneLook } from "./scenelook.js";
import {
  coordsText, editModeText, measureText, sketchEntityLength,
} from "./statusbar.js";
import { createPluginApi, loadClientPlugins } from "./plugins.js";
import { createSettingsDialog, ISSUES_URL, readLang } from "./settings.js";
import { installMenuBar, menuBarModel } from "./menubar.js";
import { installCommandSearch, installShortcutBar } from "./shortcutbar.js";
import { installFileDialog } from "./filedialog.js";
import { installWelcome, rememberRecent } from "./welcome.js";
import {
  boxMode, coverBounds, isDrag, middleAction, normalizeRect, nudgeView,
  pickInBox, readReverseWheel, writeReverseWheel, zoomSpeedFor,
} from "./navigation.js";
import { currentLang, setLang, t, translateDom } from "./i18n.js";
import { renameClickAction } from "./rename.js";

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
  isGraphFeature,
  isRepeatFeature,
  latestGraphOrRepeat,
} from "./graph.js";

const sceneTheme = readScene();

// Le ruban du noyau est rendu depuis ribbon.json avant tout câblage :
// les getElementById("btn-…") plus bas supposent les boutons présents.
// La table onglet → bandeau est complétée par les plugins (addPluginRibbon).
const RIBBONS = installCoreRibbons(document, RIBBON_LAYOUT);

const statusEl = document.getElementById("status");
const pickEl = document.getElementById("pick");
const measureEl = document.getElementById("measure");
const coordsEl = document.getElementById("coords");
const editModeEl = document.getElementById("edit-mode");
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
    clearFilletRadiusBubble();
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
const look = createSceneLook(THREE, scene, sceneTheme);

// Hauteur du frustum (unités monde) à zoom = 1. Le zoom OrbitControls
// et « Zoom au mieux » ajustent camera.zoom, pas la distance.
const ORTHO_HEIGHT = 200;

/** Caméra de vue : pilotée comme une vue orthographique (zoom,
 *  panoramique, cadrage), elle projette en perspective quand
 *  ``perspective`` est vrai (projection.js). ``focus`` : le centre de la
 *  vue, d'où se mesure le recul de l'œil. */
class ViewCamera extends THREE.OrthographicCamera {
  constructor(...args) {
    super(...args);
    this.perspective = false;
    this.focus = null;
  }

  updateProjectionMatrix() {
    super.updateProjectionMatrix();
    if (!this.perspective || !this.focus) return;
    const f = perspectiveFrustum({
      width: (this.right - this.left) / this.zoom,
      height: (this.top - this.bottom) / this.zoom,
      rigDistance: this.position.distanceTo(this.focus),
    });
    this.projectionMatrix
      .makePerspective(f.left, f.right, f.top, f.bottom, f.near, f.far)
      .multiply(new THREE.Matrix4().makeTranslation(0, 0, -f.back));
    this.projectionMatrixInverse.copy(this.projectionMatrix).invert();
  }
}

// Le lancer de rayons de three.js choisit rayons parallèles ou divergents
// selon le type de caméra ; la caméra de vue est « orthographique » pour
// les contrôles, donc on lui donne ici le rayon de sa vraie projection.
{
  const baseSetFromCamera = THREE.Raycaster.prototype.setFromCamera;
  THREE.Raycaster.prototype.setFromCamera = function setFromCamera(coords, cam) {
    if (!cam?.perspective) return baseSetFromCamera.call(this, coords, cam);
    this.camera = cam;
    this.ray.origin.set(coords.x, coords.y, -1).unproject(cam);
    this.ray.direction.set(coords.x, coords.y, 1).unproject(cam)
      .sub(this.ray.origin).normalize();
  };
}

const camera = new ViewCamera(
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
const paneCamera = new ViewCamera(-1, 1, 1, -1, 0.1, 10000);

/** Taille en pixels de la fenêtre active. */
function viewSize() {
  const width = container.clientWidth, height = container.clientHeight;
  if (panes.length < 2) return { width, height };
  return paneRect(panes[activePane], width, height);
}

const controls = new OrbitControls(camera, renderer.domElement);
camera.focus = controls.target;
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
  new THREE.PointsMaterial({ color: sceneTheme.selection, size: 10,
    sizeAttenuation: false, depthTest: false }));
pivotMarker.visible = false;
pivotMarker.renderOrder = 30;
scene.add(pivotMarker);

function pickPivot(event) {
  const rect = renderer.domElement.getBoundingClientRect();
  const ndc = eventToNdc(event.clientX, event.clientY, rect);
  const at = new THREE.Vector2(ndc.x, ndc.y);
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
  const screen = ndcToScreen(mid.x, mid.y, rect);
  return {
    name: lines.userData.sketch?.name ?? null,
    label: lines.userData.sketch?.label ?? null,
    x: screen.x,
    y: screen.y,
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
  const screen = ndcToScreen(projected.x, projected.y, rect);
  return {
    name: mesh.userData.surface?.name ?? null,
    label: mesh.userData.surface?.label ?? null,
    x: screen.x,
    y: screen.y,
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
  return ndcToScreen(projected.x, projected.y, rect);
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
    return ndcToScreen(p.x, p.y, rect);
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

const baseMaterial = new THREE.MeshStandardMaterial({
  color: sceneTheme.part, metalness: 0.08, roughness: 0.5,
  transparent: true, opacity: 1, // l'aperçu jaune estompe la pièce
  polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1,
});
const hoverMaterial = new THREE.MeshStandardMaterial({
  color: sceneTheme.accent, metalness: 0.08, roughness: 0.45,
  polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1,
});
const selectedMaterial = new THREE.MeshStandardMaterial({
  color: sceneTheme.selection, metalness: 0.08, roughness: 0.45,
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
  color: sceneTheme.partMuted, metalness: 0.1, roughness: 0.7,
  transparent: true, opacity: 0.45, depthWrite: false,
});
// Surfaces : même teinte que le solide, DoubleSide (peau ouverte).
const surfaceHoverMaterial = hoverMaterial.clone();
surfaceHoverMaterial.side = THREE.DoubleSide;
const surfaceSelectedMaterial = selectedMaterial.clone();
surfaceSelectedMaterial.side = THREE.DoubleSide;
const curvesMaterial = new THREE.LineBasicMaterial({ color: sceneTheme.curve });
const sketchesMaterial = new THREE.LineBasicMaterial({ color: sceneTheme.sketch });
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
const edgeBaseMaterial = new THREE.LineBasicMaterial({ color: sceneTheme.edge });
const edgeHoverMaterial = new THREE.LineBasicMaterial({ color: sceneTheme.accent });
const edgeSelectedMaterial = new THREE.LineBasicMaterial({ color: sceneTheme.selection });
const hiddenEdgeMaterial = new THREE.LineBasicMaterial({
  color: sceneTheme.edgeFaint,
  depthFunc: THREE.GreaterEqualDepth,
});
const maskMaterial = new THREE.MeshBasicMaterial({
  colorWrite: false,
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
  color: sceneTheme.selection, depthTest: false,
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
  ctx.fillStyle = cssHex(sceneTheme.dim);
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
  const { center, radius } = partCenterRadius();
  look.fitGrid(center, radius);
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
      color: sceneTheme.accent, transparent: true, opacity: 0.1,
      side: THREE.DoubleSide, depthWrite: false });
    fillMaterial.userData.own = true;
    const fill = new THREE.Mesh(
      new THREE.PlaneGeometry(size, size), fillMaterial);
    fill.userData.plane = id;
    const borderMaterial = new THREE.LineBasicMaterial(
      { color: sceneTheme.accent, transparent: true, opacity: 0.6 });
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
  const axes = [[1, 0, 0, sceneTheme.axisX], [0, 1, 0, sceneTheme.axisY], [0, 0, 1, sceneTheme.axisZ]];
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
  camera.perspective = !!displayState.perspective;
  camera.updateProjectionMatrix();
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
      fx.faces && !fx.mask ? sceneTheme.edge : sceneTheme.edgeOnBg);
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
  menu.querySelector("[data-projection]")?.classList.toggle(
    "on", !!displayState.perspective);
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
    if (event.target.closest("[data-projection]")) {
      setDisplay({ perspective: !displayState.perspective });
      closeViewMenus();
      return;
    }
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
  color: sceneTheme.ghost, metalness: 0.1, roughness: 0.5,
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

function showGhost(mesh, { bothSides = false } = {}) {
  if (ghostMesh) {
    ghostMesh.removeFromParent();
    ghostMesh.geometry.dispose();
    ghostMesh = null;
  }
  if (!mesh.indices.length) return;
  const geometry = new THREE.BufferGeometry();
  applyPackedGeometry(geometry, mesh);
  // Le congé OCCT renvoie la face arrondie avec des normales vers
  // l'intérieur : en FrontSide elle reste une bande sombre. DoubleSide
  // l'éclaire. Les autres aperçus gardent FrontSide.
  ghostMaterial.side = bothSides ? THREE.DoubleSide : THREE.FrontSide;
  ghostMaterial.needsUpdate = true;
  ghostMesh = new THREE.Mesh(geometry, ghostMaterial);
  volumesGroup.add(ghostMesh);
  applyVolumeVisibility();
  baseMaterial.opacity = 0.15; // la pièce s'efface derrière le résultat
  if (partBaseMaterial) partBaseMaterial.opacity = 0.15;
}

// Bulle « R = … » pendant le congé, près de l'arête choisie.
const filletBubbleGroup = new THREE.Group();
filletBubbleGroup.renderOrder = 24;
scene.add(filletBubbleGroup);
let filletRadiusSprite = null;

function clearFilletRadiusBubble() {
  if (!filletRadiusSprite) return;
  filletRadiusSprite.removeFromParent();
  const material = filletRadiusSprite.material;
  material.map?.dispose();
  material.dispose();
  filletRadiusSprite = null;
}

function selectedEdgeCenter(edgeId) {
  if (!partEdges) return null;
  const position = partEdges.geometry.getAttribute("position");
  const index = partEdges.geometry.index;
  if (!position || !index) return null;
  let x = 0, y = 0, z = 0, count = 0;
  partEdges.geometry.groups.forEach((group, i) => {
    if (edgeGroups[i]?.edgeId !== edgeId) return;
    for (let k = group.start; k < group.start + group.count; k++) {
      const vertex = index.getX(k);
      x += position.getX(vertex);
      y += position.getY(vertex);
      z += position.getZ(vertex);
      count++;
    }
  });
  return count ? new THREE.Vector3(x / count, y / count, z / count) : null;
}

function filletBubbleAnchor(sel) {
  if (sel?.kind === "edges" && sel.edges?.length) {
    return selectedEdgeCenter(sel.edges[0]);
  }
  if (sel?.kind === "face" && lastFaceHit && lastFaceHit.face === sel.face) {
    return new THREE.Vector3(lastFaceHit.x, lastFaceHit.y, lastFaceHit.z);
  }
  return null;
}

function updateFilletRadiusBubble(values) {
  clearFilletRadiusBubble();
  const text = filletRadiusLabel(values?.radius);
  const anchor = filletBubbleAnchor(values?.sel);
  if (!text || !anchor) return;
  const towardCamera = camera.position.clone().sub(controls.target);
  if (towardCamera.lengthSq() > 1e-8) {
    anchor.add(towardCamera.normalize().multiplyScalar(8));
  }
  filletRadiusSprite = createDimSprite(text, anchor.x, anchor.y, anchor.z);
  filletRadiusSprite.renderOrder = 24;
  filletBubbleGroup.add(filletRadiusSprite);
}

function focusPanelField(key) {
  const input = document.querySelector(`#panel input[data-key="${key}"]`);
  if (!input) return false;
  input.focus();
  input.select();
  return true;
}

function pickFilletRadiusBubble(event) {
  if (!filletRadiusSprite) return false;
  const rect = renderer.domElement.getBoundingClientRect();
  const projected = filletRadiusSprite.position.clone().project(camera);
  const screen = ndcToScreen(projected.x, projected.y, rect);
  const sx = screen.x;
  const sy = screen.y;
  return Math.hypot(sx - event.clientX, sy - event.clientY) < 28;
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
      showGhost(mesh, { bothSides: built.op === "add_fillet" });
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
  const ndc = eventToNdc(event.clientX, event.clientY, rect);
  pointer.x = ndc.x;
  pointer.y = ndc.y;
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
  updateHover(event);
});

// Dernière position où le survol a été calculé : un appui ailleurs (le
// pointeur arrivé sans mouvement, après un menu ou une fenêtre) le
// recalcule d'abord, sinon le clic viserait l'ancien survol.
let hoverAt = null;

/** Face, arête, esquisse, surface ou plan sous le pointeur. */
function updateHover(event) {
  hoverAt = { x: event.clientX, y: event.clientY };
  setPointerFromEvent(event);
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
  if (!partMesh && !sketchLineMeshes.length && !surfaceMeshes.length) {
    coordsEl.textContent = "";
    return;
  }
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
    let pointHit = edgeGroupIndex >= 0 ? edgeHit : faceHit;
    if (surfHit) {
      const solidHit = edgeGroupIndex >= 0 ? edgeHit : faceHit;
      if (!solidHit || surfHit.distance < solidHit.distance) {
        surfaceHit = surfHit.object.userData.surface;
        groupIndex = -1;
        edgeGroupIndex = -1;
        pointHit = surfHit;
      }
    }
    // Barre d'état : coordonnées du point visé sur la pièce.
    coordsEl.textContent = coordsText(pointHit?.point ?? null);
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
}

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
  measureEl.textContent = measureText([...selectedEdges].map((id) =>
    edgeGroups.find((g) => g.edgeId === id)?.length));
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
      points.push(ndcToScreen(v.x, v.y, host));
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
  if (!assemblyState
      && (hoverAt?.x !== event.clientX || hoverAt?.y !== event.clientY)) {
    updateHover(event);
  }
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

  if (onMeasurePointerUp()) return;

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
    const screen = ndcToScreen(projected.x, projected.y, rect);
    const sx = screen.x;
    const sy = screen.y;
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
  if (pickFilletRadiusBubble(event)) {
    focusPanelField("radius");
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
    paneCamera.perspective = camera.perspective;
    paneCamera.focus = state.target;
    paneCamera.up.copy(state.up);
    paneCamera.position.copy(state.position);
    paneCamera.zoom = state.zoom;
    paneCamera.lookAt(state.target);
    setOrthoFrustum(paneCamera, width, height);
    paneCamera.updateProjectionMatrix();
    look.follow(paneCamera);
    view.renderer.render(scene, paneCamera);
  }
}

renderer.setAnimationLoop(() => {
  controls.update();
  tickExplode();
  // En perspective, le recul de l'œil suit la distance au centre de la vue
  // (cadrage, panoramique) : la projection se recalcule à chaque image.
  if (camera.perspective) camera.updateProjectionMatrix();
  look.follow(camera);
  renderer.render(scene, camera);
  renderExtraViews();
});

// État partagé des modules. Les accesseurs lisent la variable actuelle,
// y compris celles déclarées plus bas.
const ctx = {};

function expose(name, get, set) {
  Object.defineProperty(ctx, name, {
    get, set, enumerable: true, configurable: true,
  });
}

// ---------- vues standard et boîte d'orientation ----------

expose("partMesh", () => partMesh);
expose("partEdges", () => partEdges);
expose("selectedFaceId", () => selectedFaceId);
expose("lastFaceHit", () => lastFaceHit);
expose("selectedPlane", () => selectedPlane);
Object.assign(ctx, {
  THREE, camera, controls, viewSize, ORTHO_HEIGHT, say, setLayout, container,
});
const {
  partCenterRadius, frameView, frameSketch, viewNormalTo,
  openOrientBox, closeOrientBox, orientBoxOpen,
} = installViewCube(ctx);

function applyViewNudge(event) {
  const next = nudgeView({
    position: camera.position.toArray(),
    target: controls.target.toArray(),
    up: camera.up.toArray(),
    key: event.key,
    ctrl: event.ctrlKey || event.metaKey,
    alt: event.altKey,
    shift: event.shiftKey,
    viewHeight: (camera.top - camera.bottom) / (camera.zoom || 1),
  }, { rotateLocked: sketchMode.active });
  if (!next) return false;
  event.preventDefault();
  camera.position.fromArray(next.position);
  controls.target.fromArray(next.target);
  camera.up.fromArray(next.up);
  camera.lookAt(controls.target);
  return true;
}

document.addEventListener("keydown", (event) => {
  if (event.key === "F2" && !event.repeat
      && !/^(INPUT|SELECT|TEXTAREA)$/.test(event.target.tagName)) {
    event.preventDefault();
    beginRenameSelected();
    return;
  }
  if (sketchMode.active) {
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(event.target.tagName)) return;
    if (applyViewNudge(event)) return;
    if ((event.key === "f" || event.key === "F")
        && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault();
      frameSketch();
    } else if ((event.key === "z" || event.key === "Z")
               && !event.ctrlKey && !event.metaKey && !event.altKey) {
      camera.zoom *= event.shiftKey ? 1.25 : 0.8;
      camera.updateProjectionMatrix();
    }
    return;
  }
  // Typing in a panel field must not trigger view shortcuts (F, Ctrl+1…).
  if (/^(INPUT|SELECT|TEXTAREA)$/.test(event.target.tagName)) return;
  if (applyViewNudge(event)) return;
  if (event.key !== "Escape" && pluginRuntime?.dispatchKey(event)) return;
  if (event.key === " " && !event.ctrlKey && !event.metaKey && !event.altKey) {
    event.preventDefault();
    if (orientBoxOpen()) closeOrientBox();
    else openOrientBox();
    return;
  }
  if (event.key === "Escape" && orientBoxOpen()) {
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
    cancelMeasure();
  } else if (event.key === "Escape"
      && !document.getElementById("script-trust")?.hidden) {
    event.preventDefault();
    document.getElementById("script-trust-deny")?.click();
  } else if (graphHandleEscape(event)) {
    // consommé par la vue en graphe
  } else if (pluginRuntime?.dispatchKey(event)) {
    return;
  } else if (graphHandleDelete(event)) {
    // consommé par la vue en graphe
  }
});

let welcomeApi = null;

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
    } else if (name === "home") {
      welcomeApi?.showWelcome();
    } else if (name === "create") {
      welcomeApi?.showNew();
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
    color: sceneTheme.accent, transparent: true, opacity: 0.14,
    side: THREE.DoubleSide, depthWrite: false });
  fillMaterial.userData.own = true;
  const fill = new THREE.Mesh(
    new THREE.PlaneGeometry(size, size), fillMaterial);
  const borderMaterial = new THREE.LineBasicMaterial(
    { color: sceneTheme.accent, transparent: true, opacity: 0.7 });
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
  if (bodyInfo.name) {
    bodyItem.dataset.feat = bodyInfo.name;
    if (!bodyInfo.active) bodyItem.title = t("Clic : activer ce corps");
    bodyItem.addEventListener("click", (event) => {
      if (consumeTreeRenameClick(event, bodyItem, bodyInfo)) return;
      if (!bodyInfo.active) {
        refresh(call("set_active_body", { body: bodyInfo.name }));
      }
    });
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
  item.dataset.feat = surface.name;
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
  item.addEventListener("click", (event) => {
    if (consumeTreeRenameClick(event, item, surface)) return;
    onSurfaceClick(surface);
  });
  item.addEventListener("dblclick", () => onSurfaceDblClick(surface));
  item.addEventListener("contextmenu", (event) => openMenu(event, surface));
  treeEl.appendChild(item);
  if (hasChildren && expandedFeatures.has(surface.name)) {
    for (const child of children) {
      const row = document.createElement("li");
      row.className = "child" + (inFolder ? " in-folder" : "")
        + (child.error ? " error" : "")
        + (rolledBack ? " rolled-back" : "");
      row.dataset.feat = child.name;
      row.appendChild(treeIcon("Sketcher_Sketch.svg"));
      row.appendChild(document.createTextNode(child.label));
      row.title = `${child.kind} — `
        + t("double-clic : modifier l'esquisse · clic droit : modifier");
      row.addEventListener("dblclick", () => onSketchRowDblClick(child));
      row.addEventListener("contextmenu", (event) => openMenu(event, child));
      row.addEventListener("click", (event) => {
        if (consumeTreeRenameClick(event, row, child)) return;
        onSketchRowClick(child);
      });
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
let treeRenameClick = { name: null, at: null };
let renameState = null;

function consumeTreeRenameClick(event, row, feature) {
  if (!feature?.name || event.target.closest(".arrow, input")) return false;
  const action = renameClickAction({
    previousAt: treeRenameClick.at,
    sameRow: treeRenameClick.name === feature.name,
    now: Date.now(),
    moved: false,
    dragging: row.classList.contains("dragging") || suppressTreeClick,
  });
  treeRenameClick = { name: feature.name, at: Date.now() };
  if (action === "select") {
    for (const item of treeEl.querySelectorAll("li.sel")) {
      if (item !== row) item.classList.remove("sel");
    }
    row.classList.add("sel");
  }
  if (action === "rename") {
    event.stopPropagation();
    beginInlineRename(row, feature);
    return true;
  }
  return action === "ignore";
}

function rowLabelNode(row) {
  const nodes = [...row.childNodes].filter(
    (node) => node.nodeType === Node.TEXT_NODE && node.textContent.trim());
  return nodes.at(-1) ?? null;
}

function beginInlineRename(row, feature) {
  if (!row || !feature?.name || !feature.label) return;
  if (renameState?.input?.isConnected) commitInlineRename();
  if (row.querySelector("input.tree-rename")) return;
  const text = rowLabelNode(row);
  if (!text) return;
  const shown = text.textContent;
  const input = document.createElement("input");
  input.type = "text";
  input.className = "tree-rename";
  input.value = feature.label;
  input.setAttribute("aria-label", t("Nouveau nom :"));
  text.replaceWith(input);
  renameState = { input, feature, shown };
  input.addEventListener("keydown", (event) => {
    event.stopPropagation();
    if (event.key === "Enter") {
      event.preventDefault();
      commitInlineRename();
    } else if (event.key === "Escape") {
      event.preventDefault();
      cancelInlineRename();
    }
  });
  input.addEventListener("blur", () => {
    if (renameState?.input === input) commitInlineRename();
  });
  input.focus();
  input.select();
}

function finishRenameField(input, shown) {
  if (input.isConnected) input.replaceWith(document.createTextNode(shown));
}

function commitInlineRename() {
  if (!renameState) return;
  const state = renameState;
  renameState = null;
  const label = state.input.value.trim();
  if (!label || label === state.feature.label) {
    finishRenameField(state.input, state.shown);
    return;
  }
  finishRenameField(state.input, label);
  refreshAny(call("rename", { feature: state.feature.name, label }));
}

function cancelInlineRename() {
  if (!renameState) return;
  const state = renameState;
  renameState = null;
  finishRenameField(state.input, state.shown);
}

function treeRowFor(name) {
  if (!name) return null;
  return treeEl.querySelector(`li[data-feat="${CSS.escape(name)}"]`);
}

function renameRecord(name) {
  return findFeatureInTree(lastTree, name)
    ?? (lastTree?.bodies ?? []).find((body) => body.name === name)
    ?? null;
}

function beginRenameSelected() {
  if (treeEl.querySelector("li.dragging")) return;
  const clicked = treeRenameClick.name ? treeRowFor(treeRenameClick.name) : null;
  const row = clicked?.classList.contains("sel")
    ? clicked
    : treeEl.querySelector("li.sel[data-feat]");
  if (!row) return;
  const feature = renameRecord(row.dataset.feat);
  if (!feature?.label) return;
  beginInlineRename(row, feature);
}
treeEl.addEventListener("click", (event) => {
  if (!suppressTreeClick) return;
  suppressTreeClick = false;
  event.stopPropagation();
  event.preventDefault();
}, true);

function bindFeatureDrag(row, feature) {
  row.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || panel.active || sketchMode.active) return;
    if (event.target.closest("input")) return;
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
  welcomeApi?.hideWelcome();
  clearAssemblyView(); // un arbre de pièce = le mode assemblage s'efface
  dropRolledBackSelection(tree);
  lastTree = tree;
  updateEditMode();
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
    row.addEventListener("click", (event) => {
      if (consumeTreeRenameClick(event, row, feature)) return;
      onDatumRow(feature);
    });
    row.addEventListener("mouseenter", () => refreshDatumGhost(feature));
    row.addEventListener("mouseleave", () => refreshDatumGhost(null));
  }
  if (feature.type === "Sketcher::SketchObject") {
    if (selectedSketch?.name === feature.name) row.classList.add("sel");
    row.addEventListener("click", (event) => {
      if (consumeTreeRenameClick(event, row, feature)) return;
      onSketchRowClick(feature);
    });
  } else if (feature.type !== "PartDesign::Plane") {
    row.addEventListener("click", (event) => {
      if (consumeTreeRenameClick(event, row, feature)) return;
      selectedFeatureName = feature.name;
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
      childRow.dataset.feat = child.name;
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
      childRow.addEventListener("click", (event) => {
        if (consumeTreeRenameClick(event, childRow, child)) return;
        onSketchRowClick(child);
      });
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
  CapThickness: ["Épaisseur des extrémités", "mm"],
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

// ---------- menus contextuels (arbre et zone graphique) ----------
// Lu à l'appel : certaines variables sont déclarées plus bas.

expose("assemblyState", () => assemblyState, (v) => { assemblyState = v; });
expose("measuring", () => measuring, (v) => { measuring = v; });
expose("planePicking", () => planePicking, (v) => { planePicking = v; });
expose("hoveredEdgeGroup", () => hoveredEdgeGroup, (v) => { hoveredEdgeGroup = v; });
expose("edgeGroups", () => edgeGroups, (v) => { edgeGroups = v; });
expose("hoveredSketch", () => hoveredSketch, (v) => { hoveredSketch = v; });
expose("hoveredSurface", () => hoveredSurface, (v) => { hoveredSurface = v; });
expose("hoveredGroup", () => hoveredGroup, (v) => { hoveredGroup = v; });
expose("meshGroups", () => meshGroups, (v) => { meshGroups = v; });
expose("lastTree", () => lastTree, (v) => { lastTree = v; });
expose("originShown", () => originShown, (v) => { originShown = v; });
expose("selectedSketch", () => selectedSketch, (v) => { selectedSketch = v; });
expose("sketchMode", () => sketchMode);

Object.assign(ctx, {
  call, refresh, refreshAny, refreshAssembly,
  hexColor, sceneTheme, confirm,
  onSketchRowDblClick, editSurface, editFeature,
  treeRowFor, beginInlineRename,
  findFeatureInTree,
  frameView, openOrientBox, toggleOrigin, viewNormalTo,
  selectSketch, onSurfaceDblClick,
  panel, container, renderer,
});

const { openMenu, showContextToolbar, hideContextToolbar } = installContextMenu(ctx);

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

/** Lâche la face choisie pour l'esquisse. La pièce reprend sa couleur,
 *  la barre d'état ne dit plus « sél. Face n », et rien n'est restauré
 *  à la sortie. */
function releaseFaceSelection() {
  selectedFaceId = null;
  hoveredGroup = -1;
  hoveredEdgeGroup = -1;
  repaintGroups();
  repaintEdges();
}

document.addEventListener("freesolid:sketch-enter", () => {
  releaseFaceSelection();
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
  updateEditMode();
});
document.addEventListener("freesolid:sketch-pointer", (event) => {
  coordsEl.textContent = coordsText(event.detail);
});
document.addEventListener("freesolid:sketch-selection", (event) => {
  measureEl.textContent = measureText(event.detail.map(sketchEntityLength));
});

/** Barre d'état : ce qu'on édite (esquisse, assemblage ou pièce). */
function updateEditMode() {
  const editing = sketchMode.editing;
  const label = (name) => {
    const items = (lastTree?.features ?? []).flatMap(
      (f) => [f, ...(f.children ?? [])]);
    return items.find((f) => f.name === name)?.label ?? name;
  };
  editModeEl.textContent = editModeText({
    sketch: editing ? label(editing) : null,
    assembly: !!assemblyState,
    part: lastTree?.body ?? null,
  });
}
document.addEventListener("freesolid:sketch-exit", () => {
  coordsEl.textContent = "";
  measureEl.textContent = "";
  queueMicrotask(updateEditMode);
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

// ---------- vue en graphe ----------
// Relais : ces noms sont appelés avant cette ligne (clavier, arbre, menu).
// Le corps est dans graphview.js, branché juste en dessous.

let graphOpen = false;
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
let closeGraphImpl = null;
let enterGraphFeatureImpl = null;
let syncGraphFromTreeImpl = null;
let deleteFeatureWithConfirmImpl = null;
let graphHandleEscapeImpl = null;
let graphHandleDeleteImpl = null;

function closeGraph() {
  return closeGraphImpl();
}
function enterGraphFeature(feature) {
  return enterGraphFeatureImpl(feature);
}
function syncGraphFromTree() {
  return syncGraphFromTreeImpl();
}
function deleteFeatureWithConfirm(feature) {
  return deleteFeatureWithConfirmImpl(feature);
}
function graphHandleEscape(event) {
  return graphHandleEscapeImpl(event);
}
function graphHandleDelete(event) {
  return graphHandleDeleteImpl(event);
}

expose("graphOpen", () => graphOpen, (v) => { graphOpen = v; });
expose("graphFn", () => graphFn, (v) => { graphFn = v; });
expose("selectedDatumFeature", () => selectedDatumFeature);
expose("selectedSurface", () => selectedSurface);
Object.assign(ctx, {
  TREE_ICONS,
  say, call, refresh, refreshAny, confirm, PROP_LABELS,
  featureCommand, openMenu, editFeature, renderTree, updateViewport,
  onSketchRowClick, onDatumRow, onSurfaceClick, onPlaneRow,
  onSketchRowDblClick, onSurfaceDblClick,
  openEquationsPanel, openFeaturePanel, currentSelection,
});
const graphApi = installGraphView(ctx);
closeGraphImpl = graphApi.closeGraph;
enterGraphFeatureImpl = graphApi.enterGraphFeature;
syncGraphFromTreeImpl = graphApi.syncGraphFromTree;
deleteFeatureWithConfirmImpl = graphApi.deleteFeatureWithConfirm;
graphHandleEscapeImpl = graphApi.graphHandleEscape;
graphHandleDeleteImpl = graphApi.graphHandleDelete;

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

// ---------- assemblage ----------
// Relais : ces noms sont appelés avant cette ligne (menu, boot). Le corps
// est dans assembly.js, branché juste en dessous.

let assemblyState = null;      // dernier assembly_tree, ou null (mode pièce)
let asmGroup = null;
let refreshAnyImpl = null;
let refreshAssemblyImpl = null;
let showAssemblyMeshesImpl = null;
let renderAssemblyTreeImpl = null;
let selectComponentImpl = null;
let clearAssemblyViewImpl = null;

async function refreshAny(treePromise) {
  return refreshAnyImpl(treePromise);
}
async function refreshAssembly(treePromise) {
  return refreshAssemblyImpl(treePromise);
}
function showAssemblyMeshes(data) {
  return showAssemblyMeshesImpl(data);
}
function renderAssemblyTree(tree) {
  return renderAssemblyTreeImpl(tree);
}
function selectComponent(name) {
  return selectComponentImpl(name);
}
function clearAssemblyView() {
  return clearAssemblyViewImpl();
}

expose("asmGroup", () => asmGroup, (v) => { asmGroup = v; });
expose("viewGen", () => viewGen, (v) => { viewGen = v; });
expose("lastClearedSelections", () => lastClearedSelections, (v) => { lastClearedSelections = v; });
expose("welcomeApi", () => welcomeApi, (v) => { welcomeApi = v; });
Object.assign(ctx, {
  THREE, scene, sceneTheme, showMesh, showEdgeLines,
  selectedMaterial, baseMaterial,
  call, say, sayUntilAck, panel, prompt,
  startProgressWatch, stopProgressWatch,
  renderTree, updateViewport, treeEl, treeIcon, openMenu,
  closeGraph, updateEditMode, pickEl, clearGhost,
  renderer, raycaster, pointer, camera, setPointerFromEvent,
});
const assemblyApi = installAssembly(ctx);
refreshAnyImpl = assemblyApi.refreshAny;
refreshAssemblyImpl = assemblyApi.refreshAssembly;
showAssemblyMeshesImpl = assemblyApi.showAssemblyMeshes;
renderAssemblyTreeImpl = assemblyApi.renderAssemblyTree;
selectComponentImpl = assemblyApi.selectComponent;
clearAssemblyViewImpl = assemblyApi.clearAssemblyView;
const { tickExplode } = assemblyApi;

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

let measuring = false;

Object.assign(ctx, { call, say, panel });
const { onMeasurePointerUp, cancelMeasure } = installMeasure(ctx);

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
      const face = selectedFaceId;
      releaseFaceSelection();
      sketchMode.enter(call("sketch_start", { face }));
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
        const raw = typeof entry.invalid === "function"
          ? entry.invalid(v, ctx)
          : (entry.invalid ?? "Valeurs invalides");
        const notice = panelNotice(raw);
        if (notice) say(notice.text, notice.tone === "error");
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
    spec.onChange = (v) => {
      schedulePreview(entry.build(v, ctx));
      if (entry.button === "btn-fillet") updateFilletRadiusBubble(v);
    };
    // Œil de l'en-tête : couper l'aperçu (fonction lourde), le rallumer.
    spec.onPreview = (on, v) =>
      schedulePreview(on ? entry.build(v, ctx) : null);
  }
  // Tant que la saisie est incomplète, le panneau dit ce qui manque.
  spec.hint = (v) => (entry.build(v, ctx) ? null
    : typeof entry.invalid === "function" ? entry.invalid(v, ctx)
      : entry.invalid ?? null);
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

const pickFile = installFileDialog(document, {
  listDir: (path) => call("list_dir", path ? { path } : {}),
  storage: localStore,
});

async function openDocument(path) {
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
      rememberRecent(localStore, path);
      return;
    }
    renderTree(tree);
    await updateViewport(gen);
    if (gen !== viewGen) return;
    rememberRecent(localStore, path);
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
}

document.getElementById("btn-open").addEventListener("click", async () => {
  const path = await pickFile("open");
  if (path) openDocument(path);
});

document.getElementById("btn-save").addEventListener("click", async () => {
  const path = await pickFile("save");
  if (!path) return;
  try {
    const saved = await call("save_part", { path });
    rememberRecent(localStore, saved.path);
    say(t("Enregistré : {path} — ouvrable dans FreeCAD standard.", { path: saved.path }));
  } catch (error) {
    say(error.message, true);
  }
});

document.getElementById("btn-export").addEventListener("click", async () => {
  const path = await pickFile("export");
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
  } catch (error) {
    if (gen !== viewGen) return;
    say(t("Autotest : ") + error.message, true);
  }
});

// ---------- sketch mode ----------

const sketchMode = createSketchMode(
  { scene, camera, renderer, controls, call, say, refresh, panel, boxOverlay });

installShortcutBar(document, {
  ribbon: RIBBON_LAYOUT,
  sketchActive: () => sketchMode.active,
});
installCommandSearch(document, {
  ribbon: RIBBON_LAYOUT,
  sketchActive: () => sketchMode.active,
});

pluginRuntime = createPluginApi({
  call, refresh, say,
  tree: () => lastTree,
  scene, camera, controls, renderer,
  addRibbon: addPluginRibbon,
  addFeature: addPluginFeature,
  addHud: addPluginHud,
});

// ---------- boot ----------

welcomeApi = installWelcome(document, {
  storage: localStore,
  hasDocument: () => Boolean(lastTree || assemblyState),
  onPart: () => document.getElementById("btn-new").click(),
  onAssembly: () => document.getElementById("btn-newasm").click(),
  onOpen: () => document.getElementById("btn-open").click(),
  onRecent: (path) => openDocument(path),
});

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
        // pas encore de document — l'accueil propose d'en créer un
        welcomeApi?.showWelcome();
      }
    }
  })
  .catch(() => say("Moteur injoignable — lancez engine/server.py avec freecadcmd", true));
