// Esquisse 3D : définition et solveur — le jumeau de
// engine/sketch3dmath.py (mêmes règles, mêmes nombres) : l'aperçu pendant
// un glisser est ce que le moteur enregistrera.
//
// Points partagés, entités (ligne { a, b }, spline { pts, closed,
// tangents }, point { p }), cotes (length, distance, angle) et relations
// (axis : ligne le long de X, Y ou Z). Le solveur bouge le moins possible
// les points (pas de Gauss-Newton de norme minimale).

export const AXES = "XYZ";
const TOL = 1e-9;
const TOL_OK = 1e-6;

const num = (value) => {
  const out = Number(value);
  return Number.isFinite(out) ? out : null;
};
const index = (value, count) => {
  const i = Number(value);
  return Number.isInteger(i) && i >= 0 && i < count ? i : null;
};

/** Définition nettoyée (ce qui ne tient pas tombe). */
export function cleanSpec(spec) {
  const src = spec && typeof spec === "object" ? spec : {};
  const points = (src.points ?? []).map((p) => {
    const xyz = [...(p ?? [])].slice(0, 3).map((v) => num(v) ?? 0);
    while (xyz.length < 3) xyz.push(0);
    return xyz;
  });
  const n = points.length;
  const rawLinks = src.links ?? [];
  const links = points.map((_, i) => {
    const l = rawLinks[i];
    return l === true || (l && typeof l === "object") ? l : null;
  });
  const entities = [];
  for (const e of src.entities ?? []) {
    if (!e || typeof e !== "object") continue;
    const construction = !!e.construction;
    if (e.type === "line") {
      const a = index(e.a, n);
      const b = index(e.b, n);
      if (a !== null && b !== null && a !== b) entities.push({ type: "line", a, b, construction });
    } else if (e.type === "spline") {
      const pts = (e.pts ?? []).map((i) => index(i, n));
      if (pts.length >= 2 && !pts.includes(null)) {
        const tangents = (e.tangents ?? []).slice(0, pts.length)
          .map((tg) => (tg && typeof tg === "object" ? tg : null));
        while (tangents.length < pts.length) tangents.push(null);
        entities.push({ type: "spline", pts, closed: !!e.closed, tangents, construction });
      }
    } else if (e.type === "point") {
      const p = index(e.p, n);
      if (p !== null) entities.push({ type: "point", p });
    }
  }
  const m = entities.length;
  const isLine = (i) => i !== null && entities[i]?.type === "line";
  const dims = [];
  for (const d of src.dims ?? []) {
    if (!d || typeof d !== "object") continue;
    const value = num(d.value);
    if (value === null) continue;
    if (d.type === "length") {
      const e = index(d.entity, m);
      if (isLine(e) && value > 0) dims.push({ type: "length", entity: e, value });
    } else if (d.type === "distance") {
      const p1 = index(d.p1, n);
      const p2 = index(d.p2, n);
      if (p1 !== null && p2 !== null && p1 !== p2 && value > 0) {
        dims.push({ type: "distance", p1, p2, value });
      }
    } else if (d.type === "angle") {
      const e1 = index(d.e1, m);
      const e2 = index(d.e2, m);
      if (isLine(e1) && isLine(e2) && e1 !== e2 && value >= 0 && value <= 180) {
        dims.push({ type: "angle", e1, e2, value });
      }
    }
  }
  const relations = [];
  for (const r of src.relations ?? []) {
    if (r?.type !== "axis") continue;
    const e = index(r.entity, m);
    if (isLine(e) && ["X", "Y", "Z"].includes(r.axis)) {
      relations.push({ type: "axis", entity: e, axis: r.axis });
    }
  }
  return { points, links, entities, dims, relations };
}

const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const norm = (a) => Math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2]);

function angleOf(spec, points, e1, e2) {
  const l1 = spec.entities[e1];
  const l2 = spec.entities[e2];
  const ends1 = [l1.a, l1.b];
  const ends2 = [l2.a, l2.b];
  const shared = ends1.filter((p) => ends2.includes(p));
  let u;
  let v;
  if (shared.length) {
    const c = shared[0];
    const o1 = ends1[0] === c ? ends1[1] : ends1[0];
    const o2 = ends2[0] === c ? ends2[1] : ends2[0];
    u = sub(points[o1], points[c]);
    v = sub(points[o2], points[c]);
  } else {
    u = sub(points[l1.b], points[l1.a]);
    v = sub(points[l2.b], points[l2.a]);
  }
  const cross = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]];
  const dot = u[0] * v[0] + u[1] * v[1] + u[2] * v[2];
  return { angle: Math.atan2(norm(cross), dot), scale: (norm(u) + norm(v)) / 2 };
}

/** Valeur actuelle d'une cote (mm ou degrés). */
export function measure(spec, points, dim) {
  if (dim.type === "length") {
    const line = spec.entities[dim.entity];
    return norm(sub(points[line.b], points[line.a]));
  }
  if (dim.type === "distance") return norm(sub(points[dim.p2], points[dim.p1]));
  return (angleOf(spec, points, dim.e1, dim.e2).angle * 180) / Math.PI;
}

export function residuals(spec, points) {
  const out = [];
  for (const rel of spec.relations) {
    const line = spec.entities[rel.entity];
    const a = points[line.a];
    const b = points[line.b];
    const k = AXES.indexOf(rel.axis);
    for (let j = 0; j < 3; j++) if (j !== k) out.push(b[j] - a[j]);
  }
  for (const dim of spec.dims) {
    if (dim.type === "angle") {
      const { angle, scale } = angleOf(spec, points, dim.e1, dim.e2);
      out.push((angle - (dim.value * Math.PI) / 180) * Math.max(scale, 1));
    } else {
      out.push(measure(spec, points, dim) - dim.value);
    }
  }
  return out;
}

export function constrainedPoints(spec) {
  const used = new Set();
  const ents = spec.entities;
  for (const rel of spec.relations) {
    used.add(ents[rel.entity].a);
    used.add(ents[rel.entity].b);
  }
  for (const dim of spec.dims) {
    if (dim.type === "length") {
      used.add(ents[dim.entity].a);
      used.add(ents[dim.entity].b);
    } else if (dim.type === "distance") {
      used.add(dim.p1);
      used.add(dim.p2);
    } else {
      for (const e of [dim.e1, dim.e2]) {
        used.add(ents[e].a);
        used.add(ents[e].b);
      }
    }
  }
  return [...used].sort((x, y) => x - y);
}

function solveLinear(matrix, rhs) {
  const size = matrix.length;
  const a = matrix.map((row, i) => [...row, rhs[i]]);
  for (let col = 0; col < size; col++) {
    let pivot = col;
    for (let r = col + 1; r < size; r++) if (Math.abs(a[r][col]) > Math.abs(a[pivot][col])) pivot = r;
    if (Math.abs(a[pivot][col]) < 1e-300) throw new Error("système singulier");
    [a[col], a[pivot]] = [a[pivot], a[col]];
    for (let row = col + 1; row < size; row++) {
      const factor = a[row][col] / a[col][col];
      if (!factor) continue;
      for (let k = col; k <= size; k++) a[row][k] -= factor * a[col][k];
    }
  }
  const out = new Array(size).fill(0);
  for (let row = size - 1; row >= 0; row--) {
    let acc = a[row][size];
    for (let k = row + 1; k < size; k++) acc -= a[row][k] * out[k];
    out[row] = acc / a[row][row];
  }
  return out;
}

/** Positions qui tiennent cotes et relations ; `fixed` : points qui ne
 *  bougent pas (en plus des points liés). Rend { points, ok, residual }. */
export function solve(spec, fixed = [], maxIter = 60) {
  const s = cleanSpec(spec);
  let points = s.points.map((p) => [...p]);
  const locked = new Set(fixed.map(Number));
  s.links.forEach((l, i) => { if (l) locked.add(i); });
  const free = constrainedPoints(s).filter((i) => !locked.has(i));
  const variables = free.flatMap((i) => [[i, 0], [i, 1], [i, 2]]);
  const cost = (r) => r.reduce((acc, v) => acc + v * v, 0);
  let r = residuals(s, points);
  for (let iter = 0; iter < maxIter; iter++) {
    if (!r.length || Math.max(...r.map(Math.abs)) < TOL || !variables.length) break;
    const jac = variables.map(([i, k]) => {
      const keep = points[i][k];
      const h = 1e-7 * Math.max(1, Math.abs(keep));
      points[i][k] = keep + h;
      const shifted = residuals(s, points);
      points[i][k] = keep;
      return shifted.map((v, j) => (v - r[j]) / h);
    });
    const m = r.length;
    const normal = Array.from({ length: m }, (_, a) =>
      Array.from({ length: m }, (__, b) => jac.reduce((acc, col) => acc + col[a] * col[b], 0)));
    let peak = 0;
    for (let a = 0; a < m; a++) peak = Math.max(peak, normal[a][a]);
    const mu = 1e-12 * (1 + peak);
    for (let a = 0; a < m; a++) normal[a][a] += mu;
    let y;
    try { y = solveLinear(normal, r); } catch { break; }
    const step = jac.map((col) => -col.reduce((acc, v, a) => acc + v * y[a], 0));
    const base = cost(r);
    let t = 1;
    let accepted = false;
    while (t > 1e-4) {
      const trial = points.map((p) => [...p]);
      variables.forEach(([i, k], j) => { trial[i][k] += t * step[j]; });
      const rTrial = residuals(s, trial);
      if (cost(rTrial) < base) {
        points = trial;
        r = rTrial;
        accepted = true;
        break;
      }
      t /= 2;
    }
    if (!accepted) break;
  }
  const worst = r.reduce((acc, v) => Math.max(acc, Math.abs(v)), 0);
  return { points, ok: worst < TOL_OK, residual: worst };
}

/** Axe (X, Y, Z) le plus proche de la direction `d`, s'il est à moins de
 *  `degrees` ; sinon null. */
export function inferAxis(d, degrees = 6) {
  const size = norm(d);
  if (size < 1e-9) return null;
  let best = null;
  for (let k = 0; k < 3; k++) {
    const angle = (Math.acos(Math.min(1, Math.abs(d[k]) / size)) * 180) / Math.PI;
    if (angle <= degrees && (!best || angle < best.angle)) best = { axis: AXES[k], angle };
  }
  return best?.axis ?? null;
}

/** `point` ramené sur l'axe `axis` qui passe par `from`. */
export function onAxis(from, point, axis) {
  const k = AXES.indexOf(axis);
  return from.map((v, j) => (j === k ? point[j] : v));
}

/** Les relations, cotes et entités qui touchent un point ou une entité
 *  retirés, la définition réindexée. `drop` : { points?: [], entities?:
 *  [], dims?: [], relations?: [] }. Les points qui ne servent plus à
 *  aucune entité partent aussi. */
export function removeItems(spec, drop) {
  const s = cleanSpec(spec);
  const goneDims = new Set(drop.dims ?? []);
  const goneRels = new Set(drop.relations ?? []);
  const gonePoints = new Set(drop.points ?? []);
  const goneEnts = new Set(drop.entities ?? []);
  s.entities.forEach((e, i) => {
    const pts = e.type === "line" ? [e.a, e.b] : e.type === "spline" ? e.pts : [e.p];
    if (pts.some((p) => gonePoints.has(p))) {
      if (e.type === "spline" && e.pts.filter((p) => !gonePoints.has(p)).length >= 2) return;
      goneEnts.add(i);
    }
  });
  // Splines : un point retiré sort de la liste.
  const entities0 = s.entities.map((e) => (e.type === "spline"
    ? { ...e, pts: e.pts.filter((p) => !gonePoints.has(p)),
        tangents: e.tangents.filter((_, k) => !gonePoints.has(e.pts[k])) }
    : e));
  const keptEnts = entities0.map((e, i) => (goneEnts.has(i) ? null : e));
  const used = new Set();
  keptEnts.forEach((e) => {
    if (!e) return;
    (e.type === "line" ? [e.a, e.b] : e.type === "spline" ? e.pts : [e.p]).forEach((p) => used.add(p));
  });
  const pointMap = new Map();
  const points = [];
  const links = [];
  s.points.forEach((p, i) => {
    if (!used.has(i)) return;
    pointMap.set(i, points.length);
    points.push(p);
    links.push(s.links[i]);
  });
  const entMap = new Map();
  const entities = [];
  keptEnts.forEach((e, i) => {
    if (!e) return;
    entMap.set(i, entities.length);
    if (e.type === "line") entities.push({ ...e, a: pointMap.get(e.a), b: pointMap.get(e.b) });
    else if (e.type === "spline") entities.push({ ...e, pts: e.pts.map((p) => pointMap.get(p)) });
    else entities.push({ ...e, p: pointMap.get(e.p) });
  });
  const dims = [];
  s.dims.forEach((d, i) => {
    if (goneDims.has(i)) return;
    if (d.type === "length") {
      if (entMap.has(d.entity)) dims.push({ ...d, entity: entMap.get(d.entity) });
    } else if (d.type === "distance") {
      if (pointMap.has(d.p1) && pointMap.has(d.p2)) {
        dims.push({ ...d, p1: pointMap.get(d.p1), p2: pointMap.get(d.p2) });
      }
    } else if (entMap.has(d.e1) && entMap.has(d.e2)) {
      dims.push({ ...d, e1: entMap.get(d.e1), e2: entMap.get(d.e2) });
    }
  });
  const relations = [];
  s.relations.forEach((r, i) => {
    if (!goneRels.has(i) && entMap.has(r.entity)) relations.push({ ...r, entity: entMap.get(r.entity) });
  });
  return { points, links, entities, dims, relations };
}
