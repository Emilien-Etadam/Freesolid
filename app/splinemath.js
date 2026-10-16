// Spline par points de passage, avec poignées de tangente — le jumeau de
// engine/splinemath.py : même définition, mêmes nombres, pour que
// l'aperçu pendant un glisser soit la courbe que le moteur construira.
//
// Entre deux points, un arc cubique (forme d'Hermite). La pente en un
// point est libre (courbe C2 ; aux bouts, règle « pas de nœud ») ou
// pilotée : { dir, in, out } — direction unitaire, longueurs d'entrée et
// de sortie (paramètre = longueur de corde : 1 est la vitesse naturelle).
// En plus du moteur : échantillonnage, peigne de courbure, insertion d'un
// point sans changer la forme, simplification, lissage.

const TOL = 1e-9;

const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const mul = (a, k) => [a[0] * k, a[1] * k, a[2] * k];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const norm = (a) => Math.hypot(a[0], a[1], a[2]);
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
                         a[0] * b[1] - a[1] * b[0]];

/** Points en triplets (z = 0 pour un point 2D). */
export function asPoints(points) {
  return (points ?? []).map((p) => {
    const v = [...p].slice(0, 3).map(Number);
    while (v.length < 3) v.push(0);
    return v;
  });
}

/** Une entrée par point : null (libre) ou { dir, in, out } nettoyée. */
export function cleanTangents(tangents, count) {
  const source = tangents ?? [];
  return Array.from({ length: count }, (_, i) => {
    const spec = source[i];
    if (!spec || typeof spec !== "object" || !spec.dir) return null;
    const dir = asPoints([spec.dir])[0];
    const size = norm(dir);
    const lin = Number(spec.in ?? 1);
    const lout = Number(spec.out ?? 1);
    if (!(size > TOL) || !(lin > 0) || !(lout > 0)) return null;
    return { dir: mul(dir, 1 / size), in: lin, out: lout };
  });
}

export function chords(points, closed) {
  const n = points.length;
  const count = closed ? n : n - 1;
  return Array.from({ length: Math.max(count, 0) },
    (_, i) => norm(sub(points[(i + 1) % n], points[i])));
}

function solveDense(matrix, rhs) {
  const size = matrix.length;
  const a = matrix.map((row) => [...row]);
  const b = rhs.map((r) => [...r]);
  for (let col = 0; col < size; col++) {
    let pivot = col;
    for (let r = col + 1; r < size; r++) {
      if (Math.abs(a[r][col]) > Math.abs(a[pivot][col])) pivot = r;
    }
    if (Math.abs(a[pivot][col]) < 1e-14) throw new Error("système singulier");
    [a[col], a[pivot]] = [a[pivot], a[col]];
    [b[col], b[pivot]] = [b[pivot], b[col]];
    for (let row = col + 1; row < size; row++) {
      const factor = a[row][col] / a[col][col];
      if (factor === 0) continue;
      for (let k = col; k < size; k++) a[row][k] -= factor * a[col][k];
      b[row] = sub(b[row], mul(b[col], factor));
    }
  }
  const out = new Array(size);
  for (let row = size - 1; row >= 0; row--) {
    let acc = b[row];
    for (let k = row + 1; k < size; k++) acc = sub(acc, mul(out[k], a[row][k]));
    out[row] = mul(acc, 1 / a[row][row]);
  }
  return out;
}

/** Pentes { mIn, mOut } en chaque point (voir engine/splinemath.solve). */
export function solve(points, closed = false, tangents = null) {
  const pts = asPoints(points);
  const n = pts.length;
  const tans = cleanTangents(tangents, n);
  if (n < 2) return { mIn: [], mOut: [] };
  const h = chords(pts, closed);
  if (h.some((len) => len < TOL)) throw new Error("deux points consécutifs sont confondus");
  const spans = h.length;
  const nxt = (i) => (i + 1) % n;
  const prv = (i) => (i - 1 + n) % n;
  const slope = h.map((len, i) => mul(sub(pts[nxt(i)], pts[i]), 1 / len));
  const fixedIn = tans.map((s) => (s ? mul(s.dir, s.in) : null));
  const fixedOut = tans.map((s) => (s ? mul(s.dir, s.out) : null));
  const free = [];
  tans.forEach((s, i) => { if (!s) free.push(i); });
  const index = new Map(free.map((p, k) => [p, k]));
  const mIn = [...fixedIn];
  const mOut = [...fixedOut];
  if (free.length) {
    const size = free.length;
    const matrix = Array.from({ length: size }, () => new Array(size).fill(0));
    const rhs = Array.from({ length: size }, () => [0, 0, 0]);
    const term = (row, point, coeff, side) => {
      if (index.has(point)) matrix[row][index.get(point)] += coeff;
      else rhs[row] = sub(rhs[row], mul(side === "in" ? fixedIn[point] : fixedOut[point], coeff));
    };
    const third = (row, span, sign) => {
      const k = sign / (h[span] * h[span]);
      term(row, span, k, "out");
      term(row, nxt(span), k, "in");
      rhs[row] = add(rhs[row], mul(slope[span], 2 * k));
    };
    free.forEach((i, row) => {
      if (closed || (i > 0 && i < n - 1)) {
        const a = prv(i);
        const b = i;
        term(row, a, h[b], "out");
        matrix[row][row] += 2 * (h[a] + h[b]);
        term(row, nxt(i), h[a], "in");
        rhs[row] = add(rhs[row], mul(add(mul(slope[a], h[b]), mul(slope[b], h[a])), 3));
      } else if (i === 0) {
        if (n >= 4 && index.has(1)) {
          third(row, 0, 1);
          third(row, 1, -1);
        } else if (n === 3 && index.has(1)) {
          third(row, 0, 1);
        } else {
          matrix[row][row] += 2;
          term(row, 1, 1, "in");
          rhs[row] = add(rhs[row], mul(slope[0], 3));
        }
      } else {
        const last = spans - 1;
        if (n >= 4 && index.has(n - 2)) {
          third(row, last, 1);
          third(row, last - 1, -1);
        } else if (n === 3 && index.has(1)) {
          third(row, last, 1);
        } else {
          term(row, n - 2, 1, "out");
          matrix[row][row] += 2;
          rhs[row] = add(rhs[row], mul(slope[last], 3));
        }
      }
    });
    const values = solveDense(matrix, rhs);
    for (const i of free) {
      mIn[i] = values[index.get(i)];
      mOut[i] = values[index.get(i)];
    }
  }
  return { mIn, mOut };
}

/** Pôles de Bézier de chaque arc : [[B0, B1, B2, B3], …]. */
export function controls(points, closed = false, tangents = null) {
  const pts = asPoints(points);
  const { mIn, mOut } = solve(pts, closed, tangents);
  const n = pts.length;
  return chords(pts, closed).map((len, i) => {
    const a = pts[i];
    const b = pts[(i + 1) % n];
    return [a, add(a, mul(mOut[i], len / 3)), sub(b, mul(mIn[(i + 1) % n], len / 3)), b];
  });
}

/** Point, dérivée première et seconde d'un arc de Bézier en s ∈ [0, 1]. */
export function bezierAt([b0, b1, b2, b3], s) {
  const u = 1 - s;
  const point = add(add(mul(b0, u * u * u), mul(b1, 3 * u * u * s)),
    add(mul(b2, 3 * u * s * s), mul(b3, s * s * s)));
  const d1 = mul(add(add(mul(sub(b1, b0), u * u), mul(sub(b2, b1), 2 * u * s)),
    mul(sub(b3, b2), s * s)), 3);
  const d2 = mul(add(mul(add(sub(b2, mul(b1, 2)), b0), u),
    mul(add(sub(b3, mul(b2, 2)), b1), s)), 6);
  return { point, d1, d2 };
}

/** Polyligne de la courbe : `perSpan` pas par arc. Une courbe non lisse
 *  (polyligne) ou de moins de trois points sans pente pilotée : les
 *  segments droits. */
export function sample(points, { closed = false, tangents = null, spline = true,
                                 perSpan = 24 } = {}) {
  const pts = asPoints(points);
  if (pts.length < 2) return pts;
  const piloted = (tangents ?? []).some(Boolean);
  if (!spline || (pts.length < 3 && !piloted)) {
    return closed && pts.length >= 3 ? [...pts, pts[0]] : pts;
  }
  const out = [];
  controls(pts, closed, tangents).forEach((span, i) => {
    for (let k = i ? 1 : 0; k <= perSpan; k++) out.push(bezierAt(span, k / perSpan).point);
  });
  return out;
}

/** Peigne de courbure : pour chaque échantillon, [point, bout de la dent].
 *  La dent part du côté convexe, longueur = courbure × `scale`. */
export function curvatureComb(points, { closed = false, tangents = null,
                                        perSpan = 16, scale = 1 } = {}) {
  const pts = asPoints(points);
  if (pts.length < 2) return [];
  const teeth = [];
  controls(pts, closed, tangents).forEach((span, i) => {
    for (let k = i ? 1 : 0; k <= perSpan; k++) {
      const { point, d1, d2 } = bezierAt(span, k / perSpan);
      const speed = norm(d1);
      if (speed < TOL) continue;
      // Vecteur courbure : (d1 × d2) × d1 / |d1|⁴, vers le centre.
      const kv = mul(cross(cross(d1, d2), d1), 1 / speed ** 4);
      teeth.push([point, sub(point, mul(kv, scale))]);
    }
  });
  return teeth;
}

/** Plus grande courbure de la courbe (pour régler l'échelle du peigne). */
export function maxCurvature(points, opts = {}) {
  return curvatureComb(points, { ...opts, scale: 1 }).reduce(
    (best, [p, q]) => Math.max(best, norm(sub(q, p))), 0);
}

/** Pente pilotée tirée de deux dérivées. */
export function tangentSpec(mIn, mOut) {
  const sizeIn = norm(mIn);
  const sizeOut = norm(mOut);
  const dir = sizeOut > TOL ? mOut : mIn;
  const size = norm(dir);
  if (size < TOL) return null;
  return { dir: mul(dir, 1 / size), in: Math.max(sizeIn, 1e-6), out: Math.max(sizeOut, 1e-6) };
}

const close = (a, b, tol) => norm(sub(a, b)) <= tol * Math.max(1, norm(a), norm(b));

/** Tangentes minimales qui redonnent les pentes : tout piloté, puis
 *  chaque point redevient libre si la courbe n'en change pas. */
export function classify(points, closed, mIn, mOut, tol = 1e-6) {
  const pts = asPoints(points);
  const n = pts.length;
  let tangents = pts.map((_, i) => tangentSpec(mIn[i], mOut[i]));
  // Les bouts en dernier : leur règle dépend des points voisins libres.
  const order = n > 2 ? [...Array.from({ length: n - 2 }, (_, k) => k + 1), 0, n - 1]
    : pts.map((_, i) => i);
  let changed = true;
  while (changed) {
    changed = false;
    for (const i of order) {
      if (!tangents[i]) continue;
      const trial = [...tangents];
      trial[i] = null;
      let got;
      try { got = solve(pts, closed, trial); } catch { continue; }
      if (pts.every((_, j) => close(got.mIn[j], mIn[j], tol) && close(got.mOut[j], mOut[j], tol))) {
        tangents = trial;
        changed = true;
      }
    }
  }
  return tangents;
}

/** Points et tangentes d'arcs de Bézier bout à bout. */
export function fromBeziers(spans, closed = false, tol = 1e-6) {
  if (!spans.length) return { points: [], tangents: [] };
  const pts = spans.map((s) => asPoints([s[0]])[0]);
  if (!closed) pts.push(asPoints([spans[spans.length - 1][3]])[0]);
  const n = pts.length;
  const mIn = pts.map(() => [0, 0, 0]);
  const mOut = pts.map(() => [0, 0, 0]);
  spans.forEach((span, i) => {
    const [b0, b1, b2, b3] = asPoints(span);
    const len = norm(sub(b3, b0));
    if (len < TOL) throw new Error("deux points consécutifs sont confondus");
    mOut[i] = mul(sub(b1, b0), 3 / len);
    mIn[(i + 1) % n] = mul(sub(b3, b2), 3 / len);
  });
  if (!closed) {
    mIn[0] = mOut[0];
    mOut[n - 1] = mIn[n - 1];
  }
  return { points: pts, tangents: classify(pts, closed, mIn, mOut, tol) };
}

/** Bouts des poignées du point i : { in, out } (pôles de Bézier voisins,
 *  null au bout d'une courbe ouverte), plus les pentes. */
export function handleTips(points, closed, tangents, i) {
  const spans = controls(points, closed, tangents);
  const n = points.length;
  const outSpan = closed || i < n - 1 ? spans[i] : null;
  const inSpan = closed || i > 0 ? spans[(i - 1 + n) % n] : null;
  return { in: inSpan ? inSpan[2] : null, out: outSpan ? outSpan[1] : null };
}

/** Pente du point i après avoir tiré le bout `side` ("in" | "out") de sa
 *  poignée en `target`. Sans `alone`, les deux côtés gardent leur
 *  rapport ; avec, seul le côté tiré change de longueur. La direction est
 *  toujours commune (la courbe reste lisse au point). */
export function dragTip(points, closed, tangents, i, side, target, { alone = false } = {}) {
  const pts = asPoints(points);
  const n = pts.length;
  const { mIn, mOut } = solve(pts, closed, tangents);
  const h = chords(pts, closed);
  const span = side === "out" ? i : (i - 1 + n) % n;
  let vec = sub(asPoints([target])[0], pts[i]);
  if (side === "in") vec = mul(vec, -1);
  const length = (norm(vec) * 3) / h[span];
  if (!(length > TOL)) return cleanTangents(tangents, n);
  const dir = mul(vec, 1 / norm(vec));
  const oldIn = norm(mIn[i]) || 1;
  const oldOut = norm(mOut[i]) || 1;
  let lin = oldIn;
  let lout = oldOut;
  if (side === "out") {
    lout = length;
    if (!alone) lin = (oldIn / oldOut) * length;
  } else {
    lin = length;
    if (!alone) lout = (oldOut / oldIn) * length;
  }
  const next = cleanTangents(tangents, n);
  next[i] = { dir, in: lin, out: lout };
  return next;
}

/** Fige la pente actuelle du point i (pour éditer ses poids). */
export function pinTangent(points, closed, tangents, i) {
  const { mIn, mOut } = solve(points, closed, tangents);
  const next = cleanTangents(tangents, points.length);
  next[i] = tangentSpec(mIn[i], mOut[i]);
  return next;
}

/** Arc et paramètre le plus proche d'un point (recherche sur échantillons
 *  puis affinage). */
export function nearestOnCurve(points, closed, tangents, target, perSpan = 32) {
  const spans = controls(points, closed, tangents);
  const goal = asPoints([target])[0];
  let best = { span: 0, s: 0, dist: Infinity };
  spans.forEach((span, i) => {
    for (let k = 0; k <= perSpan; k++) {
      const d = norm(sub(bezierAt(span, k / perSpan).point, goal));
      if (d < best.dist) best = { span: i, s: k / perSpan, dist: d };
    }
  });
  let step = 1 / perSpan;
  for (let iter = 0; iter < 30; iter++) {
    step /= 2;
    for (const s of [best.s - step, best.s + step]) {
      if (s < 0 || s > 1) continue;
      const d = norm(sub(bezierAt(spans[best.span], s).point, goal));
      if (d < best.dist) best = { ...best, s, dist: d };
    }
  }
  return best;
}

function splitBezier([b0, b1, b2, b3], s) {
  const lerp = (a, b) => add(a, mul(sub(b, a), s));
  const p01 = lerp(b0, b1);
  const p12 = lerp(b1, b2);
  const p23 = lerp(b2, b3);
  const p012 = lerp(p01, p12);
  const p123 = lerp(p12, p23);
  const mid = lerp(p012, p123);
  return [[b0, p01, p012, mid], [mid, p123, p23, b3]];
}

/** Ajoute un point sur l'arc `span` au paramètre `s` sans changer la
 *  forme : on part des pentes exactes (tout piloté), puis les points qui
 *  étaient libres — et le nouveau — le redeviennent si la courbe ne
 *  s'écarte pas de plus de `tol` (par défaut 0,05 % de sa taille).
 *  Rend { points, tangents, index }. */
export function insertPoint(points, closed, tangents, span, s, { tol = null } = {}) {
  const pts = asPoints(points);
  const before = cleanTangents(tangents, pts.length);
  const spans = controls(pts, closed, before);
  const [left, right] = splitBezier(spans[span], Math.min(Math.max(s, 0.02), 0.98));
  const all = [...spans.slice(0, span), left, right, ...spans.slice(span + 1)];
  const exact = fromBeziers(all, closed);
  const index = span + 1;
  let size = 0;
  for (const p of pts) for (const q of pts) size = Math.max(size, norm(sub(p, q)));
  const limit = tol ?? Math.max(size * 5e-4, 1e-6);
  const original = { points: pts, closed, tangents: before };
  const wasFree = (i) => (i < index ? !before[i] : i > index ? !before[i - 1] : true);
  const order = exact.points.map((_, i) => i).filter((i) => i !== index && wasFree(i));
  order.push(index);
  let current = exact.tangents;
  for (const i of order) {
    if (!current[i]) continue;
    const trial = [...current];
    trial[i] = null;
    try {
      if (deviation(original, { points: exact.points, closed, tangents: trial }) <= limit) {
        current = trial;
      }
    } catch { /* on garde la pente */ }
  }
  return { points: exact.points, tangents: current, index };
}

/** Retire le point i (au moins deux restent). */
export function removePoint(points, tangents, i) {
  const pts = asPoints(points);
  if (pts.length <= 2) return { points: pts, tangents: cleanTangents(tangents, pts.length) };
  const tans = cleanTangents(tangents, pts.length);
  pts.splice(i, 1);
  tans.splice(i, 1);
  return { points: pts, tangents: tans };
}

function distanceToPolyline(point, line) {
  let best = Infinity;
  for (let k = 0; k + 1 < line.length; k++) {
    const a = line[k];
    const d = sub(line[k + 1], a);
    const len2 = dot(d, d);
    const t = len2 > 0 ? Math.min(Math.max(dot(sub(point, a), d) / len2, 0), 1) : 0;
    best = Math.min(best, norm(sub(point, add(a, mul(d, t)))));
  }
  return best;
}

/** Écart maximal entre deux courbes (échantillons de l'une vers l'autre). */
export function deviation(a, b) {
  const lineB = sample(b.points, { ...b, perSpan: 48 });
  return sample(a.points, { ...a, perSpan: 24 }).reduce(
    (worst, p) => Math.max(worst, distanceToPolyline(p, lineB)), 0);
}

/** Simplifier : retire, tant que l'écart à la courbe d'origine reste sous
 *  `tolerance`, le point dont le retrait l'écarte le moins. Les bouts et
 *  les points listés dans `keep` restent. */
export function simplify(points, closed, tangents, tolerance, keep = []) {
  const original = { points: asPoints(points), closed, tangents };
  let current = { points: asPoints(points), tangents: cleanTangents(tangents, points.length) };
  const key = (p) => p.join(",");
  const kept = new Set(keep.map((i) => key(original.points[i])));
  const minimum = closed ? 3 : 2;
  for (;;) {
    if (current.points.length <= minimum) break;
    let best = null;
    current.points.forEach((p, i) => {
      if (!closed && (i === 0 || i === current.points.length - 1)) return;
      if (kept.has(key(p))) return;
      const trial = removePoint(current.points, current.tangents, i);
      let err;
      try {
        err = deviation(original, { ...trial, closed });
      } catch { return; }
      if (err <= tolerance && (!best || err < best.err)) best = { err, trial };
    });
    if (!best) break;
    current = best.trial;
  }
  return current;
}

/** Lisser : chaque point intérieur s'approche de la moyenne de ses
 *  voisins (une passe, `amount` ∈ ]0, 1]) ; les bouts d'une courbe ouverte
 *  et les points de `keep` restent. */
export function relax(points, closed, amount = 0.5, keep = []) {
  const pts = asPoints(points);
  const n = pts.length;
  const fixed = new Set(keep);
  return pts.map((p, i) => {
    if (fixed.has(i) || (!closed && (i === 0 || i === n - 1)) || n < 3) return p;
    const a = pts[(i - 1 + n) % n];
    const b = pts[(i + 1) % n];
    const target = mul(add(a, b), 0.5);
    return add(p, mul(sub(target, p), amount));
  });
}

/** Bouts des poignées de tous les points : [{ in, out }, …] (null au bout
 *  d'une courbe ouverte) — un seul calcul pour toute la courbe. */
export function allHandleTips(points, closed, tangents) {
  const spans = controls(points, closed, tangents);
  const n = points.length;
  return points.map((_, i) => ({
    in: closed || i > 0 ? spans[(i - 1 + n) % n][2] : null,
    out: closed || i < n - 1 ? spans[i][1] : null,
  }));
}

/** Choix sous le pointeur entre un point et un bout de poignée : le point
 *  gagne s'il est presque aussi proche (une poignée courte le recouvre). */
export function preferPoint(pointHit, tipHit, bias = 2) {
  if (!pointHit) return tipHit;
  if (!tipHit) return pointHit;
  return pointHit.d <= tipHit.d + bias ? pointHit : tipHit;
}
