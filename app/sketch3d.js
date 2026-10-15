// Esquisse 3D : un mode d'édition, comme l'esquisse 2D mais dans l'espace.
// On y trace des lignes (en chaîne : chaque clic prolonge, double-clic ou
// Échap termine), des splines (Entrée termine) et des points. Le point
// suivant se pose sur la pièce (sommets et centres aimantent et lient le
// point à la pièce), sur un point de l'esquisse (partagé), ou dans le vide
// sur le plan de clic qui passe par le point précédent (Tab change de
// plan). Près d'un axe X, Y ou Z, la ligne s'y cale (trait de couleur) et
// garde la relation ; Maj force l'axe le plus proche. Cotation : une
// ligne (longueur), deux points (distance), deux lignes (angle) ; les cotes
// s'affichent dans la vue, double-clic pour changer la valeur. Tout est
// tenu par le solveur (sketch3dmath.js, le même que le moteur). Ctrl+Z /
// Ctrl+Y défont dans l'esquisse ; OK l'enregistre, ✕ l'abandonne.

import { t } from "./i18n.js";
import { snapFacePoint } from "./pointsnap.js";
import { CLICK_PLANES, clickPlane, nextPlane, rayPlane } from "./curve3d.js";
import { sample } from "./splinemath.js";
import { createDimSprite } from "./sketch.js";
import {
  AXES, cleanSpec, solve, measure, inferAxis, onAxis, removeItems,
} from "./sketch3dmath.js";
import { dimText, entityText, dimLabel, dimFromPicks, findDim } from "./sketch3dtext.js";

export const SKETCH3D_TOOLS = ["select", "line", "spline", "point", "dim"];

const TOOL_LABELS = {
  select: "Sélectionner", line: "Ligne", spline: "Spline", point: "Point", dim: "Cotation",
};
const TOOL_HELP = {
  select: "Cliquez un point, une entité ou une cote ; tirez un point pour le déplacer. Suppr retire la sélection.",
  line: "Cliquez des points : chaque clic prolonge la chaîne ; double-clic ou Échap la termine. Près d'un axe, la ligne s'y cale (Maj : l'axe le plus proche).",
  spline: "Cliquez les points de passage ; Entrée ou double-clic termine la spline.",
  point: "Cliquez pour poser un point.",
  dim: "Une ligne : sa longueur (cliquez ensuite dans le vide). Deux points : leur distance. Deux lignes : leur angle.",
};
const PLANE_LABELS = { XY: "Plan de dessus", XZ: "Plan de face", YZ: "Plan de droite" };

export function installSketch3d(ctx) {
  const { THREE, camera, renderer, scene, panel, call, refresh, say } = ctx;
  const theme = ctx.sceneTheme;
  const raycaster = new THREE.Raycaster();
  const group = new THREE.Group();
  group.renderOrder = 20;
  const PICK_PX = 10;
  const LINE_PX = 7;
  let session = null;
  let reopening = false;

  const mats = {
    line: new THREE.LineBasicMaterial({ color: theme.curve, depthTest: false }),
    construction: new THREE.LineDashedMaterial({ color: theme.ink2, dashSize: 2, gapSize: 1.5,
      depthTest: false }),
    selected: new THREE.LineBasicMaterial({ color: theme.selection, depthTest: false }),
    hover: new THREE.LineBasicMaterial({ color: theme.accent, depthTest: false }),
    rubber: new THREE.LineDashedMaterial({ color: theme.curve, dashSize: 2, gapSize: 1.5,
      depthTest: false }),
    dimLine: new THREE.LineDashedMaterial({ color: theme.dim, dashSize: 1.5, gapSize: 1,
      depthTest: false }),
    point: new THREE.PointsMaterial({ color: theme.accent, size: 7, sizeAttenuation: false,
      depthTest: false }),
    linked: new THREE.PointsMaterial({ color: theme.successSoft, size: 8, sizeAttenuation: false,
      depthTest: false }),
    pointSel: new THREE.PointsMaterial({ color: theme.selection, size: 11, sizeAttenuation: false,
      depthTest: false }),
    pointHover: new THREE.PointsMaterial({ color: theme.accent, size: 11, sizeAttenuation: false,
      depthTest: false }),
    axis: AXES.split("").map((_, k) => new THREE.LineBasicMaterial({
      color: [theme.axisX, theme.axisY, theme.axisZ][k], depthTest: false,
      transparent: true, opacity: 0.8 })),
  };
  const AXIS_CSS = ["#e06666", "#6aa84f", "#4b9bd5"];

  // ---------- géométrie de l'écran ----------

  function rect() { return renderer.domElement.getBoundingClientRect(); }
  function setRay(event) {
    const r = rect();
    raycaster.setFromCamera(new THREE.Vector2(
      ((event.clientX - r.left) / r.width) * 2 - 1,
      -((event.clientY - r.top) / r.height) * 2 + 1), camera);
  }
  function screenOf(p) {
    const v = new THREE.Vector3(p[0], p[1], p[2]).project(camera);
    const r = rect();
    return { x: r.left + ((v.x + 1) / 2) * r.width, y: r.top + ((1 - v.y) / 2) * r.height };
  }
  const projectXYZ = (p) => screenOf([p.x, p.y, p.z]);
  function pixels(p, event) {
    const s = screenOf(p);
    return Math.hypot(s.x - event.clientX, s.y - event.clientY);
  }
  function segmentPixels(a, b, event) {
    const sa = screenOf(a);
    const sb = screenOf(b);
    const dx = sb.x - sa.x;
    const dy = sb.y - sa.y;
    const len2 = dx * dx + dy * dy;
    const k = len2 > 0 ? Math.min(Math.max(((event.clientX - sa.x) * dx
      + (event.clientY - sa.y) * dy) / len2, 0), 1) : 0;
    return Math.hypot(sa.x + k * dx - event.clientX, sa.y + k * dy - event.clientY);
  }
  /** Taille d'un pixel en unités du modèle (vue orthographique). */
  function worldPerPixel() {
    const height = rect().height || 1;
    if (camera.isOrthographicCamera) return (camera.top - camera.bottom) / (camera.zoom || 1) / height;
    return 0.1;
  }

  // ---------- la définition ----------

  const spec = () => session.spec;
  const round = (v) => Math.round(v * 1e6) / 1e6;

  function entityPath(e, pts = spec().points) {
    if (e.type === "line") return [pts[e.a], pts[e.b]];
    if (e.type === "spline") {
      try {
        return sample(e.pts.map((p) => pts[p]), { closed: e.closed, tangents: e.tangents, perSpan: 16 });
      } catch {
        return e.pts.map((p) => pts[p]);
      }
    }
    return [];
  }

  /** Nouvelle définition : résolue, gardée pour Ctrl+Z ; refusée (et
   *  rien ne change) si des cotes se contredisent. */
  function apply(next, { fixed = [], record = true, message = null } = {}) {
    const clean = cleanSpec(next);
    const solved = solve(clean, fixed);
    if (!solved.ok) {
      say(t("Esquisse 3D : cette cote ou relation contredit les autres — rien n'a changé."), true);
      return false;
    }
    if (record) {
      session.undo.push(session.spec);
      session.redo = [];
    }
    session.spec = { ...clean, points: solved.points.map((p) => p.map(round)) };
    session.dirty = true;
    draw();
    reopenPanel();
    if (message) say(message);
    return true;
  }

  function addPoint(draft, target) {
    if (target.index != null) return target.index;
    draft.points.push(target.point.map(round));
    draft.links.push(target.link ? true : null);
    return draft.points.length - 1;
  }

  const copy = () => JSON.parse(JSON.stringify(spec()));

  // ---------- viser ----------

  /** Point de l'esquisse sous le pointeur, ou -1. */
  function pointAt(event, skip = -1) {
    let best = -1;
    let bestD = PICK_PX;
    spec().points.forEach((p, i) => {
      if (i === skip) return;
      const d = pixels(p, event);
      if (d < bestD) { best = i; bestD = d; }
    });
    return best;
  }

  function entityAt(event) {
    let best = -1;
    let bestD = LINE_PX;
    spec().entities.forEach((e, i) => {
      const path = e.type === "point" ? null : entityPath(e);
      if (!path) return;
      for (let k = 0; k + 1 < path.length; k++) {
        const d = segmentPixels(path[k], path[k + 1], event);
        if (d < bestD) { best = i; bestD = d; }
      }
    });
    return best;
  }

  function dimAt(event) {
    for (const sprite of session.sprites) {
      const s = screenOf(sprite.position.toArray());
      const h = sprite.userData.px ?? 15;
      const w = h * (sprite.userData.aspect ?? 2);
      // Le texte est décalé de son point d'accroche (sprite.center).
      const cx = s.x + (0.5 - sprite.center.x) * w;
      const cy = s.y - (0.5 - sprite.center.y) * h;
      if (Math.abs(cx - event.clientX) < w / 2 + 3 && Math.abs(cy - event.clientY) < h / 2 + 3) {
        return sprite.userData.dimIndex;
      }
    }
    return -1;
  }

  /** Où pose-t-on le prochain point : point de l'esquisse, pièce
   *  (aimantée), ou plan de clic par `from` ; avec l'axe inféré. */
  function targetAt(event, from = null, { axes = true } = {}) {
    const hitIndex = pointAt(event);
    if (hitIndex >= 0) return { index: hitIndex, point: spec().points[hitIndex] };
    setRay(event);
    const { radius } = ctx.partMesh ? ctx.partCenterRadius() : { radius: 50 };
    raycaster.params.Line.threshold = Math.max(radius * 0.01, 0.3);
    const targets = [ctx.partMesh, ctx.partEdges, ...(ctx.surfaceMeshes ?? []),
      ...(ctx.boundaryLines ?? []).filter((l) => l.visible)].filter(Boolean);
    const hit = raycaster.intersectObjects(targets, false)[0];
    const snaps = [...(ctx.edgeSnaps ?? []), ...(ctx.boundarySnaps ?? [])];
    if (hit) {
      const snapped = snapFacePoint({ x: hit.point.x, y: hit.point.y, z: hit.point.z }, null,
        snaps, projectXYZ);
      return { point: [snapped.x, snapped.y, snapped.z],
               link: snapped.snapped === "vertex" || snapped.snapped === "center",
               snapped: snapped.snapped };
    }
    const anchor = from ?? [0, 0, 0];
    const { origin, direction } = raycaster.ray;
    let point = rayPlane(origin.toArray(), direction.toArray(),
      clickPlane(session.plane, anchor));
    if (!point) return null;
    let axis = null;
    if (from && axes) {
      const d = point.map((v, k) => v - from[k]);
      if (event.shiftKey) {
        const k = [0, 1, 2].reduce((best, j) => (Math.abs(d[j]) > Math.abs(d[best]) ? j : best), 0);
        axis = AXES[k];
      } else {
        axis = inferAxis(d, 7);
      }
      if (axis) point = onAxis(from, point, axis);
    }
    return { point, axis };
  }

  // ---------- dessin ----------

  function line(pts, material, dashed = false) {
    const obj = new THREE.Line(new THREE.BufferGeometry().setFromPoints(
      pts.map((p) => new THREE.Vector3(...p))), material);
    if (dashed) obj.computeLineDistances();
    obj.renderOrder = 21;
    group.add(obj);
    return obj;
  }
  function dots(pts, material) {
    const obj = new THREE.Points(new THREE.BufferGeometry().setFromPoints(
      pts.map((p) => new THREE.Vector3(...p))), material);
    obj.renderOrder = 23;
    group.add(obj);
  }
  function label(text, at, color) {
    const sprite = createDimSprite(text, at[0], at[1], at[2], color);
    sprite.renderOrder = 24;
    group.add(sprite);
    return sprite;
  }

  function scaleSprites() {
    if (!session) return;
    const wpp = worldPerPixel();
    for (const sprite of group.children) {
      if (!sprite.isSprite) continue;
      const h = (sprite.userData.px ?? 15) * wpp;
      sprite.scale.set(h * (sprite.userData.aspect ?? 1), h, 1);
    }
  }

  function clearGroup() {
    for (const child of [...group.children]) {
      child.geometry?.dispose();
      if (child.isSprite) {
        child.material.map?.dispose();
        child.material.dispose();
      }
      group.remove(child);
    }
  }

  function dimAnchor(dim, pts) {
    const s = spec();
    const mid = (a, b) => a.map((v, k) => (v + b[k]) / 2);
    if (dim.type === "length") {
      const e = s.entities[dim.entity];
      return mid(pts[e.a], pts[e.b]);
    }
    if (dim.type === "distance") return mid(pts[dim.p1], pts[dim.p2]);
    const l1 = s.entities[dim.e1];
    const l2 = s.entities[dim.e2];
    const shared = [l1.a, l1.b].find((p) => p === l2.a || p === l2.b);
    if (shared == null) return mid(mid(pts[l1.a], pts[l1.b]), mid(pts[l2.a], pts[l2.b]));
    const o1 = l1.a === shared ? l1.b : l1.a;
    const o2 = l2.a === shared ? l2.b : l2.a;
    const c = pts[shared];
    const unit = (p) => {
      const d = p.map((v, k) => v - c[k]);
      const n = Math.hypot(...d) || 1;
      return d.map((v) => v / n);
    };
    const u = unit(pts[o1]);
    const v = unit(pts[o2]);
    const reach = Math.min(Math.hypot(...pts[o1].map((x, k) => x - c[k])),
      Math.hypot(...pts[o2].map((x, k) => x - c[k]))) * 0.35;
    const bis = u.map((x, k) => x + v[k]);
    const n = Math.hypot(...bis) || 1;
    return c.map((x, k) => x + (bis[k] / n) * reach);
  }

  function draw() {
    clearGroup();
    session.sprites = [];
    if (!session) return;
    const s = spec();
    const pts = s.points;
    const sel = session.selection;
    const hov = session.hover;
    s.entities.forEach((e, i) => {
      if (e.type === "point") return;
      const chosen = sel?.kind === "entity" && sel.index === i;
      const over = hov?.kind === "entity" && hov.index === i;
      const material = chosen ? mats.selected : over ? mats.hover
        : e.construction ? mats.construction : mats.line;
      line(entityPath(e), material, material === mats.construction);
    });
    // Relations d'axe : la lettre de l'axe, en couleur, au milieu.
    for (const rel of s.relations) {
      const e = s.entities[rel.entity];
      const at = pts[e.a].map((v, k) => (v + pts[e.b][k]) / 2);
      const k = AXES.indexOf(rel.axis);
      const sprite = label(rel.axis, at, AXIS_CSS[k]);
      sprite.userData.px = 13;
      sprite.center.set(-0.3, 1.2);
    }
    s.dims.forEach((dim, i) => {
      if (dim.type === "distance") line([pts[dim.p1], pts[dim.p2]], mats.dimLine, true);
      const sprite = label(dimText(dim), dimAnchor(dim, pts));
      sprite.userData.dimIndex = i;
      sprite.userData.px = 15;
      if (dim.type === "length") sprite.center.set(0.5, -0.4);
      session.sprites.push(sprite);
    });
    const normal = pts.filter((_, i) => !s.links[i]);
    const linked = pts.filter((_, i) => s.links[i]);
    if (normal.length) dots(normal, mats.point);
    if (linked.length) dots(linked, mats.linked);
    if (sel?.kind === "point" && pts[sel.index]) dots([pts[sel.index]], mats.pointSel);
    if (sel?.kind === "entity") {
      const e = s.entities[sel.index];
      if (e?.type === "point") dots([pts[e.p]], mats.pointSel);
    }
    if (hov?.kind === "point" && pts[hov.index]) dots([pts[hov.index]], mats.pointHover);
    drawDraft();
    scaleSprites();
  }

  /** Tracé en cours : ligne élastique et guide d'axe, spline provisoire. */
  function drawDraft() {
    const cursor = session.cursor;
    if (session.tool === "line" && session.chain && cursor) {
      line([session.chain.point, cursor.point], mats.rubber, true);
      if (cursor.axis) {
        const k = AXES.indexOf(cursor.axis);
        const reach = Math.max(Math.hypot(...cursor.point.map((v, j) => v - session.chain.point[j])) * 3,
          ctx.partMesh ? ctx.partCenterRadius().radius : 50);
        const a = [...session.chain.point];
        const b = [...session.chain.point];
        a[k] -= reach;
        b[k] += reach;
        line([a, b], mats.axis[k]);
      }
      dots([session.chain.point], mats.pointSel);
    }
    if (session.tool === "spline" && session.splineDraft.length) {
      const list = session.splineDraft.map((d) => d.point);
      if (cursor) list.push(cursor.point);
      if (list.length >= 2) {
        try { line(sample(list, { perSpan: 16 }), mats.rubber, true); } catch { /* points confondus */ }
      }
      dots(session.splineDraft.map((d) => d.point), mats.pointSel);
    }
    if (cursor && session.tool !== "select" && session.tool !== "dim") {
      dots([cursor.point], cursor.link ? mats.linked : mats.pointHover);
    }
  }

  // ---------- outils ----------

  function setTool(tool) {
    if (!SKETCH3D_TOOLS.includes(tool)) {
      say(t("Esquisse 3D : outil non disponible — lignes, splines, points et cotes."), true);
      return;
    }
    endChain();
    session.splineDraft = [];
    session.dimPicks = [];
    session.tool = tool;
    session.cursor = null;
    renderer.domElement.style.cursor = tool === "select" ? "" : "crosshair";
    say(t(TOOL_HELP[tool]));
    draw();
    reopenPanel();
  }

  function endChain() {
    if (session) session.chain = null;
  }

  function lineClick(event) {
    const target = targetAt(event, session.chain?.point ?? null);
    if (!target) {
      say(t("Esquisse 3D : le plan de clic est vu par la tranche — Tab pour en changer"), true);
      return;
    }
    if (!session.chain) {
      session.chain = target;
      draw();
      return;
    }
    const from = session.chain;
    const same = (from.index != null && from.index === target.index)
      || Math.hypot(...target.point.map((v, k) => v - from.point[k])) < 1e-6;
    if (same) return; // second clic d'un double-clic
    const draft = copy();
    const a = addPoint(draft, from);
    const b = addPoint(draft, target);
    draft.entities.push({ type: "line", a, b });
    if (target.axis) draft.relations.push({ type: "axis", entity: draft.entities.length - 1, axis: target.axis });
    if (apply(draft)) session.chain = { index: b, point: session.spec.points[b] };
  }

  function splineClick(event) {
    const last = session.splineDraft.at(-1);
    const target = targetAt(event, last?.point ?? null, { axes: false });
    if (!target) return;
    if (last && Math.hypot(...target.point.map((v, k) => v - last.point[k])) < 1e-6) return;
    session.splineDraft.push(target);
    say(t("Spline : {n} point(s) — Entrée ou double-clic pour terminer", { n: session.splineDraft.length }));
    draw();
  }

  function finishSpline() {
    const list = session.splineDraft;
    session.splineDraft = [];
    if (list.length < 2) {
      draw();
      return;
    }
    const draft = copy();
    const pts = list.map((target) => addPoint(draft, target));
    draft.entities.push({ type: "spline", pts, closed: false, tangents: [] });
    apply(draft, { message: t("Spline ajoutée ({n} points).", { n: pts.length }) });
  }

  function pointClick(event) {
    const target = targetAt(event, null, { axes: false });
    if (!target) return;
    const draft = copy();
    const p = addPoint(draft, target);
    if (draft.entities.some((e) => e.type === "point" && e.p === p)) return;
    draft.entities.push({ type: "point", p });
    apply(draft);
  }

  function pickAt(event) {
    const p = pointAt(event);
    if (p >= 0) return { kind: "point", index: p };
    const e = entityAt(event);
    if (e >= 0) return { kind: "entity", index: e };
    return null;
  }

  async function dimClick(event, last = pickAt(event)) {
    const result = dimFromPicks(spec(), session.dimPicks, last);
    if (result.reset) {
      session.dimPicks = [];
      say(t(TOOL_HELP.dim));
      draw();
      return;
    }
    if (result.wait) {
      session.dimPicks = [result.wait];
      session.selection = result.wait;
      say(result.wait.kind === "point"
        ? t("Cotation : cliquez un second point")
        : t("Cotation : cliquez une seconde ligne pour l'angle, ou dans le vide pour la longueur"));
      draw();
      return;
    }
    session.dimPicks = [];
    session.selection = null;
    const dim = result.dim;
    const existing = findDim(spec(), dim);
    if (existing >= 0) {
      // Déjà cotée : on change la valeur de la cote existante.
      editDim(existing);
      return;
    }
    const current = measure(spec(), spec().points, { ...dim, value: 0 });
    const at = screenOf(dimAnchor(dim, spec().points));
    const value = await askValue(at, current, dim.type === "angle" ? "°" : "mm");
    if (value == null) {
      draw();
      return;
    }
    const draft = copy();
    draft.dims.push({ ...dim, value });
    apply(draft, { message: t("Cote ajoutée : {v}.", { v: dimText({ ...dim, value }) }) });
  }

  // ---------- saisie d'une valeur, près de la cote ----------

  let editBox = null;
  function askValue(at, initial, unit) {
    editBox?.cancel();
    return new Promise((resolve) => {
      const box = document.createElement("div");
      box.className = "sk3d-edit";
      box.dataset.ownKeys = "";
      const input = document.createElement("input");
      input.type = "text";
      input.inputMode = "decimal";
      input.value = String(Number(initial.toFixed(3)));
      const unitEl = document.createElement("span");
      unitEl.textContent = unit;
      const ok = document.createElement("button");
      ok.textContent = "✓";
      ok.title = t("Valider (Entrée)");
      box.append(input, unitEl, ok);
      box.style.left = `${Math.round(at.x)}px`;
      box.style.top = `${Math.round(at.y)}px`;
      document.body.append(box);
      input.focus();
      input.select();
      const done = (value) => {
        box.remove();
        if (editBox?.box === box) editBox = null;
        resolve(value);
      };
      const commit = () => {
        const value = Number(input.value.replace(",", "."));
        if (!Number.isFinite(value) || value < 0 || (unit !== "°" && value === 0)
            || (unit === "°" && value > 180)) {
          input.classList.add("bad");
          return;
        }
        done(value);
      };
      input.addEventListener("keydown", (event) => {
        event.stopPropagation();
        if (event.key === "Enter") commit();
        else if (event.key === "Escape") done(null);
      });
      ok.addEventListener("click", commit);
      editBox = { box, cancel: () => done(null) };
    });
  }

  async function editDim(index) {
    const dim = spec().dims[index];
    if (!dim) return;
    const at = screenOf(dimAnchor(dim, spec().points));
    const value = await askValue(at, dim.value, dim.type === "angle" ? "°" : "mm");
    if (value == null) return;
    const draft = copy();
    draft.dims[index] = { ...dim, value };
    apply(draft);
  }

  // ---------- sélection, glisser, supprimer ----------

  function deleteSelection() {
    const sel = session.selection;
    if (!sel) return false;
    const drop = sel.kind === "point" ? { points: [sel.index] }
      : sel.kind === "entity" ? { entities: [sel.index] }
        : sel.kind === "dim" ? { dims: [sel.index] }
          : { relations: [sel.index] };
    session.selection = null;
    apply(removeItems(spec(), drop), { message: t("Supprimé.") });
    return true;
  }

  function beginDrag(index, event) {
    session.drag = { index, moved: false, start: { x: event.clientX, y: event.clientY },
      origin: [...spec().points[index]], undo: spec() };
    ctx.controls.enabled = false;
  }

  function moveDrag(event) {
    const drag = session.drag;
    if (!drag.moved && Math.hypot(event.clientX - drag.start.x, event.clientY - drag.start.y) < 4) return;
    drag.moved = true;
    setRay(event);
    const { origin, direction } = raycaster.ray;
    const point = rayPlane(origin.toArray(), direction.toArray(),
      clickPlane(session.plane, drag.origin))
      ?? rayPlane(origin.toArray(), direction.toArray(),
        { normal: camera.getWorldDirection(new THREE.Vector3()).toArray(), point: drag.origin });
    if (!point) return;
    const draft = copy();
    draft.points[drag.index] = point.map(round);
    draft.links[drag.index] = null; // tiré, le point quitte la pièce
    const solved = solve(draft, [drag.index]);
    if (!solved.ok) return; // la position précédente reste
    session.spec = { ...cleanSpec(draft), points: solved.points.map((p) => p.map(round)) };
    draw();
  }

  function endDrag() {
    const drag = session.drag;
    session.drag = null;
    ctx.controls.enabled = true;
    if (drag.moved) {
      session.undo.push(drag.undo);
      session.redo = [];
      session.dirty = true;
      reopenPanel();
    }
    return drag;
  }

  // ---------- événements ----------

  function inPanel(event) {
    return !!event.target?.closest?.("aside, input, select, textarea, button, .sk3d-edit");
  }

  function onCaptureDown(event) {
    if (!session || event.button !== 0 || event.target !== renderer.domElement) return;
    if (session.tool !== "select") return;
    const p = pointAt(event);
    if (p < 0) return;
    event.stopImmediatePropagation();
    event.preventDefault();
    beginDrag(p, event);
  }

  function onCaptureMove(event) {
    if (!session?.drag) return;
    event.stopImmediatePropagation();
    moveDrag(event);
  }

  function onCaptureUp(event) {
    if (!session?.drag || event.button !== 0) return;
    event.stopImmediatePropagation();
    const drag = endDrag();
    if (!drag.moved) {
      session.selection = { kind: "point", index: drag.index };
      draw();
      reopenPanel();
    }
  }

  let press = null;
  function onDown(event) {
    if (!session || event.button !== 0) return;
    press = { x: event.clientX, y: event.clientY };
  }

  function onUp(event) {
    if (!session || !press || event.button !== 0) return;
    const travel = Math.hypot(event.clientX - press.x, event.clientY - press.y);
    press = null;
    if (travel > 5) return; // orbite, pas un clic
    if (session.tool === "line") lineClick(event);
    else if (session.tool === "spline") splineClick(event);
    else if (session.tool === "point") pointClick(event);
    else if (session.tool === "dim") dimClick(event);
    else {
      const d = dimAt(event);
      const pick = d >= 0 ? { kind: "dim", index: d } : pickAt(event);
      session.selection = pick;
      draw();
      reopenPanel();
    }
  }

  function onDouble(event) {
    if (!session) return;
    if (session.tool === "line") {
      endChain();
      draw();
      say(t("Chaîne terminée — cliquez pour en commencer une autre."));
    } else if (session.tool === "spline") {
      finishSpline();
    } else if (session.tool === "select") {
      const d = dimAt(event);
      if (d >= 0) editDim(d);
    }
  }

  function onMove(event) {
    if (!session || session.drag) return;
    if (session.tool === "line" || session.tool === "spline" || session.tool === "point") {
      const from = session.tool === "line" ? session.chain?.point
        : session.splineDraft.at(-1)?.point;
      session.cursor = targetAt(event, from ?? null, { axes: session.tool === "line" });
      session.hover = null;
    } else {
      session.cursor = null;
      const d = session.tool === "select" ? dimAt(event) : -1;
      session.hover = d >= 0 ? { kind: "dim", index: d } : pickAt(event);
    }
    renderer.domElement.style.cursor = session.tool === "select"
      ? (session.hover?.kind === "point" ? "grab" : session.hover ? "pointer" : "")
      : "crosshair";
    draw();
  }

  function undo(stack, other) {
    const previous = stack.pop();
    if (!previous) return;
    other.push(session.spec);
    session.spec = previous;
    session.selection = null;
    endChain();
    draw();
    reopenPanel();
  }

  function onKey(event) {
    if (!session || inPanel(event)) return;
    const key = event.key;
    const ctrl = event.ctrlKey || event.metaKey;
    const consume = () => {
      event.preventDefault();
      event.stopImmediatePropagation();
    };
    if (ctrl && (key === "z" || key === "Z") && !event.shiftKey) {
      consume();
      undo(session.undo, session.redo);
    } else if (ctrl && (key === "y" || key === "Y")) {
      consume();
      undo(session.redo, session.undo);
    } else if (key === "Escape") {
      consume();
      if (session.tool === "spline" && session.splineDraft.length) finishSpline();
      else if (session.chain) {
        endChain();
        draw();
      } else if (session.dimPicks.length) {
        session.dimPicks = [];
        draw();
      } else if (session.tool !== "select") setTool("select");
      else if (session.selection) {
        session.selection = null;
        draw();
        reopenPanel();
      }
    } else if (key === "Enter") {
      consume();
      if (session.tool === "spline") finishSpline();
      else if (session.tool === "dim" && session.dimPicks.length) dimClick(event, null);
    } else if (key === "Tab") {
      consume();
      session.plane = nextPlane(session.plane);
      say(t("Plan de clic : {p}", { p: t(PLANE_LABELS[session.plane]) }));
      reopenPanel();
    } else if (key === "Delete" || key === "Backspace") {
      if (deleteSelection()) consume();
    } else if (!ctrl && !event.altKey) {
      const tool = { l: "line", p: "point", d: "dim", s: "select" }[key.toLowerCase()];
      if (tool) {
        consume();
        setTool(tool);
      }
    }
  }

  /** Les boutons Ligne, Spline, Point, Cotation, Sélectionner du ruban
   *  Esquisse servent aussi en esquisse 3D. */
  function onSketchbar(event) {
    if (!session) return;
    const button = event.target.closest?.("button");
    if (!button) return;
    const tool = button.dataset.tool;
    if (tool) {
      event.stopImmediatePropagation();
      event.preventDefault();
      setTool(tool);
    } else if (button.id === "sk-start") {
      event.stopImmediatePropagation();
      say(t("Terminez d'abord l'esquisse 3D (OK ou ✕)."), true);
    }
  }

  // ---------- panneau ----------

  function selectionGroup() {
    const sel = session.selection;
    const s = spec();
    if (!sel) return null;
    if (sel.kind === "point") {
      const p = s.points[sel.index];
      if (!p) return null;
      const rows = ["X", "Y", "Z"].map((axis, k) => ({
        type: "number", key: `sel${axis}`, label: axis, unit: "mm", lazy: true, value: p[k] }));
      if (s.links[sel.index]) {
        rows.push({ type: "note", readonly: true, text: t("⛓ Lié à la pièce : il la suit.") });
      }
      rows.push({ type: "buttons", items: [
        ...(s.links[sel.index] ? [{ label: t("Délier"), onClick: () => {
          const draft = copy();
          draft.links[sel.index] = null;
          apply(draft);
        } }] : []),
        { label: t("Supprimer"), onClick: () => deleteSelection() },
      ] });
      return { label: t("Point P{n}", { n: sel.index + 1 }), rows };
    }
    if (sel.kind === "entity") {
      const e = s.entities[sel.index];
      if (!e) return null;
      const rows = [];
      if (e.type === "line") {
        const length = Math.hypot(...s.points[e.b].map((v, k) => v - s.points[e.a][k]));
        const rel = s.relations.find((r) => r.entity === sel.index);
        rows.push(
          { type: "note", readonly: true, text: t("Longueur : {v} mm", { v: Number(length.toFixed(3)) }) },
          { type: "select", key: "selAxis", label: t("Le long de"), value: rel?.axis ?? "",
            options: [["", "—"], ["X", "X"], ["Y", "Y"], ["Z", "Z"]] },
        );
      } else if (e.type === "spline") {
        rows.push({ type: "check", key: "selClosed", label: t("Fermée"), value: e.closed });
      }
      if (e.type !== "point") {
        rows.push({ type: "check", key: "selConstruction", label: t("Construction"), value: !!e.construction });
      }
      rows.push({ type: "buttons", items: [
        ...(e.type === "line" ? [{ label: t("Coter la longueur"),
          onClick: () => { session.dimPicks = [{ kind: "entity", index: sel.index }]; dimClick({}, null); } }] : []),
        { label: t("Supprimer"), onClick: () => deleteSelection() },
      ] });
      return { label: entityText(s, sel.index), rows };
    }
    if (sel.kind === "dim") {
      const dim = s.dims[sel.index];
      if (!dim) return null;
      return { label: dimLabel(s, dim), rows: [
        { type: "number", key: "selValue", label: t("Valeur"), lazy: true,
          unit: dim.type === "angle" ? "°" : "mm", value: dim.value },
        { type: "buttons", items: [{ label: t("Supprimer"), onClick: () => deleteSelection() }] },
      ] };
    }
    return null;
  }

  /** Une valeur du groupe de sélection a changé. */
  function onPanelChange(values) {
    if (!session || reopening) return;
    if (values.plane && values.plane !== session.plane) {
      session.plane = values.plane;
      return;
    }
    const sel = session.selection;
    const s = spec();
    if (!sel) return;
    const draft = copy();
    if (sel.kind === "point") {
      const p = s.points[sel.index];
      const next = ["X", "Y", "Z"].map((axis, k) => Number(String(values[`sel${axis}`]).replace(",", ".")));
      if (next.some((v) => !Number.isFinite(v)) || next.every((v, k) => Math.abs(v - p[k]) < 1e-9)) return;
      draft.points[sel.index] = next;
      draft.links[sel.index] = null;
      apply(draft, { fixed: [sel.index] });
    } else if (sel.kind === "entity") {
      const e = s.entities[sel.index];
      if (e.type === "line" && "selAxis" in values) {
        const rel = s.relations.findIndex((r) => r.entity === sel.index);
        const want = values.selAxis || "";
        if ((rel >= 0 ? s.relations[rel].axis : "") !== want) {
          draft.relations = draft.relations.filter((r) => r.entity !== sel.index);
          if (want) draft.relations.push({ type: "axis", entity: sel.index, axis: want });
          apply(draft);
          return;
        }
      }
      if ("selConstruction" in values && !!values.selConstruction !== !!e.construction) {
        draft.entities[sel.index].construction = !!values.selConstruction;
        apply(draft);
        return;
      }
      if (e.type === "spline" && "selClosed" in values && !!values.selClosed !== !!e.closed) {
        draft.entities[sel.index].closed = !!values.selClosed;
        apply(draft);
      }
    } else if (sel.kind === "dim") {
      const value = Number(String(values.selValue).replace(",", "."));
      const dim = s.dims[sel.index];
      if (!dim || !Number.isFinite(value) || value <= 0 || Math.abs(value - dim.value) < 1e-9) return;
      draft.dims[sel.index] = { ...dim, value };
      apply(draft);
    }
  }

  function reopenPanel() {
    if (!session) return;
    const s = spec();
    const scroller = document.getElementById("panel");
    const scrollTop = scroller?.scrollTop ?? 0;
    const sel = session.selection;
    const toolButtons = SKETCH3D_TOOLS.map((tool) => ({
      label: (session.tool === tool ? "● " : "") + t(TOOL_LABELS[tool]),
      onClick: () => setTool(tool),
    }));
    const groups = [
      { label: t("Outils"), rows: [
        { type: "buttons", items: toolButtons },
        { type: "note", readonly: true, text: t(TOOL_HELP[session.tool]) },
        { type: "select", key: "plane", label: t("Plan de clic"), value: session.plane,
          options: CLICK_PLANES.map((k) => [k, PLANE_LABELS[k]]) },
      ] },
    ];
    const selGroup = selectionGroup();
    if (selGroup) groups.push(selGroup);
    groups.push(
      { label: t("Entités ({n})", { n: s.entities.length }), rows: [{
        type: "list", empty: t("— rien encore : choisissez Ligne, Spline ou Point —"),
        items: s.entities.map((_, i) => ({
          label: entityText(s, i),
          editable: sel?.kind === "entity" && sel.index === i,
          onEdit: () => { session.selection = { kind: "entity", index: i }; draw(); reopenPanel(); },
          onDelete: () => { session.selection = { kind: "entity", index: i }; deleteSelection(); },
        })),
      }] },
      { label: t("Cotes ({n})", { n: s.dims.length }), rows: [{
        type: "list", empty: t("— aucune : outil Cotation (D) —"),
        items: s.dims.map((dim, i) => ({
          label: dimLabel(s, dim), editable: true,
          onEdit: () => editDim(i),
          onDelete: () => { session.selection = { kind: "dim", index: i }; deleteSelection(); },
        })),
      }] },
      { label: t("Relations ({n})", { n: s.relations.length }), rows: [{
        type: "list", empty: t("— aucune —"),
        items: s.relations.map((rel, i) => ({
          label: t("Ligne {n} le long de {a}", { n: rel.entity + 1, a: rel.axis }),
          onDelete: () => { session.selection = { kind: "relation", index: i }; deleteSelection(); },
        })),
      }] },
    );
    reopening = true;
    panel.open({
      icon: "sketch3d",
      title: session.entry ? session.entry.label : t("Esquisse 3D"),
      autoFocus: false,
      groups,
      note: t("OK enregistre l'esquisse 3D, ✕ l'abandonne. Ctrl+Z / Ctrl+Y défont et refont dans l'esquisse."),
      onChange: onPanelChange,
      // Fermé (✕, autre commande) : on sort. Après OK, onApply passe
      // juste après et enregistre d'abord.
      onClose: () => { if (!reopening) queueMicrotask(() => stop()); },
      onApply: () => save(),
      onCancel: () => say(t("Esquisse 3D : modifications abandonnées.")),
    });
    reopening = false;
    if (scroller) scroller.scrollTop = scrollTop;
  }

  // ---------- entrer, sortir ----------

  function hideEdited(hidden) {
    const name = session?.entry?.name;
    if (!name) return;
    for (const lines of ctx.boundaryLines ?? []) {
      if (lines.userData.boundary?.name === name) lines.visible = !hidden;
    }
  }

  function save() {
    const s = spec();
    const payload = { points: s.points, links: s.links, entities: s.entities, dims: s.dims,
      relations: s.relations };
    const entry = session.entry;
    if (!s.entities.length) {
      say(t("Esquisse 3D vide : rien n'est enregistré."), true);
      stop();
      return;
    }
    stop();
    refresh(entry ? call("edit_sketch3d", { sketch3d: entry.name, spec: payload })
      : call("add_sketch3d", { spec: payload }));
  }

  function stop() {
    if (!session) return;
    editBox?.cancel();
    if (session.drag) ctx.controls.enabled = true;
    hideEdited(false);
    clearGroup();
    group.removeFromParent();
    session = null;
    renderer.domElement.style.cursor = "";
    renderer.domElement.removeEventListener("pointerdown", onDown);
    renderer.domElement.removeEventListener("pointerup", onUp);
    renderer.domElement.removeEventListener("pointermove", onMove);
    renderer.domElement.removeEventListener("dblclick", onDouble);
    window.removeEventListener("pointerdown", onCaptureDown, true);
    window.removeEventListener("pointermove", onCaptureMove, true);
    window.removeEventListener("pointerup", onCaptureUp, true);
    window.removeEventListener("keydown", onKey, true);
    document.getElementById("sketchbar")?.removeEventListener("click", onSketchbar, true);
    ctx.controls.removeEventListener?.("change", scaleSprites);
    document.body.classList.remove("sketch3d-active");
  }

  /** Ouvre le mode ; `entry` (entrée d'arbre avec `sketch3d`) le réédite. */
  function open(entry = null) {
    stop();
    session = {
      entry, spec: cleanSpec(entry?.sketch3d ?? {}), undo: [], redo: [], dirty: false,
      tool: entry ? "select" : "line", plane: "XY", chain: null, splineDraft: [], dimPicks: [],
      selection: null, hover: null, cursor: null, drag: null, sprites: [],
    };
    scene.add(group);
    hideEdited(true);
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);
    renderer.domElement.addEventListener("pointermove", onMove);
    renderer.domElement.addEventListener("dblclick", onDouble);
    window.addEventListener("pointerdown", onCaptureDown, true);
    window.addEventListener("pointermove", onCaptureMove, true);
    window.addEventListener("pointerup", onCaptureUp, true);
    window.addEventListener("keydown", onKey, true);
    document.getElementById("sketchbar")?.addEventListener("click", onSketchbar, true);
    ctx.controls.addEventListener?.("change", scaleSprites);
    document.body.classList.add("sketch3d-active");
    renderer.domElement.style.cursor = session.tool === "select" ? "" : "crosshair";
    draw();
    reopenPanel();
    say(entry ? t("Esquisse 3D : {n} — cliquez un point, une entité ou une cote.", { n: entry.label })
      : t(TOOL_HELP.line));
  }

  return {
    open,
    stop,
    get active() { return session !== null; },
    /** Débogage et tests de fumée : l'esquisse en cours, à l'écran. */
    screen() {
      if (!session) return null;
      const toScreen = (p) => {
        const s = screenOf(p);
        return [Math.round(s.x), Math.round(s.y)];
      };
      return { tool: session.tool, spec: spec(), points: spec().points.map(toScreen),
               dims: session.sprites.map((s) => toScreen(s.position.toArray())) };
    },
  };
}
