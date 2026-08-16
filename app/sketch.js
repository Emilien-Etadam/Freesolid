// FreeSolid — sketch mode. The viewport becomes a 2D drafting surface:
// the camera locks onto the sketch plane, clicks land in sketch-local
// coordinates, endpoints snap, dimensions are drawn and double-clickable.
//
// The server owns truth (geometry, solver); this module owns gesture.

import * as THREE from "three";
import { createLocalSolver } from "./solver.js";
import { arcAngles, chainClickAction, distanceToEntity } from "./geom2d.js";
import { num } from "./num.js";

export function createSketchMode(deps) {
  const { scene, camera, renderer, controls, call, say, refresh, panel } =
    deps;

  const group = new THREE.Group();
  scene.add(group);

  // depthTest off + high renderOrder: the sketch reads through the solid,
  // SolidWorks-style — a sketch drawn on a face was invisible behind the
  // mesh (user report).
  const lineMaterial = new THREE.LineBasicMaterial(
    { color: 0xe8edf2, depthTest: false });
  // Construction geometry: dashed and dimmed, as in every CAD since ever.
  const constructionMaterial = new THREE.LineDashedMaterial(
    { color: 0x8b939d, dashSize: 2.5, gapSize: 1.8, depthTest: false });
  const previewMaterial = new THREE.LineBasicMaterial(
    { color: 0x4f8fdb, depthTest: false });
  const selectedMaterial = new THREE.LineBasicMaterial(
    { color: 0xd9924a, depthTest: false });
  const pointMaterial = new THREE.PointsMaterial({
    color: 0x4f8fdb, size: 7, sizeAttenuation: false, depthTest: false });
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
    pendingEllipse: null, // { c, major? } — centre, grand axe, petit axe
    pendingArc3: null,    // [p1, p2] — départ, fin, puis passage
    pendingSlot: null,    // { a, b? } — centres puis largeur
    pendingPoly: null,    // { sides, c? } — centre puis sommet
    pendingFillet: null,  // { geo, x, y } — première ligne cliquée
    pendingDim: null,     // { geo, point? } — première entité cotée
    selection: [],        // [{ geo, point? }] — outil Sélectionner
    justDragged: false,   // un drag qui finit ne doit pas sélectionner
    drag: null,           // { geo, point } while dragging
    dragLocal: null,      // dernière position locale d'un drag local (M3)
    solverOk: false,      // l'esquisse est chargée dans le solveur local
    savedCamera: null,
    matrix: new THREE.Matrix4(),
    inverse: new THREE.Matrix4(),
    plane: new THREE.Plane(),
    lastFinished: null,   // sketch name, for "pad what I just drew"
  };

  const SNAP_PX = 12;
  let building = false; // construction multi-appels (rectangle) en cours

  // M3 : le solveur planegcs (WASM) côté client. Pendant un drag, la
  // résolution est locale (60 fps, zéro réseau) ; le serveur réconcilie
  // au lâcher. Si l'esquisse contient une géométrie ou contrainte non
  // traduite, solverOk reste false et on retombe sur le drag serveur.
  const localSolver = createLocalSolver();

  const CURSORS = { select: "default", line: "crosshair", rect: "crosshair",
                    rectc: "crosshair", circle: "crosshair",
                    arc: "crosshair", arc3: "crosshair", slot: "crosshair",
                    polygon: "crosshair", skfillet: "pointer",
                    trim: "pointer", construction: "pointer",
                    spline: "crosshair", ellipse: "crosshair",
                    dim: "crosshair" };

  function setCursor(name) {
    renderer.domElement.style.cursor = name;
  }

  // ---------- coordinates ----------

  function toLocal(event) {
    const rect = renderer.domElement.getBoundingClientRect();
    const pointer = new THREE.Vector2(
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      -((event.clientY - rect.top) / rect.height) * 2 + 1);
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
    return {
      x: (projected.x + 1) / 2 * rect.width + rect.left,
      y: (-projected.y + 1) / 2 * rect.height + rect.top,
    };
  }

  function* endpoints() {
    for (const entity of mode.state?.entities ?? []) {
      if (entity.type === "line" || entity.type === "arc") {
        yield { geo: entity.id, point: 1, x: entity.p1[0], y: entity.p1[1] };
        yield { geo: entity.id, point: 2, x: entity.p2[0], y: entity.p2[1] };
      }
      if (entity.type === "circle" || entity.type === "arc") {
        yield { geo: entity.id, point: 3, x: entity.c[0], y: entity.c[1] };
      }
    }
  }

  function snap(local, event) {
    // Endpoint snap first (screen-space), then axis snap along the chain.
    for (const p of endpoints()) {
      const s = toScreen(p.x, p.y);
      if (Math.hypot(s.x - event.clientX, s.y - event.clientY) < SNAP_PX) {
        return { x: p.x, y: p.y, onPoint: p };
      }
    }
    let { x, y } = local;
    if (mode.chain) {
      const sHere = toScreen(x, y);
      const sAxisV = toScreen(mode.chain.x, y);
      const sAxisH = toScreen(x, mode.chain.y);
      if (Math.hypot(sHere.x - sAxisV.x, sHere.y - sAxisV.y) < SNAP_PX) {
        x = mode.chain.x;
      } else if (Math.hypot(sHere.x - sAxisH.x, sHere.y - sAxisH.y) < SNAP_PX) {
        y = mode.chain.y;
      }
    }
    return { x, y, onPoint: null };
  }

  // ---------- drawing ----------

  function makeDimSprite(text, x, y) {
    const canvas = document.createElement("canvas");
    canvas.width = 256; canvas.height = 40;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "rgba(23,25,28,0.85)";
    ctx.fillRect(0, 0, 256, 40);
    ctx.font = "22px system-ui";
    ctx.fillStyle = "#7fc4ff";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(text, 128, 21);
    const material = new THREE.SpriteMaterial({
      map: new THREE.CanvasTexture(canvas), depthTest: false });
    material.userData.own = true;
    const sprite = new THREE.Sprite(material);
    sprite.position.set(x, y, 0.01);
    sprite.scale.set(26, 4.1, 1);
    return sprite;
  }

  // « largeur = 60.00 », préfixe Σ quand une équation pilote la cote.
  function dimText(dim) {
    const number = dim.type === "Angle"
      ? (dim.value * 180 / Math.PI).toFixed(1) + "°"
      : dim.value.toFixed(2);
    return (dim.expr ? "Σ " : "")
      + (dim.name ? dim.name + " = " : "") + number;
  }

  let previewLine = null;

  // Calque d'image d'esquisse : mesh + texture alloués ici, jamais
  // envoyés au serveur. Une seule image à la fois ; survit aux redraw,
  // disparaît à l'exit.
  const MAX_SKETCH_IMAGE_BYTES = 25 * 1024 * 1024;
  let imageLayer = null; // { mesh, aspect, fileName, params }
  let pendingImageUrl = null;
  let imageLoadGen = 0;

  function revokePendingImageUrl() {
    if (!pendingImageUrl) return;
    URL.revokeObjectURL(pendingImageUrl);
    pendingImageUrl = null;
  }

  function disposeImageLayer() {
    if (!imageLayer) return;
    const mesh = imageLayer.mesh;
    if (mesh) {
      group.remove(mesh);
      mesh.geometry?.dispose();
      const mat = mesh.material;
      if (mat?.userData?.own) { mat.map?.dispose(); mat.dispose(); }
    }
    imageLayer = null;
  }

  function applyImageLayer(values) {
    if (!imageLayer?.mesh) return;
    const width = Math.max(0.01, num(values.width) ?? 100);
    const height = width / (imageLayer.aspect || 1);
    const x = num(values.x) ?? 0;
    const y = num(values.y) ?? 0;
    const deg = num(values.rotation) ?? 0;
    let opacity = num(values.opacity);
    if (opacity === null) opacity = 0.5;
    opacity = Math.min(1, Math.max(0.1, opacity));
    imageLayer.mesh.position.set(x, y, 0);
    imageLayer.mesh.rotation.set(0, 0, deg * Math.PI / 180);
    imageLayer.mesh.scale.set(width, height, 1);
    imageLayer.mesh.material.opacity = opacity;
    imageLayer.params = { width, x, y, rotation: deg, opacity };
  }

  function openImagePanel() {
    const params = imageLayer?.params ?? {
      width: 100, x: 0, y: 0, rotation: 0, opacity: 0.5,
    };
    panel.open({
      icon: "Sketcher_Sketch.svg",
      title: "Image d'esquisse",
      groups: [
        {
          label: "Placement",
          rows: [
            { type: "number", key: "width", label: "Largeur",
              value: params.width, unit: "mm", min: 0.01 },
            { type: "number", key: "x", label: "X",
              value: params.x, unit: "mm" },
            { type: "number", key: "y", label: "Y",
              value: params.y, unit: "mm" },
            { type: "number", key: "rotation", label: "Rotation",
              value: params.rotation, unit: "°" },
            { type: "number", key: "opacity", label: "Opacité",
              value: params.opacity, min: 0.1, step: 0.05 },
          ],
        },
        {
          label: "Calque",
          rows: [{
            type: "list",
            items: [{
              label: imageLayer?.fileName || "image",
              onDelete: () => {
                disposeImageLayer();
                say("Image d'esquisse supprimée.");
                document.querySelector("#panel .pcancel")?.click();
              },
            }],
          }],
        },
      ],
      note: "L'image ne survit pas à la fermeture de l'esquisse — "
        + "réimporter au besoin. Elle ne quitte pas le navigateur.",
      onChange: (v) => applyImageLayer(v),
      onApply: () => {},
    });
  }

  function loadSketchImage(file) {
    if (!mode.active) return;
    if (file.size > MAX_SKETCH_IMAGE_BYTES) {
      say("Image trop lourde (max 25 Mo).", true);
      return;
    }
    const type = file.type || "";
    const name = file.name || "";
    const okType = type.startsWith("image/")
      || /\.(png|jpe?g|gif|webp|svg)$/i.test(name);
    if (!okType) {
      say("Fichier non reconnu comme image (PNG, JPEG, SVG…).", true);
      return;
    }

    revokePendingImageUrl();
    const url = URL.createObjectURL(file);
    pendingImageUrl = url;
    const gen = ++imageLoadGen;
    const img = new Image();
    img.onload = () => {
      if (pendingImageUrl === url) {
        URL.revokeObjectURL(url);
        pendingImageUrl = null;
      }
      if (gen !== imageLoadGen || !mode.active) return;
      const w = img.naturalWidth || img.width;
      const h = img.naturalHeight || img.height;
      if (!w || !h) {
        say("Impossible de lire l'image (dimensions nulles).", true);
        return;
      }
      const texture = new THREE.Texture(img);
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.needsUpdate = true;
      disposeImageLayer();
      const material = new THREE.MeshBasicMaterial({
        map: texture,
        transparent: true,
        opacity: 0.5,
        depthTest: false,
        depthWrite: false,
        side: THREE.DoubleSide,
      });
      material.userData.own = true;
      const mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), material);
      mesh.renderOrder = 0;
      // Décor : ni snap, ni sélection, ni drag. nearestEntity() ne
      // parcourt que les entités serveur ; ce no-op protège un
      // éventuel raycast du groupe.
      mesh.raycast = () => {};
      imageLayer = {
        mesh,
        aspect: w / h,
        fileName: name || "image",
        params: { width: 100, x: 0, y: 0, rotation: 0, opacity: 0.5 },
      };
      applyImageLayer(imageLayer.params);
      group.add(mesh);
      openImagePanel();
      say("Image d'esquisse posée — calque de travail, non enregistré.");
    };
    img.onerror = () => {
      if (pendingImageUrl === url) {
        URL.revokeObjectURL(url);
        pendingImageUrl = null;
      }
      if (gen !== imageLoadGen) return;
      say("Impossible de charger l'image.", true);
    };
    img.src = url;
  }

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

  function redraw() {
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
    for (const entity of mode.state.entities) {
      const isSelected = mode.selection.some((s) => s.geo === entity.id);
      const material = isSelected ? selectedMaterial
        : entity.construction ? constructionMaterial : lineMaterial;
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
    if (points.length) {
      const flat = new Float32Array(points.flatMap((p) => [p[0], p[1], 0]));
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.BufferAttribute(flat, 3));
      const cloud = new THREE.Points(geometry, pointMaterial);
      cloud.renderOrder = 21;
      group.add(cloud);
    }

    for (const dim of mode.state.dims) {
      const entity = mode.state.entities.find((e) => e.id === dim.geo);
      if (!entity) continue;
      let x, y;
      if (entity.type === "line") {
        x = (entity.p1[0] + entity.p2[0]) / 2;
        y = (entity.p1[1] + entity.p2[1]) / 2 + 4;
      } else {
        x = entity.c[0] + (entity.r ?? 0) * 0.7;
        y = entity.c[1] + (entity.r ?? 0) * 0.7;
      }
      const sprite = makeDimSprite(dimText(dim), x, y);
      sprite.userData.dim = dim;
      sprite.renderOrder = 22;
      group.add(sprite);
    }

    const dof = mode.state.dof;
    say(mode.state.fullyConstrained
      ? "Esquisse : totalement contrainte"
      : dof !== null
        ? `Esquisse : sous-contrainte (${dof} DDL)`
        : "Esquisse : en édition");
  }

  function applyState(state) {
    mode.state = state;
    // Geometry ids may have shifted (trim, delete): stale picks lie.
    mode.selection = [];
    mode.pendingDim = null;
    mode.pendingFillet = null;
    mode.matrix.set(...state.placement);
    mode.inverse.copy(mode.matrix).invert();
    const normal = new THREE.Vector3(0, 0, 1)
      .transformDirection(mode.matrix);
    const origin = new THREE.Vector3().setFromMatrixPosition(mode.matrix);
    mode.plane.setFromNormalAndCoplanarPoint(normal, origin);
    mode.solverOk = localSolver.ready && localSolver.load(state);
    redraw();
  }

  // ---------- gestures ----------

  async function safe(promise) {
    try {
      applyState(await promise);
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

  async function onClick(event) {
    if (building) return;
    const local = toLocal(event);
    if (!local || !mode.state) return;
    const snapped = snap(local, event);
    const name = mode.state.sketch;

    if (mode.tool === "select") {
      if (mode.justDragged) { mode.justDragged = false; return; }
      const endpoint = overEndpoint(event);
      const picked = endpoint
        ? { geo: endpoint.geo, point: endpoint.point }
        : (() => { const n = nearestEntity(event);
                   return n === null ? null : { geo: n }; })();
      if (picked === null) {
        mode.selection = [];
      } else {
        mode.selection = [...mode.selection, picked].slice(-8);
        say(`Sélection : ${mode.selection.length} entité(s) — ` +
            "relation, symétrie ou répétition ; clic dans le vide = vider");
      }
      redraw();
    } else if (mode.tool === "line") {
      if (!mode.chain) {
        mode.chain = { x: snapped.x, y: snapped.y };
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
        mode.chain = snapped.onPoint ? null : { x: snapped.x, y: snapped.y };
        safe(call("sketch_add_line", { sketch: name,
          x1: from.x, y1: from.y, x2: snapped.x, y2: snapped.y }));
      }
    } else if (mode.tool === "rect") {
      if (!mode.pendingRect) {
        mode.pendingRect = { x: snapped.x, y: snapped.y };
        say("Rectangle : cliquez le sommet opposé");
      } else {
        const a = mode.pendingRect;
        mode.pendingRect = null;
        building = true;
        try {
          await addRectangle(name, a, snapped);
        } finally {
          building = false;
        }
      }
    } else if (mode.tool === "rectc") {
      if (!mode.pendingRectC) {
        mode.pendingRectC = { x: snapped.x, y: snapped.y };
        say("Rectangle par le centre : cliquez un sommet");
      } else {
        const c = mode.pendingRectC;
        mode.pendingRectC = null;
        building = true;
        try {
          await addRectangle(name,
            { x: 2 * c.x - snapped.x, y: 2 * c.y - snapped.y }, snapped);
        } finally {
          building = false;
        }
      }
    } else if (mode.tool === "circle") {
      if (!mode.pendingCircle) {
        mode.pendingCircle = { x: snapped.x, y: snapped.y };
        say("Cercle : cliquez pour donner le rayon");
      } else {
        const c = mode.pendingCircle;
        mode.pendingCircle = null;
        const r = Math.hypot(snapped.x - c.x, snapped.y - c.y);
        if (r > 0) safe(call("sketch_add_circle",
          { sketch: name, cx: c.x, cy: c.y, r }));
      }
    } else if (mode.tool === "arc") {
      if (!mode.pendingArc) {
        mode.pendingArc = { c: { x: snapped.x, y: snapped.y } };
        say("Arc : cliquez le point de départ");
      } else if (!mode.pendingArc.start) {
        mode.pendingArc.start = { x: snapped.x, y: snapped.y };
        say("Arc : cliquez le point d'arrivée (sens anti-horaire)");
      } else {
        const { c, start } = mode.pendingArc;
        mode.pendingArc = null;
        const r = Math.hypot(start.x - c.x, start.y - c.y);
        if (r <= 0) return;
        const a1 = Math.atan2(start.y - c.y, start.x - c.x);
        let a2 = Math.atan2(snapped.y - c.y, snapped.x - c.x);
        if (a2 <= a1) a2 += Math.PI * 2;
        safe(call("sketch_add_arc",
          { sketch: name, cx: c.x, cy: c.y, r, a1, a2 }));
      }
    } else if (mode.tool === "arc3") {
      if (!mode.pendingArc3) {
        mode.pendingArc3 = [{ x: snapped.x, y: snapped.y }];
        say("Arc 3 points : cliquez le point d'arrivée");
      } else if (mode.pendingArc3.length === 1) {
        mode.pendingArc3.push({ x: snapped.x, y: snapped.y });
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
        safe(call("sketch_add_arc",
          { sketch: name, cx: c.x, cy: c.y, r, ...params }));
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
        safe(call("sketch_add_polygon", { sketch: name,
          cx: c.x, cy: c.y, x: snapped.x, y: snapped.y, sides }));
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
        const radius = num(
          prompt("Rayon du congé d'esquisse (mm) :", "3") ?? "");
        if (!radius) return;
        safe(call("sketch_fillet", { sketch: name,
          geo1: first.geo, geo2: target,
          x1: first.x, y1: first.y, x2: local.x, y2: local.y, radius }));
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
      say(`Spline : ${mode.pendingSpline.length} point(s) — ` +
          "Entrée pour terminer (min 3), Échap pour annuler");
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
      const endpoint = overEndpoint(event);
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
        if (!target
            || (target.geo === first.geo && target.point === first.point)) {
          safe(call("sketch_dim", { sketch: name, geo: first.geo }));
        } else {
          const params = { sketch: name, geo: first.geo, geo2: target.geo };
          if (first.point != null) params.point = first.point;
          if (target.point != null) params.point2 = target.point;
          safe(call("sketch_dim", params));
        }
      }
    }
  }

  async function addRectangle(name, a, b) {
    // Four chained lines: the server's auto-constraints close the loop
    // (coincidents) and square it (horizontal/vertical) — exactly what
    // drawing them by hand would earn.
    if (a.x === b.x || a.y === b.y) {
      say("Rectangle : les sommets doivent être en diagonale", true);
      return;
    }
    try {
      const corners = [a, { x: b.x, y: a.y }, b, { x: a.x, y: b.y }, a];
      let state = null;
      for (let i = 0; i < 4; i++) {
        state = await call("sketch_add_line", { sketch: name,
          x1: corners[i].x, y1: corners[i].y,
          x2: corners[i + 1].x, y2: corners[i + 1].y });
      }
      applyState(state);
    } catch (error) {
      say(error.message, true);
    }
  }

  function nearestEntity(event) {
    // Distance réelle à la courbe (segment / |d−r|), seuil écran 18 px.
    const local = toLocal(event);
    if (!local) return null;
    let best = null, bestDistance = 18;
    for (const entity of mode.state.entities) {
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
    if (mode.tool !== "select" || !mode.state) return;
    const p = overEndpoint(event);
    if (p) {
      mode.drag = { geo: p.geo, point: p.point };
      controls.enabled = false;
      setCursor("grabbing");
      return;
    }
    // Drag d'arête entière (Sketcher point 0 = courbe).
    const entity = overEntity(event);
    if (!entity) return;
    const local = toLocal(event);
    if (!local) return;
    mode.drag = {
      geo: entity.id,
      point: 0,
      grab: { x: local.x, y: local.y },
      base: snapshotEntity(entity),
    };
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

  /** Cible abs. pour sketch_move point 0 : nouveau départ (ligne) ou centre. */
  function wholeCurveTarget(drag, local) {
    const dx = local.x - drag.grab.x, dy = local.y - drag.grab.y;
    const b = drag.base;
    if (b.type === "circle" || b.type === "arc") {
      return { x: b.c[0] + dx, y: b.c[1] + dy };
    }
    return { x: b.p1[0] + dx, y: b.p1[1] + dy };
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
  let pendingMove = null; // { sketch, geo, point, x, y, gen } | null
  let moveGen = 0;

  // File sérielle du fallback serveur : un seul sketch_move en vol ;
  // pendant l'attente on ne garde que la dernière (x, y) ; seule la
  // réponse la plus récente peut applyState. Le sketch_move final du
  // pointerup (chemin solveur local) passe par ici aussi.
  function enqueueSketchMove(x, y) {
    if (!mode.state || !mode.drag) return;
    pendingMove = {
      sketch: mode.state.sketch,
      geo: mode.drag.geo,
      point: mode.drag.point,
      x, y,
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
      const state = await call("sketch_move", {
        sketch: req.sketch, geo: req.geo, point: req.point,
        x: req.x, y: req.y,
      });
      if (req.gen === moveGen) applyState(state);
    } catch (error) {
      if (req.gen === moveGen) {
        say(error.message, true);
        if (mode.state?.sketch) {
          safe(call("sketch_state", { sketch: mode.state.sketch }));
        }
      }
    } finally {
      moveInFlight = false;
      if (pendingMove) flushSketchMoves();
    }
  }

  function onPointerMove(event) {
    mode.lastMouse = { clientX: event.clientX, clientY: event.clientY };
    if (mode.tool === "select" && !mode.drag) {
      const hot = overEndpoint(event) || overEntity(event);
      setCursor(hot ? "grab" : "default");
    }
    if (mode.drag) {
      const local = toLocal(event);
      if (!local) return;
      const target = mode.drag.point === 0
        ? wholeCurveTarget(mode.drag, local) : local;
      // M3 : résolution locale planegcs — toutes les contraintes tiennent
      // à 60 fps, zéro réseau ; le serveur réconcilie au pointerup.
      if (mode.solverOk) {
        const updates = localSolver.drag(
          mode.drag.geo, mode.drag.point, target.x, target.y);
        if (updates) {
          mode.dragLocal = target; // pour le sketch_move final
          redraw();
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
          entity.p1 = [local.x, local.y];
        } else if (mode.drag.point === 2 && entity.p2) {
          entity.p2 = [local.x, local.y];
        } else if (mode.drag.point === 3 && entity.c) {
          entity.c = [local.x, local.y];
        }
        redraw();
      }
      enqueueSketchMove(target.x, target.y);
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
    }
  }

  function onPointerUp() {
    if (mode.drag) {
      // Drag local (M3) : un seul sketch_move au lâcher, via la même
      // file — il ne double pas un move serveur déjà en vol.
      if (mode.solverOk && mode.dragLocal && mode.state) {
        enqueueSketchMove(mode.dragLocal.x, mode.dragLocal.y);
      }
      mode.dragLocal = null;
      mode.drag = null;
      mode.justDragged = true; // le click qui suit n'est pas une sélection
      controls.enabled = true;
      setCursor("grab");
    }
  }

  // Double-clic sur une cote : nom, valeur ou expression — le panneau
  // remplace le prompt, c'est la porte d'entrée du paramétrique.
  function editDim(dim) {
    const isAngle = dim.type === "Angle";
    const shown = dim.expr
      || (isAngle ? (dim.value * 180 / Math.PI).toFixed(2)
                  : String(+dim.value.toFixed(4)));
    panel.open({
      icon: "Constraint_Dimension.svg",
      title: "Cote" + (dim.name ? ` — ${dim.name}` : ""),
      groups: [{
        label: "Cote",
        rows: [
          { type: "text", key: "name", label: "Nom", value: dim.name,
            placeholder: "largeur" },
          { type: "text", key: "value", label: "Valeur ou expression",
            value: shown, unit: isAngle ? "°" : "mm" },
        ],
      }],
      note: "Expression : « Variables.Largeur / 2 » ou " +
            "« .Constraints.largeur * 2 » (les noms de cotes de cette " +
            "esquisse s'utilisent avec .Constraints.nom)",
      onApply: (v) => {
        const params = { sketch: mode.state.sketch, dim: dim.id };
        const name = (v.name ?? "").trim();
        if (name !== (dim.name ?? "")) params.name = name;
        const raw = String(v.value ?? "").trim();
        if (raw && raw !== shown) {
          if (/^-?\d+([.,]\d+)?$/.test(raw)) {
            const parsed = num(raw);
            params.value = isAngle ? parsed * Math.PI / 180 : parsed;
          } else {
            params.expr = raw;
          }
        }
        if (params.name === undefined && params.value === undefined
            && params.expr === undefined) return;
        safe(call("sketch_set_dim", params));
      },
    });
  }

  function onDoubleClick(event) {
    if (!mode.state) return;
    for (const child of group.children) {
      const dim = child.userData?.dim;
      if (!dim) continue;
      const s = toScreen(child.position.x, child.position.y);
      if (Math.hypot(s.x - event.clientX, s.y - event.clientY) < 22) {
        editDim(dim);
        return;
      }
    }
  }

  function onKey(event) {
    if (!mode.active) return;
    // Taper dans un champ du panneau ne doit pas changer d'outil.
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(event.target.tagName)) return;
    const key = event.key.toLowerCase();
    if (event.key === "Escape") {
      if (previewLine) previewLine.visible = false;
      setTool("select");
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
    else if (key === "s") setTool("spline");
    else if (key === "e") setTool("ellipse");
    else if (key === "t") setTool("trim");
    else if (key === "g") setTool("construction");
    else if (key === "d") setTool("dim");
  }

  // ---------- toolbar ----------

  const bar = document.getElementById("sketchbar");

  function setTool(tool) {
    if (building) return;
    mode.tool = tool;
    mode.chain = null;
    mode.pendingCircle = null;
    mode.pendingRect = null;
    mode.pendingRectC = null;
    mode.pendingArc = null;
    mode.pendingArc3 = null;
    mode.pendingSlot = null;
    mode.pendingFillet = null;
    mode.pendingDim = null;
    mode.pendingSpline = null;
    mode.pendingEllipse = null;
    mode.selection = [];
    if (tool === "polygon") {
      const sides = parseInt(prompt("Polygone — nombre de côtés :", "6")
                             ?? "", 10);
      mode.pendingPoly = sides >= 3 ? { sides } : null;
      if (!mode.pendingPoly) { setTool("select"); return; }
    } else {
      mode.pendingPoly = null;
    }
    setCursor(CURSORS[tool] ?? "default");
    if (previewLine) previewLine.visible = false;
    for (const button of bar.querySelectorAll("button[data-tool]")) {
      button.classList.toggle("on", button.dataset.tool === tool);
    }
    const hints = {
      select: "Sélectionner : glissez un point, ou cliquez 1-2 entités " +
              "puis une contrainte",
      line: "Ligne : cliquez le premier point",
      rect: "Rectangle par sommet : cliquez le premier sommet",
      rectc: "Rectangle par le centre : cliquez le centre",
      circle: "Cercle : cliquez le centre",
      spline: "Spline : cliquez les points, Entrée pour terminer (S)",
      ellipse: "Ellipse : cliquez le centre",
      arc: "Arc par centre : cliquez le centre",
      arc3: "Arc 3 points : cliquez le point de départ",
      slot: "Rainure : cliquez le centre du premier bout",
      polygon: "Polygone : cliquez le centre",
      skfillet: "Congé d'esquisse : cliquez la première ligne, près du coin",
      trim: "Ajuster : cliquez le tronçon à supprimer",
      construction: "Construction : cliquez une entité pour la basculer",
      dim: "Cotation intelligente : cliquez une entité ou une extrémité",
    };
    say(hints[tool]);
    redraw();
  }

  bar.addEventListener("click", (event) => {
    if (!mode.active) return; // le ruban Esquisse est visible mais inerte
    const tool = event.target.dataset?.tool;
    if (tool) setTool(tool);
  });

  // ---------- relations manuelles ----------

  //: relation -> nombre d'entités attendues. symmetric : 2 points + l'axe.
  const CONSTRAINT_NEEDS = {
    horizontal: 1, vertical: 1, fixed: 1,
    parallel: 2, perpendicular: 2, equal: 2, tangent: 2,
    coincident: 2, concentric: 2, collinear: 2, midpoint: 2,
    symmetric: 3,
  };

  function applyConstraint(kind) {
    if (!mode.state) return;
    const needed = CONSTRAINT_NEEDS[kind];
    if (mode.selection.length < needed) {
      say(`Relation : sélectionnez d'abord ${needed} entité(s) ` +
          "avec l'outil Sélectionner", true);
      return;
    }
    const selection = mode.selection.slice(-needed);
    const params = { sketch: mode.state.sketch, kind,
                     geo1: selection[0].geo };
    if (selection[0].point != null) params.point1 = selection[0].point;
    if (selection[1]) {
      params.geo2 = selection[1].geo;
      if (selection[1].point != null) params.point2 = selection[1].point;
    }
    if (needed >= 3 && selection[2]) params.geo3 = selection[2].geo;
    safe(call("sketch_constrain", params));
  }

  for (const kind of Object.keys(CONSTRAINT_NEEDS)) {
    document.getElementById("sk-c-" + kind)
      .addEventListener("click", () => applyConstraint(kind));
  }

  // ---------- panneau Relations (voir et supprimer) ----------

  async function openRelationsPanel() {
    if (!mode.state) return;
    if (mode.selection.length !== 1) {
      say("Relations : sélectionnez d'abord UNE entité " +
          "(outil Sélectionner)", true);
      return;
    }
    const geo = mode.selection[0].geo;
    let listed;
    try {
      listed = await call("sketch_constraints",
        { sketch: mode.state.sketch, geo });
    } catch (error) {
      say(error.message, true);
      return;
    }
    panel.open({
      icon: "Sketcher_ToggleConstraint.svg",
      title: `Relations — entité ${geo}`,
      groups: [{
        label: "Relations de l'entité",
        rows: [{
          type: "list",
          empty: "— aucune relation sur cette entité —",
          items: listed.constraints.map((c) => ({
            label: c.label
              + (c.name ? ` « ${c.name} »` : "")
              + (c.value !== undefined
                 ? " = " + (c.type === "Angle"
                     ? (c.value * 180 / Math.PI).toFixed(1) + "°"
                     : c.value.toFixed(2))
                 : ""),
            onDelete: async () => {
              try {
                applyState(await call("sketch_delete_constraint",
                  { sketch: mode.state.sketch, constraint: c.id }));
                mode.selection = [{ geo }];
                redraw();
                openRelationsPanel(); // ré-ouvre avec la liste à jour
              } catch (error) {
                say(error.message, true);
              }
            },
          })),
        }],
      }],
      note: "✕ supprime la relation — la sortie des esquisses " +
            "sur-contraintes",
      onApply: () => {},
    });
  }

  document.getElementById("sk-relations")
    .addEventListener("click", openRelationsPanel);

  // Symétrie d'entités : la sélection SAUF la dernière est symétrisée,
  // la dernière entité sélectionnée est l'axe.
  document.getElementById("sk-mirror").addEventListener("click", () => {
    if (!mode.state) return;
    if (mode.selection.length < 2) {
      say("Symétrie : sélectionnez les entités PUIS la ligne d'axe " +
          "en dernier", true);
      return;
    }
    const geos = mode.selection.slice(0, -1).map((s) => s.geo);
    const axis = mode.selection[mode.selection.length - 1].geo;
    safe(call("sketch_mirror",
      { sketch: mode.state.sketch, geos, axis }));
  });

  document.getElementById("sk-array").addEventListener("click", () => {
    if (!mode.state) return;
    if (!mode.selection.length) {
      say("Répétition : sélectionnez d'abord des entités", true);
      return;
    }
    const geos = mode.selection.map((s) => s.geo);
    panel.open({
      icon: "Sketcher_RectangularArray.svg",
      title: "Répétition d'entités",
      groups: [{
        label: "Paramètres",
        rows: [
          { type: "number", key: "dx", label: "Pas X", value: 15,
            unit: "mm" },
          { type: "number", key: "dy", label: "Pas Y", value: 0,
            unit: "mm" },
          { type: "number", key: "cols", label: "Colonnes", value: 3,
            min: 1, step: 1 },
          { type: "number", key: "rows", label: "Lignes", value: 1,
            min: 1, step: 1 },
        ],
      }],
      note: "Le pas est piloté par des lignes de construction — " +
            "cotables ensuite.",
      onApply: (v) => safe(call("sketch_array", {
        sketch: mode.state.sketch, geos,
        dx: num(v.dx) ?? 0, dy: num(v.dy) ?? 0,
        cols: parseInt(v.cols, 10) || 1,
        rows: parseInt(v.rows, 10) || 1 })),
    });
  });

  document.getElementById("sk-offset").addEventListener("click", () => {
    if (!mode.state) return;
    if (!mode.selection.length) {
      say("Décaler : sélectionnez d'abord une chaîne d'entités", true);
      return;
    }
    const geos = mode.selection.map((s) => s.geo);
    panel.open({
      icon: "Sketcher_Copy.svg",
      title: "Décaler les entités",
      groups: [{
        label: "Paramètres",
        rows: [
          { type: "number", key: "distance", label: "Distance", value: 5,
            unit: "mm", min: 0.01 },
          { type: "check", key: "reversed", label: "Inverser le côté",
            value: false },
        ],
      }],
      note: "Les copies restent libres — le décalage paramétrique " +
            "viendra plus tard.",
      onApply: (v) => safe(call("sketch_offset", {
        sketch: mode.state.sketch, geos,
        distance: num(v.distance) ?? 5,
        reversed: !!v.reversed })),
    });
  });

  const imageInput = document.getElementById("sk-image-file");
  document.getElementById("sk-image").addEventListener("click", () => {
    if (!mode.active || !mode.state) {
      say("Image d'esquisse : ouvrez d'abord une esquisse.", true);
      return;
    }
    imageInput.value = "";
    imageInput.click();
  });
  imageInput.addEventListener("change", () => {
    const file = imageInput.files?.[0];
    if (!file) return;
    loadSketchImage(file);
  });

  // Convertir les entités : le contour de la face porteuse arrive en
  // géométrie réelle bloquée — le point de départ SolidWorks classique.
  document.getElementById("sk-convert").addEventListener("click", () => {
    if (!mode.active || !mode.state) return;
    call("sketch_convert", { sketch: mode.state.sketch })
      .then((state) => {
        applyState(state);
        say(`Converti : ${state.converted} entité(s)`
          + (state.skipped ? ` — ${state.skipped} ignorée(s)` : ""));
      })
      .catch((error) => say(error.message, true));
  });
  document.getElementById("sk-finish").addEventListener("click", () => exit(true));
  document.getElementById("sk-cancel").addEventListener("click", () => exit(false));

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

      for (const [type, handler] of listeners) {
        renderer.domElement.addEventListener(type, handler);
      }
      document.addEventListener("keydown", onKey);
      // Le ruban bascule sur l'onglet Esquisse (main.js écoute).
      document.dispatchEvent(new Event("freesolid:sketch-enter"));
      setTool("line");
    } catch (error) {
      say(error.message, true);
    }
  }

  async function exit(keep) {
    if (!mode.active) return;
    mode.active = false;
    document.dispatchEvent(new Event("freesolid:sketch-exit"));
    for (const [type, handler] of listeners) {
      renderer.domElement.removeEventListener(type, handler);
    }
    document.removeEventListener("keydown", onKey);
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
          say("Esquisse fermée — contour ouvert : utilisable comme "
              + "trajectoire ou surface, pas comme profil de bossage.");
        }
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
    get lastFinished() { return mode.lastFinished; },
    enter,
    // Termine l'esquisse en la gardant — cliquer une fonction du ruban
    // pendant le dessin appelle ceci avant d'ouvrir son panneau.
    finish: () => exit(true),
  };
}
