// FreeSolid — sketch mode. The viewport becomes a 2D drafting surface:
// the camera locks onto the sketch plane, clicks land in sketch-local
// coordinates, endpoints snap, dimensions are drawn and double-clickable.
//
// The server owns truth (geometry, solver); this module owns gesture.

import * as THREE from "three";
import { t } from "./i18n.js";
import { iconSrc } from "./icons.js";
import { createLocalSolver } from "./solver.js";
import { CLICK_TOOLS, OPEN_TOOLS, curvatureComb,
  endpointDirection, gridStep, hiddenByLayers,
  polygonVertexFromApothem } from "./sketchtools.js";
import {
  arcAngles, chainClickAction, clickSelection, distanceToEntity,
  relationGlyphs, samePick,
  sketchPreviewPoints,
} from "./geom2d.js";
import { fmtMm } from "./num.js";
import { eventToNdc, ndcToScreen } from "./screen.js";
import { createSplineEditor2d } from "./splineedit2d.js";
import {
  boxMode, isDrag, normalizeRect, pickInBox, sketchLocalPoints,
} from "./navigation.js";
import {
  arrowTriangle, dimEditPayload, dimGeometry, dimLabel, dimOffsetAt,
  openDimEditor, pointPairDimKind, pointPairDimPath,
} from "./dims.js";
import { ORIGIN_GEO, sceneTheme } from "./sketch/commun.js";
import {
  SNAP_KINDS, SNAP_PX, SNAP_TOL, activeSnaps, arcSnaps, circleSnaps,
  engineSnaps, lineSnaps, modelEdgeOf, modelEdgeSnaps, normalizeSnapSettings,
  onCircle, readSnapSettings, rectSnaps, sketchEndpoints, sketchSnapPoints,
  snapSketchPoint, snapTarget, writeSnapSettings,
} from "./sketchsnap.js";
import {
  normalizeSketchPrefs, readSketchPrefs, writeSketchPrefs,
} from "./sketchprefs.js";
import {
  DIM_LABEL_RATIO, DIM_TEXT_PX, createDimSprite, createGlyphSprite,
} from "./sketch/dimsprite.js";
import { installCommandes } from "./sketch/commandes.js";
import { installRelations } from "./sketch/relations.js";
import { installEntites } from "./sketch/entites.js";
import { installImage } from "./sketch/image.js";
import { installPanneauOutil } from "./sketch/panneauoutil.js";
import { installSaisie } from "./sketch/saisie.js";
import { installBoiteCote } from "./sketch/boitecote.js";

export { DIM_TEXT_PX, createDimSprite };

export function createSketchMode(deps) {
  const { scene, camera, renderer, controls, call: engineCall, say, refresh,
    panel, boxOverlay, hideContextToolbar, storage = null,
    modelEdges = () => null } = deps;

  /** L'appel au moteur : un accrochage à une arête de la pièce
   *  ("edge:k") lui est nommé `{ edge: k }` (engineSnaps). */
  function call(op, params = {}) {
    return engineCall(op, params.snaps
      ? { ...params, snaps: engineSnaps(params.snaps) } : params);
  }

  // Session partagée avec les modules de app/sketch/ : ils lisent les
  // fonctions et const de cette fermeture une fois, à l'installation, et
  // les `let` (ou redraw, réaffectée plus bas) à l'usage, par `sk.x` —
  // le patron de main.js et ctx.
  const sk = {};
  function expose(name, get, set) {
    Object.defineProperty(sk, name, {
      get, set, enumerable: true, configurable: true,
    });
  }
  expose("redraw", () => redraw);

  const group = new THREE.Group();
  scene.add(group);

  // depthTest off + high renderOrder: the sketch reads through the solid,
  // as in common modelers — a sketch drawn on a face was invisible behind the
  // mesh (user report).
  // Couleur = état de définition de l'entité (moteur : entity.status) :
  // bleu = encore libre, clair = entièrement définie, rouge = en trop.
  const STATUS_COLORS = { under: sceneTheme.under, full: sceneTheme.defined, over: sceneTheme.danger };
  // « transparent » partout : la pièce l'est (estompage de l'aperçu), donc
  // dessinée dans la passe transparente — un trait opaque passerait avant
  // elle et resterait caché par le solide (esquisse sur un plan qui le
  // traverse). Dans la même passe, l'ordre 20 du groupe le met devant.
  const ON_TOP = { depthTest: false, transparent: true };
  const lineMaterials = {};
  const constructionMaterials = {};
  for (const [status, color] of Object.entries(STATUS_COLORS)) {
    lineMaterials[status] = new THREE.LineBasicMaterial({ color, ...ON_TOP });
    // Construction : en tirets et estompée, comme partout.
    constructionMaterials[status] = new THREE.LineDashedMaterial({
      color, dashSize: 2.5, gapSize: 1.8, depthTest: false,
      transparent: true, opacity: 0.6 });
  }
  const previewMaterial = new THREE.LineBasicMaterial(
    { color: sceneTheme.accent, ...ON_TOP });
  // Références liées à la pièce : couleur des courbes 3D, elles suivent
  // la pièce et ne se déplacent pas à la main.
  const externalMaterial = new THREE.LineBasicMaterial(
    { color: sceneTheme.curve, ...ON_TOP });
  // Une matière par couleur de calque, gardée (jamais disposée).
  const layerMaterials = new Map();
  function layerMaterial(color) {
    if (!layerMaterials.has(color)) {
      layerMaterials.set(color, new THREE.LineBasicMaterial(
        { color: new THREE.Color(color), ...ON_TOP }));
    }
    return layerMaterials.get(color);
  }
  const combMaterial = new THREE.LineBasicMaterial(
    { color: sceneTheme.accent, transparent: true, opacity: 0.55,
      depthTest: false });
  const selectedMaterial = new THREE.LineBasicMaterial(
    { color: sceneTheme.selection, ...ON_TOP });
  // Cotes : lignes d'attache, ligne de cote et flèches. Pilotante en bleu
  // clair, de référence (pilotée) en gris.
  const dimLineMaterial = new THREE.LineBasicMaterial(
    { color: sceneTheme.dim, ...ON_TOP });
  const drivenDimLineMaterial = new THREE.LineBasicMaterial(
    { color: sceneTheme.ink2, ...ON_TOP });
  const dimTipMaterial = new THREE.MeshBasicMaterial(
    { color: sceneTheme.dim, side: THREE.DoubleSide, ...ON_TOP });
  const drivenDimTipMaterial = new THREE.MeshBasicMaterial(
    { color: sceneTheme.ink2, side: THREE.DoubleSide, ...ON_TOP });
  const pointMaterial = new THREE.PointsMaterial({
    color: sceneTheme.accent, size: 7, sizeAttenuation: false, ...ON_TOP });
  // Un point choisi (extrémité, centre) : plus gros, couleur de la
  // sélection — son entité, elle, ne l'est pas.
  const selectedPointMaterial = new THREE.PointsMaterial({
    color: sceneTheme.selection, size: 11, sizeAttenuation: false, ...ON_TOP });
  // Sous le curseur de l'outil Sélectionner : ce que le clic choisira, le
  // point ou l'entité entière — en jaune, ni le bleu du tracé ni l'orange
  // de la sélection.
  const hoverMaterial = new THREE.LineBasicMaterial(
    { color: sceneTheme.ghost, ...ON_TOP });
  const hoverPointMaterial = new THREE.PointsMaterial({
    color: sceneTheme.ghost, size: 11, sizeAttenuation: false, ...ON_TOP });
  group.renderOrder = 20;

  const mode = {
    active: false,
    state: null,          // last sketch_state from the server
    tool: "select",       // select | line | circle | dim
    chain: null,          // last point of the line chain, sketch-local
    pendingCircle: null,  // center while waiting for the radius click
    pendingRect: null,    // first corner while waiting for the second
    pendingRectC: null,   // center while waiting for a corner
    pendingArc: null,     // { c, start? } — centre puis départ puis fin
    pendingSpline: null,  // points cliqués — Entrée pour terminer
    pendingClicks: null,  // clics des outils de sketchtools.js
    chamfer: { distance: 2, distance2: null }, // outil chanfrein
    pendingEllipse: null, // { c, major? } — centre, grand axe, petit axe
    pendingArc3: null,    // [p1, p2] — départ, fin, puis passage
    pendingSlot: null,    // { a, b? } — centres puis largeur
    pendingPoly: null,    // { sides, c? } — centre puis sommet
    pendingFillet: null,  // { geo, x, y } — première ligne cliquée
    pendingDim: null,     // { geo, point? } — première entité cotée
    pendingDimPair: null, // deux points choisis, la cote attend sa place
    dimDrag: null,        // cote saisie par son étiquette, en déplacement
    filletRadius: 3,      // rayon du congé d'esquisse (panneau de l'outil)
    polygonSides: 6,      // côtés du polygone (panneau de l'outil)
    selection: [],        // [{ geo, point? }] — outil Sélectionner
    hover: null,          // { geo, point? } sous le curseur de Sélectionner
    justDragged: false,   // un drag qui finit ne doit pas sélectionner
    drag: null,           // { geo, point } while dragging
    box: null,            // { x, y } — appui dans le vide : cadre possible
    dragLocal: null,      // dernière position d'un glisser, pour le lâcher
    solverOk: false,      // l'esquisse est chargée dans le solveur local
    snapSettings: readSnapSettings(storage), // sortes d'accrochage (réglage)
    prefs: readSketchPrefs(storage), // vue, grille, symboles, cotes (réglage)
    quickSnap: null,      // { kind, keep } — accrochage rapide en cours
    savedCamera: null,
    matrix: new THREE.Matrix4(),
    inverse: new THREE.Matrix4(),
    plane: new THREE.Plane(),
    lastFinished: null,   // sketch name, for "pad what I just drew"
  };

  const DRAG_CLICK_PX = 3; // en-dessous : clic, pas un drag
  let building = false; // construction multi-appels (rectangle) en cours

  let entityPanelOpen = false;
  let entityPanelGeo = null;
  let entityPanelGen = 0;
  expose("entityPanelOpen", () => entityPanelOpen, (v) => { entityPanelOpen = v; });
  expose("entityPanelGeo", () => entityPanelGeo, (v) => { entityPanelGeo = v; });
  expose("entityPanelGen", () => entityPanelGen, (v) => { entityPanelGen = v; });

  // Spline sélectionnée : points de passage, poignées, pôles dans la vue.
  const splineEdit = createSplineEditor2d({
    THREE, theme: sceneTheme, toScreen, toLocal, call, say, controls,
    getState: () => mode.state,
    // La spline choisie seule et entière (un de ses bouts choisi : non).
    selectedSpline: () => {
      const [pick, ...rest] = mode.active ? mode.selection : [];
      return pick && !rest.length && pick.point == null
        ? mode.state?.entities.find((e) => e.id === pick.geo) ?? null : null;
    },
    applyState: (state, opts) => applyState(state, opts),
    redraw: () => redraw(),
    setCursor: (name) => setCursor(name),
  });
  splineEdit.onChosen = () => syncEntityPanel({ refresh: true });

  // Le corps est dans sketch/entites.js.
  Object.assign(sk, {
    call, say, panel, mode, splineEdit, applyState, safe, editListedDim,
  });
  const {
    entityPicks, uniqueSelectionGeos, abandonEntityPanel, closeEntityPanel,
    syncEntityPanel, openEntityPanel,
  } = installEntites(sk);

  // M3 : le solveur planegcs (WASM) côté client. Pendant un drag, la
  // résolution est locale (60 fps, zéro réseau) ; le serveur réconcilie
  // au lâcher. Si l'esquisse contient une géométrie ou contrainte non
  // traduite, solverOk reste false et on retombe sur le drag serveur.
  const localSolver = createLocalSolver();

  const CURSORS = { select: "default", line: "crosshair", rect: "crosshair",
                    rectc: "crosshair", circle: "crosshair",
                    arc: "crosshair", arc3: "crosshair", slot: "crosshair",
                    polygon: "crosshair", skfillet: "pointer",
                    skchamfer: "pointer", extend: "pointer", split: "pointer",
                    skcorner: "pointer", splconvert: "pointer", g2: "crosshair",
                    splknot: "pointer", spldegree: "pointer",
                    dimarc: "crosshair", dimaxis: "crosshair",
                    dimdia: "crosshair", ordx: "crosshair", ordy: "crosshair",
                    trim: "pointer", construction: "pointer",
                    spline: "crosshair", ellipse: "crosshair",
                    dim: "crosshair",
                    ...Object.fromEntries(
                      [...Object.keys(CLICK_TOOLS), ...Object.keys(OPEN_TOOLS)]
                        .map((tool) => [tool, "crosshair"])) };

  function setCursor(name) {
    renderer.domElement.style.cursor = name;
  }

  // ---------- coordinates ----------

  function toLocal(event) {
    const rect = renderer.domElement.getBoundingClientRect();
    const ndc = eventToNdc(event.clientX, event.clientY, rect);
    const pointer = new THREE.Vector2(ndc.x, ndc.y);
    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(pointer, camera);
    const world = new THREE.Vector3();
    if (!raycaster.ray.intersectPlane(mode.plane, world)) return null;
    return world.applyMatrix4(mode.inverse);
  }

  function toScreen(x, y) {
    const world = new THREE.Vector3(x, y, 0).applyMatrix4(mode.matrix);
    const projected = world.project(camera);
    const rect = renderer.domElement.getBoundingClientRect();
    return ndcToScreen(projected.x, projected.y, rect);
  }

  /** Unité de tracé des cotes : suit le zoom, taille constante à l'écran. */
  function dimDrawSize() {
    return (camera.top - camera.bottom) / (camera.zoom || 1) * 0.02;
  }

  /** Entités sur un calque masqué : invisibles et hors d'atteinte. */
  function hiddenIds() {
    return hiddenByLayers(mode.state?.entities, mode.state?.layers);
  }

  function endpoints() {
    return sketchEndpoints(mode.state?.entities, hiddenIds());
  }

  // Points d'accrochage : les extrémités et centres, plus l'origine de
  // l'esquisse — on démarre souvent un profil dessus. L'origine ne se
  // glisse pas : overEndpoint ne la voit pas.
  function snapPoints() {
    return sketchSnapPoints(mode.state?.entities, hiddenIds());
  }

  // Les arêtes de la pièce dans le plan de l'esquisse (modelEdgeSnaps) :
  // recalculées quand le maillage des arêtes ou l'état de l'esquisse
  // change.
  const NO_MODEL = { entities: [], points: [] };
  let modelCache = { edges: null, state: null, snaps: NO_MODEL };
  function modelSnaps() {
    const edges = modelEdges();
    if (!edges || !mode.state) return NO_MODEL;
    if (modelCache.edges !== edges || modelCache.state !== mode.state) {
      const inSketch = (x, y, z) => {
        const v = new THREE.Vector3(x, y, z).applyMatrix4(mode.inverse);
        return [v.x, v.y, v.z];
      };
      modelCache = { edges, state: mode.state, snaps: modelEdgeSnaps(
        edges, inSketch,
        { externals: mode.state.entities.filter((e) => e.external) }) };
    }
    return modelCache.snaps;
  }

  /** Les arêtes de la pièce accrochent au tracé et au glisser d'un point.
   *  Pas au premier clic de l'arc tangent : il part d'une extrémité de
   *  l'esquisse ; ni aux outils qui nomment un point de l'esquisse (cote
   *  ordonnée, courbure…). */
  function modelSnapsFor(moving) {
    const first = CLICK_TOOLS[mode.tool]?.needsEndpoint
      && !mode.pendingClicks?.length;
    return (moving || DRAW_TOOLS.has(mode.tool)) && !first
      ? modelSnaps() : NO_MODEL;
  }

  /** Une entité de l'esquisse, ou une arête de la pièce ("edge:k"). */
  function snapEntity(id) {
    return modelEdgeOf(id) != null
      ? modelSnaps().entities.find((e) => e.id === id)
      : mode.state?.entities.find((e) => e.id === id);
  }

  /** Les sortes d'accrochage actives : le réglage, ou l'accrochage
   *  rapide. Le premier clic de l'arc tangent vise une extrémité : il en
   *  garde l'accrochage. */
  function snapKinds() {
    const kinds = activeSnaps(mode.snapSettings, mode.quickSnap);
    if (CLICK_TOOLS[mode.tool]?.needsEndpoint && !mode.pendingClicks?.length) {
      kinds.add("endpoint");
    }
    return kinds;
  }

  /** Où tombe le curseur : voir snapSketchPoint (sketchsnap.js).
   *  `moving` : pendant un glisser, les entités qui bougent avec le point
   *  — il ne s'accroche pas à elles ; Ctrl suspend l'accrochage. Les
   *  arêtes de la pièce accrochent après celles de l'esquisse. */
  function snap(local, event, { moving = null } = {}) {
    const hidden = hiddenIds();
    const still = (geo) => !moving?.has(geo);
    const model = modelSnapsFor(moving);
    // Grille : un pas rond qui suit le zoom (≈ 1/40 de la vue).
    const step = gridStep((camera.top - camera.bottom) / (camera.zoom || 1));
    return snapSketchPoint(local, { x: event.clientX, y: event.clientY }, {
      points: [...snapPoints().filter((p) => still(p.geo)), ...model.points],
      toScreen, chain: moving ? null : mode.chain,
      entities: [...(mode.state?.entities ?? [])
        .filter((e) => !hidden.has(e.id) && still(e.id)), ...model.entities],
      woken: mode.woken ?? [], angleStep: mode.snapSettings.angleStep,
      kinds: snapKinds(),
      // Maj maintenu : des longueurs au pas de la grille, affichée ou non.
      lengthStep: event.shiftKey && !moving ? step : null,
      gridStep: mode.prefs.gridSnap ? step : null,
      suspended: moving ? !!(event.ctrlKey || event.metaKey)
        : suspendsSnap(event),
    });
  }

  /**
   * Accrochage rapide : la seule sorte `kind` (SNAP_KINDS) pour l'entité
   * en cours, même accrochages coupés. Choisie une seconde fois, elle est
   * gardée jusqu'au changement d'outil ; null la retire.
   */
  function pickQuickSnap(kind) {
    const label = SNAP_KINDS.find((k) => k.key === kind)?.label;
    if (!DRAW_TOOLS.has(mode.tool) || !label) {
      mode.quickSnap = null;
      say(t("Accrochage rapide retiré"));
      return;
    }
    const keep = mode.quickSnap?.kind === kind;
    mode.quickSnap = { kind, keep };
    say(t(keep
      ? "Accrochage rapide gardé : {k} — jusqu'au changement d'outil"
      : "Accrochage rapide : {k} — pour l'entité en cours ; choisissez-le "
        + "de nouveau pour le garder", { k: t(label) }));
  }

  /** Le réglage des accrochages : appliqué, gardé, et l'interrupteur de
   *  la barre d'esquisse suit. */
  function setSnapSettings(settings) {
    mode.snapSettings = normalizeSnapSettings(settings);
    writeSnapSettings(storage, mode.snapSettings);
    document.getElementById("sk-snap")
      ?.classList.toggle("on", mode.snapSettings.enabled);
  }
  sk.setSnapSettings = setSnapSettings;

  //: Réglage d'esquisse -> son bouton dans la barre d'esquisse.
  const PREF_BUTTONS = {
    gridSnap: "sk-grid", showComb: "sk-comb",
    showRelations: "sk-show-rel", showDims: "sk-show-dims",
  };

  /** Les réglages d'affichage de l'esquisse : appliqués, gardés, et les
   *  boutons de la barre suivent. */
  function setSketchPrefs(prefs) {
    mode.prefs = normalizeSketchPrefs(prefs);
    writeSketchPrefs(storage, mode.prefs);
    for (const [key, id] of Object.entries(PREF_BUTTONS)) {
      document.getElementById(id)?.classList.toggle("on", mode.prefs[key]);
    }
    if (mode.active) redraw();
  }
  sk.setSketchPrefs = setSketchPrefs;

  /** Les lignes survolées pendant le tracé : la suivante peut leur être
   *  parallèle ou perpendiculaire. Les deux dernières. */
  function wake(s) {
    const entity = s.hover != null && snapEntity(s.hover);
    if (entity?.type !== "line") return;
    mode.woken = [entity.id, ...(mode.woken ?? []).filter((id) => id !== entity.id)]
      .slice(0, 2);
  }

  /** Ctrl maintenu pendant un tracé : le point reste sous le curseur,
   *  sans accrochage ni relation. Pas au premier clic d'un outil qui
   *  part d'une extrémité (arc tangent) : il doit en viser une. */
  function suspendsSnap(event) {
    if (!(event.ctrlKey || event.metaKey) || !DRAW_TOOLS.has(mode.tool)) {
      return false;
    }
    return !(CLICK_TOOLS[mode.tool]?.needsEndpoint
      && !mode.pendingClicks?.length);
  }

  /** Ce qu'un tracé garde d'un clic : où, et ce qu'il a accroché. */
  function clickOf(snapped) {
    return { x: snapped.x, y: snapped.y, onPoint: snapped.onPoint ?? null,
             target: snapped.target ?? null,
             direction: snapped.direction ?? null,
             suspended: !!snapped.suspended };
  }

  // ---------- aides au tracé ----------
  // Lignes d'inférence pointillées, point accroché en évidence et lecture
  // (longueur, angle, dimensions) près du curseur.

  const DRAW_TOOLS = new Set(["line", "rect", "rectc", "circle", "arc",
    "arc3", "slot", "polygon", "spline", "ellipse",
    ...Object.keys(CLICK_TOOLS), ...Object.keys(OPEN_TOOLS)]);
  const guideMaterial = new THREE.LineDashedMaterial({
    color: sceneTheme.under, dashSize: 1.5, gapSize: 1.2, depthTest: false,
    transparent: true, opacity: 0.8 });
  const snapMaterial = new THREE.PointsMaterial({
    color: sceneTheme.selection, size: 11, sizeAttenuation: false, depthTest: false, transparent: true });
  // Ligne d'aide d'une direction qui posera une relation : la couleur du
  // point accroché. Les repères (alignement, pas d'angle) restent bleus.
  const rayMaterial = new THREE.LineDashedMaterial({
    color: sceneTheme.selection, dashSize: 1.5, gapSize: 1.2, depthTest: false,
    transparent: true, opacity: 0.9 });
  // Milieu et quadrants de l'entité survolée : où le clic peut se poser.
  const wakeMaterial = new THREE.PointsMaterial({
    color: sceneTheme.under, size: 6, sizeAttenuation: false, depthTest: false,
    transparent: true, opacity: 0.9 });
  let inferLines = null;
  let rayLines = null;
  let snapPoint = null;
  let wakePoints = null;
  let modelLines = null;
  let readoutEl = null;

  // Le symbole de la relation que le clic posera, devant la lecture.
  const SNAP_SYMBOLS = {
    point: ["rel_coincident", "Coïncidente"],
    midpoint: ["rel_midpoint", "Milieu"],
    quadrant: ["rel_onobject", "Quadrant"],
    intersection: ["rel_intersection", "Croisement"],
    on: ["rel_onobject", "Sur l'entité"],
    H: ["rel_horizontal", "Horizontale"],
    V: ["rel_vertical", "Verticale"],
    parallel: ["rel_parallel", "Parallèle"],
    perpendicular: ["rel_perpendicular", "Perpendiculaire"],
    tangent: ["rel_tangent", "Tangente"],
  };

  function dropInferenceObjects() {
    for (const obj of [inferLines, rayLines, snapPoint, wakePoints, modelLines]) {
      if (obj) { group.remove(obj); obj.geometry.dispose(); }
    }
    inferLines = null;
    rayLines = null;
    snapPoint = null;
    wakePoints = null;
    modelLines = null;
  }

  function dashedLines(segments, material, order) {
    const lines = new THREE.LineSegments(
      new THREE.BufferGeometry().setFromPoints(segments.flatMap(
        ([x1, y1, x2, y2]) => [new THREE.Vector3(x1, y1, 0),
                               new THREE.Vector3(x2, y2, 0)])), material);
    lines.computeLineDistances();
    lines.renderOrder = order;
    group.add(lines);
    return lines;
  }

  function clearInference() {
    dropInferenceObjects();
    if (readoutEl) readoutEl.hidden = true;
  }

  function readoutText(s) {
    const parts = [];
    if (mode.tool === "line" && mode.chain) {
      const dx = s.x - mode.chain.x, dy = s.y - mode.chain.y;
      parts.push(t("L {v} mm", { v: fmtMm(Math.hypot(dx, dy)) }),
        `${fmtMm(Math.atan2(dy, dx) * 180 / Math.PI)}°`);
    } else if (mode.tool === "rect" && mode.pendingRect) {
      parts.push(`${fmtMm(Math.abs(s.x - mode.pendingRect.x))} × `
        + `${fmtMm(Math.abs(s.y - mode.pendingRect.y))} mm`);
    } else if (mode.tool === "rectc" && mode.pendingRectC) {
      parts.push(`${fmtMm(2 * Math.abs(s.x - mode.pendingRectC.x))} × `
        + `${fmtMm(2 * Math.abs(s.y - mode.pendingRectC.y))} mm`);
    } else if (mode.tool === "circle" && mode.pendingCircle) {
      const r = Math.hypot(s.x - mode.pendingCircle.x, s.y - mode.pendingCircle.y);
      parts.push(t("R {v} mm", { v: fmtMm(r) }));
    } else {
      parts.push(`${fmtMm(s.x)}, ${fmtMm(s.y)}`);
    }
    return parts.join(" · ");
  }

  /** Position du curseur dans l'esquisse, pour la barre d'état. */
  function emitPointer(local) {
    document.dispatchEvent(new CustomEvent("freesolid:sketch-pointer", {
      detail: local ? { x: local.x, y: local.y } : null }));
  }

  function updateInference(event) {
    const local = toLocal(event);
    if (!local || !mode.state) { clearInference(); emitPointer(null); return; }
    const s = snap(local, event);
    mode.lastLocal = { x: s.x, y: s.y };
    emitPointer(s);
    if (!s.suspended) wake(s);
    showInference(s, event);
  }

  /** Les aides d'un accrochage `s` (snapSketchPoint) : lignes
   *  d'alignement et de direction, point accroché, points remarquables
   *  de l'entité survolée, et la lecture près du curseur avec le symbole
   *  de la relation qui sera posée. */
  function showInference(s, event) {
    dropInferenceObjects();
    const plain = [...s.guides.map((g) => [g.x, g.y, s.x, s.y]),
      ...s.rays.filter((r) => !r.relation).map((r) => [r.x1, r.y1, r.x2, r.y2])];
    const related = s.rays.filter((r) => r.relation)
      .map((r) => [r.x1, r.y1, r.x2, r.y2]);
    if (plain.length) inferLines = dashedLines(plain, guideMaterial, 23);
    if (related.length) rayLines = dashedLines(related, rayMaterial, 23);
    if (s.target) {
      snapPoint = new THREE.Points(new THREE.BufferGeometry().setFromPoints(
        [new THREE.Vector3(s.x, s.y, 0)]), snapMaterial);
      snapPoint.renderOrder = 24;
      group.add(snapPoint);
    }
    if (s.wake.length) {
      wakePoints = new THREE.Points(new THREE.BufferGeometry().setFromPoints(
        s.wake.map((p) => new THREE.Vector3(p.x, p.y, 0))), wakeMaterial);
      wakePoints.renderOrder = 23;
      group.add(wakePoints);
    }
    // Les arêtes de la pièce visées ou survolées : en évidence — le clic
    // les liera à l'esquisse.
    const edges = new Set([s.target?.geo, ...(s.target?.geos ?? []),
      s.direction?.geo, s.hover].filter((id) => modelEdgeOf(id) != null));
    const segments = [...edges].flatMap((id) => {
      const pts = entityPolyline(snapEntity(id) ?? {});
      return pts.slice(1).flatMap((q, i) => [
        new THREE.Vector3(pts[i][0], pts[i][1], 0), new THREE.Vector3(q[0], q[1], 0)]);
    });
    if (segments.length) {
      modelLines = new THREE.LineSegments(
        new THREE.BufferGeometry().setFromPoints(segments), hoverMaterial);
      modelLines.renderOrder = 22;
      group.add(modelLines);
    }
    if (!readoutEl) {
      readoutEl = document.createElement("div");
      readoutEl.className = "sk-readout";
      renderer.domElement.parentElement.appendChild(readoutEl);
    }
    const host = renderer.domElement.parentElement.getBoundingClientRect();
    readoutEl.hidden = false;
    // Les symboles des relations que le clic posera, puis la lecture.
    const parts = [s.kind, s.direction?.kind, s.hv]
      .map((key) => SNAP_SYMBOLS[key]).filter(Boolean).map(([icon, label]) => {
        const img = document.createElement("img");
        img.src = iconSrc(icon);
        img.alt = img.title = t(label);
        return img;
      });
    readoutEl.replaceChildren(...parts, document.createTextNode(readoutText(s)));
    readoutEl.style.left = `${event.clientX - host.left + 16}px`;
    readoutEl.style.top = `${event.clientY - host.top + 18}px`;
  }

  // ---------- drawing ----------

  let previewLine = null;
  expose("previewLine", () => previewLine);

  let imageLayer = null; // { mesh, aspect, fileName, params }
  let imageLoadGen = 0;
  expose("imageLayer", () => imageLayer, (v) => { imageLayer = v; });
  expose("imageLoadGen", () => imageLoadGen, (v) => { imageLoadGen = v; });

  // Le corps est dans sketch/image.js.
  Object.assign(sk, { call, say, panel, group, mode, abandonEntityPanel });
  const {
    revokePendingImageUrl, disposeImageLayer, loadSketchImage, showImage,
  } = installImage(sk);

  // Qui alloue dispose. Matériaux partagés (lineMaterial, etc.) : pas
  // de flag, jamais disposés. Sprites de cotes : userData.own = true.
  // Image d'esquisse : retirée avant ce parcours (comme previewLine).
  function disposeSubtree(root) {
    root.traverse((obj) => {
      obj.geometry?.dispose();
      const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
      for (const m of mats) {
        if (m && m.userData?.own) { m.map?.dispose(); m.dispose(); }
      }
    });
  }

  let hoverObject = null;

  /** Ce que le clic de Sélectionner choisira, en évidence : le point
   *  (extrémité, centre, origine) ou l'entité entière. */
  function drawHover() {
    if (hoverObject) {
      group.remove(hoverObject);
      hoverObject.geometry.dispose();
      hoverObject = null;
    }
    const pick = mode.tool === "select" && !mode.drag && !mode.box
      ? mode.hover : null;
    // Déjà choisi : la sélection le montre.
    if (!pick || !mode.state || mode.selection.some((s) => samePick(s, pick))) {
      return;
    }
    if (pick.point != null) {
      const p = pickPoint(pick);
      if (!p) return;
      hoverObject = new THREE.Points(new THREE.BufferGeometry().setFromPoints(
        [new THREE.Vector3(p.x, p.y, 0)]), hoverPointMaterial);
    } else {
      const entity = mode.state.entities.find((e) => e.id === pick.geo);
      const pts = entity ? entityPolyline(entity) : [];
      if (pts.length < 2) return;
      hoverObject = new THREE.Line(new THREE.BufferGeometry().setFromPoints(
        pts.map((q) => new THREE.Vector3(q[0], q[1], 0))), hoverMaterial);
    }
    hoverObject.renderOrder = 22;
    group.add(hoverObject);
  }

  /** Le survol de l'outil Sélectionner change : redessiné s'il le faut. */
  function setHover(pick) {
    const same = pick && mode.hover ? samePick(pick, mode.hover)
      : !pick && !mode.hover;
    if (same) return;
    mode.hover = pick;
    drawHover();
  }

  function redraw() {
    updateRelationButtons();
    if (previewLine) group.remove(previewLine);
    const imageMesh = imageLayer?.mesh;
    if (imageMesh) group.remove(imageMesh);
    disposeSubtree(group);
    group.clear();
    group.matrix.copy(mode.matrix);
    group.matrixAutoUpdate = false;
    if (imageMesh && mode.active) group.add(imageMesh);
    if (!mode.state) return;

    const points = [];
    const hidden = hiddenIds();
    const layerColor = new Map((mode.state.layers ?? [])
      .filter((l) => l.color).map((l) => [l.name, l.color]));
    for (const entity of mode.state.entities) {
      if (hidden.has(entity.id)) continue;
      // Un point choisi ne colore pas son entité : seule l'entité entière.
      const isSelected = mode.selection.some(
        (s) => s.geo === entity.id && s.point == null);
      const status = STATUS_COLORS[entity.status] ? entity.status : "under";
      const tint = layerColor.get(entity.layer);
      const material = isSelected ? selectedMaterial
        : entity.external ? externalMaterial
          : entity.construction ? constructionMaterials[status]
            : tint ? layerMaterial(tint) : lineMaterials[status];
      if (entity.type === "arc") {
        const { a1, a2 } = arcAngles(entity);
        const segments = [];
        for (let i = 0; i <= 32; i++) {
          const a = a1 + (i / 32) * (a2 - a1);
          segments.push(new THREE.Vector3(
            entity.c[0] + entity.r * Math.cos(a),
            entity.c[1] + entity.r * Math.sin(a), 0));
        }
        const arc = new THREE.Line(
          new THREE.BufferGeometry().setFromPoints(segments), material);
        if (entity.construction && !isSelected) arc.computeLineDistances();
        arc.renderOrder = 20;
        group.add(arc);
        points.push(entity.p1, entity.p2);
      } else if (entity.type === "line") {
        const geometry = new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(entity.p1[0], entity.p1[1], 0),
          new THREE.Vector3(entity.p2[0], entity.p2[1], 0)]);
        const line = new THREE.Line(geometry, material);
        if (entity.construction) line.computeLineDistances();
        line.renderOrder = 20;
        group.add(line);
        points.push(entity.p1, entity.p2);
      } else if (entity.type === "circle") {
        const segments = [];
        for (let i = 0; i <= 48; i++) {
          const a = (i / 48) * Math.PI * 2;
          segments.push(new THREE.Vector3(
            entity.c[0] + entity.r * Math.cos(a),
            entity.c[1] + entity.r * Math.sin(a), 0));
        }
        const circle = new THREE.Line(
          new THREE.BufferGeometry().setFromPoints(segments), material);
        if (entity.construction) circle.computeLineDistances();
        circle.renderOrder = 20;
        group.add(circle);
        points.push(entity.c);
      } else if (entity.type === "point") {
        points.push(entity.p1);
      } else if (entity.type === "poly" && entity.points?.length > 1) {
        // Splines, ellipses, coniques : le serveur envoie la polyligne.
        const pts = entity.points.map(
          (p) => new THREE.Vector3(p[0], p[1], 0));
        const line = new THREE.Line(
          new THREE.BufferGeometry().setFromPoints(pts), material);
        if (entity.construction && !isSelected) line.computeLineDistances();
        line.renderOrder = 20;
        group.add(line);
      }
    }
    // Origine de l'esquisse : deux flèches courtes, à taille d'écran.
    const span = (camera.top - camera.bottom) / (camera.zoom || 1);
    const size = span * 0.035;
    const originSelected = mode.selection.some((s) => s.geo === ORIGIN_GEO);
    for (const [dx, dy] of [[1, 0], [0, 1]]) {
      const arrow = new THREE.ArrowHelper(
        new THREE.Vector3(dx, dy, 0), new THREE.Vector3(0, 0, 0),
        size, originSelected ? sceneTheme.accent : sceneTheme.axisX,
        size * 0.3, size * 0.18);
      arrow.traverse((obj) => {
        if (obj.material) {
          obj.material.transparent = true;
          obj.material.depthTest = false;
          obj.material.userData.own = true;
        }
        obj.renderOrder = 19;
      });
      group.add(arrow);
    }

    if (mode.prefs.showComb) {
      // Peigne de courbure : une dent par point, normale à la courbe,
      // longue comme la courbure — on voit où elle se tend ou s'aplatit.
      // Les courbes sélectionnées, sinon toutes les courbes libres (pas
      // les contours bloqués d'un texte).
      const blocked = new Set((mode.state.constraints ?? [])
        .filter((c) => c.type === "Block").map((c) => c.geos[0]));
      const picked = new Set(mode.selection.map((s) => s.geo));
      const curves = mode.state.entities.filter((e) => e.type === "poly"
        && e.points?.length > 2
        && (picked.size ? picked.has(e.id) : !blocked.has(e.id)));
      const comb = [];
      for (const [p, q] of curvatureComb(curves.map((e) => e.points),
        span * 0.08)) {
        comb.push(new THREE.Vector3(p[0], p[1], 0),
                  new THREE.Vector3(q[0], q[1], 0));
      }
      if (comb.length) {
        const teeth = new THREE.LineSegments(
          new THREE.BufferGeometry().setFromPoints(comb), combMaterial);
        teeth.renderOrder = 20;
        group.add(teeth);
      }
    }

    if (points.length) {
      const flat = new Float32Array(points.flatMap((p) => [p[0], p[1], 0]));
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.BufferAttribute(flat, 3));
      const cloud = new THREE.Points(geometry, pointMaterial);
      cloud.renderOrder = 21;
      group.add(cloud);
    }
    const chosen = mode.selection
      .filter((s) => s.point != null && s.geo !== ORIGIN_GEO && !hidden.has(s.geo))
      .map(pickPoint).filter(Boolean);
    if (chosen.length) {
      const dots = new THREE.Points(new THREE.BufferGeometry().setFromPoints(
        chosen.map((p) => new THREE.Vector3(p.x, p.y, 0))), selectedPointMaterial);
      dots.renderOrder = 22;
      group.add(dots);
    }

    // Calques masqués : ni symboles, ni cotes de leurs entités. Les
    // boutons de la barre masquent tous les symboles, ou toutes les cotes.
    const shown = mode.state.entities.filter((e) => !hidden.has(e.id));
    const glyphs = !mode.prefs.showRelations ? []
      : relationGlyphs(mode.state.constraints, shown, span * 0.025);
    for (const glyph of glyphs) {
      const sprite = createGlyphSprite(glyph.text);
      sprite.position.set(glyph.x, glyph.y, 0.01);
      sprite.scale.set(span * 0.028, span * 0.028, 1);
      sprite.renderOrder = 22;
      group.add(sprite);
    }

    // L'unité de tracé suit le zoom : la cote garde sa taille à l'écran.
    const dimSize = dimDrawSize();
    // Un pixel d'écran, en unités de l'esquisse.
    const px = span / Math.max(renderer.domElement.clientHeight, 1);
    for (const dim of !mode.prefs.showDims ? [] : mode.state.dims) {
      const constraint = (mode.state.constraints ?? [])
        .find((c) => c.id === dim.id);
      if ((constraint?.geos ?? [dim.geo]).some((g) => hidden.has(g))) continue;
      const shape = dimGeometry(dim, constraint, mode.state.entities, dimSize);
      if (!shape) continue;
      const segments = shape.segments;
      if (shape.arrows.length) {
        // Pointes pleines et fines, à taille d'écran (9 × 3 px).
        const tips = new Float32Array(shape.arrows.flatMap((a) => {
          const [x1, y1, x2, y2, x3, y3] = arrowTriangle(a, px * 9, px * 1.6);
          return [x1, y1, 0, x2, y2, 0, x3, y3, 0];
        }));
        const tipGeometry = new THREE.BufferGeometry();
        tipGeometry.setAttribute("position", new THREE.BufferAttribute(tips, 3));
        const arrows = new THREE.Mesh(tipGeometry,
          constraint?.driving === false ? drivenDimTipMaterial : dimTipMaterial);
        arrows.renderOrder = 21;
        group.add(arrows);
      }
      if (segments.length) {
        const flat = new Float32Array(segments.flatMap(
          ([x1, y1, x2, y2]) => [x1, y1, 0, x2, y2, 0]));
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute("position", new THREE.BufferAttribute(flat, 3));
        const lines = new THREE.LineSegments(geometry,
          constraint?.driving === false ? drivenDimLineMaterial
            : dimLineMaterial);
        lines.renderOrder = 21;
        group.add(lines);
      }
      const sprite = createDimSprite(dimLabel(dim), shape.label.x, shape.label.y);
      // Étiquette à taille d'écran constante.
      const labelHeight = px * DIM_TEXT_PX * DIM_LABEL_RATIO;
      const labelWidth = labelHeight * sprite.userData.aspect;
      sprite.scale.set(labelWidth, labelHeight, 1);
      if (shape.along && shape.normal) {
        // Juste à côté de sa ligne, sans la chevaucher : le texte est plus
        // large que haut, une cote verticale l'écarte de sa demi-largeur.
        const n = shape.normal;
        const reach = Math.abs(n.x) * labelWidth / 2
          + Math.abs(n.y) * labelHeight / 2 + px * 2;
        sprite.position.set(shape.along.x + n.x * reach,
                            shape.along.y + n.y * reach, 0.01);
      }
      sprite.userData.dim = dim;
      sprite.renderOrder = 22;
      group.add(sprite);
    }

    splineEdit.draw(group);
    hoverObject = null; // group.clear() l'a retiré
    drawHover();

    const dof = mode.state.dof;
    const definition = mode.state.definition
      ?? (mode.state.fullyConstrained ? "full" : "under");
    say(definition === "over"
      ? t("Esquisse : sur-contrainte — une relation ou une cote est en trop")
      : definition === "full"
        ? t("Esquisse : totalement contrainte")
        : dof !== null
          ? t("Esquisse : sous-contrainte ({n} DDL)", { n: dof })
          : t("Esquisse : en édition"));
  }

  function applyState(state, { keepSelection = false } = {}) {
    const prevSelection = keepSelection ? mode.selection : [];
    const before = mode.state?.entities?.length ?? 0;
    mode.state = state;
    // Une entité de plus pendant un tracé : elle est finie, l'accrochage
    // rapide pris pour elle seule s'arrête là.
    if (mode.quickSnap && !mode.quickSnap.keep && DRAW_TOOLS.has(mode.tool)
        && (state.entities?.length ?? 0) > before) {
      mode.quickSnap = null;
    }
    // Geometry ids may have shifted (trim, delete): stale picks lie,
    // unless the appelant garantit que les ids tiennent (move, cote…).
    const ids = new Set((state.entities ?? []).map((e) => e.id));
    mode.selection = prevSelection.filter(
      (s) => ids.has(s.geo) || s.geo === ORIGIN_GEO);
    mode.pendingDim = null;
    mode.pendingDimPair = null;
    mode.pendingFillet = null;
    mode.matrix.set(...state.placement);
    mode.inverse.copy(mode.matrix).invert();
    const normal = new THREE.Vector3(0, 0, 1)
      .transformDirection(mode.matrix);
    const origin = new THREE.Vector3().setFromMatrixPosition(mode.matrix);
    mode.plane.setFromNormalAndCoplanarPoint(normal, origin);
    mode.solverOk = localSolver.ready && localSolver.load(state);
    redraw();
    document.dispatchEvent(new Event("freesolid:sketch-state"));
    if (!mode.drag && entityPanelOpen) syncEntityPanel({ refresh: true });
  }

  // ---------- gestures ----------

  async function safe(promise, opts) {
    try {
      applyState(await promise, opts);
    } catch (error) {
      say(error.message, true);
    }
  }

  // Circumcenter of three points; null when they are collinear.
  function circumcenter(a, b, c) {
    const d = 2 * (a.x * (b.y - c.y) + b.x * (c.y - a.y) + c.x * (a.y - b.y));
    if (Math.abs(d) < 1e-9) return null;
    const a2 = a.x * a.x + a.y * a.y;
    const b2 = b.x * b.x + b.y * b.y;
    const c2 = c.x * c.x + c.y * c.y;
    return {
      x: (a2 * (b.y - c.y) + b2 * (c.y - a.y) + c2 * (a.y - b.y)) / d,
      y: (a2 * (c.x - b.x) + b2 * (a.x - c.x) + c2 * (b.x - a.x)) / d,
    };
  }

  /** Le point qui termine l'entité en cours (second clic, ou cotes
   *  tapées) : ligne (la chaîne continue), rectangle, cercle. */
  async function placeDrawPoint(point) {
    const name = mode.state.sketch;
    if (mode.tool === "line" && mode.chain) {
      const from = mode.chain;
      // Le point suivant part d'ici ; le moteur le voit coïncider avec la
      // fin de cette ligne.
      mode.chain = point.onPoint ? null : { x: point.x, y: point.y };
      await safe(call("sketch_add_line", { sketch: name,
        x1: from.x, y1: from.y, x2: point.x, y2: point.y,
        snaps: lineSnaps(from, point) }));
    } else if (mode.tool === "rect" && mode.pendingRect) {
      const a = mode.pendingRect;
      mode.pendingRect = null;
      building = true;
      try {
        await addRectangle(name, a, point, false,
          rectSnaps({ corner1: a, corner2: point }));
      } finally {
        building = false;
      }
    } else if (mode.tool === "rectc" && mode.pendingRectC) {
      const c = mode.pendingRectC;
      mode.pendingRectC = null;
      building = true;
      try {
        await addRectangle(name,
          { x: 2 * c.x - point.x, y: 2 * c.y - point.y }, point, true,
          rectSnaps({ corner2: point, center: c }));
      } finally {
        building = false;
      }
    } else if (mode.tool === "circle" && mode.pendingCircle) {
      const c = mode.pendingCircle;
      mode.pendingCircle = null;
      const r = Math.hypot(point.x - c.x, point.y - c.y);
      if (r > 0) await safe(call("sketch_add_circle",
        { sketch: name, cx: c.x, cy: c.y, r, snaps: circleSnaps(c, [point]) }));
    }
  }

  /** Point déjà posé par l'outil en cours, si la saisie numérique a un
   *  sens maintenant. */
  function pendingDrawPoint() {
    if (mode.tool === "line") return mode.chain;
    if (mode.tool === "circle") return mode.pendingCircle;
    if (mode.tool === "rect") return mode.pendingRect;
    if (mode.tool === "rectc") return mode.pendingRectC;
    return null;
  }

  // Le corps est dans sketch/saisie.js.
  Object.assign(sk, {
    renderer, say, mode, clearInference, placeDrawPoint, pendingDrawPoint,
    dimTyped,
  });
  const { closeNumericEntry, openNumericEntry } = installSaisie(sk);

  /** Les valeurs tapées deviennent des cotes de l'entité tracée : on a
   *  donné la dimension exacte, l'esquisse la garde. */
  async function dimTyped(tool, before, a, b) {
    if (!mode.state) return;
    const fresh = mode.state.entities.filter((e) => !before.has(e.id));
    const sketch = mode.state.sketch;
    const dims = [];
    if (tool === "circle") {
      const circle = fresh.find((e) => e.type === "circle");
      if (circle && a > 0) dims.push({ geo: circle.id, radius: true, value: a });
    } else if (tool === "line") {
      const line = fresh.find((e) => e.type === "line");
      if (line && a > 0) dims.push({ geo: line.id, value: a });
    } else if (tool === "rect" || tool === "rectc") {
      const lines = fresh.filter((e) => e.type === "line");
      const flat = lines.find((e) => Math.abs(e.p1[1] - e.p2[1]) < 1e-9);
      const upright = lines.find((e) => Math.abs(e.p1[0] - e.p2[0]) < 1e-9);
      if (flat && a > 0) dims.push({ geo: flat.id, value: a });
      if (upright && b > 0) dims.push({ geo: upright.id, value: b });
    }
    for (const dim of dims) {
      await safe(call("sketch_dim", { sketch, ...dim }));
    }
  }

  /** Un clic d'un outil de sketchtools.js : rangé, puis l'op au dernier. */
  async function clickToolStep(spec, snapped, name) {
    const pts = [...(mode.pendingClicks ?? [])];
    let p = clickOf(snapped);
    if (spec.needsEndpoint && !pts.length) {
      const on = snapped.onPoint;
      const entity = on && (mode.state.entities ?? []).find(
        (e) => e.id === on.geo);
      const dir = entity && (on.point === 1 || on.point === 2)
        ? endpointDirection(entity, on.point) : null;
      if (!dir) {
        say(t(spec.prompts[0]), true);
        return;
      }
      p = { ...p, geo: on.geo, point: on.point, dir };
    }
    pts.push(p);
    if (pts.length < spec.clicks) {
      mode.pendingClicks = pts;
      say(t(spec.prompts[pts.length]));
      return;
    }
    mode.pendingClicks = null;
    if (previewLine) previewLine.visible = false;
    const out = spec.build(pts);
    if (out.error) {
      say(t(out.error), true);
      return;
    }
    say(t(spec.prompts[0]));
    const snaps = spec.snaps?.(pts);
    await safe(call(out.op,
      { sketch: name, ...out.params, ...(snaps ? { snaps } : {}) }));
  }

  async function onClick(event) {
    if (building) return;
    const local = toLocal(event);
    if (!local || !mode.state) return;
    const snapped = snap(local, event);
    const name = mode.state.sketch;

    if (CLICK_TOOLS[mode.tool]) {
      await clickToolStep(CLICK_TOOLS[mode.tool], snapped, name);
      return;
    }
    if (OPEN_TOOLS[mode.tool]) {
      const spec = OPEN_TOOLS[mode.tool];
      const pts = mode.pendingClicks ?? [];
      const last = pts[pts.length - 1];
      if (last && chainClickAction(toScreen(last.x, last.y),
          { x: event.clientX, y: event.clientY }, SNAP_PX) === "finish") {
        return;
      }
      mode.pendingClicks = [...pts, { x: snapped.x, y: snapped.y }];
      say(t(spec.prompt, { n: mode.pendingClicks.length }));
      return;
    }

    if (mode.tool === "select") {
      if (mode.justDragged) { mode.justDragged = false; return; }
      // Un clic choisit ce qu'il touche, seul ; Ctrl (ou Maj) l'ajoute à
      // la sélection, ou l'en retire.
      const additive = event.ctrlKey || event.metaKey || event.shiftKey;
      const pick = selectPickAt(event);
      mode.selection = clickSelection(mode.selection, pick, additive);
      redraw();
      if (mode.selection.length) {
        say(t("Sélection : {n} entité(s) — relation, symétrie ou répétition ; clic dans le vide = vider",
          { n: mode.selection.length }));
      }
      syncEntityPanel();
      if (additive && pick) sk.showQuickRelations(event);
    } else if (mode.tool === "line") {
      if (!mode.chain) {
        mode.chain = clickOf(snapped);
        say("Ligne : cliquez le point suivant (Échap pour terminer)");
      } else {
        const from = mode.chain;
        const prevScreen = toScreen(from.x, from.y);
        // Double-clic (2e clic sur le point venant d'être posé) : terminer
        // la chaîne comme Échap, sans segment de longueur nulle.
        if (chainClickAction(prevScreen,
            { x: event.clientX, y: event.clientY }, SNAP_PX) === "finish") {
          setTool("select");
          return;
        }
        await placeDrawPoint(snapped);
      }
    } else if (mode.tool === "rect") {
      if (!mode.pendingRect) {
        mode.pendingRect = clickOf(snapped);
        say("Rectangle : cliquez le sommet opposé — ou tapez la largeur");
      } else {
        await placeDrawPoint(snapped);
      }
    } else if (mode.tool === "rectc") {
      if (!mode.pendingRectC) {
        mode.pendingRectC = clickOf(snapped);
        say("Rectangle par le centre : cliquez un sommet — ou tapez la largeur");
      } else {
        await placeDrawPoint(snapped);
      }
    } else if (mode.tool === "circle") {
      if (!mode.pendingCircle) {
        mode.pendingCircle = clickOf(snapped);
        say("Cercle : cliquez pour donner le rayon — ou tapez-le");
      } else {
        await placeDrawPoint(snapped);
      }
    } else if (mode.tool === "arc") {
      if (!mode.pendingArc) {
        mode.pendingArc = { c: clickOf(snapped) };
        say("Arc : cliquez le point de départ");
      } else if (!mode.pendingArc.start) {
        mode.pendingArc.start = clickOf(snapped);
        say("Arc : cliquez le point d'arrivée (sens anti-horaire)");
      } else {
        const { c, start } = mode.pendingArc;
        mode.pendingArc = null;
        const r = Math.hypot(start.x - c.x, start.y - c.y);
        if (r <= 0) return;
        const a1 = Math.atan2(start.y - c.y, start.x - c.x);
        let a2 = Math.atan2(snapped.y - c.y, snapped.x - c.x);
        if (a2 <= a1) a2 += Math.PI * 2;
        // Le bout ne tombe sur le point visé que s'il est au même rayon.
        const end = onCircle(snapped, c, r) ? clickOf(snapped) : null;
        safe(call("sketch_add_arc", { sketch: name, cx: c.x, cy: c.y, r,
          a1, a2, snaps: arcSnaps({ center: c, start, end }) }));
      }
    } else if (mode.tool === "arc3") {
      if (!mode.pendingArc3) {
        mode.pendingArc3 = [clickOf(snapped)];
        say("Arc 3 points : cliquez le point d'arrivée");
      } else if (mode.pendingArc3.length === 1) {
        mode.pendingArc3.push(clickOf(snapped));
        say("Arc 3 points : cliquez un point de passage");
      } else {
        const [p1, p2] = mode.pendingArc3;
        mode.pendingArc3 = null;
        const c = circumcenter(p1, p2, snapped);
        if (!c) { say("Arc : les trois points sont alignés", true); return; }
        const r = Math.hypot(p1.x - c.x, p1.y - c.y);
        const norm = (a, from) => (a <= from ? a + Math.PI * 2 : a);
        const aS = Math.atan2(p1.y - c.y, p1.x - c.x);
        const aE = norm(Math.atan2(p2.y - c.y, p2.x - c.x), aS);
        const aM = norm(Math.atan2(snapped.y - c.y, snapped.x - c.x), aS);
        // CCW from p1 must pass through the third point; otherwise the
        // arc runs the other way round (start at p2).
        const params = aM < aE
          ? { a1: aS, a2: aE }
          : { a1: aE - Math.PI * 2, a2: aS };
        const [start, end] = aM < aE ? [p1, p2] : [p2, p1];
        safe(call("sketch_add_arc", { sketch: name, cx: c.x, cy: c.y, r,
          ...params, snaps: arcSnaps({ start, end, on: [clickOf(snapped)] }) }));
      }
    } else if (mode.tool === "slot") {
      if (!mode.pendingSlot) {
        mode.pendingSlot = { a: { x: snapped.x, y: snapped.y } };
        say("Rainure : cliquez le centre du second bout");
      } else if (!mode.pendingSlot.b) {
        mode.pendingSlot.b = { x: snapped.x, y: snapped.y };
        say("Rainure : cliquez pour donner la largeur");
      } else {
        const { a, b } = mode.pendingSlot;
        mode.pendingSlot = null;
        const len = Math.hypot(b.x - a.x, b.y - a.y);
        if (len <= 0) return;
        const width = 2 * Math.abs(
          ((b.x - a.x) * (a.y - snapped.y)
            - (b.y - a.y) * (a.x - snapped.x)) / len);
        if (width <= 0) { say("Rainure : largeur nulle", true); return; }
        safe(call("sketch_add_slot", { sketch: name,
          x1: a.x, y1: a.y, x2: b.x, y2: b.y, width }));
      }
    } else if (mode.tool === "polygon") {
      if (!mode.pendingPoly) return; // le nombre de côtés a été annulé
      if (!mode.pendingPoly.c) {
        mode.pendingPoly.c = { x: snapped.x, y: snapped.y };
        say("Polygone : cliquez un sommet");
      } else {
        const { sides, c } = mode.pendingPoly;
        mode.pendingPoly = { sides };
        // Cercle inscrit : le clic est au milieu d'un côté, pas au sommet.
        const vertex = mode.polygonInscribed
          ? polygonVertexFromApothem(c, snapped, sides) : snapped;
        safe(call("sketch_add_polygon", { sketch: name,
          cx: c.x, cy: c.y, x: vertex.x, y: vertex.y, sides }));
      }
    } else if (mode.tool === "skfillet") {
      const target = nearestEntity(event);
      if (target === null) return;
      if (!mode.pendingFillet) {
        mode.pendingFillet = { geo: target, x: local.x, y: local.y };
        say("Congé d'esquisse : cliquez la seconde ligne, près du coin");
      } else if (mode.pendingFillet.geo !== target) {
        const first = mode.pendingFillet;
        mode.pendingFillet = null;
        // Le rayon vient du panneau de l'outil, réglé avant les clics.
        const radius = mode.filletRadius;
        if (!(radius > 0)) {
          say(t("Congé d'esquisse : rayon invalide"), true);
          return;
        }
        say(t("Congé d'esquisse : cliquez deux lignes près du coin"));
        await safe(call("sketch_fillet", { sketch: name,
          geo1: first.geo, geo2: target,
          x1: first.x, y1: first.y, x2: local.x, y2: local.y, radius }));
      }
    } else if (mode.tool === "skchamfer") {
      const target = nearestEntity(event);
      if (target === null) return;
      if (!mode.pendingFillet) {
        mode.pendingFillet = { geo: target, x: local.x, y: local.y };
        say("Chanfrein d'esquisse : cliquez la seconde ligne, près du coin");
      } else if (mode.pendingFillet.geo !== target) {
        const first = mode.pendingFillet;
        mode.pendingFillet = null;
        const { distance, distance2 } = mode.chamfer;
        if (!(distance > 0)) {
          say(t("Chanfrein d'esquisse : distance invalide"), true);
          return;
        }
        say(t("Chanfrein d'esquisse : cliquez deux lignes près du coin"));
        await safe(call("sketch_chamfer", { sketch: name,
          geo1: first.geo, geo2: target, x1: first.x, y1: first.y,
          x2: local.x, y2: local.y, distance,
          ...(distance2 > 0 ? { distance2 } : {}) }));
      }
    } else if (mode.tool === "skcorner") {
      const target = nearestEntity(event);
      if (target === null) return;
      if (!mode.pendingFillet) {
        mode.pendingFillet = { geo: target, x: local.x, y: local.y };
        say(t("Coin : cliquez la seconde ligne, du côté à garder"));
      } else if (mode.pendingFillet.geo !== target) {
        const first = mode.pendingFillet;
        mode.pendingFillet = null;
        say(t("Coin : cliquez deux lignes, du côté à garder"));
        await safe(call("sketch_corner", { sketch: name,
          geo1: first.geo, geo2: target, x1: first.x, y1: first.y,
          x2: local.x, y2: local.y }));
      }
    } else if (mode.tool === "g2") {
      // Égaliser la courbure : le bout de la spline de référence, puis le
      // bout de celle qui s'y raccorde.
      let point = snapped.onPoint;
      if (point && mode.pendingG2 && point.geo === mode.pendingG2.geo) {
        // Raccord : les deux bouts sont au même endroit — on prend celui
        // de l'autre spline.
        point = [...endpoints()].find((q) => q.geo !== point.geo
          && Math.hypot(q.x - point.x, q.y - point.y) < 1e-6) ?? point;
      }
      const entity = point && mode.state.entities.find((e) => e.id === point.geo);
      if (!entity || entity.kind !== "spline" || !(point.point === 1 || point.point === 2)) {
        say(t("Courbure : cliquez le bout d'une spline"), true);
        return;
      }
      if (!mode.pendingG2) {
        mode.pendingG2 = point;
        say(t("Courbure : cliquez le bout de la spline à raccorder"));
      } else {
        const first = mode.pendingG2;
        mode.pendingG2 = null;
        say(t("Courbure : cliquez le bout de la spline de référence"));
        await safe(call("sketch_match_curvature", { sketch: name,
          geo1: first.geo, point1: first.point,
          geo2: point.geo, point2: point.point }));
      }
    } else if (["splconvert", "splknot", "spldegree"].includes(mode.tool)) {
      const target = nearestEntity(event);
      if (target !== null) {
        const action = { splconvert: "convert", splknot: "knot",
                         spldegree: "degree" }[mode.tool];
        safe(call("sketch_spline", { sketch: name, geo: target, action,
          x: local.x, y: local.y }));
      }
    } else if (["dimarc", "dimaxis", "dimdia"].includes(mode.tool)) {
      const target = nearestEntity(event);
      if (target !== null) {
        const measure = { dimarc: "arc_length", dimaxis: "axis_angle",
                          dimdia: "diameter" }[mode.tool];
        safe(call("sketch_dim", { sketch: name, geo: target, measure,
          at: [snapped.x, snapped.y] }));
      }
    } else if (mode.tool === "ordx" || mode.tool === "ordy") {
      // Cote ordonnée : le point de base, puis chaque point coté depuis
      // lui, le long de X (ordx) ou de Y (ordy).
      const point = snapped.onPoint;
      if (!point) {
        say(t("Cote ordonnée : cliquez un point (extrémité, centre, origine)"), true);
        return;
      }
      if (!mode.ordinateBase) {
        mode.ordinateBase = point;
        say(t("Cote ordonnée : cliquez les points à coter depuis la base"));
      } else {
        const base = mode.ordinateBase;
        safe(call("sketch_dim", { sketch: name,
          geo: base.geo, point: base.point, geo2: point.geo,
          point2: point.point, axis: mode.tool === "ordx" ? "x" : "y",
          at: [snapped.x, snapped.y] }));
      }
    } else if (mode.tool === "extend" || mode.tool === "split") {
      const target = nearestEntity(event);
      if (target !== null) {
        safe(call(mode.tool === "extend" ? "sketch_extend" : "sketch_split",
          { sketch: name, geo: target, x: snapped.x, y: snapped.y }));
      }
    } else if (mode.tool === "trim") {
      const target = nearestEntity(event);
      if (target !== null) {
        safe(call("sketch_trim",
          { sketch: name, geo: target, x: local.x, y: local.y }));
      }
    } else if (mode.tool === "spline") {
      mode.pendingSpline = mode.pendingSpline ?? [];
      const last = mode.pendingSpline[mode.pendingSpline.length - 1];
      if (last) {
        const prevScreen = toScreen(last.x, last.y);
        if (chainClickAction(prevScreen,
            { x: event.clientX, y: event.clientY }, SNAP_PX) === "finish") {
          return;
        }
      }
      mode.pendingSpline.push({ x: snapped.x, y: snapped.y });
      say(t("Spline : {n} point(s) — Entrée pour terminer (min 3), Échap pour annuler",
        { n: mode.pendingSpline.length }));
    } else if (mode.tool === "ellipse") {
      if (!mode.pendingEllipse) {
        mode.pendingEllipse = { c: { x: snapped.x, y: snapped.y } };
        say("Ellipse : cliquez l'extrémité du grand axe");
      } else if (!mode.pendingEllipse.major) {
        mode.pendingEllipse.major = { x: snapped.x, y: snapped.y };
        say("Ellipse : cliquez pour donner le petit rayon");
      } else {
        const { c, major } = mode.pendingEllipse;
        mode.pendingEllipse = null;
        const rx = Math.hypot(major.x - c.x, major.y - c.y);
        if (rx <= 0) return;
        const angle = Math.atan2(major.y - c.y, major.x - c.x)
          * 180 / Math.PI;
        const ux = (major.x - c.x) / rx, uy = (major.y - c.y) / rx;
        const ry = Math.abs(
          ux * (snapped.y - c.y) - uy * (snapped.x - c.x));
        if (ry <= 0) { say("Ellipse : petit rayon nul", true); return; }
        safe(call("sketch_add_ellipse",
          { sketch: name, cx: c.x, cy: c.y, rx, ry, angle }));
      }
    } else if (mode.tool === "construction") {
      const target = nearestEntity(event);
      if (target !== null) {
        safe(call("sketch_toggle_construction",
          { sketch: name, geo: target }));
      }
    } else if (mode.tool === "dim") {
      if (mode.pendingDimPair) {
        // 3e clic : l'endroit choisi décide horizontale, verticale ou alignée.
        const { first, second, a, b } = mode.pendingDimPair;
        mode.pendingDimPair = null;
        if (previewLine) previewLine.visible = false;
        const kind = pointPairDimKind(a, b, local);
        const params = { sketch: name, geo: first.geo, geo2: second.geo,
                         point: first.point, point2: second.point };
        if (kind === "DistanceX") params.axis = "x";
        if (kind === "DistanceY") params.axis = "y";
        await addDim(params, event);
        return;
      }
      const endpoint = overPoint(event);
      const nearest = nearestEntity(event);
      const target = endpoint
        ? { geo: endpoint.geo, point: endpoint.point }
        : nearest !== null ? { geo: nearest } : null;
      if (!mode.pendingDim) {
        if (!target) return;
        mode.pendingDim = target;
        say("Cotation : cliquez une 2e entité — ou dans le vide pour " +
            "coter celle-ci seule");
      } else {
        const first = mode.pendingDim;
        mode.pendingDim = null;
        if (previewLine) previewLine.visible = false;
        let params;
        if (!target
            || (target.geo === first.geo && target.point === first.point)) {
          if (first.geo === ORIGIN_GEO) {
            // L'origine seule n'a rien à coter : il lui faut un vis-à-vis.
            mode.pendingDim = first;
            say(t("Cotation : cliquez l'entité à coter depuis l'origine"));
            return;
          }
          params = { sketch: name, geo: first.geo };
          // Une ligne : ce 2e clic pose sa longueur — à côté : verticale,
          // dessus ou dessous : horizontale, entre : alignée.
          const ends = lineEnds(first);
          if (ends && local) {
            const kind = pointPairDimKind(ends[0], ends[1], local);
            if (kind !== "Distance") {
              Object.assign(params, { geo2: first.geo, point: 1, point2: 2,
                                      axis: kind === "DistanceX" ? "x" : "y" });
            }
          }
        } else if (target.geo === first.geo && isRound(first.geo)
                   && [first.point, target.point].includes(3)
                   && [first.point, target.point].includes(undefined)) {
          // Un cercle puis son centre (ou l'inverse) : le rayon.
          params = { sketch: name, geo: first.geo, radius: true };
        } else {
          // Deux points (un cercle compte par son centre) : la cote se
          // pose d'un 3e clic, qui choisit son sens.
          const pair = [first, target].map((pick) => (pick.point == null
            && isRound(pick.geo) ? { geo: pick.geo, point: 3 } : pick));
          const ends = pair.map(pickPoint);
          if (ends.every(Boolean)) {
            mode.pendingDimPair = { first: pair[0], second: pair[1],
                                    a: ends[0], b: ends[1] };
            say(t("Cotation : cliquez où poser la cote — à côté : verticale, "
              + "dessus ou dessous : horizontale, entre : alignée"));
            return;
          }
          params = { sketch: name, geo: first.geo, geo2: target.geo };
          if (first.point != null) params.point = first.point;
          if (target.point != null) params.point2 = target.point;
        }
        await addDim(params, event);
      }
    }
  }

  /** Pose la cote à la valeur mesurée, puis ouvre la saisie de la vraie. */
  async function addDim(params, event) {
    const before = new Set((mode.state.dims ?? []).map((d) => d.id));
    const at = { x: event.clientX, y: event.clientY };
    // Là où on a cliqué pour la poser : la cote y reste.
    const local = toLocal(event);
    const placed = local ? { ...params, at: [local.x, local.y] } : params;
    try {
      applyState(await call("sketch_dim", placed));
      const created = (mode.state.dims ?? [])
        .find((d) => !before.has(d.id));
      if (created) openModifyBox(created, at);
    } catch (error) {
      say(error.message, true);
    }
  }

  /** Extrémités d'une ligne choisie entière, ou null. */
  function lineEnds(pick) {
    if (pick.point != null) return null;
    const entity = mode.state?.entities.find((e) => e.id === pick.geo);
    if (entity?.type !== "line") return null;
    return [{ x: entity.p1[0], y: entity.p1[1] },
            { x: entity.p2[0], y: entity.p2[1] }];
  }

  function isRound(geo) {
    const entity = mode.state?.entities.find((e) => e.id === geo);
    return entity?.type === "circle" || entity?.type === "arc";
  }

  /** Coordonnées locales d'un point choisi (extrémité, centre, origine). */
  function pickPoint(pick) {
    if (pick.geo === ORIGIN_GEO) return { x: 0, y: 0 };
    const entity = mode.state?.entities.find((e) => e.id === pick.geo);
    const p = pick.point === 1 ? entity?.p1 : pick.point === 2 ? entity?.p2
      : pick.point === 3 ? entity?.c : null;
    return p ? { x: p[0], y: p[1] } : null;
  }

  // Le corps est dans sketch/panneauoutil.js.
  Object.assign(sk, { panel, mode, abandonEntityPanel, setTool });
  const { openToolPanel, closeToolPanel } = installPanneauOutil(sk);

  async function addRectangle(name, a, b, center = false, snaps = {}) {
    // Une seule opération (un seul Ctrl+Z) : le moteur enchaîne les quatre
    // côtés comme tracés à la main (coïncidences, horizontal/vertical) ;
    // par le centre, les coins restent symétriques autour de lui.
    if (a.x === b.x || a.y === b.y) {
      say("Rectangle : les sommets doivent être en diagonale", true);
      return;
    }
    try {
      applyState(await call("sketch_add_rectangle", { sketch: name,
        x1: a.x, y1: a.y, x2: b.x, y2: b.y, center, snaps }));
    } catch (error) {
      say(error.message, true);
    }
  }

  function nearestEntity(event) {
    // Distance réelle à la courbe (segment / |d−r|), seuil écran 18 px.
    const local = toLocal(event);
    if (!local) return null;
    let best = null, bestDistance = 18;
    const hidden = hiddenIds();
    for (const entity of mode.state.entities) {
      if (hidden.has(entity.id)) continue;
      const distLocal = distanceToEntity(local.x, local.y, entity);
      if (!Number.isFinite(distLocal)) continue;
      // Convertir en pixels via un voisinage local (dérivée approx.).
      const s0 = toScreen(local.x, local.y);
      const s1 = toScreen(local.x + 1, local.y);
      const pxPerUnit = Math.hypot(s1.x - s0.x, s1.y - s0.y) || 1;
      const distance = distLocal * pxPerUnit;
      if (distance < bestDistance) {
        best = entity.id;
        bestDistance = distance;
      }
    }
    return best;
  }

  function overEntity(event) {
    const id = nearestEntity(event);
    if (id == null) return null;
    return mode.state.entities.find((e) => e.id === id) ?? null;
  }

  function onPointerDown(event) {
    if (event.button !== 0 || mode.tool !== "select" || !mode.state) return;
    // Spline sélectionnée : ses points, poignées et pôles d'abord.
    if (splineEdit.pointerDown(event)) {
      mode.justDragged = true; // le click qui suit garde la sélection
      return;
    }
    // Étiquette de cote : on la glisse pour déplacer la cote.
    const dim = dimLabelAt(event);
    const grab = dim && grabDelta(dim, event);
    if (grab != null) {
      mode.dimDrag = { dim, grab, screen: { x: event.clientX, y: event.clientY },
                       moved: false, offset: null };
      controls.enabled = false;
      setCursor("grabbing");
      return;
    }
    const p = overEndpoint(event);
    if (p) {
      // Ce qui bouge avec le point : son entité et celles dont un point
      // lui coïncide — il ne s'accroche pas à elles.
      const moving = new Set([p.geo, ...endpoints()
        .filter((q) => Math.hypot(q.x - p.x, q.y - p.y) < SNAP_TOL)
        .map((q) => q.geo)]);
      mode.drag = { geo: p.geo, point: p.point, moving, snapped: null };
      mode.dragMoved = false;
      mode.dragScreen = { x: event.clientX, y: event.clientY };
      controls.enabled = false;
      setCursor("grabbing");
      return;
    }
    // Drag d'arête entière (Sketcher point 0 = courbe) : elle glisse sans
    // se déformer — une ligne, un cercle, un arc, une spline ; une
    // ellipse, non (le moteur ne sait pas la translater).
    const entity = overEntity(event);
    if (!entity) {
      mode.box = { x: event.clientX, y: event.clientY };
      return;
    }
    if (!slidesWhole(entity)) return;
    const local = toLocal(event);
    if (!local) return;
    mode.drag = {
      geo: entity.id,
      point: 0,
      grab: { x: local.x, y: local.y },
      base: snapshotEntity(entity),
    };
    mode.dragMoved = false;
    mode.dragScreen = { x: event.clientX, y: event.clientY };
    controls.enabled = false;
    setCursor("grabbing");
  }

  function snapshotEntity(entity) {
    const snap = { type: entity.type };
    if (entity.p1) snap.p1 = [...entity.p1];
    if (entity.p2) snap.p2 = [...entity.p2];
    if (entity.c) snap.c = [...entity.c];
    if (entity.r != null) snap.r = entity.r;
    if (entity.points) snap.points = entity.points.map((p) => [...p]);
    return snap;
  }

  /** Une entité qui glisse entière (sketch_move point 0). */
  function slidesWhole(entity) {
    return ["line", "circle", "arc"].includes(entity.type)
      || (entity.type === "poly" && entity.kind === "spline"
          && entity.points?.length > 1);
  }

  /** Cible abs. pour sketch_move point 0 : nouveau départ (ligne,
   *  spline) ou centre (cercle, arc) — le repère du moteur. */
  function wholeCurveTarget(drag, local) {
    const dx = local.x - drag.grab.x, dy = local.y - drag.grab.y;
    const b = drag.base;
    if (b.type === "circle" || b.type === "arc") {
      return { x: b.c[0] + dx, y: b.c[1] + dy };
    }
    const start = b.p1 ?? b.points[0];
    return { x: start[0] + dx, y: start[1] + dy };
  }

  function applyWholeCurveLocal(entity, drag, local) {
    const dx = local.x - drag.grab.x, dy = local.y - drag.grab.y;
    const b = drag.base;
    if (b.p1) entity.p1 = [b.p1[0] + dx, b.p1[1] + dy];
    if (b.p2) entity.p2 = [b.p2[0] + dx, b.p2[1] + dy];
    if (b.c) entity.c = [b.c[0] + dx, b.c[1] + dy];
    if (b.points) {
      entity.points = b.points.map((p) => [p[0] + dx, p[1] + dy]);
    }
  }

  /** Ce que le clic de Sélectionner choisit sous le curseur : un point
   *  d'abord (extrémité, centre, origine), sinon l'entité entière, ou
   *  null. */
  function selectPickAt(event) {
    const p = overPoint(event);
    if (p) return { geo: p.geo, point: p.point };
    const id = nearestEntity(event);
    return id === null ? null : { geo: id };
  }

  /** Extrémité, centre ou origine sous le curseur — ce qu'on clique pour
   *  sélectionner ou coter ; l'origine, elle, ne se glisse pas. */
  function overPoint(event) {
    for (const p of snapPoints()) {
      const s = toScreen(p.x, p.y);
      if (Math.hypot(s.x - event.clientX, s.y - event.clientY) < SNAP_PX) {
        return p;
      }
    }
    return null;
  }

  function overEndpoint(event) {
    for (const p of endpoints()) {
      const s = toScreen(p.x, p.y);
      if (Math.hypot(s.x - event.clientX, s.y - event.clientY) < SNAP_PX) {
        return p;
      }
    }
    return null;
  }

  let moveInFlight = false;
  let pendingMove = null; // { sketch, geo, point, x, y, snaps, gen } | null
  let moveGen = 0;

  // File sérielle du fallback serveur : un seul sketch_move en vol ;
  // pendant l'attente on ne garde que la dernière (x, y) ; seule la
  // réponse la plus récente peut applyState. Le lâcher du pointerup
  // (`drop` : sketch_drop, avec ses `snaps`) passe par ici aussi.
  function enqueueSketchMove(x, y, snaps = null, { drop = false } = {}) {
    if (!mode.state || !mode.drag) return;
    pendingMove = {
      sketch: mode.state.sketch,
      geo: mode.drag.geo,
      point: mode.drag.point,
      x, y, snaps, drop,
      gen: ++moveGen,
    };
    flushSketchMoves();
  }

  async function flushSketchMoves() {
    if (moveInFlight || !pendingMove) return;
    const req = pendingMove;
    pendingMove = null;
    moveInFlight = true;
    try {
      const state = await call(req.drop ? "sketch_drop" : "sketch_move", {
        sketch: req.sketch, geo: req.geo, point: req.point,
        x: req.x, y: req.y, ...(req.snaps ? { snaps: req.snaps } : {}),
      });
      if (req.gen === moveGen) applyState(state, { keepSelection: true });
    } catch (error) {
      if (req.gen === moveGen) {
        say(error.message, true);
        if (mode.state?.sketch) {
          safe(call("sketch_state", { sketch: mode.state.sketch }),
            { keepSelection: true });
        }
      }
    } finally {
      moveInFlight = false;
      if (pendingMove) flushSketchMoves();
    }
  }

  /** Ctrl+Z, Ctrl+Y (ou les boutons) dans l'esquisse : le moteur n'y
   *  défait que ses pas, jamais l'esquisse elle-même. Un tracé en cours
   *  repart de zéro : il visait peut-être ce qui vient d'être défait. */
  async function stepHistory(op, steps = 1) {
    if (!mode.active || !mode.state || building || mode.drag) return;
    const sketch = mode.state.sketch;
    setTool(mode.tool);
    await safe(call(op, { sketch, ...(steps > 1 ? { steps } : {}) }));
  }

  /** Une entité en polyligne, dans l'esquisse : `[[x, y]…]`. */
  function entityPolyline(entity) {
    let pts = [];
    if (entity.type === "line") {
      pts = [entity.p1, entity.p2];
    } else if (entity.type === "circle" || entity.type === "arc") {
      const { a1, a2 } = entity.type === "arc"
        ? arcAngles(entity) : { a1: 0, a2: Math.PI * 2 };
      for (let i = 0; i <= 32; i++) {
        const a = a1 + (i / 32) * (a2 - a1);
        pts.push([entity.c[0] + entity.r * Math.cos(a),
                  entity.c[1] + entity.r * Math.sin(a)]);
      }
    } else if (entity.points) {
      pts = entity.points;
    }
    return pts;
  }

  /** Points écran d'une entité, en polyligne, pour le cadre. */
  function entityScreenPoints(entity) {
    return entityPolyline(entity).map((p) => toScreen(p[0], p[1]));
  }

  function selectInBox(start, end, additive) {
    const items = (mode.state?.entities ?? []).map((entity) => ({
      id: entity.id, points: entityScreenPoints(entity),
    }));
    const ids = pickInBox(items, normalizeRect(start, end),
      boxMode(start, end));
    const kept = additive ? mode.selection : [];
    const fresh = ids.filter((id) => !kept.some((s) => s.geo === id))
      .map((geo) => ({ geo }));
    mode.selection = [...kept, ...fresh];
    say(t("Sélection : {n} entité(s) — relation, symétrie ou répétition ; clic dans le vide = vider",
      { n: mode.selection.length }));
    redraw();
    syncEntityPanel();
    sk.showQuickRelations({ clientX: end.x, clientY: end.y });
  }

  function onPointerMove(event) {
    mode.lastMouse = { clientX: event.clientX, clientY: event.clientY };
    if (DRAW_TOOLS.has(mode.tool)) updateInference(event);
    else {
      if (inferLines || snapPoint || !readoutEl?.hidden) clearInference();
      emitPointer(toLocal(event));
    }
    if (mode.box) {
      const here = { x: event.clientX, y: event.clientY };
      if (isDrag(mode.box, here)) boxOverlay?.show(mode.box, here);
      return;
    }
    if (mode.tool === "select" && splineEdit.pointerMove(event)) return;
    if (mode.dimDrag) {
      const drag = mode.dimDrag;
      if (Math.hypot(event.clientX - drag.screen.x,
                     event.clientY - drag.screen.y) > DRAG_CLICK_PX) {
        drag.moved = true;
      }
      const under = dragOffset(drag.dim, event);
      if (drag.moved && under != null) {
        // Aperçu local : la cote suit, le moteur la retient au lâcher.
        // L'étiquette garde sa prise : elle reste sous le curseur.
        const offset = under - drag.grab;
        drag.offset = offset;
        const live = mode.state.dims.find((d) => d.id === drag.dim.id);
        if (live) live.offset = offset;
        redraw();
      }
      return;
    }
    if (mode.tool === "select" && !mode.drag) {
      const hot = overEndpoint(event) || overEntity(event)
        || dimLabelAt(event);
      setCursor(hot ? "grab" : "default");
      setHover(selectPickAt(event));
    }
    if (mode.drag) {
      if (mode.dragScreen
          && Math.hypot(event.clientX - mode.dragScreen.x,
                        event.clientY - mode.dragScreen.y) > DRAG_CLICK_PX) {
        mode.dragMoved = true;
      }
      const local = toLocal(event);
      if (!local) return;
      // Un point glissé s'accroche comme un point tracé ; une entité
      // entière, non.
      const snapped = mode.drag.point === 0 ? null
        : snap(local, event, { moving: mode.drag.moving });
      mode.drag.snapped = snapped;
      const target = snapped ? { x: snapped.x, y: snapped.y }
        : wholeCurveTarget(mode.drag, local);
      mode.dragLocal = target; // pour le lâcher (sketch_drop)
      // M3 : résolution locale planegcs — toutes les contraintes tiennent
      // à 60 fps, zéro réseau ; le serveur réconcilie au pointerup.
      if (mode.solverOk) {
        const updates = localSolver.drag(
          mode.drag.geo, mode.drag.point, target.x, target.y);
        if (updates) {
          redraw();
          if (snapped) showInference(snapped, event);
          return;
        }
        mode.solverOk = false; // solveur KO : retour au chemin serveur
      }
      // Fallback : le point suit le curseur en local ; le solveur
      // serveur corrige via une file sérielle (un sketch_move en vol,
      // dernière position en attente).
      const entity = mode.state?.entities.find(
        (e) => e.id === mode.drag.geo);
      if (entity) {
        if (mode.drag.point === 0) {
          applyWholeCurveLocal(entity, mode.drag, local);
        } else if (mode.drag.point === 1 && entity.p1) {
          entity.p1 = [target.x, target.y];
        } else if (mode.drag.point === 2 && entity.p2) {
          entity.p2 = [target.x, target.y];
        } else if (mode.drag.point === 3 && entity.c) {
          entity.c = [target.x, target.y];
        }
        redraw();
        if (snapped) showInference(snapped, event);
      }
      enqueueSketchMove(target.x, target.y);
    } else if (mode.tool === "dim" && mode.pendingDim && previewLine
               && lineEnds(mode.pendingDim)) {
      const local = toLocal(event);
      if (!local) return;
      // Sur une autre entité, c'est une cote à deux qui se prépare.
      const other = overPoint(event) ?? nearestEntity(event);
      if (other != null && (other.geo ?? other) !== mode.pendingDim.geo) {
        previewLine.visible = false;
        return;
      }
      const [a, b] = lineEnds(mode.pendingDim);
      const path = pointPairDimPath(a, b, pointPairDimKind(a, b, local), local);
      previewLine.geometry.setFromPoints(
        path.map((p) => new THREE.Vector3(p.x, p.y, 0)));
      previewLine.visible = true;
    } else if ((CLICK_TOOLS[mode.tool] || OPEN_TOOLS[mode.tool])
               && mode.pendingClicks?.length && previewLine) {
      const local = toLocal(event);
      if (!local) return;
      const spec = CLICK_TOOLS[mode.tool] ?? OPEN_TOOLS[mode.tool];
      const pts = spec.preview(mode.pendingClicks, snap(local, event));
      if (pts.length < 2) {
        previewLine.visible = false;
        return;
      }
      previewLine.geometry.setFromPoints(
        pts.map((q) => new THREE.Vector3(q.x, q.y, 0)));
      previewLine.visible = true;
    } else if (mode.tool === "dim" && mode.pendingDimPair && previewLine) {
      const local = toLocal(event);
      if (!local) return;
      const { a, b } = mode.pendingDimPair;
      const path = pointPairDimPath(a, b, pointPairDimKind(a, b, local), local);
      previewLine.geometry.setFromPoints(
        path.map((p) => new THREE.Vector3(p.x, p.y, 0)));
      previewLine.visible = true;
    } else if (mode.tool === "line" && mode.chain && previewLine) {
      const local = toLocal(event);
      if (!local) return;
      const snapped = snap(local, event);
      previewLine.geometry.setFromPoints([
        new THREE.Vector3(mode.chain.x, mode.chain.y, 0),
        new THREE.Vector3(snapped.x, snapped.y, 0)]);
      previewLine.visible = true;
    } else if (mode.tool === "rect" && mode.pendingRect && previewLine) {
      const local = toLocal(event);
      if (!local) return;
      const a = mode.pendingRect, b = snap(local, event);
      previewLine.geometry.setFromPoints([
        new THREE.Vector3(a.x, a.y, 0), new THREE.Vector3(b.x, a.y, 0),
        new THREE.Vector3(b.x, b.y, 0), new THREE.Vector3(a.x, b.y, 0),
        new THREE.Vector3(a.x, a.y, 0)]);
      previewLine.visible = true;
    } else if (mode.tool === "rectc" && mode.pendingRectC && previewLine) {
      const local = toLocal(event);
      if (!local) return;
      const c = mode.pendingRectC, k = snap(local, event);
      const a = { x: 2 * c.x - k.x, y: 2 * c.y - k.y };
      previewLine.geometry.setFromPoints([
        new THREE.Vector3(a.x, a.y, 0), new THREE.Vector3(k.x, a.y, 0),
        new THREE.Vector3(k.x, k.y, 0), new THREE.Vector3(a.x, k.y, 0),
        new THREE.Vector3(a.x, a.y, 0)]);
      previewLine.visible = true;
    } else if (mode.tool === "spline" && mode.pendingSpline?.length
               && previewLine) {
      const local = toLocal(event);
      if (!local) return;
      const snapped = snap(local, event);
      previewLine.geometry.setFromPoints([
        ...mode.pendingSpline.map((p) => new THREE.Vector3(p.x, p.y, 0)),
        new THREE.Vector3(snapped.x, snapped.y, 0)]);
      previewLine.visible = true;
    } else if (previewLine) {
      const pending = mode.tool === "circle" ? mode.pendingCircle
        : mode.tool === "ellipse" ? mode.pendingEllipse
        : mode.tool === "slot" ? mode.pendingSlot
        : mode.tool === "arc" ? mode.pendingArc
        : mode.tool === "polygon"
          ? (mode.pendingPoly && { ...mode.pendingPoly,
            inscribed: !!mode.polygonInscribed })
        : null;
      if (!pending) return;
      const local = toLocal(event);
      if (!local) return;
      const pts = sketchPreviewPoints(mode.tool, pending, snap(local, event));
      if (pts.length < 2) {
        previewLine.visible = false;
        return;
      }
      previewLine.geometry.setFromPoints(
        pts.map((p) => new THREE.Vector3(p.x, p.y, 0)));
      previewLine.visible = true;
    }
  }

  function onPointerUp(event) {
    if (splineEdit.pointerUp(event)) {
      mode.justDragged = true;
      return;
    }
    if (mode.dimDrag) {
      const { dim, moved, offset } = mode.dimDrag;
      mode.dimDrag = null;
      controls.enabled = true;
      setCursor("grab");
      mode.justDragged = moved; // le click qui suit ne sélectionne rien
      if (moved && offset != null && mode.state) {
        safe(call("sketch_place_dim",
          { sketch: mode.state.sketch, dim: dim.id, offset }),
          { keepSelection: true });
      }
      return;
    }
    if (mode.box) {
      const start = mode.box;
      mode.box = null;
      boxOverlay?.hide();
      const end = { x: event.clientX, y: event.clientY };
      if (isDrag(start, end)) {
        mode.justDragged = true; // le click qui suit ne vide pas la sélection
        selectInBox(start, end, event.ctrlKey || event.metaKey);
      }
      return;
    }
    if (mode.drag) {
      // Le lâcher (sketch_drop) : tout le glisser en un seul Ctrl+Z, et,
      // lâché sur ce qu'il a accroché, la relation avec. Par la même
      // file que les sketch_move du glisser : il passe après eux.
      const { snapped } = mode.drag;
      const at = mode.dragMoved && snapped && !snapped.suspended
        ? snapTarget(snapped) : null;
      if (mode.dragMoved && mode.dragLocal && mode.state) {
        enqueueSketchMove(mode.dragLocal.x, mode.dragLocal.y,
          at ? { at } : null, { drop: true });
      }
      clearInference();
      const moved = !!mode.dragMoved;
      mode.dragLocal = null;
      mode.drag = null;
      mode.dragMoved = false;
      mode.dragScreen = null;
      mode.justDragged = moved; // un vrai drag ne doit pas sélectionner
      controls.enabled = true;
      setCursor("grab");
      drawHover();
      if (moved) syncEntityPanel({ refresh: true });
    }
  }

  // Double-clic sur une cote : nom, valeur ou expression — le panneau
  // remplace le prompt, c'est la porte d'entrée du paramétrique.
  function editDim(dim) {
    if (!mode.state) return;
    abandonEntityPanel();
    openDimEditor({
      panel,
      dim: { ...dim, kind: "sketch" },
      onApply: (values, meta) => {
        const extra = dimEditPayload(values, { ...dim, kind: "sketch" }, meta);
        if (extra.name === undefined && extra.value === undefined
            && extra.expr === undefined && extra.driving === undefined) return;
        const params = { sketch: mode.state.sketch, dim: dim.id, ...extra };
        safe((async () => {
          const state = await call("sketch_set_dim", params);
          // La pièce sous l'esquisse doit suivre : sans ça, la cote
          // change et l'écran ne bouge pas.
          await refresh(call("get_tree"));
          return state;
        })());
      },
    });
  }

  function editListedDim(constraint, geo) {
    if (!mode.state) return;
    const dim = {
      kind: "sketch",
      id: constraint.id,
      type: constraint.type,
      value: constraint.value,
      name: constraint.name || "",
      expr: constraint.expr || "",
    };
    openDimEditor({
      panel,
      dim,
      onApply: (values, meta) => {
        const extra = dimEditPayload(values, dim, meta);
        if (extra.name === undefined && extra.value === undefined
            && extra.expr === undefined) {
          openEntityPanel(geo);
          return;
        }
        safe((async () => {
          const state = await call("sketch_set_dim", {
            sketch: mode.state.sketch, dim: constraint.id, ...extra,
          });
          await refresh(call("get_tree"));
          return state;
        })(), { keepSelection: true });
      },
      onCancel: () => {
        if (mode.active) openEntityPanel(geo);
      },
    });
  }

  function onDoubleClick(event) {
    if (!mode.state) return;
    const dim = dimLabelAt(event);
    if (dim) openModifyBox(dim, { x: event.clientX, y: event.clientY });
  }

  /** La cote dont l'étiquette est sous le curseur, ou null. */
  function dimLabelAt(event) {
    for (const child of group.children) {
      const dim = child.userData?.dim;
      if (!dim) continue;
      const s = toScreen(child.position.x, child.position.y);
      if (Math.hypot(s.x - event.clientX, s.y - event.clientY) < 22) {
        return dim;
      }
    }
    return null;
  }

  /** Écart, en décalage, entre le curseur qui saisit l'étiquette et la
   *  ligne de cote actuelle — gardé pendant le glisser. null : cote qui
   *  ne se déplace pas (diamètre, rayon, angle). */
  function grabDelta(dim, event) {
    const under = dragOffset(dim, event);
    if (under == null) return null;
    const constraint = (mode.state.constraints ?? [])
      .find((c) => c.id === dim.id);
    const shape = dimGeometry(dim, constraint, mode.state.entities,
      dimDrawSize());
    const line = shape?.segments?.[2];
    if (!line) return null;
    const current = dimOffsetAt(dim, constraint, mode.state.entities,
      { x: line[0], y: line[1] });
    return current == null ? null : under - current;
  }

  /** Décalage de la cote si sa ligne passait sous le curseur. */
  function dragOffset(dim, event) {
    const local = toLocal(event);
    if (!local || !mode.state) return null;
    const constraint = (mode.state.constraints ?? [])
      .find((c) => c.id === dim.id);
    return dimOffsetAt(dim, constraint, mode.state.entities, local);
  }

  // ---------- boîte de saisie d'une cote ----------
  // Le corps est dans sketch/boitecote.js.
  Object.assign(sk, { renderer, call, refresh, mode, safe, editDim });
  const { closeModifyBox, openModifyBox } = installBoiteCote(sk);

  // Ctrl ou Maj enfoncé ou relâché : l'aperçu suit tout de suite, sans
  // attendre que la souris bouge (voir suspendsSnap, lengthStep).
  function onModifierKey(event) {
    if (!["Control", "Meta", "Shift"].includes(event.key)) return;
    if (!mode.active || !mode.lastMouse) return;
    if (!DRAW_TOOLS.has(mode.tool) && !mode.drag) return;
    onPointerMove({ ...mode.lastMouse, ctrlKey: event.ctrlKey,
      metaKey: event.metaKey, shiftKey: event.shiftKey });
  }

  function onKey(event) {
    if (!mode.active) return;
    // Taper dans un champ du panneau ne doit pas changer d'outil.
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(event.target.tagName)) return;
    const key = event.key.toLowerCase();
    if (/^[0-9.,]$/.test(event.key) && !event.ctrlKey && !event.metaKey
        && !event.altKey && pendingDrawPoint()) {
      event.preventDefault();
      openNumericEntry(event.key);
      return;
    }
    if (event.key === "Escape") {
      if (previewLine) previewLine.visible = false;
      setTool("select");
    } else if (event.key === "Enter" && OPEN_TOOLS[mode.tool]) {
      const spec = OPEN_TOOLS[mode.tool];
      const pts = mode.pendingClicks ?? [];
      if (pts.length >= spec.min) {
        mode.pendingClicks = null;
        if (previewLine) previewLine.visible = false;
        const out = spec.build(pts);
        safe(call(out.op, { sketch: mode.state.sketch, ...out.params }));
      } else {
        say(t(spec.prompt, { n: pts.length }), true);
      }
    } else if (event.key === "Enter" && mode.tool === "spline") {
      const pts = mode.pendingSpline ?? [];
      if (pts.length >= 3) {
        const name = mode.state.sketch;
        mode.pendingSpline = [];
        if (previewLine) previewLine.visible = false;
        safe(call("sketch_add_spline",
          { sketch: name, points: pts.map((p) => [p.x, p.y]) }));
      } else {
        say("Spline : au moins 3 points avant Entrée", true);
      }
    } else if (event.key === "Delete" && splineEdit.deleteKey()) {
      // Point choisi d'une spline : il part, la spline reste.
    } else if (event.key === "Delete") {
      const target = mode.lastMouse ? nearestEntity(mode.lastMouse) : null;
      if (target !== null) {
        safe(call("sketch_delete_geo",
          { sketch: mode.state.sketch, geo: target }));
      } else {
        say("Suppr : survolez d'abord la géométrie à supprimer");
      }
    } else if (key === "l") setTool("line");
    else if (key === "r") setTool("rect");
    else if (key === "c") setTool("circle");
    else if (key === "a") setTool("arc3");
    else if (key === "e") setTool("ellipse");
    else if (key === "t") setTool("trim");
    else if (key === "g") setTool("construction");
    else if (key === "d") setTool("dim");
  }

  // ---------- toolbar ----------

  const bar = document.getElementById("sketchbar");

  function setTool(tool) {
    if (building) return;
    closeNumericEntry();
    clearInference();
    mode.tool = tool;
    mode.chain = null;
    mode.woken = [];
    mode.quickSnap = null;
    mode.pendingCircle = null;
    mode.pendingRect = null;
    mode.pendingRectC = null;
    mode.pendingArc = null;
    mode.pendingArc3 = null;
    mode.pendingSlot = null;
    mode.pendingFillet = null;
    mode.pendingDim = null;
    mode.pendingDimPair = null;
    mode.pendingSpline = null;
    mode.pendingClicks = null;
    mode.ordinateBase = null;
    mode.pendingG2 = null;
    mode.pendingEllipse = null;
    mode.selection = [];
    mode.hover = null;
    if (tool === "polygon") {
      mode.pendingPoly = { sides: mode.polygonSides };
      openToolPanel("polygon");
    } else {
      mode.pendingPoly = null;
    }
    if (tool === "skfillet" || tool === "skchamfer") openToolPanel(tool);
    else if (tool !== "polygon") closeToolPanel();
    setCursor(CURSORS[tool] ?? "default");
    if (previewLine) previewLine.visible = false;
    for (const button of bar.querySelectorAll("button[data-tool]")) {
      button.classList.toggle("on", button.dataset.tool === tool);
    }
    const hints = {
      select: "Sélectionner : cliquez un point ou une entité, Ctrl+clic pour en ajouter ; glissez pour déplacer",
      line: "Ligne : cliquez le premier point",
      rect: "Rectangle par sommet : cliquez le premier sommet",
      rectc: "Rectangle par le centre : cliquez le centre",
      circle: "Cercle : cliquez le centre",
      spline: "Spline : cliquez les points, Entrée pour terminer",
      ellipse: "Ellipse : cliquez le centre",
      arc: "Arc par centre : cliquez le centre",
      arc3: "Arc 3 points : cliquez le point de départ",
      slot: "Rainure : cliquez le centre du premier bout",
      polygon: "Polygone : cliquez le centre",
      skfillet: "Congé d'esquisse : cliquez la première ligne, près du coin",
      skchamfer: "Chanfrein d'esquisse : cliquez la première ligne, près du coin",
      extend: "Prolonger : cliquez l'entité près du bout à allonger",
      skcorner: "Coin : cliquez deux lignes, du côté à garder",
      splconvert: "Convertir en spline : cliquez une entité",
      splknot: "Insérer un nœud : cliquez la spline à l'endroit voulu",
      spldegree: "Augmenter le degré : cliquez une spline",
      g2: "Courbure : cliquez le bout de la spline de référence",
      dimarc: "Longueur d'arc : cliquez un arc",
      dimaxis: "Angle à l'axe : cliquez une ligne",
      dimdia: "Diamètre : cliquez un cercle ou un arc",
      ordx: "Cote ordonnée horizontale : cliquez le point de base",
      ordy: "Cote ordonnée verticale : cliquez le point de base",
      split: "Scinder : cliquez l'entité à l'endroit de la coupure",
      trim: "Ajuster : cliquez le tronçon à supprimer",
      construction: "Construction : cliquez une entité pour la basculer",
      dim: "Cotation : cliquez une entité ou une extrémité",
    };
    say(hints[tool] ?? (CLICK_TOOLS[tool] ? t(CLICK_TOOLS[tool].prompts[0])
      : OPEN_TOOLS[tool] ? t(OPEN_TOOLS[tool].prompt, { n: 0 }) : undefined));
    redraw();
    syncEntityPanel();
  }

  // Hors esquisse, un outil du ruban Esquisse fait comme dans les
  // modeleurs courants : choisir le plan (ou la face sélectionnée), puis
  // l'esquisse s'ouvre avec cet outil.
  let pendingTool = null;
  bar.addEventListener("click", (event) => {
    const tool = event.target.closest?.("button[data-tool]")?.dataset.tool;
    if (!tool) return;
    if (mode.active) {
      setTool(tool);
      return;
    }
    pendingTool = tool;
    document.getElementById("btn-sketch")?.click();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !mode.active) pendingTool = null;
  });
  document.getElementById("sk-start").addEventListener("click", () => {
    if (mode.active) exit(true);
    else document.getElementById("btn-sketch")?.click();
  });

  // ---------- relations manuelles ----------

  // Le corps est dans sketch/relations.js.
  Object.assign(sk, {
    call, say, mode, safe, uniqueSelectionGeos, openEntityPanel, renderer,
  });
  const { updateRelationButtons } = installRelations(sk);

  // Le corps est dans sketch/commandes.js.
  Object.assign(sk, {
    call, say, panel, mode, loadSketchImage, applyState, safe, entityPicks,
    abandonEntityPanel, exit,
  });
  installCommandes(sk);

  // ---------- lifecycle ----------

  const listeners = [
    ["click", onClick], ["pointerdown", onPointerDown],
    ["pointermove", onPointerMove], ["pointerup", onPointerUp],
    ["dblclick", onDoubleClick],
  ];

  async function enter(statePromise) {
    try {
      const state = await statePromise;
      mode.active = true;
      // La barre d'icônes de la face cliquée resterait au milieu du dessin
      // et prendrait les clics destinés à l'esquisse.
      hideContextToolbar?.();
      applyState(state);
      // Le WASM se charge en fond ; dès qu'il est prêt, l'esquisse
      // courante y est (re)chargée.
      localSolver.ensureInit().then((ok) => {
        if (ok && mode.active && mode.state) {
          mode.solverOk = localSolver.load(mode.state);
        }
      });

      previewLine = new THREE.Line(
        new THREE.BufferGeometry(), previewMaterial);
      previewLine.visible = false;
      group.add(previewLine);

      // Vue tournée face au plan (réglage, par défaut) : la vue d'avant
      // revient à la sortie. Sinon la vue reste, et tourne encore.
      mode.savedCamera = null;
      if (mode.prefs.normalView) {
        mode.savedCamera = {
          position: camera.position.clone(),
          target: controls.target.clone(),
          zoom: camera.zoom,
        };
        const normal = new THREE.Vector3(0, 0, 1)
          .transformDirection(mode.matrix);
        const origin = new THREE.Vector3().setFromMatrixPosition(mode.matrix);
        camera.position.copy(origin.clone().add(normal.multiplyScalar(220)));
        controls.target.copy(origin);
        controls.enableRotate = false;
      }
      // Matrices à jour tout de suite : un clic arrivé avant l'image
      // suivante se projette déjà dans la vue de l'esquisse.
      controls.update();
      camera.updateMatrixWorld();

      for (const [type, handler] of listeners) {
        renderer.domElement.addEventListener(type, handler);
      }
      document.addEventListener("keydown", onKey);
      document.addEventListener("keydown", onModifierKey);
      document.addEventListener("keyup", onModifierKey);
      // Le ruban bascule sur l'onglet Esquisse (main.js écoute).
      document.dispatchEvent(new Event("freesolid:sketch-enter"));
      setTool(pendingTool ?? "line");
      pendingTool = null;
      call("sketch_picture", { sketch: state.sketch }).then(({ picture }) => {
        if (picture?.data && mode.active && mode.state?.sketch === state.sketch) {
          const { data, fileName, ...params } = picture;
          showImage(data, fileName || "image", params, true);
        }
      }).catch(() => {});
    } catch (error) {
      say(error.message, true);
    }
  }

  async function exit(keep) {
    if (!mode.active) return;
    closeEntityPanel();
    closeModifyBox();
    clearInference();
    readoutEl?.remove();
    readoutEl = null;
    mode.active = false;
    document.dispatchEvent(new Event("freesolid:sketch-exit"));
    for (const [type, handler] of listeners) {
      renderer.domElement.removeEventListener(type, handler);
    }
    document.removeEventListener("keydown", onKey);
    document.removeEventListener("keydown", onModifierKey);
    document.removeEventListener("keyup", onModifierKey);
    setCursor("");
    imageLoadGen += 1;
    revokePendingImageUrl();
    disposeImageLayer();
    disposeSubtree(group);
    group.clear();
    previewLine = null;

    if (mode.savedCamera) {
      camera.position.copy(mode.savedCamera.position);
      controls.target.copy(mode.savedCamera.target);
      camera.zoom = mode.savedCamera.zoom;
      camera.updateProjectionMatrix();
    }
    controls.enableRotate = true;

    if (keep && mode.state) {
      mode.lastFinished = mode.state.sketch;
      try {
        const tree = await call("sketch_finish",
          { sketch: mode.state.sketch });
        await refresh(Promise.resolve(tree));
        if (tree.open_profile) {
          say("Esquisse terminée — profil non fermé : il servira de "
              + "trajectoire ou de surface, pas de profil d'extrusion.");
        }
      } catch (error) {
        say(error.message, true);
      }
    } else if (mode.state) {
      // Quitter sans garder : le moteur défait tout depuis l'entrée.
      try {
        await refresh(call("sketch_cancel", { sketch: mode.state.sketch }));
        say("Esquisse quittée sans enregistrer les modifications.");
      } catch (error) {
        say(error.message, true);
      }
    } else {
      await refresh(call("get_tree"));
    }
    mode.state = null;
  }

  // Preview line must survive redraws: patch redraw to re-add it.
  const baseRedraw = redraw;
  redraw = function patchedRedraw() {
    baseRedraw();
    if (previewLine && mode.active) group.add(previewLine);
  };

  return {
    get active() { return mode.active; },
    /** Nom de l'esquisse ouverte, ou null. */
    get editing() { return mode.active ? mode.state?.sketch ?? null : null; },
    get definition() { return mode.active ? mode.state?.definition ?? null : null; },
    get lastFinished() { return mode.lastFinished; },
    enter,
    // Termine l'esquisse en la gardant — cliquer une fonction du ruban
    // pendant le dessin appelle ceci avant d'ouvrir son panneau.
    finish: () => exit(true),
    /** Quitter sans garder (coin de confirmation, bouton Quitter). */
    cancel: () => exit(false),
    /** Un outil de tracé est actif : l'accrochage rapide a un sens. */
    get drawing() { return mode.active && DRAW_TOOLS.has(mode.tool); },
    get quickSnap() { return mode.quickSnap; },
    pickQuickSnap,
    get snapSettings() { return mode.snapSettings; },
    setSnapSettings,
    get sketchPrefs() { return mode.prefs; },
    setSketchPrefs,
    /** Ctrl+Z dans l'esquisse : ses pas seulement (`steps` d'un coup). */
    undo: (steps) => stepHistory("undo", steps),
    /** Ctrl+Y dans l'esquisse. */
    redo: (steps) => stepHistory("redo", steps),
    /** Points monde de la géométrie, pour cadrer sans quitter le plan. */
    framePoints() {
      if (!mode.active) return [];
      return sketchLocalPoints(mode.state?.entities).map(([x, y]) => {
        const world = new THREE.Vector3(x, y, 0).applyMatrix4(mode.matrix);
        return [world.x, world.y, world.z];
      });
    },
  };
}
