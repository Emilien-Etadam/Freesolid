// Outils de tracé à clics comptés : chaque outil dit combien de clics il
// attend, ce que la barre d'état demande à chaque étape, l'aperçu qui
// suit le curseur et l'op moteur qu'il appelle au dernier clic. Le mode
// esquisse (sketch.js) ne fait que ranger les clics ; tout le reste est
// ici, en fonctions pures.

import { circlePoints, ellipsePoints, slotPoints } from "./geom2d.js";

const TAU = Math.PI * 2;

function arcPts(cx, cy, r, a1, a2, segments = 32) {
  if (!(r > 0)) return [];
  let sweep = a2 - a1;
  while (sweep <= 0) sweep += TAU;
  const pts = [];
  for (let i = 0; i <= segments; i++) {
    const a = a1 + (i / segments) * sweep;
    pts.push({ x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) });
  }
  return pts;
}

/** Centre du cercle passant par trois points, ou null s'ils sont alignés. */
export function circumcircle(a, b, c) {
  const d = 2 * (a.x * (b.y - c.y) + b.x * (c.y - a.y) + c.x * (a.y - b.y));
  if (Math.abs(d) < 1e-12) return null;
  const a2 = a.x * a.x + a.y * a.y;
  const b2 = b.x * b.x + b.y * b.y;
  const c2 = c.x * c.x + c.y * c.y;
  const x = (a2 * (b.y - c.y) + b2 * (c.y - a.y) + c2 * (a.y - b.y)) / d;
  const y = (a2 * (c.x - b.x) + b2 * (a.x - c.x) + c2 * (b.x - a.x)) / d;
  return { x, y, r: Math.hypot(a.x - x, a.y - y) };
}

/** Arc tangent à `dir` en `start`, passant par `end` (même calcul que le
 *  moteur) : { cx, cy, r, a1, a2 } en sens trigo, ou null. */
export function tangentArc(start, dir, end) {
  const n = Math.hypot(dir.x, dir.y);
  if (n < 1e-12) return null;
  const tx = dir.x / n, ty = dir.y / n;
  const nx = -ty, ny = tx;
  const dx = end.x - start.x, dy = end.y - start.y;
  const side = dx * nx + dy * ny;
  if (Math.abs(side) < 1e-9) return null;
  const r = (dx * dx + dy * dy) / (2 * side);
  const cx = start.x + nx * r, cy = start.y + ny * r;
  const as = Math.atan2(start.y - cy, start.x - cx);
  const ae = Math.atan2(end.y - cy, end.x - cx);
  let [a1, a2] = r > 0 ? [as, ae] : [ae, as];
  while (a2 <= a1) a2 += TAU;
  return { cx, cy, r: Math.abs(r), a1, a2 };
}

/** Coins d'un rectangle par un côté et la largeur (ou d'un
 *  parallélogramme par deux côtés). */
export function rect3Corners(p1, p2, p3, parallelogram = false) {
  const ux = p2.x - p1.x, uy = p2.y - p1.y;
  let hx = p3.x - p2.x, hy = p3.y - p2.y;
  if (!parallelogram) {
    const l2 = ux * ux + uy * uy;
    if (l2 < 1e-18) return null;
    const along = (hx * ux + hy * uy) / l2;
    hx -= along * ux;
    hy -= along * uy;
  }
  if (Math.abs(ux * hy - uy * hx) < 1e-9) return null;
  return [p1, p2, { x: p2.x + hx, y: p2.y + hy }, { x: p1.x + hx, y: p1.y + hy }];
}

/** Ellipse par centre, extrémité du grand axe et un point de la courbe :
 *  { rx, ry, angle (rad), t (paramètre du point) }, ou null. */
export function ellipseThrough(c, major, p) {
  const rx = Math.hypot(major.x - c.x, major.y - c.y);
  if (!(rx > 0)) return null;
  const angle = Math.atan2(major.y - c.y, major.x - c.x);
  const cos = Math.cos(angle), sin = Math.sin(angle);
  const lx = (p.x - c.x) * cos + (p.y - c.y) * sin;
  const ly = -(p.x - c.x) * sin + (p.y - c.y) * cos;
  const k = 1 - (lx / rx) ** 2;
  const ry = k > 1e-6 ? Math.abs(ly) / Math.sqrt(k) : Math.abs(ly);
  if (!(ry > 0)) return null;
  return { rx, ry, angle, t: Math.atan2(ly / ry, lx / rx) };
}

/** Paramètre d'un point sur une ellipse déjà définie. */
function ellipseParam(c, e, p) {
  const cos = Math.cos(e.angle), sin = Math.sin(e.angle);
  const lx = (p.x - c.x) * cos + (p.y - c.y) * sin;
  const ly = -(p.x - c.x) * sin + (p.y - c.y) * cos;
  return Math.atan2(ly / e.ry, lx / e.rx);
}

function ellipseArcPts(c, e, t1, t2, segments = 32) {
  let sweep = t2 - t1;
  while (sweep <= 0) sweep += TAU;
  const cos = Math.cos(e.angle), sin = Math.sin(e.angle);
  const pts = [];
  for (let i = 0; i <= segments; i++) {
    const t = t1 + (i / segments) * sweep;
    const lx = e.rx * Math.cos(t), ly = e.ry * Math.sin(t);
    pts.push({ x: c.x + lx * cos - ly * sin, y: c.y + lx * sin + ly * cos });
  }
  return pts;
}

/** Points d'une parabole de sommet `v` et de foyer `f`, entre les
 *  projections de `a` et `b` sur la tangente au sommet. */
export function parabolaPoints(v, f, a, b, segments = 32) {
  const focal = Math.hypot(f.x - v.x, f.y - v.y);
  if (!(focal > 0)) return [];
  const ax = (f.x - v.x) / focal, ay = (f.y - v.y) / focal;
  const bx = -ay, by = ax;
  const u1 = (a.x - v.x) * bx + (a.y - v.y) * by;
  const u2 = (b.x - v.x) * bx + (b.y - v.y) * by;
  const pts = [];
  for (let i = 0; i <= segments; i++) {
    const u = u1 + (i / segments) * (u2 - u1);
    const h = (u * u) / (4 * focal);
    pts.push({ x: v.x + h * ax + u * bx, y: v.y + h * ay + u * by });
  }
  return pts;
}

/** rho d'une conique depuis le point d'épaule : sa place entre le milieu
 *  de la corde (0) et le sommet (1), bornée à ]0,05 ; 0,95[. */
export function conicRho(p0, p2, apex, shoulder) {
  const mx = (p0.x + p2.x) / 2, my = (p0.y + p2.y) / 2;
  const ax = apex.x - mx, ay = apex.y - my;
  const l2 = ax * ax + ay * ay;
  if (l2 < 1e-18) return 0.5;
  const rho = ((shoulder.x - mx) * ax + (shoulder.y - my) * ay) / l2;
  return Math.min(0.95, Math.max(0.05, rho));
}

/** Points d'une conique (Bézier rationnelle de degré 2). */
export function conicPoints(p0, p2, apex, rho, segments = 32) {
  const w = rho / (1 - rho);
  const pts = [];
  for (let i = 0; i <= segments; i++) {
    const t = i / segments;
    const b0 = (1 - t) ** 2, b1 = 2 * t * (1 - t) * w, b2 = t * t;
    const s = b0 + b1 + b2;
    pts.push({ x: (b0 * p0.x + b1 * apex.x + b2 * p2.x) / s,
               y: (b0 * p0.y + b1 * apex.y + b2 * p2.y) / s });
  }
  return pts;
}

/** Spline par pôles (aperçu) : B-spline uniforme serrée, degré ≤ 3. */
export function polesSplinePoints(poles, segments = 48) {
  const n = poles.length;
  if (n < 2) return [...poles];
  const p = Math.min(3, n - 1);
  const knots = [];
  for (let i = 0; i <= p; i++) knots.push(0);
  for (let i = 1; i < n - p; i++) knots.push(i / (n - p));
  for (let i = 0; i <= p; i++) knots.push(1);
  const basis = (i, k, t) => {
    if (k === 0) {
      if (t === 1) return i === n - 1 ? 1 : 0;
      return knots[i] <= t && t < knots[i + 1] ? 1 : 0;
    }
    const d1 = knots[i + k] - knots[i];
    const d2 = knots[i + k + 1] - knots[i + 1];
    const a = d1 > 0 ? ((t - knots[i]) / d1) * basis(i, k - 1, t) : 0;
    const b = d2 > 0 ? ((knots[i + k + 1] - t) / d2) * basis(i + 1, k - 1, t) : 0;
    return a + b;
  };
  const pts = [];
  for (let s = 0; s <= segments; s++) {
    const t = s / segments;
    let x = 0, y = 0;
    for (let i = 0; i < n; i++) {
      const w = basis(i, p, t);
      x += w * poles[i].x;
      y += w * poles[i].y;
    }
    pts.push({ x, y });
  }
  return pts;
}

/** Rectangle par le centre, le milieu d'un côté et la demi-largeur :
 *  les trois points que `rect3Corners` attend (un côté, puis la largeur). */
export function centerRect3Points(c, mid, p) {
  const ax = mid.x - c.x, ay = mid.y - c.y;
  const len = Math.hypot(ax, ay);
  if (len < 1e-12) return null;
  const vx = -ay / len, vy = ax / len;
  const h = (p.x - c.x) * vx + (p.y - c.y) * vy;
  if (Math.abs(h) < 1e-9) return null;
  const p1 = { x: c.x - ax - h * vx, y: c.y - ay - h * vy };
  const p2 = { x: c.x + ax - h * vx, y: c.y + ay - h * vy };
  const p3 = { x: p2.x + 2 * h * vx, y: p2.y + 2 * h * vy };
  return [p1, p2, p3];
}

/** Sommet d'un polygone donné par son cercle inscrit : le clic est au
 *  milieu d'un côté. */
export function polygonVertexFromApothem(c, p, sides) {
  const a = Math.PI / sides;
  const dx = p.x - c.x, dy = p.y - c.y;
  const k = 1 / Math.cos(a);
  return { x: c.x + k * (dx * Math.cos(a) - dy * Math.sin(a)),
           y: c.y + k * (dx * Math.sin(a) + dy * Math.cos(a)) };
}

/** Rainure en arc par trois points : bouts de l'arc médian, un point de
 *  passage, puis la largeur — mêmes paramètres que la rainure par centre. */
function arcSlot3Params([p1, p2, through, w]) {
  const k = circumcircle(p1, p2, through);
  if (!k) return null;
  const c = { x: k.x, y: k.y };
  const norm = (a, from) => {
    let v = a;
    while (v <= from) v += TAU;
    return v;
  };
  const aS = polar(c, p1);
  const aE = norm(polar(c, p2), aS);
  const aM = norm(polar(c, through), aS);
  const [a1, a2] = aM < aE ? [aS, aE] : [polar(c, p2), norm(aS, polar(c, p2))];
  const width = w ? 2 * Math.abs(Math.hypot(w.x - c.x, w.y - c.y) - k.r) : 0;
  return { cx: c.x, cy: c.y, r: k.r, a1, a2, width };
}

/** Angle polaire de `p` autour de `c`. */
const polar = (c, p) => Math.atan2(p.y - c.y, p.x - c.x);

/** Rainure en arc : centre, départ, arrivée (sens trigo), largeur. */
function arcSlotParams([c, s, e, w]) {
  const r = Math.hypot(s.x - c.x, s.y - c.y);
  const a1 = polar(c, s);
  let a2 = polar(c, e);
  while (a2 <= a1) a2 += TAU;
  const width = 2 * Math.abs(Math.hypot(w.x - c.x, w.y - c.y) - r);
  return { cx: c.x, cy: c.y, r, a1, a2, width };
}

function arcSlotPoints({ cx, cy, r, a1, a2, width }) {
  const h = width / 2;
  if (!(r > h) || !(h > 0)) return arcPts(cx, cy, r, a1, a2);
  const at = (a) => ({ x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) });
  const e2 = at(a2), e1 = at(a1);
  return [
    ...arcPts(cx, cy, r + h, a1, a2),
    ...arcPts(e2.x, e2.y, h, a2, a2 + Math.PI, 12).slice(1),
    ...arcPts(cx, cy, r - h, a1, a2).reverse().slice(1),
    ...arcPts(e1.x, e1.y, h, a1 + Math.PI, a1 + TAU, 12).slice(1),
  ];
}

/** Largeur d'une rainure droite d'axe a→b, donnée par le curseur. */
function slotWidth(a, b, p) {
  const len = Math.hypot(b.x - a.x, b.y - a.y);
  if (!(len > 0)) return 0;
  return 2 * Math.abs(((b.x - a.x) * (a.y - p.y) - (b.y - a.y) * (a.x - p.x))
    / len);
}

const xy = (p) => ({ x: p.x, y: p.y });

/**
 * Les outils. `prompts[i]` : la consigne après i clics. `build(pts, opts)`
 * renvoie `{ op, params }` ou `{ error }`. `preview(pts, cursor, opts)`
 * renvoie une polyligne (coordonnées d'esquisse).
 */
export const CLICK_TOOLS = {
  point: {
    clicks: 1,
    prompts: ["Point : cliquez où le poser"],
    build: ([p]) => ({ op: "sketch_add_point", params: { x: p.x, y: p.y } }),
    preview: () => [],
  },
  centerline: {
    clicks: 2,
    prompts: ["Ligne d'axe : cliquez le départ",
      "Ligne d'axe : cliquez l'arrivée"],
    build: ([a, b]) => ({ op: "sketch_add_line", params: {
      x1: a.x, y1: a.y, x2: b.x, y2: b.y, construction: true } }),
    preview: ([a], cur) => [xy(a), xy(cur)],
  },
  circle3: {
    clicks: 3,
    prompts: ["Cercle 3 points : cliquez un premier point du cercle",
      "Cercle 3 points : cliquez un deuxième point",
      "Cercle 3 points : cliquez le troisième point"],
    build: ([a, b, c]) => {
      const k = circumcircle(a, b, c);
      if (!k) return { error: "Cercle : les trois points sont alignés" };
      return { op: "sketch_add_circle", params: { cx: k.x, cy: k.y, r: k.r } };
    },
    preview: (pts, cur) => {
      if (pts.length < 2) return [xy(pts[0]), xy(cur)];
      const k = circumcircle(pts[0], pts[1], cur);
      return k ? circlePoints(k.x, k.y, k.r) : [xy(pts[0]), xy(pts[1])];
    },
  },
  tarc: {
    clicks: 2,
    needsEndpoint: true,
    prompts: ["Arc tangent : cliquez l'extrémité d'une ligne ou d'un arc",
      "Arc tangent : cliquez le point d'arrivée"],
    build: ([start, end]) => ({ op: "sketch_add_tangent_arc", params: {
      geo: start.geo, point: start.point, x: end.x, y: end.y } }),
    preview: ([start], cur) => {
      if (!start.dir) return [xy(start), xy(cur)];
      const k = tangentArc(start, start.dir, cur);
      return k ? arcPts(k.cx, k.cy, k.r, k.a1, k.a2) : [xy(start), xy(cur)];
    },
  },
  rect3: {
    clicks: 3,
    prompts: ["Rectangle 3 points : cliquez le premier coin",
      "Rectangle 3 points : cliquez le bout du premier côté",
      "Rectangle 3 points : cliquez pour donner la largeur"],
    build: ([a, b, c]) => (rect3Corners(a, b, c)
      ? { op: "sketch_add_rect3", params: {
        x1: a.x, y1: a.y, x2: b.x, y2: b.y, x3: c.x, y3: c.y } }
      : { error: "Rectangle : les trois points sont alignés" }),
    preview: (pts, cur) => {
      if (pts.length < 2) return [xy(pts[0]), xy(cur)];
      const k = rect3Corners(pts[0], pts[1], cur);
      return k ? [...k.map(xy), xy(k[0])] : [xy(pts[0]), xy(pts[1])];
    },
  },
  parallelogram: {
    clicks: 3,
    prompts: ["Parallélogramme : cliquez le premier coin",
      "Parallélogramme : cliquez le bout du premier côté",
      "Parallélogramme : cliquez le bout du second côté"],
    build: ([a, b, c]) => (rect3Corners(a, b, c, true)
      ? { op: "sketch_add_rect3", params: {
        x1: a.x, y1: a.y, x2: b.x, y2: b.y, x3: c.x, y3: c.y,
        parallelogram: true } }
      : { error: "Parallélogramme : les trois points sont alignés" }),
    preview: (pts, cur) => {
      if (pts.length < 2) return [xy(pts[0]), xy(cur)];
      const k = rect3Corners(pts[0], pts[1], cur, true);
      return k ? [...k.map(xy), xy(k[0])] : [xy(pts[0]), xy(pts[1])];
    },
  },
  slotc: {
    clicks: 3,
    prompts: ["Rainure par le centre : cliquez le milieu",
      "Rainure par le centre : cliquez le centre d'un bout",
      "Rainure par le centre : cliquez pour donner la largeur"],
    build: ([c, b, w]) => {
      const a = { x: 2 * c.x - b.x, y: 2 * c.y - b.y };
      const width = slotWidth(a, b, w);
      if (!(width > 0)) return { error: "Rainure : largeur nulle" };
      return { op: "sketch_add_slot", params: {
        x1: a.x, y1: a.y, x2: b.x, y2: b.y, width } };
    },
    preview: (pts, cur) => {
      const [c, b] = pts;
      if (!b) return [{ x: 2 * c.x - cur.x, y: 2 * c.y - cur.y }, xy(cur)];
      const a = { x: 2 * c.x - b.x, y: 2 * c.y - b.y };
      return slotPoints(a, b, slotWidth(a, b, cur));
    },
  },
  arcslot: {
    clicks: 4,
    prompts: ["Rainure en arc : cliquez le centre de l'arc",
      "Rainure en arc : cliquez le départ de l'arc",
      "Rainure en arc : cliquez l'arrivée (sens anti-horaire)",
      "Rainure en arc : cliquez pour donner la largeur"],
    build: (pts) => {
      const k = arcSlotParams(pts);
      if (!(k.width > 0) || !(k.r > k.width / 2)) {
        return { error: "Rainure en arc : largeur nulle ou plus grande que l'arc" };
      }
      return { op: "sketch_add_arc_slot", params: k };
    },
    preview: (pts, cur) => {
      const [c, s, e] = pts;
      const r = s ? Math.hypot(s.x - c.x, s.y - c.y) : 0;
      if (!s) return circlePoints(c.x, c.y, Math.hypot(cur.x - c.x, cur.y - c.y));
      if (!e) return arcPts(c.x, c.y, r, polar(c, s), polar(c, cur));
      return arcSlotPoints(arcSlotParams([c, s, e, cur]));
    },
  },
  arcslot3: {
    clicks: 4,
    prompts: ["Rainure en arc 3 points : cliquez un bout de l'arc",
      "Rainure en arc 3 points : cliquez l'autre bout",
      "Rainure en arc 3 points : cliquez un point de passage",
      "Rainure en arc 3 points : cliquez pour donner la largeur"],
    build: (pts) => {
      const k = arcSlot3Params(pts);
      if (!k) return { error: "Rainure en arc : les trois points sont alignés" };
      if (!(k.width > 0) || !(k.r > k.width / 2)) {
        return { error: "Rainure en arc : largeur nulle ou plus grande que l'arc" };
      }
      return { op: "sketch_add_arc_slot", params: k };
    },
    preview: (pts, cur) => {
      if (pts.length < 2) return [xy(pts[0]), xy(cur)];
      if (pts.length < 3) {
        const k = arcSlot3Params([pts[0], pts[1], cur]);
        return k ? arcPts(k.cx, k.cy, k.r, k.a1, k.a2) : [xy(pts[0]), xy(cur)];
      }
      const k = arcSlot3Params([...pts, cur]);
      return k ? arcSlotPoints(k) : [];
    },
  },
  rectc3: {
    clicks: 3,
    prompts: ["Rectangle 3 points par le centre : cliquez le centre",
      "Rectangle 3 points par le centre : cliquez le milieu d'un côté",
      "Rectangle 3 points par le centre : cliquez pour donner la largeur"],
    build: ([c, mid, p]) => {
      const k = centerRect3Points(c, mid, p);
      if (!k) return { error: "Rectangle : les trois points sont alignés" };
      const [a, b, d] = k;
      return { op: "sketch_add_rect3", params: {
        x1: a.x, y1: a.y, x2: b.x, y2: b.y, x3: d.x, y3: d.y } };
    },
    preview: (pts, cur) => {
      if (pts.length < 2) {
        return [{ x: 2 * pts[0].x - cur.x, y: 2 * pts[0].y - cur.y }, xy(cur)];
      }
      const k = centerRect3Points(pts[0], pts[1], cur);
      if (!k) return [];
      const q = rect3Corners(...k);
      return q ? [...q.map(xy), xy(q[0])] : [];
    },
  },
  ellarc: {
    clicks: 4,
    prompts: ["Arc d'ellipse : cliquez le centre",
      "Arc d'ellipse : cliquez l'extrémité du grand axe",
      "Arc d'ellipse : cliquez le départ de l'arc (il fixe le petit rayon)",
      "Arc d'ellipse : cliquez l'arrivée (sens anti-horaire)"],
    build: ([c, major, s, e]) => {
      const k = ellipseThrough(c, major, s);
      if (!k) return { error: "Ellipse : petit rayon nul" };
      return { op: "sketch_add_ellipse_arc", params: {
        cx: c.x, cy: c.y, rx: k.rx, ry: k.ry,
        angle: (k.angle * 180) / Math.PI,
        a1: k.t, a2: ellipseParam(c, k, e) } };
    },
    preview: (pts, cur) => {
      const [c, major, s] = pts;
      if (!major) return [xy(c), xy(cur)];
      if (!s) {
        const k = ellipseThrough(c, major, cur);
        return k ? ellipsePoints(c.x, c.y, k.rx, k.ry, k.angle)
          : [xy(c), xy(major)];
      }
      const k = ellipseThrough(c, major, s);
      return k ? ellipseArcPts(c, k, k.t, ellipseParam(c, k, cur)) : [];
    },
  },
  parabola: {
    clicks: 4,
    prompts: ["Parabole : cliquez le sommet", "Parabole : cliquez le foyer",
      "Parabole : cliquez un bout", "Parabole : cliquez l'autre bout"],
    build: ([v, f, a, b]) => ({ op: "sketch_add_parabola", params: {
      vx: v.x, vy: v.y, fx: f.x, fy: f.y, x1: a.x, y1: a.y,
      x2: b.x, y2: b.y } }),
    preview: (pts, cur) => {
      const [v, f, a] = pts;
      if (!f) return [xy(v), xy(cur)];
      if (!a) return parabolaPoints(v, f, cur, { x: 2 * v.x - cur.x, y: 2 * v.y - cur.y });
      return parabolaPoints(v, f, a, cur);
    },
  },
  conic: {
    clicks: 4,
    prompts: ["Conique : cliquez le départ", "Conique : cliquez l'arrivée",
      "Conique : cliquez le sommet (croisement des tangentes)",
      "Conique : cliquez le galbe (entre la corde et le sommet)"],
    build: ([p0, p2, apex, shoulder]) => ({ op: "sketch_add_conic", params: {
      x1: p0.x, y1: p0.y, x2: p2.x, y2: p2.y, ax: apex.x, ay: apex.y,
      rho: conicRho(p0, p2, apex, shoulder) } }),
    preview: (pts, cur) => {
      const [p0, p2, apex] = pts;
      if (!p2) return [xy(p0), xy(cur)];
      if (!apex) return [xy(p0), xy(cur), xy(p2)];
      return conicPoints(p0, p2, apex, conicRho(p0, p2, apex, cur));
    },
  },
};

/** Outils dont le nombre de clics est libre (Entrée pour finir). */
export const OPEN_TOOLS = {
  splinecp: {
    min: 3,
    prompt: "Spline par pôles : {n} pôle(s) — Entrée pour terminer (min 3), Échap pour annuler",
    build: (pts) => ({ op: "sketch_add_spline_poles", params: {
      points: pts.map((p) => [p.x, p.y]) } }),
    preview: (pts, cur) => {
      const all = [...pts, cur].map(xy);
      return [...all, ...polesSplinePoints(all).reverse()];
    },
  },
};

/** Direction qui prolonge une ligne ou un arc à son extrémité `point`
 *  (1 départ, 2 arrivée) — la tangente d'un arc tangent qui y part. */
export function endpointDirection(entity, point) {
  if (entity?.type === "line") {
    const [a, b] = point === 2 ? [entity.p1, entity.p2] : [entity.p2, entity.p1];
    return { x: b[0] - a[0], y: b[1] - a[1] };
  }
  if (entity?.type === "arc") {
    const p = point === 2 ? entity.p2 : entity.p1;
    const rx = p[0] - entity.c[0], ry = p[1] - entity.c[1];
    // Sens trigo : on suit la tangente à l'arrivée, on la remonte au départ.
    return point === 2 ? { x: -ry, y: rx } : { x: ry, y: -rx };
  }
  return null;
}

/** Pas de grille rond (1, 2 ou 5 × 10ⁿ) pour une vue de hauteur `view`. */
export function gridStep(view) {
  const raw = Math.max(view, 1e-6) / 40;
  const power = 10 ** Math.floor(Math.log10(raw));
  const unit = raw / power;
  return (unit < 1.5 ? 1 : unit < 3.5 ? 2 : unit < 7.5 ? 5 : 10) * power;
}

/** Peigne de courbure de plusieurs polylignes : pour chaque point
 *  intérieur, la dent [point, bout] le long de la normale, de longueur
 *  proportionnelle à la courbure — la plus forte de toutes vaut `reach`. */
export function curvatureComb(polylines, reach) {
  const samples = [];
  for (const points of polylines) {
    for (let i = 1; i + 1 < points.length; i++) {
      const [ax, ay] = points[i - 1], [bx, by] = points[i];
      const [cx, cy] = points[i + 1];
      const ab = Math.hypot(bx - ax, by - ay), bc = Math.hypot(cx - bx, cy - by);
      const ca = Math.hypot(ax - cx, ay - cy);
      const cross = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
      const k = ab * bc * ca > 1e-12 ? (2 * cross) / (ab * bc * ca) : 0;
      const tx = cx - ax, ty = cy - ay, tn = Math.hypot(tx, ty) || 1;
      samples.push({ p: [bx, by], n: [-ty / tn, tx / tn], k });
    }
  }
  const top = Math.max(0, ...samples.map((c) => Math.abs(c.k)));
  if (!(top > 0)) return [];
  return samples.map(({ p, n, k }) => {
    const len = (k / top) * reach;
    return [p, [p[0] - n[0] * len, p[1] - n[1] * len]];
  });
}
