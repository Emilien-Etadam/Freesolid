// FreeSolid — sketch mode. The viewport becomes a 2D drafting surface:
// the camera locks onto the sketch plane, clicks land in sketch-local
// coordinates, endpoints snap, dimensions are drawn and double-clickable.
//
// The server owns truth (geometry, solver); this module owns gesture.

import * as THREE from "three";

export function createSketchMode(deps) {
  const { scene, camera, renderer, controls, call, say, refresh } = deps;

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
    drag: null,           // { geo, point } while dragging
    savedCamera: null,
    matrix: new THREE.Matrix4(),
    inverse: new THREE.Matrix4(),
    plane: new THREE.Plane(),
    lastFinished: null,   // sketch name, for "pad what I just drew"
  };

  const SNAP_PX = 12;

  const CURSORS = { select: "default", line: "crosshair", rect: "crosshair",
                    rectc: "crosshair", circle: "crosshair",
                    construction: "pointer", dim: "crosshair" };

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
      if (entity.type === "line") {
        yield { geo: entity.id, point: 1, x: entity.p1[0], y: entity.p1[1] };
        yield { geo: entity.id, point: 2, x: entity.p2[0], y: entity.p2[1] };
      } else if (entity.type === "circle") {
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
    canvas.width = 128; canvas.height = 40;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "rgba(23,25,28,0.85)";
    ctx.fillRect(0, 0, 128, 40);
    ctx.font = "24px system-ui";
    ctx.fillStyle = "#7fc4ff";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(text, 64, 21);
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
      map: new THREE.CanvasTexture(canvas), depthTest: false }));
    sprite.position.set(x, y, 0.01);
    sprite.scale.set(14, 4.4, 1);
    return sprite;
  }

  let previewLine = null;

  function redraw() {
    group.clear();
    group.matrix.copy(mode.matrix);
    group.matrixAutoUpdate = false;
    if (!mode.state) return;

    const points = [];
    for (const entity of mode.state.entities) {
      const material = entity.construction ? constructionMaterial
                                           : lineMaterial;
      if (entity.type === "line") {
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
      const sprite = makeDimSprite(dim.value.toFixed(2), x, y);
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
    mode.matrix.set(...state.placement);
    mode.inverse.copy(mode.matrix).invert();
    const normal = new THREE.Vector3(0, 0, 1)
      .transformDirection(mode.matrix);
    const origin = new THREE.Vector3().setFromMatrixPosition(mode.matrix);
    mode.plane.setFromNormalAndCoplanarPoint(normal, origin);
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

  function onClick(event) {
    const local = toLocal(event);
    if (!local || !mode.state) return;
    const snapped = snap(local, event);
    const name = mode.state.sketch;

    if (mode.tool === "line") {
      if (!mode.chain) {
        mode.chain = { x: snapped.x, y: snapped.y };
        say("Ligne : cliquez le point suivant (Échap pour terminer)");
      } else {
        const from = mode.chain;
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
        addRectangle(name, a, snapped);
      }
    } else if (mode.tool === "rectc") {
      if (!mode.pendingRectC) {
        mode.pendingRectC = { x: snapped.x, y: snapped.y };
        say("Rectangle par le centre : cliquez un sommet");
      } else {
        const c = mode.pendingRectC;
        mode.pendingRectC = null;
        addRectangle(name,
          { x: 2 * c.x - snapped.x, y: 2 * c.y - snapped.y }, snapped);
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
    } else if (mode.tool === "construction") {
      const target = nearestEntity(event);
      if (target !== null) {
        safe(call("sketch_toggle_construction",
          { sketch: name, geo: target }));
      }
    } else if (mode.tool === "dim") {
      const target = nearestEntity(event);
      if (target !== null) {
        safe(call("sketch_dim", { sketch: name, geo: target }));
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
    // Screen-space distance to segment midpoints / circle rims — coarse but
    // honest for v1; proper hit-testing comes with hover highlighting.
    let best = null, bestDistance = 18;
    for (const entity of mode.state.entities) {
      let s;
      if (entity.type === "line") {
        s = toScreen((entity.p1[0] + entity.p2[0]) / 2,
                     (entity.p1[1] + entity.p2[1]) / 2);
      } else if (entity.type === "circle") {
        s = toScreen(entity.c[0] + entity.r, entity.c[1]);
      } else continue;
      const distance = Math.hypot(s.x - event.clientX, s.y - event.clientY);
      if (distance < bestDistance) { best = entity.id; bestDistance = distance; }
    }
    return best;
  }

  function onPointerDown(event) {
    if (mode.tool !== "select" || !mode.state) return;
    const p = overEndpoint(event);
    if (p) {
      mode.drag = { geo: p.geo, point: p.point };
      controls.enabled = false;
      setCursor("grabbing");
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

  let dragTimer = null;
  function onPointerMove(event) {
    mode.lastMouse = { clientX: event.clientX, clientY: event.clientY };
    if (mode.tool === "select" && !mode.drag) {
      setCursor(overEndpoint(event) ? "grab" : "default");
    }
    if (mode.drag) {
      const local = toLocal(event);
      if (!local || dragTimer) return;
      dragTimer = setTimeout(() => { dragTimer = null; }, 45);
      safe(call("sketch_move", { sketch: mode.state.sketch,
        geo: mode.drag.geo, point: mode.drag.point,
        x: local.x, y: local.y }));
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
    }
  }

  function onPointerUp() {
    if (mode.drag) {
      mode.drag = null;
      controls.enabled = true;
      setCursor("grab");
    }
  }

  function onDoubleClick(event) {
    // Double-click a dimension label: edit its value.
    if (!mode.state) return;
    for (const child of group.children) {
      const dim = child.userData?.dim;
      if (!dim) continue;
      const s = toScreen(child.position.x, child.position.y);
      if (Math.hypot(s.x - event.clientX, s.y - event.clientY) < 22) {
        const raw = prompt("Nouvelle valeur (mm) :", dim.value.toFixed(2));
        if (raw === null) return;
        const value = parseFloat(raw);
        if (!Number.isNaN(value)) {
          safe(call("sketch_set_dim",
            { sketch: mode.state.sketch, dim: dim.id, value }));
        }
        return;
      }
    }
  }

  function onKey(event) {
    if (!mode.active) return;
    if (event.key === "Escape") {
      mode.chain = null;
      mode.pendingCircle = null;
      mode.pendingRect = null;
      mode.pendingRectC = null;
      if (previewLine) previewLine.visible = false;
      setTool("select");
    } else if (event.key === "Delete") {
      const target = mode.lastMouse ? nearestEntity(mode.lastMouse) : null;
      if (target !== null) {
        safe(call("sketch_delete_geo",
          { sketch: mode.state.sketch, geo: target }));
      } else {
        say("Suppr : survolez d'abord la géométrie à supprimer");
      }
    } else if (event.key === "l") setTool("line");
    else if (event.key === "r") setTool("rect");
    else if (event.key === "c") setTool("circle");
    else if (event.key === "d") setTool("dim");
  }

  // ---------- toolbar ----------

  const bar = document.getElementById("sketchbar");

  function setTool(tool) {
    mode.tool = tool;
    mode.chain = null;
    mode.pendingCircle = null;
    mode.pendingRect = null;
    mode.pendingRectC = null;
    setCursor(CURSORS[tool] ?? "default");
    if (previewLine) previewLine.visible = false;
    for (const button of bar.querySelectorAll("button[data-tool]")) {
      button.classList.toggle("on", button.dataset.tool === tool);
    }
    const hints = {
      select: "Sélectionner : glissez un point (le solveur suit)",
      line: "Ligne : cliquez le premier point",
      rect: "Rectangle par sommet : cliquez le premier sommet",
      rectc: "Rectangle par le centre : cliquez le centre",
      circle: "Cercle : cliquez le centre",
      construction: "Construction : cliquez une entité pour la basculer",
      dim: "Cotation intelligente : cliquez une ligne ou un cercle",
    };
    say(hints[tool]);
  }

  bar.addEventListener("click", (event) => {
    const tool = event.target.dataset?.tool;
    if (tool) setTool(tool);
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

      previewLine = new THREE.Line(
        new THREE.BufferGeometry(), previewMaterial);
      previewLine.visible = false;
      group.add(previewLine);

      mode.savedCamera = {
        position: camera.position.clone(),
        target: controls.target.clone(),
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
      bar.style.display = "flex";
      setTool("line");
    } catch (error) {
      say(error.message, true);
    }
  }

  async function exit(keep) {
    mode.active = false;
    bar.style.display = "none";
    for (const [type, handler] of listeners) {
      renderer.domElement.removeEventListener(type, handler);
    }
    document.removeEventListener("keydown", onKey);
    setCursor("");
    group.clear();
    previewLine = null;

    if (mode.savedCamera) {
      camera.position.copy(mode.savedCamera.position);
      controls.target.copy(mode.savedCamera.target);
    }
    controls.enableRotate = true;

    if (keep && mode.state) {
      mode.lastFinished = mode.state.sketch;
      await refresh(call("sketch_finish", { sketch: mode.state.sketch }));
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
  };
}
