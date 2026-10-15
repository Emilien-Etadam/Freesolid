// Spline 3D : l'esquisse 3D de FreeSolid. Chaque clic pose un point — sur
// la pièce, une surface ou une courbe (les sommets et centres tout
// proches aimantent), ou dans le vide sur le plan de clic, qui passe par
// le dernier point posé. Tab change de plan. Les coordonnées se
// corrigent dans la liste du panneau ; la courbe se réédite depuis l'arbre.
// Édition dans la vue : tirer un point, choisir un point pour tirer les
// bouts de sa poignée de tangente (Alt : un seul côté), Ctrl+clic sur la
// courbe pour un point de plus, Suppr pour retirer le point choisi ;
// peigne de courbure, polygone de contrôle (pôles à tirer), simplifier,
// lisser (calcul : splinemath.js, le même que le moteur).

import { t } from "./i18n.js";
import { snapFacePoint } from "./pointsnap.js";
import {
  sample, curvatureComb, maxCurvature, allHandleTips, preferPoint, dragTip, pinTangent,
  insertPoint, removePoint, simplify, relax, nearestOnCurve, cleanTangents,
  solve,
} from "./splinemath.js";

export const CLICK_PLANES = ["XY", "XZ", "YZ"];

const NORMALS = { XY: [0, 0, 1], XZ: [0, 1, 0], YZ: [1, 0, 0] };

/** Plan de clic : normale du plan choisi, passant par `anchor`. */
export function clickPlane(key, anchor = [0, 0, 0]) {
  return { normal: NORMALS[key] ?? NORMALS.XY, point: anchor };
}

/** Intersection d'un rayon et d'un plan, ou null (rayon parallèle, ou
 *  plan derrière la caméra). */
export function rayPlane(origin, direction, plane) {
  const [nx, ny, nz] = plane.normal;
  const denom = direction[0] * nx + direction[1] * ny + direction[2] * nz;
  if (Math.abs(denom) < 1e-9) return null;
  const tt = ((plane.point[0] - origin[0]) * nx
    + (plane.point[1] - origin[1]) * ny
    + (plane.point[2] - origin[2]) * nz) / denom;
  if (tt < 0) return null;
  return [origin[0] + tt * direction[0], origin[1] + tt * direction[1],
          origin[2] + tt * direction[2]];
}

/** Le point ramené sur l'axe X, Y ou Z qui passe par `last` — celui où
 *  le segment avance le plus (Maj : segment parallèle à un axe). */
export function alongAxis(last, point) {
  const delta = point.map((v, i) => v - last[i]);
  const axis = delta.reduce((best, v, i, all) =>
    (Math.abs(v) > Math.abs(all[best]) ? i : best), 0);
  return { point: last.map((v, i) => (i === axis ? point[i] : v)),
           axis: "XYZ"[axis] };
}

/** Applique les règles des segments (axe imposé, longueur cotée) en
 *  chaîne : le segment i garde sa direction, ramenée sur son axe, prend
 *  sa longueur, et la suite de la courbe suit en bloc. Même calcul que le
 *  moteur (solve_curve_rules). */
export function solveRules(points, rules, fixed = []) {
  const pts = (points ?? []).map((p) => p.slice(0, 3).map(Number));
  const locked = new Set(fixed);
  (rules ?? []).forEach((rule, i) => {
    if (!rule || i + 1 >= pts.length || locked.has(i + 1)) return;
    const [a, b] = [pts[i], pts[i + 1]];
    let d = b.map((v, k) => v - a[k]);
    const k = "XYZ".indexOf(rule.axis ?? "");
    if (rule.axis && k >= 0) {
      d = d.map((v, n) => (n === k ? v : 0));
      if (Math.abs(d[k]) < 1e-9) d[k] = 1;
    } else if (rule.angle != null && i >= 1) {
      d = turnToAngle(a.map((v, n) => v - pts[i - 1][n]), d, rule.angle);
    }
    if (rule.length != null && rule.length > 0) {
      const size = Math.hypot(...d);
      if (size > 1e-9) d = d.map((v) => (v * rule.length) / size);
    }
    const shift = a.map((v, n) => v + d[n] - b[n]);
    for (let j = i + 1; j < pts.length; j++) {
      if (locked.has(j)) break; // un point lié arrête la propagation
      pts[j] = pts[j].map((v, n) => v + shift[n]);
    }
  });
  return relaxRules(pts, rules ?? [], locked);
}

/** Passe globale par relaxation (comme le moteur) : chaque règle déplace
 *  les extrémités libres de son segment jusqu'à ce que toutes tiennent.
 *  Sans point lié, le premier sert d'ancre. Rend le meilleur résultat —
 *  le moteur refuse à l'OK des règles incompatibles. */
export function relaxRules(pts, rules, locked = new Set(), rounds = 4000) {
  const active = (r) => r && ["axis", "length", "angle"]
    .some((k) => r[k] != null && r[k] !== "");
  if (pts.length < 2 || !rules.some(active)) return pts;
  const fixed = locked.size ? locked : new Set([0]);
  const free = (i) => (fixed.has(i) ? 0 : 1);
  const diff = (i) => pts[i + 1].map((v, k) => v - pts[i][k]);
  const move = (i, j, delta) => {
    const total = free(i) + free(j);
    if (!total) return;
    pts[i] = pts[i].map((v, k) => v - (delta[k] * free(i)) / total);
    pts[j] = pts[j].map((v, k) => v + (delta[k] * free(j)) / total);
  };
  const want = (i, rule) => {
    const d = diff(i);
    const k = "XYZ".indexOf(rule.axis ?? "");
    if (rule.axis && k >= 0) return d.map((v, n) => (n === k ? v : 0));
    if (rule.angle != null && rule.angle !== "" && i >= 1) {
      return turnToAngle(pts[i].map((v, n) => v - pts[i - 1][n]), d,
        Number(rule.angle));
    }
    return d;
  };
  const residual = () => rules.reduce((worst, rule, i) => {
    if (!rule || i + 1 >= pts.length) return worst;
    const d = diff(i);
    const w = want(i, rule);
    let r = Math.hypot(...w.map((v, k) => v - d[k]));
    if (rule.length != null && rule.length !== "") {
      r = Math.max(r, Math.abs(Math.hypot(...d) - Number(rule.length)));
    }
    return Math.max(worst, r);
  }, 0);
  for (let round = 0; round < rounds && residual() > 1e-7; round++) {
    rules.forEach((rule, i) => {
      if (!rule || i + 1 >= pts.length) return;
      const d = diff(i);
      const w = want(i, rule);
      move(i, i + 1, w.map((v, k) => v - d[k]));
      if (rule.length != null && rule.length !== "") {
        const e = diff(i);
        const size = Math.hypot(...e);
        if (size > 1e-12) {
          const grow = (Number(rule.length) - size) / size;
          move(i, i + 1, e.map((v) => v * grow));
        }
      }
    });
  }
  return pts;
}

/** `d` tourné dans le plan (prev, d) pour faire `degrees` avec `prev`,
 *  longueur gardée — même calcul que le moteur. */
export function turnToAngle(prev, d, degrees) {
  const norm = (v) => Math.hypot(...v);
  const size = norm(d);
  const base = norm(prev);
  if (size < 1e-9 || base < 1e-9) return d;
  const e1 = prev.map((c) => c / base);
  const dot = (u, v) => u.reduce((s, c, k) => s + c * v[k], 0);
  let side = d.map((c, k) => c - dot(d, e1) * e1[k]);
  if (norm(side) < 1e-9) {
    const helper = Math.abs(e1[2]) < 0.9 ? [0, 0, 1] : [1, 0, 0];
    side = helper.map((c, k) => c - dot(helper, e1) * e1[k]);
  }
  const e2 = side.map((c) => c / norm(side));
  const theta = (degrees * Math.PI) / 180;
  return e1.map((c, k) =>
    size * (Math.cos(theta) * c + Math.sin(theta) * e2[k]));
}

/** Indices des points liés (pour le solveur). */
function linkedIndices(links) {
  return (links ?? []).flatMap((l, i) => (l ? [i] : []));
}

function samePoints(a, b) {
  return a.length === b.length && a.every((p, i) =>
    p.every((v, k) => Math.abs(v - b[i][k]) < 1e-9));
}

/** Plan suivant (Tab). */
export function nextPlane(key) {
  const i = CLICK_PLANES.indexOf(key);
  return CLICK_PLANES[(i + 1) % CLICK_PLANES.length];
}

/** Ce qui manque pour créer la courbe, ou null. */
export function curveProblem(points, closed) {
  if ((points?.length ?? 0) < 2) return "Spline 3D : au moins deux points";
  if (closed && points.length < 3) {
    return "Spline 3D : une courbe fermée demande trois points";
  }
  for (let i = 1; i < points.length; i++) {
    const [a, b] = [points[i - 1], points[i]];
    if (Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]) < 1e-6) {
      return "Spline 3D : deux points consécutifs sont confondus";
    }
  }
  return null;
}

const PLANE_LABELS = {
  XY: "Plan de dessus", XZ: "Plan de face", YZ: "Plan de droite",
};

/** Champs de la poignée du point choisi : pilotée ?, longueurs en %. */
export function handleFields(values) {
  const sel = values.selected;
  const pts = values.points ?? [];
  if (sel == null || sel >= pts.length || !values.spline || pts.length < 2) return null;
  let slopes;
  try { slopes = solve(pts, !!values.closed, values.tangents); } catch { return null; }
  const pct = (v) => Math.round(Math.hypot(...v) * 1000) / 10;
  return { handleDriven: !!(values.tangents ?? [])[sel],
           handleIn: pct(slopes.mIn[sel]), handleOut: pct(slopes.mOut[sel]) };
}

const HANDLE_KEYS = ["handleDriven", "handleIn", "handleOut"];

/** Tangentes après une saisie dans les champs de poignée (null : rien n'a
 *  changé). Taper une longueur pilote la poignée ; décocher la libère. */
export function tangentsFromFields(values, previous) {
  const sel = values.selected;
  const pts = values.points ?? [];
  const tangents = cleanTangents(values.tangents, pts.length);
  const typed = ["handleIn", "handleOut"].some(
    (k) => String(values[k]) !== String(previous[k]));
  const toggled = !!values.handleDriven !== !!previous.handleDriven;
  if (!typed && !toggled) return null;
  if (!typed && !values.handleDriven) {
    tangents[sel] = null;
    return tangents;
  }
  const pinned = tangents[sel] ?? pinTangent(pts, !!values.closed, tangents, sel)[sel];
  if (!pinned) return null;
  const lin = Number(String(values.handleIn).replace(",", ".")) / 100;
  const lout = Number(String(values.handleOut).replace(",", ".")) / 100;
  tangents[sel] = { dir: pinned.dir, in: lin > 0 ? lin : pinned.in,
                    out: lout > 0 ? lout : pinned.out };
  return tangents;
}

export function installCurve3d(ctx) {
  const { THREE, camera, renderer, scene, panel, call, refresh, say } = ctx;
  const raycaster = new THREE.Raycaster();
  const preview = new THREE.Group();
  preview.renderOrder = 20;
  let tool = null; // { curve, values, sync, poles, polesKey, picked }
  let press = null;
  let drag = null;   // { kind: "point"|"tip"|"pole", index, side?, normal, origin, moved }
  let rubber = null; // point sous le curseur (aperçu du segment suivant)
  let poleBusy = false;
  let poleNext = null;
  const PICK_PX = 9;

  const theme = ctx.sceneTheme;
  const lineMaterial = new THREE.LineBasicMaterial({ color: theme.curve, depthTest: false });
  const rubberMaterial = new THREE.LineDashedMaterial({
    color: theme.curve, dashSize: 2, gapSize: 1.5, depthTest: false });
  const dotMaterial = new THREE.PointsMaterial({
    color: theme.accent, size: 7, sizeAttenuation: false, depthTest: false });
  const chosenMaterial = new THREE.PointsMaterial({
    color: theme.selection, size: 11, sizeAttenuation: false, depthTest: false });
  const handleMaterial = new THREE.LineBasicMaterial({ color: theme.selection, depthTest: false });
  const tipMaterial = new THREE.PointsMaterial({
    color: theme.selection, size: 9, sizeAttenuation: false, depthTest: false });
  const handleSoftMaterial = new THREE.LineBasicMaterial({
    color: theme.accent, depthTest: false, transparent: true, opacity: 0.7 });
  const tipSoftMaterial = new THREE.PointsMaterial({
    color: theme.accent, size: 7, sizeAttenuation: false, depthTest: false });
  const combMaterial = new THREE.LineBasicMaterial({
    color: theme.dim, depthTest: false, transparent: true, opacity: 0.7 });
  const polygonMaterial = new THREE.LineDashedMaterial({
    color: theme.ink2, dashSize: 1.5, gapSize: 1, depthTest: false });
  const poleMaterial = new THREE.PointsMaterial({
    color: theme.ink2, size: 7, sizeAttenuation: false, depthTest: false });

  function points() { return tool?.values.points ?? []; }
  function tangents() { return cleanTangents(tool?.values.tangents, points().length); }
  function isSpline() { return !!tool?.values.spline; }
  function closed() { return !!tool?.values.closed; }

  function clearPreview() {
    for (const child of [...preview.children]) {
      child.geometry?.dispose();
      preview.remove(child);
    }
  }

  const vec = (p) => new THREE.Vector3(...p);
  function addLine(pts, material, dashed = false) {
    const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts.map(vec)), material);
    if (dashed) line.computeLineDistances();
    line.renderOrder = 21;
    preview.add(line);
  }
  function addDots(pts, material) {
    const dots = new THREE.Points(new THREE.BufferGeometry().setFromPoints(pts.map(vec)), material);
    dots.renderOrder = 22;
    preview.add(dots);
  }

  /** Taille de référence pour l'échelle du peigne. */
  function curveSize() {
    const pts = points();
    let size = 1;
    for (const p of pts) {
      for (const q of pts) size = Math.max(size, Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]));
    }
    return size;
  }

  function curveKey() {
    const v = tool?.values ?? {};
    return JSON.stringify([v.points, tangents(), !!v.closed]);
  }

  function drawPreview() {
    clearPreview();
    const list = points();
    if (!list.length) return;
    const opts = { closed: closed(), tangents: tangents(), spline: isSpline() };
    let path = list;
    try { path = sample(list, opts); } catch { /* points confondus : polyligne */ }
    if (path.length >= 2) addLine(path, lineMaterial);
    addDots(list, dotMaterial);
    const sel = tool.values.selected;
    // Poignées de tous les points, comme dans les modeleurs courants ;
    // celle du point choisi ressort.
    if (isSpline() && list.length >= 2) {
      try {
        allHandleTips(list, closed(), tangents()).forEach((tips, i) => {
          const chosen = i === sel;
          addLine([tips.in, list[i], tips.out].filter(Boolean),
            chosen ? handleMaterial : handleSoftMaterial);
          addDots([tips.in, tips.out].filter(Boolean), chosen ? tipMaterial : tipSoftMaterial);
        });
      } catch { /* rien à montrer */ }
    }
    if (sel != null && list[sel]) addDots([list[sel]], chosenMaterial);
    if (isSpline() && list.length >= 2 && tool.values.comb) {
      try {
        const peak = maxCurvature(list, opts) || 1;
        const scale = (curveSize() * 0.25 * (Number(tool.values.combScale) || 100) / 100) / peak;
        const teeth = curvatureComb(list, { ...opts, scale });
        for (const [p, q] of teeth) addLine([p, q], combMaterial);
        if (teeth.length >= 2) addLine(teeth.map(([, q]) => q), combMaterial);
      } catch { /* pas de peigne */ }
    }
    if (isSpline() && tool.values.polygon && tool.poles && tool.polesKey === curveKey()) {
      addLine(tool.poles, polygonMaterial, true);
      addDots(tool.poles, poleMaterial);
    }
    if (rubber && !drag) addLine([list[list.length - 1], rubber], rubberMaterial, true);
  }

  /** Polygone de contrôle : demandé au moteur (pôles de la B-spline). */
  let polesTimer = null;
  function requestPoles() {
    clearTimeout(polesTimer);
    if (!tool?.values.polygon || !isSpline() || points().length < 2) return;
    const key = curveKey();
    if (tool.polesKey === key) return;
    polesTimer = setTimeout(async () => {
      try {
        const result = await call("curve_poles",
          { points: points(), closed: closed(), tangents: tangents() });
        if (!tool || curveKey() !== key) return;
        tool.poles = result.poles;
        tool.polesKey = key;
        drawPreview();
      } catch { /* pas de polygone */ }
    }, 40);
  }

  function setRay(event) {
    const rect = renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      -((event.clientY - rect.top) / rect.height) * 2 + 1);
    raycaster.setFromCamera(ndc, camera);
  }

  function project(point) {
    const v = new THREE.Vector3(point.x, point.y, point.z).project(camera);
    const rect = renderer.domElement.getBoundingClientRect();
    return { x: rect.left + (v.x + 1) / 2 * rect.width,
             y: rect.top + (1 - v.y) / 2 * rect.height };
  }
  const pixels = (p, event) => {
    const s = project({ x: p[0], y: p[1], z: p[2] });
    return Math.hypot(s.x - event.clientX, s.y - event.clientY);
  };

  /** Ce qu'il y a sous le pointeur : bout de poignée, point, pôle. */
  function hitAt(event) {
    const list = points();
    const nearest = (candidates) => {
      let best = null;
      for (const [p, hit] of candidates) {
        if (!p) continue;
        const d = pixels(p, event);
        if (d < PICK_PX && (!best || d < best.d)) best = { d, hit };
      }
      return best;
    };
    let tips = [];
    if (isSpline() && list.length >= 2) {
      try {
        tips = allHandleTips(list, closed(), tangents()).flatMap((tip, i) => [
          [tip.in, { kind: "tip", index: i, side: "in", at: tip.in }],
          [tip.out, { kind: "tip", index: i, side: "out", at: tip.out }]]);
      } catch { /* pas de poignée */ }
    }
    const found = preferPoint(nearest(list.map((p, i) => [p, { kind: "point", index: i, at: p }])),
      nearest(tips));
    if (found) return found.hit;
    const best = { d: PICK_PX, hit: null };
    const consider = (p, hit) => {
      const d = pixels(p, event);
      if (d < best.d) { best.d = d; best.hit = hit; }
    };
    if (isSpline() && tool.values.polygon && tool.poles && tool.polesKey === curveKey()) {
      tool.poles.forEach((p, i) => consider(p, { kind: "pole", index: i, at: p }));
    }
    return best.hit;
  }

  /** Point de la courbe sous le pointeur (pour Ctrl+clic : insérer). */
  function curveHit(event) {
    const list = points();
    if (list.length < 2) return null;
    let path;
    try {
      path = sample(list, { closed: closed(), tangents: tangents(), spline: isSpline(), perSpan: 48 });
    } catch { return null; }
    let best = null;
    for (const p of path) {
      const d = pixels(p, event);
      if (d < PICK_PX && (!best || d < best.d)) best = { d, p };
    }
    return best?.p ?? null;
  }

  /** Point visé : sur la géométrie (aimanté), sinon sur le plan de clic. */
  function aimedPoint(event) {
    setRay(event);
    const { radius } = ctx.partMesh ? ctx.partCenterRadius() : { radius: 50 };
    raycaster.params.Line.threshold = Math.max(radius * 0.01, 0.3);
    const targets = [ctx.partMesh, ctx.partEdges, ...ctx.surfaceMeshes,
      ...ctx.boundaryLines].filter(Boolean);
    const hit = raycaster.intersectObjects(targets, false)[0];
    const snaps = [...(ctx.edgeSnaps ?? []), ...(ctx.boundarySnaps ?? []),
      ...points().map(([x, y, z]) => ({ x, y, z, kind: "vertex" }))];
    if (hit) {
      const snapped = snapFacePoint(
        { x: hit.point.x, y: hit.point.y, z: hit.point.z }, null, snaps,
        project);
      return { point: [snapped.x, snapped.y, snapped.z],
               snapped: snapped.snapped, onGeometry: true };
    }
    const list = points();
    const plane = clickPlane(tool.values.plane,
      list.length ? list[list.length - 1] : [0, 0, 0]);
    const { origin, direction } = raycaster.ray;
    const point = rayPlane([origin.x, origin.y, origin.z],
      [direction.x, direction.y, direction.z], plane);
    if (!point) return null;
    // Un sommet tout proche à l'écran gagne aussi dans le vide.
    const snapped = snapFacePoint({ x: point[0], y: point[1], z: point[2] },
      null, snaps, project);
    return { point: [snapped.x, snapped.y, snapped.z],
             snapped: snapped.snapped, onGeometry: false };
  }

  /** Où le pointeur tombe sur le plan de glisser (repli : face à l'écran). */
  function dragTarget(event) {
    setRay(event);
    const { origin, direction } = raycaster.ray;
    const hitPlane = (normal) => rayPlane([origin.x, origin.y, origin.z],
      [direction.x, direction.y, direction.z], { normal, point: drag.origin });
    return hitPlane(drag.normal)
      ?? hitPlane(camera.getWorldDirection(new THREE.Vector3()).toArray());
  }

  const round = (v) => Math.round(v * 1000) / 1000;

  function beginDrag(hit, event) {
    const view = camera.getWorldDirection(new THREE.Vector3()).toArray();
    // Un point glisse dans le plan de clic (Tab le change) ; une poignée
    // ou un pôle, face à l'écran.
    const normal = hit.kind === "point" ? clickPlane(tool.values.plane).normal : view;
    drag = { ...hit, normal, origin: hit.at, moved: false,
             screen: { x: event.clientX, y: event.clientY } };
    if (hit.kind !== "pole") tool.values.selected = hit.index;
    ctx.controls.enabled = false;
  }

  function moveDrag(event) {
    if (!drag.moved && Math.hypot(event.clientX - drag.screen.x,
      event.clientY - drag.screen.y) < 4) return;
    drag.moved = true;
    const target = dragTarget(event);
    if (!target) return;
    const v = tool.values;
    if (drag.kind === "point") {
      const next = (v.points ?? []).map((p) => [...p]);
      next[drag.index] = target.map(round);
      const links = [...(v.links ?? [])];
      if (links[drag.index]) links[drag.index] = null; // le point quitte la pièce
      panel.assign({ points: next, links, selected: drag.index });
    } else if (drag.kind === "tip") {
      const next = dragTip(v.points, !!v.closed, tangents(), drag.index, drag.side,
        target, { alone: event.altKey });
      panel.assign({ tangents: next, selected: drag.index });
    } else if (drag.kind === "pole") {
      movePole(drag.index, target);
    }
  }

  /** Tirer un pôle : le moteur rend les points et poignées (une requête à
   *  la fois ; la dernière position gagne). */
  async function movePole(index, target) {
    if (poleBusy) { poleNext = { index, target }; return; }
    poleBusy = true;
    try {
      const result = await call("curve_move_pole", { points: points(), closed: closed(),
        tangents: tangents(), index, point: target });
      if (tool) {
        panel.assign({ points: result.points.map((p) => p.map(round)), tangents: result.tangents });
        tool.poles = result.poles;
        tool.polesKey = curveKey();
        drawPreview();
      }
    } catch (error) {
      say(error.message ?? String(error), true);
    } finally {
      poleBusy = false;
      const next = poleNext;
      poleNext = null;
      // La dernière position compte, même si le bouton est déjà relâché.
      if (next && tool) movePole(next.index, next.target);
    }
  }

  function endDrag() {
    const wasMoved = drag.moved;
    drag = null;
    ctx.controls.enabled = true;
    panel.restore({}); // la liste des points suit
    return wasMoved;
  }

  // Avant la navigation : un point, une poignée ou un pôle prend le geste.
  function onCaptureDown(event) {
    if (!tool || event.button !== 0 || event.target !== renderer.domElement) return;
    const hit = hitAt(event);
    if (!hit) return;
    event.stopImmediatePropagation();
    event.preventDefault();
    beginDrag(hit, event);
    drawPreview();
  }

  function onCaptureMove(event) {
    if (!tool || !drag) return;
    event.stopImmediatePropagation();
    moveDrag(event);
  }

  function onCaptureUp(event) {
    if (!tool || !drag || event.button !== 0) return;
    event.stopImmediatePropagation();
    const hit = { kind: drag.kind, index: drag.index };
    const moved = endDrag();
    if (!moved && hit.kind === "point") {
      // Un clic sur un point le choisit (un second le relâche).
      const same = tool.picked === hit.index;
      tool.picked = same ? null : hit.index;
      panel.restore({ selected: same ? null : hit.index });
      say(same ? t("Point relâché.")
        : t("Point P{n} : tirez-le, ou tirez les bouts de sa poignée (Alt : un seul côté).",
          { n: hit.index + 1 }));
    } else if (moved && hit.kind !== "pole") {
      tool.picked = hit.index;
    }
  }

  function onDown(event) {
    if (!tool || event.button !== 0) return;
    press = { x: event.clientX, y: event.clientY };
  }

  function onUp(event) {
    if (!tool || !press || event.button !== 0) return;
    const travel = Math.hypot(event.clientX - press.x, event.clientY - press.y);
    press = null;
    if (travel > 5) return; // orbite, pas un clic
    if (event.ctrlKey || event.metaKey) {
      insertAt(event);
      return;
    }
    if (tool.values.selected != null) {
      // Clic ailleurs : on relâche d'abord le point choisi.
      tool.picked = null;
      panel.restore({ selected: null });
      return;
    }
    const aimed = aimedPoint(event);
    if (!aimed) {
      say(t("Spline 3D : le plan de clic est vu par la tranche — Tab pour en changer"), true);
      return;
    }
    const list = points();
    let axis = null;
    if (event.shiftKey && list.length) {
      // Maj : le segment suit l'axe X, Y ou Z où il avance le plus.
      const locked = alongAxis(list[list.length - 1], aimed.point);
      aimed.point = locked.point;
      axis = locked.axis;
    }
    const [x, y, z] = aimed.point.map(round);
    panel.notifyPick("point3d", { kind: "point3d", x, y, z });
    if (aimed.onGeometry && aimed.snapped && !axis) {
      // Clic aimanté sur un sommet ou un centre : le point s'y lie et
      // suivra la pièce (le moteur retrouve l'élément).
      const links = [...(tool.values.links ?? [])];
      while (links.length < list.length) links.push(null);
      links[list.length] = true;
      panel.restore({ links });
    }
    if (axis) {
      // Maj : l'axe devient une règle du segment, gardée à la réédition.
      const rules = [...(tool.values.rules ?? [])];
      while (rules.length < list.length) rules.push({ axis: "", length: null });
      rules[list.length - 1] = { ...rules[list.length - 1], axis };
      panel.restore({ rules });
    }
    if (axis) {
      say(t("Point le long de l'axe {a}.", { a: axis }));
      return;
    }
    say(aimed.snapped === "center" ? t("Point au centre du cercle.")
      : aimed.snapped === "vertex" ? t("Point sur le sommet.")
        : aimed.onGeometry ? t("Point sur la géométrie.")
          : t("Point sur le {p}.", { p: t(PLANE_LABELS[tool.values.plane]) }));
  }

  /** Ctrl+clic sur la courbe : un point de plus, la forme ne bouge pas. */
  function insertAt(event) {
    const on = curveHit(event);
    if (!on) {
      say(t("Ctrl+clic sur la courbe pour y ajouter un point"), true);
      return;
    }
    const v = tool.values;
    const n = points().length;
    let result;
    if (isSpline() && n >= 2) {
      const near = nearestOnCurve(v.points, !!v.closed, tangents(), on);
      result = insertPoint(v.points, !!v.closed, tangents(), near.span, near.s);
    } else {
      // Polyligne : le point se pose sur le segment le plus proche.
      let best = { i: 0, d: Infinity };
      const count = v.closed ? n : n - 1;
      for (let i = 0; i < count; i++) {
        const a = v.points[i];
        const b = v.points[(i + 1) % n];
        const d = pixels(a.map((c, k) => (c + b[k]) / 2), event);
        if (d < best.d) best = { i, d };
      }
      const pts = v.points.map((p) => [...p]);
      pts.splice(best.i + 1, 0, on);
      const tans = tangents();
      tans.splice(best.i + 1, 0, null);
      result = { points: pts, tangents: tans, index: best.i + 1 };
    }
    const at = result.index;
    const links = [...(v.links ?? [])];
    while (links.length < n) links.push(null);
    links.splice(at, 0, null);
    const rules = [...(v.rules ?? [])];
    if (rules.length >= at) {
      // Le segment coupé : ses deux moitiés gardent l'axe, pas la cote.
      const cut = rules[at - 1] ?? { axis: "", length: null };
      const half = { axis: cut.axis ?? "", length: null };
      rules.splice(at - 1, 1, half, { ...half });
    }
    tool.picked = at;
    panel.restore({ points: result.points.map((p) => p.map(round)),
      tangents: result.tangents, links, rules, selected: at });
    say(t("Point P{n} ajouté.", { n: at + 1 }));
  }

  function removeSelected() {
    const v = tool.values;
    const sel = v.selected;
    if (sel == null) return false;
    if (points().length <= 2) {
      say(t("Une courbe garde au moins deux points."), true);
      return true;
    }
    const { points: pts, tangents: tans } = removePoint(v.points, tangents(), sel);
    const links = [...(v.links ?? [])];
    links.splice(sel, 1);
    const rules = [...(v.rules ?? [])];
    if (rules.length) rules.splice(Math.min(sel, rules.length - 1), 1);
    tool.picked = null;
    panel.restore({ points: pts, tangents: tans, links, rules, selected: null });
    say(t("Point P{n} retiré.", { n: sel + 1 }));
    return true;
  }

  function onMove(event) {
    if (!tool || drag) return;
    const over = hitAt(event);
    renderer.domElement.style.cursor = over ? "grab"
      : (event.ctrlKey && curveHit(event)) ? "copy" : "";
    if (!points().length || tool.values.selected != null) {
      if (rubber) { rubber = null; drawPreview(); }
      return;
    }
    rubber = aimedPoint(event)?.point ?? null;
    if (rubber && event.shiftKey) {
      const list = points();
      rubber = alongAxis(list[list.length - 1], rubber).point;
    }
    drawPreview();
  }

  function onKey(event) {
    if (!tool) return;
    // Dans le panneau (champs, boutons), les touches gardent leur rôle.
    if (event.target?.closest?.("aside, input, select, textarea, button")) {
      return;
    }
    if (event.key === "Delete" && removeSelected()) {
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    if (event.key !== "Tab") return;
    event.preventDefault();
    const plane = nextPlane(tool.values.plane);
    panel.restore({ plane });
    say(t("Plan de clic : {p}", { p: t(PLANE_LABELS[plane]) }));
  }

  function stop() {
    if (!tool) return;
    if (drag) {
      drag = null;
      ctx.controls.enabled = true;
    }
    tool = null;
    rubber = null;
    clearTimeout(polesTimer);
    clearPreview();
    preview.removeFromParent();
    renderer.domElement.style.cursor = "";
    renderer.domElement.removeEventListener("pointerdown", onDown);
    renderer.domElement.removeEventListener("pointerup", onUp);
    renderer.domElement.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerdown", onCaptureDown, true);
    window.removeEventListener("pointermove", onCaptureMove, true);
    window.removeEventListener("pointerup", onCaptureUp, true);
    document.removeEventListener("keydown", onKey, true);
  }

  /** Libère la poignée du point choisi (ou toutes, sans point choisi). */
  function resetHandles(values) {
    const sel = values.selected;
    const next = cleanTangents(values.tangents, points().length);
    if (sel != null) next[sel] = null;
    else next.fill(null);
    panel.restore({ tangents: next });
    say(sel != null ? t("Poignée du point P{n} libérée.", { n: sel + 1 })
      : t("Toutes les poignées sont libérées."));
  }

  function simplifyCurve(values) {
    const before = points().length;
    const tol = Math.max(Number(String(values.tolerance ?? "0.1").replace(",", ".")) || 0.1, 1e-4);
    const keep = (values.links ?? []).flatMap((l, i) => (l ? [i] : []));
    let result;
    try {
      result = simplify(values.points, !!values.closed, tangents(), tol, keep);
    } catch (error) {
      say(error.message, true);
      return;
    }
    const removed = before - result.points.length;
    if (!removed) {
      say(t("Simplifier : aucun point ne part sans dépasser {tol} mm.", { tol }));
      return;
    }
    // Points restants : on retrouve leurs liens par position.
    const key = (p) => p.join(",");
    const linkOf = new Map(values.points.map((p, i) => [key(p), (values.links ?? [])[i] ?? null]));
    tool.picked = null;
    panel.restore({ points: result.points, tangents: result.tangents,
      links: result.points.map((p) => linkOf.get(key(p)) ?? null), rules: [], selected: null });
    say(t("Simplifier : {n} point(s) en moins (écart ≤ {tol} mm).", { n: removed, tol }));
  }

  function relaxCurve(values) {
    const keep = (values.links ?? []).flatMap((l, i) => (l ? [i] : []));
    const next = relax(values.points, !!values.closed, 0.5, keep).map((p) => p.map(round));
    panel.restore({ points: next });
    say(t("Courbe lissée (cliquez encore pour lisser davantage)."));
  }

  /** Ouvre l'outil ; `curve` (entrée d'arbre avec `curve`) le réédite. */
  function open(curve = null) {
    stop();
    const spec = curve?.curve;
    tool = { curve, sync: null, poles: null, polesKey: null, picked: null, values: {
      points: spec?.points ?? [], plane: "XY", rules: spec?.rules ?? [],
      links: spec?.links ?? [], tangents: spec?.tangents ?? [],
      spline: spec?.spline ?? true, closed: spec?.closed ?? false,
      selected: null, handleDriven: false, handleIn: 100, handleOut: 100,
      comb: false, combScale: 100, polygon: false, tolerance: 0.1 } };
    scene.add(preview);
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);
    renderer.domElement.addEventListener("pointermove", onMove);
    window.addEventListener("pointerdown", onCaptureDown, true);
    window.addEventListener("pointermove", onCaptureMove, true);
    window.addEventListener("pointerup", onCaptureUp, true);
    document.addEventListener("keydown", onKey, true);
    const chosen = (v) => v.selected != null && v.spline && (v.points?.length ?? 0) >= 2;
    const smooth = (v) => !!v.spline;
    panel.open({
      icon: "spline3d",
      title: curve ? curve.label : t("Spline 3D"),
      autoFocus: false,
      values: tool.values,
      groups: [
        { label: t("Points"),
          rows: [
            { type: "points", key: "points", linksKey: "links",
              tangentsKey: "tangents", selectKey: "selected",
              value: tool.values.points },
            // La note porte aussi la valeur « links » (liste parallèle aux
            // points) : le panneau la garde et la rend à l'OK.
            { type: "note", readonly: true, key: "links",
              value: tool.values.links,
              text: t("⛓ : point lié à un sommet ou un centre de la pièce") },
          ] },
        { label: t("Poignée du point choisi"),
          rows: [
            { type: "check", key: "handleDriven", label: t("Tangente pilotée"),
              showIf: chosen },
            { type: "number", key: "handleIn", label: t("Longueur avant"),
              unit: "%", min: 1, step: 5, showIf: chosen },
            { type: "number", key: "handleOut", label: t("Longueur après"),
              unit: "%", min: 1, step: 5, showIf: chosen },
            { type: "buttons", showIf: (v) => v.selected != null,
              items: [
                { label: t("Libérer la poignée"), onClick: resetHandles },
                { label: t("Retirer le point"), onClick: () => removeSelected() },
              ] },
            { type: "note", readonly: true, showIf: (v) => v.selected == null,
              text: t("Cliquez un point de la courbe (ou son nom dans la liste) pour le choisir.") },
          ] },
        { label: t("Segments"),
          rows: [{ type: "segments", key: "rules", pointsKey: "points",
                   value: tool.values.rules }] },
        { label: t("Courbe"),
          rows: [
            { type: "check", key: "comb", label: t("Peigne de courbure"), showIf: smooth },
            { type: "number", key: "combScale", label: t("Échelle du peigne"), unit: "%",
              min: 1, step: 10, showIf: (v) => v.spline && v.comb },
            { type: "check", key: "polygon", label: t("Polygone de contrôle"), showIf: smooth },
            { type: "number", key: "tolerance", label: t("Tolérance"), unit: "mm",
              min: 0.0001, step: 0.05, showIf: smooth },
            { type: "buttons", showIf: smooth,
              items: [
                { label: t("Simplifier"),
                  title: "Retire les points superflus sans écarter la courbe de plus que la tolérance",
                  onClick: simplifyCurve },
                { label: t("Lisser"), title: "Rapproche chaque point intérieur de ses voisins",
                  onClick: relaxCurve },
                { label: t("Libérer toutes les poignées"),
                  onClick: (v) => resetHandles({ ...v, selected: null }) },
              ] },
          ] },
        { label: t("Options"),
          rows: [
            { type: "select", key: "plane", label: t("Plan de clic"),
              value: "XY",
              options: CLICK_PLANES.map((k) => [k, PLANE_LABELS[k]]) },
            { type: "check", key: "spline", label: t("Courbe lisse (spline)"),
              value: tool.values.spline },
            { type: "check", key: "closed", label: t("Fermée"),
              value: tool.values.closed },
          ] },
      ],
      note: t("Cliquez sur la pièce, une surface ou une courbe — sommets et "
        + "centres aimantent — ou dans le vide : le point se pose sur le "
        + "plan de clic, qui passe par le dernier point. Tab change de plan, "
        + "Maj garde le segment parallèle à un axe. Tirez un point pour le "
        + "déplacer ; cliquez-le pour sa poignée de tangente (Alt : un seul "
        + "côté). Ctrl+clic sur la courbe ajoute un point, Suppr retire le "
        + "point choisi."),
      hint: (v) => {
        const problem = curveProblem(v.points, v.closed);
        return problem ? { text: problem, tone: "guide" } : null;
      },
      onChange: (v) => {
        if (!tool) return;
        // Les règles recalent les points : la liste montre le résultat.
        const solved = solveRules(v.points ?? [], v.rules,
          linkedIndices(v.links));
        if (!samePoints(solved, v.points ?? [])) {
          panel.restore({ points: solved });
          return;
        }
        const n = (v.points ?? []).length;
        if (v.selected != null && v.selected >= n) {
          panel.restore({ selected: null });
          return;
        }
        // Champs de la poignée : une saisie change la tangente ; une
        // tangente changée (glisser, autre point) remet les champs.
        const state = handleFields(v);
        if (state && tool.sync && tool.sync.selected === v.selected && !drag) {
          const next = tangentsFromFields(v, tool.sync);
          if (next) {
            tool.sync = { selected: v.selected, ...handleFields({ ...v, tangents: next }) };
            panel.assign({ tangents: next, handleDriven: tool.sync.handleDriven });
            return;
          }
        }
        if (state && HANDLE_KEYS.some((k) => String(v[k]) !== String(state[k]))) {
          tool.sync = { selected: v.selected, ...state };
          if (drag) panel.assign(state);
          else panel.restore(state);
          return;
        }
        tool.sync = state ? { selected: v.selected, ...state } : null;
        tool.values = v;
        drawPreview();
        requestPoles();
      },
      onClose: () => stop(),
      onApply: (v) => {
        const problem = curveProblem(v.points, v.closed);
        if (problem) {
          // Le panneau est déjà fermé : on le rouvre tel quel.
          open(curve);
          panel.restore(v);
          say(t(problem), true);
          return;
        }
        const pts = solveRules(v.points, v.rules, linkedIndices(v.links));
        const params = { points: pts,
                         rules: v.rules ?? [], links: v.links ?? [],
                         tangents: v.spline ? cleanTangents(v.tangents, pts.length) : [],
                         spline: !!v.spline, closed: !!v.closed };
        refresh(curve
          ? call("edit_curve3d", { curve: curve.name, ...params })
          : call("add_curve3d", params));
      },
    });
  }

  return {
    open,
    get active() { return tool !== null; },
    /** Débogage et tests de fumée : la courbe et ses points à l'écran. */
    screen() {
      if (!tool) return null;
      const toScreen = (p) => {
        const s = project({ x: p[0], y: p[1], z: p[2] });
        return [Math.round(s.x), Math.round(s.y)];
      };
      let path = [];
      try {
        path = sample(points(), { closed: closed(), tangents: tangents(), spline: isSpline() });
      } catch { /* rien */ }
      return { points: points().map(toScreen), path: path.map(toScreen),
               selected: tool.values.selected };
    },
  };
}
