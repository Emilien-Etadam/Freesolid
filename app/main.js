// FreeSolid app — M0. One part, one mesh, a feature tree,
// face picking by construction (each engine face is an index group).

import * as THREE from "three";
import { createSketchMode, createDimSprite } from "./sketch.js";
import {
  filletRadiusLabel,
} from "./dims.js";
import { createPropertyPanel } from "./panel.js";
import { num } from "./num.js";
import { ndcToScreen } from "./screen.js";
import { readScene } from "./theme.js";
import {
  readDisplay, writeDisplay, displayEffects,
} from "./display.js";
import { FEATURES } from "./features.js";
import { installContextMenu } from "./contextmenu.js";
import { installMeasure } from "./measure.js";
import { VIEW_KEYS, VIEWS, installViewCube } from "./viewcube.js";
import { installAssembly } from "./assembly.js";
import { installGraphView } from "./graphview.js";
import { paramLabel, paramLabels, installTree } from "./tree.js";
import { installPicking } from "./picking.js";
import { installViewport } from "./viewport.js";
import { installApi } from "./main/api.js";
import { installBoot } from "./main/boot.js";
import { installDebug } from "./main/debug.js";
import { installFeaturePanel } from "./main/featurepanel.js";
import { installPluginHost } from "./main/pluginhost.js";
import {
  coordsText, editModeText, measureText, sketchEntityLength,
} from "./statusbar.js";
import { createSettingsDialog, ISSUES_URL, readLang } from "./settings.js";
import { insertionItems, installMenuBar, menuBarModel } from "./menubar.js";
import {
  assignShortcut, comboLabel, comboOf, installRichTips, readShortcuts,
  writeShortcuts,
} from "./shortcuts.js";
import { countTreeErrors, undoStepLabel } from "./history.js";
import { installRefGeometry } from "./refgeom.js";
import { installGestures } from "./gestures.js";
import { installHandles } from "./handles.js";
import { installCommandSearch, installShortcutBar } from "./shortcutbar.js";
import { installFileDialog } from "./filedialog.js";
import { rememberRecent } from "./welcome.js";
import {
  SELECT_KINDS, filterActive,
  nudgeView, readReverseWheel, readSelectFilter,
  writeSelectFilter,
} from "./navigation.js";

// Noms des types du filtre de sélection (barre d'état).
const FILTER_NAMES = { faces: "Faces", edges: "Arêtes", sketches: "Esquisses",
                       surfaces: "Surfaces et courbes" };
import { currentLang, setLang, t, translateDom } from "./i18n.js";
import { applyStaticIcons } from "./icons.js";
// La langue avant tout rendu : ruban, panneaux et messages passent par t().
setLang(readLang((() => { try { return window.localStorage; } catch { return null; } })(),
  navigator.language));
document.documentElement.lang = currentLang();
translateDom(document.body);
applyStaticIcons(document);

// prompt()/confirm() natifs, message traduit : les appels gardent le texte
// source en français, le dictionnaire fait le reste.
const prompt = (message, fallback) => window.prompt(t(message), fallback);
const confirm = (message) => window.confirm(t(message));
import { installCoreRibbons } from "./ribbon.js";
import RIBBON_LAYOUT from "./ribbon.json" with { type: "json" };
import { edgeSnapPoints } from "./pointsnap.js";
import { installCurve3d } from "./curve3d.js";
import { installSketch3d } from "./sketch3d.js";
import { installBreadcrumbs } from "./breadcrumbs.js";
import { installManagerTabs } from "./managertabs.js";
import { installOrientCube } from "./orientcube.js";
import { installTaskPane } from "./taskpane.js";
import { installPoles } from "./poles.js";

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

// État partagé des modules. Les accesseurs lisent la variable actuelle,
// y compris celles déclarées plus bas.
const ctx = {};

// ---------- api ----------
// Le corps est dans main/api.js.

let statusSticky = false;
expose("statusSticky", () => statusSticky, (v) => { statusSticky = v; });
Object.assign(ctx, { statusEl });
const {
  call, startProgressWatch, stopProgressWatch, say, sayUntilAck,
} = installApi(ctx);

// Side property panel — feature options live there, not in
// prompt() dialogs. See panel.js for its anatomy. Closing the
// panel (OK or cancel) always clears the yellow ghost preview.
const panel = createPropertyPanel({
  say,
  onClose: () => {
    clearGhost();
    clearFilletRadiusBubble();
    sketchInfoOpen = false;
  },
  onPicks: (items) => setSelectedBoundaries(items),
  onToggle: () => {
    updateConfirmCorner();
    updateTreeFlyout();
    ctx.managerTabs?.sync();
    // La barre d'icônes du clic précédent n'a plus lieu d'être.
    ctx.hideContextToolbar?.();
  },
});

Object.assign(ctx, { THREE, sceneTheme, say, call, disposeSubtree, syncVisibilityMenu });
const {
  container, renderer, scene, camera, controls,
  ORTHO_HEIGHT, viewSize, boxOverlay, localStore, originGroup,
  setReverseWheel, setLayout, rebuildPlanes, rebuildOrigin,
  toggleOrigin, setOriginShown, updatePlaneVisibility,
  startPlanePick, cancelPlanePick, pickPlane, rotationPivot,
  rememberView, previousView, captureImage,
} = installViewport(ctx);
ctx.rememberView = rememberView;


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

// Outils de débogage (window.__freesolidDebug, lu par le smoke) :
// le corps est dans main/debug.js.
Object.assign(ctx, { camera, renderer, rotationPivot, volumesGroup, refresh });
installDebug(ctx);

const baseMaterial = new THREE.MeshStandardMaterial({
  color: sceneTheme.part, metalness: 0.08, roughness: 0.5,
  transparent: true, opacity: 1, // l'aperçu jaune estompe la pièce
  polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1,
});
// Transparents comme la pièce : pendant un aperçu, la face choisie
// s'estompe aussi au lieu de cacher le résultat (une ouverture de coque).
const hoverMaterial = new THREE.MeshStandardMaterial({
  color: sceneTheme.accent, metalness: 0.08, roughness: 0.45,
  transparent: true, opacity: 1,
  polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1,
});
const selectedMaterial = new THREE.MeshStandardMaterial({
  color: sceneTheme.selection, metalness: 0.08, roughness: 0.45,
  transparent: true, opacity: 1,
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
let partFaceMaterials = []; // clones possédés — faces colorées
let meshGroups = [];
let edgeGroups = [];
let edgeSnaps = []; // centres de cercles et sommets (clics de position)
let edgeData = null; // le maillage des arêtes, où l'esquisse s'accroche
let hoveredEdgeGroup = -1;
let hoveredGroup = -1;

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
// Bords : arêtes des surfaces et courbes 3D, une LineSegments par objet,
// un groupe par arête — remplissage, prolongement, trajectoire.
let boundaryLines = [];
let boundarySnaps = []; // sommets et centres des bords (spline 3D)
let hoveredBoundary = null; // { name, label, edge, curve } | null
let selectedBoundaries = new Set(); // clés « nom:arête »
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
  ctx.handles?.hide(); // la géométrie change : la poignée ne vaut plus
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
  for (const lines of boundaryLines) {
    lines.removeFromParent();
    lines.geometry.dispose();
  }
  boundaryLines = [];
  boundarySnaps = [];
  hoveredBoundary = null;
  selectedBoundaries = new Set();
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
    surfMesh.userData.groups = surface.groups ?? [];
    surfMesh.userData.baseMaterial = material;
    volumesGroup.add(surfMesh);
    surfaceMeshes.push(surfMesh);
    addBoundaryLines(surface, false);
  }
  for (const curve of Array.isArray(mesh.curves) ? mesh.curves : []) {
    addBoundaryLines(curve, true);
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
  // Faces colorées : une matière par couleur, après survol et sélection.
  const materials = [partBaseMaterial, hoverMaterial, selectedMaterial];
  const byColor = new Map();
  partFaceMaterials = [];
  mesh.groups.forEach((g, i) => {
    const color = hexColor(g.color);
    if (!color) return;
    if (!byColor.has(color)) {
      const material = ownedMaterial(baseMaterial, color);
      byColor.set(color, materials.length);
      materials.push(material);
      partFaceMaterials.push(material);
    }
    g.baseIndex = byColor.get(color);
    geometry.groups[i].materialIndex = g.baseIndex;
  });
  partMesh = new THREE.Mesh(geometry, materials);
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
  edgeData = data;
  edgeSnaps = edgeSnapPoints(data);
  hoveredEdgeGroup = -1;
  selectedEdges = new Set(); // ids shift after every rebuild, like faces
  // La barre d'état citait encore les arêtes d'avant la reconstruction.
  repaintGroups();
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

function addBoundaryLines(item, curve) {
  const edges = item.edges;
  if (!edges?.indices?.length) return;
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position",
    new THREE.Float32BufferAttribute(edges.positions, 3));
  geometry.setIndex(edges.indices);
  for (const g of edges.groups) geometry.addGroup(g.start, g.count, 0);
  const lines = new THREE.LineSegments(geometry, [
    curve ? curvesMaterial : edgeBaseMaterial,
    edgeHoverMaterial, edgeSelectedMaterial]);
  lines.userData.boundary = {
    name: item.name, label: item.label, curve, groups: edges.groups };
  // Une courbe reste visible même volumes masqués, comme une esquisse.
  (curve ? scene : volumesGroup).add(lines);
  boundaryLines.push(lines);
  boundarySnaps.push(...edgeSnapPoints(edges));
}

function boundaryKey(name, edge) { return `${name}:${edge}`; }

let boundaryOwnsEdges = false; // selectedEdges vient des bords du panneau

function repaintBoundaries() {
  for (const lines of boundaryLines) {
    const { name, groups } = lines.userData.boundary;
    lines.geometry.groups.forEach((g, i) => {
      const edge = groups[i].edgeId;
      g.materialIndex = selectedBoundaries.has(boundaryKey(name, edge)) ? 2
        : (hoveredBoundary?.name === name && hoveredBoundary.edge === edge
          ? 1 : 0);
    });
  }
}

/** Bords retenus par le panneau : surlignés dans la vue. */
function setSelectedBoundaries(items) {
  const bounds = (items ?? []).filter((i) => i.kind === "boundary");
  selectedBoundaries = new Set(bounds.filter((i) => !i.body)
    .map((i) => boundaryKey(i.name, i.edge)));
  repaintBoundaries();
  // Arêtes du solide prises comme bords : surlignées comme une sélection,
  // effacées quand le panneau se ferme.
  const bodyEdges = bounds.filter((i) => i.body).map((i) => i.edge);
  if (bodyEdges.length || boundaryOwnsEdges) {
    selectedEdges = new Set(bodyEdges);
    boundaryOwnsEdges = bodyEdges.length > 0;
    repaintEdges();
  }
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
let displayState = readDisplay(localStore);
let originShown = displayState.origin;

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
  const menus = ["style-menu", "visibility-menu", "undo-menu", "filter-menu"]
    .map((id) => document.getElementById(id)).filter(Boolean);
  const open = menus.some((menu) => !menu.hidden);
  for (const menu of menus) menu.hidden = true;
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

  // Filtre de sélection : gardé d'une session à l'autre.
  const filterButton = document.getElementById("btn-select-filter");
  const filterMenu = document.getElementById("filter-menu");
  ctx.selectFilter = readSelectFilter(localStore);
  const syncFilter = () => {
    for (const input of filterMenu.querySelectorAll("[data-filter]")) {
      input.checked = ctx.selectFilter[input.dataset.filter] !== false;
    }
    filterButton.classList.toggle("on", filterActive(ctx.selectFilter));
  };
  const setFilter = (next) => {
    ctx.selectFilter = next;
    writeSelectFilter(localStore, next);
    syncFilter();
    say(filterActive(next)
      ? t("Filtre de sélection : {k}", { k: SELECT_KINDS
        .filter((kind) => next[kind] !== false)
        .map((kind) => t(FILTER_NAMES[kind])).join(", ") || t("rien") })
      : t("Filtre de sélection : tout"));
  };
  filterButton.addEventListener("click", (event) => {
    event.stopPropagation();
    const open = filterMenu.hidden;
    closeViewMenus();
    filterMenu.hidden = !open;
    syncFilter();
  });
  filterMenu.addEventListener("change", (event) => {
    const input = event.target.closest("[data-filter]");
    if (input) setFilter({ ...ctx.selectFilter, [input.dataset.filter]: input.checked });
  });
  filterMenu.addEventListener("click", (event) => {
    event.stopPropagation();
    if (event.target.closest("[data-filter-all]")) {
      setFilter(readSelectFilter(null));
      closeViewMenus();
    }
  });
  syncFilter();
  document.addEventListener("click", () => closeViewMenus());
  syncStyleMenu();
  syncVisibilityMenu();
}


// ---------- aperçu jaune (le fantôme du panneau de propriétés) ----------

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
  clearPlaneGhost();
  if (ghostMesh) {
    ghostMesh.removeFromParent();
    ghostMesh.geometry.dispose();
    ghostMesh = null;
  }
  baseMaterial.opacity = 1;
  if (partBaseMaterial) partBaseMaterial.opacity = 1;
  for (const material of partFaceMaterials) material.opacity = 1;
  hoverMaterial.opacity = selectedMaterial.opacity = 1;
}

// Aperçu d'un plan de référence : un carré translucide là où le moteur
// le pose (matrice 4 × 4 par lignes), à l'échelle de la pièce.
let planeGhost = null;

function clearPlaneGhost() {
  if (!planeGhost) return;
  planeGhost.removeFromParent();
  planeGhost.traverse((obj) => obj.geometry?.dispose());
  planeGhost = null;
}

function showPlaneGhost(matrix) {
  clearPlaneGhost();
  const size = partMesh ? Math.max(partCenterRadius().radius * 2.4, 40) : 100;
  const fill = new THREE.Mesh(new THREE.PlaneGeometry(size, size),
    new THREE.MeshBasicMaterial({ color: sceneTheme.accent, transparent: true,
      opacity: 0.18, side: THREE.DoubleSide, depthWrite: false }));
  const border = new THREE.LineSegments(new THREE.EdgesGeometry(fill.geometry),
    new THREE.LineBasicMaterial({ color: sceneTheme.accent }));
  planeGhost = new THREE.Group();
  planeGhost.add(fill, border);
  planeGhost.matrixAutoUpdate = false;
  planeGhost.matrix.set(...matrix);
  planeGhost.renderOrder = 15;
  scene.add(planeGhost);
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
  for (const material of partFaceMaterials) material.opacity = 0.15;
  hoverMaterial.opacity = selectedMaterial.opacity = 0.3;
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
// réponse obsolète ne montre ni n'efface le fantôme. Un aperçu réussi
// efface le message d'un aperçu raté précédent.
let previewFailed = false;
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
      if (mesh.plane) showPlaneGhost(mesh.plane);
      else showGhost(mesh, { bothSides: built.op === "add_fillet" });
      if (previewFailed) say("");
      previewFailed = false;
    } catch (error) {
      if (gen !== previewGen) return;
      if (!panel.active) return;
      clearGhost();
      say("Aperçu — " + error.message);
      previewFailed = true;
    }
  }, 250);
}



function expose(name, get, set) {
  Object.defineProperty(ctx, name, {
    get, set, enumerable: true, configurable: true,
  });
}

expose("featureDimSprites", () => featureDimSprites, (v) => { featureDimSprites = v; });
expose("lastFaceMatch", () => lastFaceMatch);
expose("hoverPlane", () => hoverPlane, (v) => { hoverPlane = v; });
expose("sketchLineMeshes", () => sketchLineMeshes);
expose("surfaceMeshes", () => surfaceMeshes);
expose("boundaryLines", () => boundaryLines);
expose("boundarySnaps", () => boundarySnaps);
expose("hoveredBoundary", () => hoveredBoundary,
  (v) => { hoveredBoundary = v; });
expose("planeMeshes", () => planeMeshes, (v) => { planeMeshes = v; });
expose("othersMeshes", () => othersMeshes);
Object.assign(ctx, {
  THREE, scene, camera, renderer, controls, container, viewSize, ORTHO_HEIGHT,
  say, call, panel, pickEl, measureEl, coordsEl, refresh, selectComponent,
  boxOverlay, featureDimsGroup, createDimSprite,
  surfaceHoverMaterial, surfaceSelectedMaterial,
  repaintBoundaries, setSelectedBoundaries,
  focusPanelField, pickFilletRadiusBubble,
  updatePlaneVisibility, repaintEdges, pickPlane,
});
const {
  raycaster, pointer, setPointerFromEvent,
  repaintGroups, repaintSurfaces, findFeatureInTree, clearFeatureDims,
  selectEdgeIds,
} = installPicking(ctx);
ctx.selectEdgeIds = selectEdgeIds;
ctx.raycaster = raycaster;

// ---------- vues standard et boîte d'orientation ----------

expose("partMesh", () => partMesh);
expose("partEdges", () => partEdges);
expose("edgeSnaps", () => edgeSnaps);
expose("selectedFaceId", () => selectedFaceId, (v) => { selectedFaceId = v; });
expose("lastFaceHit", () => lastFaceHit, (v) => { lastFaceHit = v; });
expose("selectedPlane", () => selectedPlane);
Object.assign(ctx, {
  THREE, camera, controls, viewSize, ORTHO_HEIGHT, say, setLayout, container,
});
const {
  partCenterRadius, frameView, frameSketch, viewNormalTo, zoomToSelection,
  openOrientBox, closeOrientBox, orientBoxOpen,
} = installViewCube(ctx);

// Tab : masque ce qui est sous le pointeur (la surface visée, sinon le
// corps actif) ; Maj+Tab : affiche tout ce qui est masqué.
let pointerInView = false;
container.addEventListener("pointerenter", () => { pointerInView = true; });
container.addEventListener("pointerleave", () => { pointerInView = false; });

function hideUnderPointer(showAll) {
  if (showAll) {
    const hidden = [...(lastTree?.bodies ?? []), ...(lastTree?.surfaces ?? [])]
      .filter((entry) => entry.hidden).map((entry) => entry.name);
    if (!hidden.length) {
      say(t("Rien n'est masqué"));
      return;
    }
    refreshAny(call("set_hidden", { objects: hidden, hidden: false }));
    return;
  }
  const target = hoveredSurface?.name
    ?? (hoveredGroup >= 0
      ? lastTree?.bodies?.find((body) => body.active)?.name : null);
  if (!target) {
    say(t("Tab : survolez un corps ou une surface à masquer (Maj+Tab : tout afficher)"));
    return;
  }
  refreshAny(call("set_hidden", { objects: [target], hidden: true }));
}

function goPreviousView() {
  if (!previousView()) say(t("Vue précédente : aucune vue à reprendre"));
}

/** Enregistre la vue en PNG (le fond et l'éclairage de l'écran). */
function saveScreenshot() {
  const link = document.createElement("a");
  link.href = captureImage();
  link.download = "freesolid.png";
  link.click();
  say(t("Capture enregistrée : freesolid.png"));
}

document.getElementById("view-prev").addEventListener("click", goPreviousView);
document.getElementById("view-zoom-sel").addEventListener("click", () => {
  if (!sketchMode.active) zoomToSelection();
});
ctx.frameView = frameView;

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
    if ((event.ctrlKey || event.metaKey) && event.shiftKey
        && (event.key === "z" || event.key === "Z")) {
      event.preventDefault();
      goPreviousView();
    } else if ((event.ctrlKey || event.metaKey) && !event.altKey
               && ["z", "Z", "y", "Y"].includes(event.key)) {
      // Ctrl+Z, Ctrl+Y : les pas de l'esquisse, pas ceux de la pièce.
      event.preventDefault();
      if (event.key === "z" || event.key === "Z") sketchMode.undo();
      else sketchMode.redo();
    } else if ((event.key === "f" || event.key === "F")
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
  if (handleBarKey(event)) return; // barre de retour sélectionnée : ↑/↓
  if (applyViewNudge(event)) return;
  if (event.key !== "Escape" && pluginRuntime?.dispatchKey(event)) return;
  // Raccourcis personnels : une commande du ruban par combinaison.
  const combo = event.repeat ? null : comboOf(event);
  const customId = combo && Object.keys(userShortcuts)
    .find((id) => userShortcuts[id] === combo);
  if (customId) {
    const button = document.getElementById(customId);
    if (button && !button.disabled) {
      event.preventDefault();
      button.click();
      return;
    }
  }
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
  if (event.key === "Tab" && pointerInView && !ctx.assemblyState
      && !event.ctrlKey && !event.metaKey && !event.altKey) {
    event.preventDefault();
    hideUnderPointer(event.shiftKey);
    return;
  }
  if ((event.key === "f" || event.key === "F")
      && !event.ctrlKey && !event.metaKey && !event.altKey) {
    frameView(null, null);
  } else if ((event.key === "z" || event.key === "Z")
             && !event.ctrlKey && !event.metaKey && !event.altKey) {
    // Z : zoom arrière, Maj+Z : zoom avant, autour du centre de la vue.
    camera.zoom *= event.shiftKey ? 1.25 : 0.8;
    camera.updateProjectionMatrix();
  } else if ((event.ctrlKey || event.metaKey) && event.shiftKey
             && (event.key === "z" || event.key === "Z")) {
    event.preventDefault();
    goPreviousView();
  } else if ((event.ctrlKey || event.metaKey) && event.key === "8") {
    event.preventDefault();
    viewNormalTo();
  } else if ((event.ctrlKey || event.metaKey) && VIEW_KEYS[event.key]) {
    event.preventDefault();
    frameView(VIEWS[VIEW_KEYS[event.key]].direction,
              VIEWS[VIEW_KEYS[event.key]].up);
  } else if ((event.ctrlKey || event.metaKey) && !event.shiftKey
             && !event.altKey && (event.key === "c" || event.key === "C")) {
    if (copySelectedFeature({ quiet: true })) event.preventDefault();
  } else if ((event.ctrlKey || event.metaKey) && !event.shiftKey
             && !event.altKey && (event.key === "v" || event.key === "V")) {
    if (copiedFeature) {
      event.preventDefault();
      pasteFeature();
    }
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
    } else if (name === "flat-tree") {
      setFlatTree(!isFlatTree());
    } else if (name === "report") {
      window.open(ISSUES_URL, "_blank", "noopener");
    } else if (name === "home") {
      welcomeApi?.showWelcome();
    } else if (name === "create") {
      welcomeApi?.showNew();
    } else if (name === "screenshot") {
      saveScreenshot();
    } else if (name === "properties") {
      openDocumentProperties();
    } else if (name === "shortcuts") {
      openShortcutPanel();
    } else if (name === "config-table") {
      openConfigTable();
    } else if (name === "save-template") {
      saveAsTemplate();
    } else if (name === "copy") {
      copySelectedFeature();
    } else if (name === "paste") {
      pasteFeature();
    }
  },
});

// ---------- arbre de création ----------
// Relais : ces noms sont appelés partout (vue, menu, graphe, boot).
// Le corps est dans tree.js.

let selectedDatumFeature = null; // { name, placement }
let lastTree = null;
let sketchInfoOpen = false;

expose("selectedDatumFeature", () => selectedDatumFeature, (v) => { selectedDatumFeature = v; });
expose("sketchInfoOpen", () => sketchInfoOpen, (v) => { sketchInfoOpen = v; });
expose("selectedPlane", () => selectedPlane, (v) => { selectedPlane = v; });
expose("pluginRuntime", () => pluginRuntime, (v) => { pluginRuntime = v; });
expose("selectedEdges", () => selectedEdges, (v) => { selectedEdges = v; });
expose("selectedFeatureName", () => selectedFeatureName, (v) => { selectedFeatureName = v; });
expose("treeHoverPlane", () => treeHoverPlane, (v) => { treeHoverPlane = v; });
expose("sketchHighlightGroup", () => sketchHighlightGroup, (v) => { sketchHighlightGroup = v; });
Object.assign(ctx, {
  THREE, scene, treeEl, panel,
  say, call, refresh, refreshAny,
  disposeSubtree, hexColor, partCenterRadius,
  repaintEdges, repaintGroups, repaintSurfaces, sketchHighlightMaterial,
  updatePlaneVisibility, pickPlane, schedulePreview,
  findFeatureInTree, updateEditMode, toggleOrigin, openEquationsPanel,
  clearAssemblyView, closeGraph, enterGraphFeature, syncGraphFromTree,
});
const {
  updateTreeFlyout, refreshDatumGhost, onDatumRow, treeIcon,
  onSketchRowClick, onSketchRowDblClick, clearSketchSelection,
  cancelPendingSurfaceClick, onSurfaceClick, onSurfaceDblClick,
  clearSurfaceSelection, selectSketch, onPlaneRow,
  beginInlineRename, treeRowFor, beginRenameSelected,
  renderTree, editSurface, editFeature,
  moveBar, stepBar, barToPrevious, barCommands, isAfterBar, handleBarKey,
  setFlatTree, isFlatTree,
} = installTree(ctx);
Object.assign(ctx, {
  renderTree, refreshDatumGhost, clearSketchSelection,
  cancelPendingSurfaceClick, onSurfaceClick, onSurfaceDblClick,
  clearSurfaceSelection, selectSketch,
  moveBar, stepBar, barToPrevious, barCommands, isAfterBar,
  setFlatTree, isFlatTree,
});

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
expose("displayState", () => displayState, (v) => { displayState = v; });
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

const {
  openMenu, openBarMenu, openTreeTitleMenu, showContextToolbar, hideContextToolbar,
} = installContextMenu(ctx);
ctx.openMenu = openMenu;
ctx.openBarMenu = openBarMenu;
ctx.openTreeTitleMenu = openTreeTitleMenu;
ctx.showContextToolbar = showContextToolbar;
ctx.hideContextToolbar = hideContextToolbar;

// ---------- ruban à onglets ----------

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
  // Esquisse rééditée : tout son contenu à l'écran, pas seulement la pièce.
  if (sketchMode.framePoints().length) frameSketch();
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
  // sketchMode est créé plus bas ; le panneau ne s'ouvre qu'après.
  sketchSnaps: {
    read: () => sketchMode.snapSettings,
    apply: (settings) => sketchMode.setSnapSettings(settings),
  },
  storage: (() => { try { return window.localStorage; } catch { return null; } })(),
  navigatorLang: navigator.language,
});
document.getElementById("btn-settings").addEventListener("click", () => {
  settingsDialog.toggle();
});
/** Le panneau Paramètres ouvert sur une section (menu de l'esquisse). */
ctx.openSettings = (section) => settingsDialog.open(section);

// Cliquer une fonction pendant une esquisse la termine d'abord — le
// réflexe de modeleur : on dessine, puis on clique Extrusion, sans passer
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

let clipState = null; // { axis, position, flip } de la coupe visuelle

function setClip(axis, position, flip, { handle = true } = {}) {
  if (!axis || axis === "off") {
    renderer.clippingPlanes = [];
    clipState = null;
    ctx.handles?.hide();
    say("Plan de coupe désactivé.");
    return;
  }
  clipState = { axis, position, flip };
  if (handle) showClipHandle();
  const normals = { X: [1, 0, 0], Y: [0, 1, 0], Z: [0, 0, 1] };
  const n = new THREE.Vector3(...normals[axis]);
  if (flip) n.negate();
  renderer.clippingPlanes = [
    new THREE.Plane(n, flip ? position : -position)];
  say(t("Coupe {axis} à {position} mm — purement visuelle.", { axis, position }));
}

/** Poignée du plan de coupe : la tirer déplace la coupe en direct. */
function showClipHandle() {
  if (!clipState || !ctx.handles) return;
  const { axis, position, flip } = clipState;
  const index = { X: 0, Y: 1, Z: 2 }[axis];
  const dir = [0, 0, 0];
  dir[index] = 1;
  const origin = partCenterRadius().center.toArray();
  origin[index] = position;
  ctx.handles.show({
    origin, dir,
    onDrag: (d) => setClip(axis, Math.round((position + d) * 10) / 10, flip,
      { handle: false }),
    onEnd: () => showClipHandle(),
  });
}

// Tirer la face du bout d'une extrusion ou d'un enlèvement : sa
// profondeur suit, l'aperçu jaune montre le résultat, le lâcher l'applique.
ctx.onFacePicked = async (face) => {
  if (face === null || sketchMode.active || panel.active || assemblyState) {
    if (ctx.handles?.active) ctx.handles.hide();
    if (face === null) showClipHandle();
    return;
  }
  const info = await call("face_drag_info", { face }).catch(() => null);
  const drag = info?.drag;
  if (!drag || selectedFaceId !== face) return;
  const valueAt = (d) => Math.round((drag.value + drag.factor * d) * 2) / 2;
  ctx.handles.show({
    origin: drag.point, dir: drag.normal,
    onDrag: (d) => {
      const value = valueAt(d);
      say(t("{f} : profondeur {v} mm — relâchez pour appliquer",
        { f: drag.label, v: value }));
      if (value > 0) {
        schedulePreview({ op: "set_params", params: {
          feature: drag.feature, values: { [drag.key]: value } } });
      }
    },
    onEnd: (d) => {
      clearGhost();
      const value = valueAt(d);
      if (value === drag.value) return;
      if (!(value > 0)) {
        say(t("La profondeur doit rester positive"), true);
        ctx.onFacePicked(face);
        return;
      }
      refresh(call("set_params", { feature: drag.feature,
                                   values: { [drag.key]: value } }));
    },
  });
};

document.getElementById("btn-clip").addEventListener("click", () => {
  const active = renderer.clippingPlanes.length > 0;
  panel.open({
    icon: "Std_ToggleClipPlane",
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

// ---------- panneaux des fonctions (FEATURES) ----------
// Le corps est dans main/featurepanel.js. Installé ici : la vue en graphe
// et la géométrie de référence le lisent dès leur branchement ; les
// boutons du ruban sont liés plus bas, à leur place d'origine.

Object.assign(ctx, {
  panel, confirm, call, say, refresh, updateFilletRadiusBubble,
  schedulePreview, findFeatureInTree, refreshAny, enterGraphFeature,
  featureCommand,
});
const { currentSelection, openFeaturePanel, bindFeature } = installFeaturePanel(ctx);

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
expose("selectedDatumFeature", () => selectedDatumFeature, (v) => { selectedDatumFeature = v; });
expose("selectedSurface", () => selectedSurface, (v) => { selectedSurface = v; });
Object.assign(ctx, {
  say, call, refresh, refreshAny, confirm, paramLabels,
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

// Spline 3D : clics dans la vue, points corrigeables dans le panneau.
const curveTool = installCurve3d(ctx);
ctx.curveTool = curveTool;
ctx.openCurve3d = (curve) => curveTool.open(curve);
document.getElementById("btn-curve3d").addEventListener("click", () =>
  featureCommand(() => curveTool.open()));

// Esquisse 3D : un mode d'édition (lignes, splines, points, cotes).
const sketch3dTool = installSketch3d(ctx);
ctx.sketch3dTool = sketch3dTool;
ctx.openSketch3d = (entry = null) => {
  if (sketchMode.active) {
    say(t("Fermez d'abord l'esquisse 2D en cours."), true);
    return;
  }
  sketch3dTool.open(entry);
};
for (const id of ["sk-start3d", "btn-sketch3d"]) {
  document.getElementById(id)?.addEventListener("click", () =>
    featureCommand(() => ctx.openSketch3d()));
}

// Points de contrôle : la grille de pôles d'une surface, déplacés un à un.
const polesTool = installPoles(ctx);
ctx.polesTool = polesTool;
ctx.openPoles = (surface) => polesTool.open(surface);
document.getElementById("btn-surf-poles").addEventListener("click", () =>
  featureCommand(() => polesTool.open()));

document.getElementById("btn-drawing").addEventListener("click", () => {
  panel.open({
    icon: "TechDraw_PageDefault",
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
ctx.tickExplode = tickExplode;

// ---------- actions ----------

async function refresh(treePromise) {
  const gen = ++viewGen;
  lastClearedSelections = false;
  startProgressWatch();
  let ok = false;
  try {
    const tree = await treePromise;
    if (gen !== viewGen) return;
    // L'opération a réussi : l'erreur d'avant (gardée jusqu'au clic) n'a
    // plus lieu d'être.
    statusSticky = false;
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

/** Le document en cours peut-il être abandonné (nouveau, ouvrir) ? S'il
 *  a des modifications non enregistrées, l'utilisateur confirme. */
async function mayDiscard() {
  let status = null;
  try {
    status = await call("document_status");
  } catch {
    return true; // moteur injoignable : l'appel suivant le dira
  }
  if (!status?.open || !status.modified) return true;
  return confirm("Le document en cours a des modifications non enregistrées. Les abandonner ?");
}
ctx.mayDiscard = mayDiscard;

document.getElementById("btn-new").addEventListener("click", async () => {
  if (!(await mayDiscard())) return;
  clearFeatureDims();
  refresh(call("new_part"));
});

// Dans l'esquisse, Annuler et Rétablir ne touchent que ses pas.
document.getElementById("btn-undo").addEventListener("click", () =>
  (sketchMode.active ? sketchMode.undo() : refreshAny(call("undo"))));

// Liste de l'historique : un clic sur un pas défait tout jusqu'à lui.
document.getElementById("btn-undo-list").addEventListener("click", async (event) => {
  event.stopPropagation();
  const menu = document.getElementById("undo-menu");
  const wasOpen = !menu.hidden;
  closeViewMenus();
  if (wasOpen) return;
  const history = await call("undo_history", sketchMode.active
    ? { sketch: sketchMode.editing } : {}).catch(() => null);
  menu.replaceChildren();
  const head = document.createElement("div");
  head.className = "menu-head";
  head.textContent = history?.undo?.length
    ? t("Annuler jusqu'à…") : t("Rien à annuler");
  menu.appendChild(head);
  (history?.undo ?? []).slice(0, 30).forEach((op, i) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = t(undoStepLabel(op));
    button.addEventListener("click", () => {
      closeViewMenus();
      if (sketchMode.active) sketchMode.undo(i + 1);
      else refreshAny(call("undo", { steps: i + 1 }));
    });
    menu.appendChild(button);
  });
  menu.hidden = false;
});

// Erreurs de reconstruction : le compte dans la barre d'état, la liste
// (avec le message du modeleur) au clic ; une ligne ouvre la fonction.
const errorsBadge = document.getElementById("errors-badge");
ctx.treeHooks = [(tree) => {
  const count = countTreeErrors(tree);
  errorsBadge.hidden = count === 0;
  errorsBadge.textContent = t("⚠ {n} erreur(s)", { n: count });
}];

// Gestes de la souris : glisser au bouton droit dans la vue.
installGestures(ctx);
ctx.handles = installHandles(ctx);

// Axes, points et repères : panneaux du ruban, dessin à chaque arbre.
Object.assign(ctx, { currentSelection, featureCommand });
const refGeometry = installRefGeometry(ctx);
ctx.treeHooks.push((tree) => refGeometry.draw(tree));
// Fil de la sélection : pièce › fonction › esquisse › face.
installBreadcrumbs(ctx);
// Gestionnaire à onglets : arbre, propriétés, configurations, affichage.
ctx.updateTreeFlyout = updateTreeFlyout;
ctx.managerTabs = installManagerTabs(ctx);
// Cube d'orientation (haut droite) et trièdre (bas gauche).
installOrientCube(ctx);
// Volet de ressources (bord droit) : matières, gabarits, aide.
ctx.openShortcutPanel = () => openShortcutPanel();
installTaskPane(ctx);
errorsBadge.addEventListener("click", async () => {
  const result = await call("rebuild_errors").catch((error) => {
    say(String(error.message ?? error), true);
    return null;
  });
  if (!result) return;
  panel.open({
    icon: "rebuild",
    title: t("Erreurs de reconstruction"),
    groups: [{ label: t("Fonctions en erreur"), rows: [{
      type: "list",
      empty: t("Aucune erreur"),
      items: result.errors.map((error) => ({
        label: error.message,
        onEdit: () => {
          const feature = findFeatureInTree(lastTree, error.name);
          if (feature) editFeature(feature);
        },
      })),
    }] }],
    note: t("Un clic ouvre la fonction. Corrigez d'abord la première : "
      + "les suivantes en dépendent souvent."),
    noApply: true,
  });
});

/** La pièce en cours devient un gabarit, proposé ensuite par Nouveau. */
async function saveAsTemplate() {
  if (!lastTree) {
    say(t("Gabarit : ouvrez d'abord une pièce"), true);
    return;
  }
  const name = prompt("Nom du gabarit :", "Pièce");
  if (name === null || !name.trim()) return;
  try {
    await call("save_template", { name: name.trim() });
    say(t("Gabarit « {n} » enregistré — Nouveau le propose", { n: name.trim() }));
  } catch (error) {
    say(String(error.message ?? error), true);
  }
}

// Copier-coller de fonctions : Ctrl+C sur une fonction à esquisse (ou une
// esquisse), Ctrl+V sur une face, un plan ou un plan de référence.
let copiedFeature = null;
/** Tableau des configurations : une ligne par cote, une valeur par
 *  configuration ; OK enregistre les valeurs changées. */
async function openConfigTable() {
  const table = await call("configuration_table").catch((error) => {
    say(String(error.message ?? error), true);
    return null;
  });
  if (!table) return;
  if (!table.names.length) {
    say(t("Ajoutez d'abord une configuration (onglet Configurations du gestionnaire)"));
    return;
  }
  panel.open({
    icon: "configurations",
    title: t("Tableau des configurations"),
    groups: table.rows.map((row, i) => ({
      label: row.param
        ? `${row.label} · ${t(paramLabel(row.type_key, row.param)[0])}` : row.label,
      rows: table.names.map((name) => ({
        type: "number", key: `${i}|${name}`,
        label: name === table.active ? `${name} ✓` : name,
        value: row.values[name] ?? 0,
      })),
    })),
    note: t("Une ligne par cote ; la configuration active (✓) s'applique tout de suite."),
    onApply: (v) => {
      const values = {};
      table.rows.forEach((row, i) => {
        for (const name of table.names) {
          const next = num(v[`${i}|${name}`]);
          if (next == null || next === row.values[name]) continue;
          (values[name] ??= {})[row.key] = next;
        }
      });
      if (Object.keys(values).length) {
        refresh(call("set_configuration_values", { values }));
      }
    },
  });
}
ctx.openConfigTable = openConfigTable;

// Dossier de l'arbre : clic droit pour le renommer (vide : le défaire).
ctx.promptText = prompt;
ctx.onFolderMenu = (folder) => {
  const name = prompt("Renommer le dossier (vide : le défaire) :", folder);
  if (name === null) return;
  refresh(call("rename_folder", { folder, name: name.trim() }));
};
ctx.canCopyFeature = (feature) => feature?.type_key === "sketch"
  || (feature?.children ?? []).some((c) => c.type_key === "sketch");
ctx.copyFeature = (feature) => {
  copiedFeature = { name: feature.name, label: feature.label };
  say(t("« {f} » copiée — sélectionnez une face ou un plan, puis Ctrl+V",
    { f: feature.label }));
};

function copySelectedFeature({ quiet = false } = {}) {
  const feature = findFeatureInTree(lastTree, selectedFeatureName)
    ?? (selectedSketch ? findFeatureInTree(lastTree, selectedSketch.name) : null);
  if (!feature || !ctx.canCopyFeature(feature)) {
    if (!quiet) say(t("Copier : cliquez d'abord une fonction à esquisse dans l'arbre"));
    return false;
  }
  ctx.copyFeature(feature);
  return true;
}

function pasteFeature() {
  if (!copiedFeature) {
    say(t("Coller : rien n'a été copié"));
    return;
  }
  const target = selectedFaceId !== null ? { face: selectedFaceId }
    : selectedDatumFeature ? { datum: selectedDatumFeature.name }
      : selectedPlane !== null ? { plane: selectedPlane } : null;
  if (!target) {
    say(t("Coller : sélectionnez la face ou le plan d'accueil"), true);
    return;
  }
  refresh(call("paste_feature", { feature: copiedFeature.name, ...target }));
}

// Raccourcis personnels (Outils → Raccourcis clavier…), gardés dans le
// navigateur ; les infobulles des barres les montrent.
let userShortcuts = readShortcuts(localStore);
installRichTips(document, {
  selector: "[id^=\"ribbon-\"] button, #viewbar button, #quickbar button, #sketchbar button",
  shortcutFor: (id) => userShortcuts[id] ?? null,
});

function openShortcutPanel() {
  const commands = insertionItems(RIBBON_LAYOUT).filter((item) => item.click);
  const labelOf = (id) => t(commands.find((c) => c.click === id)?.label ?? id);
  panel.open({
    icon: "shortcuts",
    title: t("Raccourcis clavier"),
    groups: [
      { label: t("Raccourcis attribués"), rows: [{
        type: "list",
        empty: t("Aucun pour l'instant"),
        items: Object.entries(userShortcuts).map(([id, combo]) => ({
          label: `${labelOf(id)} — ${comboLabel(combo)}`,
          onDelete: () => {
            const { [id]: _removed, ...rest } = userShortcuts;
            userShortcuts = rest;
            writeShortcuts(localStore, userShortcuts);
            openShortcutPanel();
          },
        })),
      }] },
      { label: t("Nouveau raccourci"), rows: [
        { type: "select", key: "command", label: t("Commande"),
          value: commands[0]?.click,
          options: commands.map((c) => [c.click, t(c.label)]) },
        { type: "text", key: "keys", label: t("Touches"), value: "",
          placeholder: t("Ctrl+Maj+E") },
      ] },
    ],
    note: t("Dans la pièce, hors esquisse. Les touches de vue (F, Z, Ctrl+1…) "
      + "et du navigateur restent réservées."),
    onApply: (v) => {
      if (!String(v.keys ?? "").trim()) return;
      const result = assignShortcut(userShortcuts, v.command, v.keys);
      if (result.error) {
        say(t(result.error), true);
        return;
      }
      userShortcuts = result.map;
      writeShortcuts(localStore, userShortcuts);
      say(result.replaced
        ? t("{c} : {k} (retiré de {o})", { c: labelOf(v.command),
          k: comboLabel(userShortcuts[v.command]), o: labelOf(result.replaced) })
        : t("{c} : {k}", { c: labelOf(v.command),
          k: comboLabel(userShortcuts[v.command]) }));
    },
  });
}

/** Propriétés du fichier : auteur, société, description, propriétés
 *  libres (une ligne par nom ; valeur vide : retirée). */
async function openDocumentProperties() {
  const props = await call("document_properties").catch((error) => {
    say(String(error.message ?? error), true);
    return null;
  });
  if (!props) return;
  const custom = Object.entries(props.custom ?? {});
  panel.open({
    icon: "doc_props",
    title: t("Propriétés du fichier"),
    groups: [
      { label: t("Résumé"), rows: [
        { type: "text", key: "author", label: t("Auteur"), value: props.author },
        { type: "text", key: "company", label: t("Société"), value: props.company },
        { type: "text", key: "description", label: t("Description"),
          value: props.description },
      ] },
      { label: t("Propriétés libres"), rows: [
        ...custom.map(([name, value], i) => ({
          type: "text", key: `custom${i}`, label: name, value })),
        { type: "text", key: "newName", label: t("Nouvelle propriété"),
          value: "", placeholder: t("Référence, matière, client…") },
        { type: "text", key: "newValue", label: t("Valeur"), value: "" },
      ] },
    ],
    note: t("Enregistrées dans le fichier .FCStd ; une valeur vide retire la propriété."),
    onApply: async (v) => {
      const next = {};
      custom.forEach(([name], i) => { next[name] = String(v[`custom${i}`] ?? ""); });
      const fresh = String(v.newName ?? "").trim();
      if (fresh) next[fresh] = String(v.newValue ?? "");
      await call("set_document_properties", { values: {
        author: String(v.author ?? ""), company: String(v.company ?? ""),
        description: String(v.description ?? ""), custom: next } })
        .then(() => say(t("Propriétés du fichier enregistrées")))
        .catch((error) => say(String(error.message ?? error), true));
    },
  });
}
document.getElementById("btn-redo").addEventListener("click", () =>
  (sketchMode.active ? sketchMode.redo() : refreshAny(call("redo"))));
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
    icon: "VarSet",
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
ctx.onMeasurePointerUp = onMeasurePointerUp;

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
      // à vous de cliquer — le geste attendu.
      startPlanePick();
    }
  }));

// Chaque entrée de FEATURES ouvre son panneau (main/featurepanel.js).
for (const entry of FEATURES) bindFeature(entry);

document.getElementById("btn-body").addEventListener("click", () =>
  featureCommand(() => {
    const name = prompt("Nom du nouveau corps :", "Corps");
    if (name === null) return;
    refresh(call("add_body", name.trim() ? { name: name.trim() } : {}));
  }));

document.getElementById("btn-datum").addEventListener("click", () =>
  featureCommand(() => panel.open({
    icon: "PartDesign_Plane",
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
    // Aperçu : le plan se dessine là où il se posera.
    onChange: (v) => schedulePreview(datumBuild(v)),
    onPreview: (on, v) => schedulePreview(on ? datumBuild(v) : null),
    onApply: (v) => {
      clearGhost();
      refresh(call("add_datum_plane", datumBuild(v).params));
    },
  })));

function datumBuild(v) {
  const params = {
    offset: num(v.offset) ?? 0,
    angle: num(v.angle) ?? 0,
  };
  if (v.sel && v.sel.face != null) params.face = v.sel.face;
  else params.base = v.base;
  return { op: "add_datum_plane", params };
}

const pickFile = installFileDialog(document, {
  listDir: (path) => call("list_dir", path ? { path } : {}),
  storage: localStore,
});

async function openDocument(path) {
  if (!path) return;
  if (!(await mayDiscard())) return;
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
          icon: "view-measurement",
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
  { scene, camera, renderer, controls, call, say, refresh, panel, boxOverlay,
    hideContextToolbar: () => ctx.hideContextToolbar?.(), storage: localStore,
    modelEdges: () => edgeData });

installShortcutBar(document, {
  ribbon: RIBBON_LAYOUT,
  sketchActive: () => sketchMode.active,
});
installCommandSearch(document, {
  ribbon: RIBBON_LAYOUT,
  sketchActive: () => sketchMode.active,
});

// Hôte des plugins : le corps est dans main/pluginhost.js.
Object.assign(ctx, {
  RIBBONS, call, say, refresh, scene, camera, controls, renderer, showTab,
  bindFeature,
});
installPluginHost(ctx);

// ---------- boot ----------
// Le corps est dans main/boot.js.
Object.assign(ctx, {
  call, say, localStore, refresh, updateViewport, renderTree, clearFeatureDims,
  openDocument, showTab, bindFeature, showAssemblyMeshes, renderAssemblyTree,
  mayDiscard,
});
installBoot(ctx);
