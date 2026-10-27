// Magnétisme de l'esquisse : où tombe un clic, et ce qu'il accroche.
// Pur (sans Three.js) : sketch.js fournit la projection à l'écran.
//
// L'interface décide : un clic accroché au centre d'un cercle devient une
// cible { geo, point } que le tracé envoie au moteur dans `snaps`
// (engine/sketchsnap.py), qui pose la relation dans la même opération.
// Un tracé de l'interface envoie toujours `snaps`, même vide.
//
// Cibles : un point d'esquisse { geo, point } ; { kind: "midpoint", geo },
// { kind: "quadrant", geo, quadrant } (0 à droite du centre, sens trigo),
// { kind: "on", geo } (n'importe où sur la courbe) et
// { kind: "intersection", geos: [a, b] }.

import { arcAngles, distanceToEntity } from "./geom2d.js";

/** Rayon d'accrochage, en pixels écran. */
export const SNAP_PX = 12;
/** Une courbe attire de moins loin qu'un point : on trace souvent près
 *  d'elle sans vouloir s'y poser. */
export const ON_CURVE_PX = 8;
/** Deux points sont le même : la tolérance du moteur (`_SNAP_TOL`). */
export const SNAP_TOL = 1e-7;
/** Le point racine du moteur : l'origine de l'esquisse (point 1). */
export const ORIGIN_GEO = -1;

/**
 * Points d'esquisse d'où une ligne peut partir : extrémités, centres,
 * points, bouts de spline. Numérotation du moteur : 1 départ, 2 fin,
 * 3 centre. `hidden` : ids des entités sur un calque masqué.
 */
export function* sketchEndpoints(entities, hidden = new Set()) {
  for (const entity of entities ?? []) {
    if (hidden.has(entity.id)) continue;
    if (entity.type === "point") {
      yield { geo: entity.id, point: 1, x: entity.p1[0], y: entity.p1[1] };
    }
    if (entity.type === "line" || entity.type === "arc") {
      yield { geo: entity.id, point: 1, x: entity.p1[0], y: entity.p1[1] };
      yield { geo: entity.id, point: 2, x: entity.p2[0], y: entity.p2[1] };
    }
    if (entity.type === "circle" || entity.type === "arc") {
      yield { geo: entity.id, point: 3, x: entity.c[0], y: entity.c[1] };
    }
    if (entity.type === "poly" && entity.kind === "spline"
        && entity.points?.length > 1) {
      // Bouts d'une spline : départ (1) et arrivée (2), comme Sketcher.
      const [x1, y1] = entity.points[0];
      const [x2, y2] = entity.points[entity.points.length - 1];
      yield { geo: entity.id, point: 1, x: x1, y: y1 };
      if (Math.hypot(x2 - x1, y2 - y1) > 1e-9) {
        yield { geo: entity.id, point: 2, x: x2, y: y2 };
      }
    }
  }
}

/**
 * Points d'accrochage : les extrémités et centres, plus l'origine de
 * l'esquisse — on démarre souvent un profil dessus.
 */
export function sketchSnapPoints(entities, hidden) {
  return [...sketchEndpoints(entities, hidden),
    { geo: ORIGIN_GEO, point: 1, x: 0, y: 0 }];
}

const TAU = Math.PI * 2;

/** L'angle `a` tombe-t-il dans le balayage [a1, a2] d'un arc ? */
function inSweep(a, a1, a2, eps = 1e-12) {
  while (a < a1 - eps) a += TAU;
  while (a > a2 + eps) a -= TAU;
  return a >= a1 - eps && a <= a2 + eps;
}

/**
 * Points remarquables d'une entité, que l'on voit quand le curseur la
 * survole : milieu d'une ligne ou d'un arc, quadrants d'un cercle ou d'un
 * arc (ceux que l'arc couvre). `[{ x, y, kind, target }]`.
 */
export function entityFeatures(entity) {
  const out = [];
  if (entity?.type === "line") {
    out.push({ x: (entity.p1[0] + entity.p2[0]) / 2,
               y: (entity.p1[1] + entity.p2[1]) / 2, kind: "midpoint",
               target: { kind: "midpoint", geo: entity.id } });
  }
  if (entity?.type !== "circle" && entity?.type !== "arc") return out;
  const [cx, cy] = entity.c;
  const sweep = entity.type === "arc" ? arcAngles(entity) : null;
  if (sweep) {
    const a = (sweep.a1 + sweep.a2) / 2;
    out.push({ x: cx + entity.r * Math.cos(a), y: cy + entity.r * Math.sin(a),
               kind: "midpoint",
               target: { kind: "midpoint", geo: entity.id } });
  }
  for (let quadrant = 0; quadrant < 4; quadrant++) {
    const a = quadrant * Math.PI / 2;
    if (sweep && !inSweep(a, sweep.a1, sweep.a2)) continue;
    // Les quadrants tombent pile sur les axes du centre : c'est ce que
    // le moteur tient (horizontale ou verticale avec le centre).
    const [dx, dy] = [[1, 0], [0, 1], [-1, 0], [0, -1]][quadrant];
    out.push({ x: cx + entity.r * dx, y: cy + entity.r * dy, kind: "quadrant",
               target: { kind: "quadrant", geo: entity.id, quadrant } });
  }
  return out;
}

function nearestOnSegment(x, y, a, b) {
  const abx = b[0] - a[0], aby = b[1] - a[1];
  const len2 = abx * abx + aby * aby;
  const u = len2 < 1e-18 ? 0 : Math.max(0, Math.min(1,
    ((x - a[0]) * abx + (y - a[1]) * aby) / len2));
  return { x: a[0] + u * abx, y: a[1] + u * aby };
}

/** Le point de l'entité le plus proche de (x, y), ou null (un point, ou
 *  un arc visé hors de son balayage : son bout y est déjà). */
export function nearestOnEntity(entity, x, y) {
  if (entity?.type === "line") return nearestOnSegment(x, y, entity.p1, entity.p2);
  if (entity?.type === "circle" || entity?.type === "arc") {
    const [cx, cy] = entity.c;
    const a = Math.atan2(y - cy, x - cx);
    if (entity.type === "arc") {
      const { a1, a2 } = arcAngles(entity);
      if (!inSweep(a, a1, a2)) return null;
    }
    return { x: cx + entity.r * Math.cos(a), y: cy + entity.r * Math.sin(a) };
  }
  if (entity?.type === "poly" && entity.points?.length > 1) {
    let best = null, bestD = Infinity;
    for (let i = 0; i < entity.points.length - 1; i++) {
      const q = nearestOnSegment(x, y, entity.points[i], entity.points[i + 1]);
      const d = Math.hypot(q.x - x, q.y - y);
      if (d < bestD) { best = q; bestD = d; }
    }
    return best;
  }
  return null;
}

/** Morceaux d'une entité pour les croisements : segments et cercles
 *  (un arc garde son balayage). Une spline, une ellipse : sa polyligne. */
function pieces(entity) {
  if (entity?.type === "line") return [{ seg: [entity.p1, entity.p2] }];
  if (entity?.type === "circle") return [{ c: entity.c, r: entity.r }];
  if (entity?.type === "arc") {
    return [{ c: entity.c, r: entity.r, sweep: arcAngles(entity) }];
  }
  if (entity?.type === "poly" && entity.points?.length > 1) {
    return entity.points.slice(1).map((p, i) => ({ seg: [entity.points[i], p] }));
  }
  return [];
}

const EPS = 1e-9;

function onPiece(piece, p) {
  if (piece.seg) {
    const [a, b] = piece.seg;
    const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
    const u = ((p.x - a[0]) * (b[0] - a[0]) + (p.y - a[1]) * (b[1] - a[1]))
      / (len * len || 1);
    return piece.infinite || (u >= -EPS && u <= 1 + EPS);
  }
  return !piece.sweep || inSweep(
    Math.atan2(p.y - piece.c[1], p.x - piece.c[0]), piece.sweep.a1, piece.sweep.a2);
}

function lineCrossings(p, q) {
  const [a, b] = p.seg, [c, d] = q.seg;
  const rx = b[0] - a[0], ry = b[1] - a[1];
  const sx = d[0] - c[0], sy = d[1] - c[1];
  const den = rx * sy - ry * sx;
  if (Math.abs(den) < 1e-12 * (Math.hypot(rx, ry) * Math.hypot(sx, sy) || 1)) {
    return [];
  }
  const u = ((c[0] - a[0]) * sy - (c[1] - a[1]) * sx) / den;
  return [{ x: a[0] + u * rx, y: a[1] + u * ry }];
}

function lineCircleCrossings(line, circle) {
  const [a, b] = line.seg;
  const [cx, cy] = circle.c;
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const fx = a[0] - cx, fy = a[1] - cy;
  const A = dx * dx + dy * dy;
  const B = 2 * (fx * dx + fy * dy);
  const C = fx * fx + fy * fy - circle.r * circle.r;
  const disc = B * B - 4 * A * C;
  if (A < 1e-18 || disc < 0) return [];
  const root = Math.sqrt(disc);
  const us = root < 1e-12 ? [-B / (2 * A)]
    : [(-B - root) / (2 * A), (-B + root) / (2 * A)];
  return us.map((u) => ({ x: a[0] + u * dx, y: a[1] + u * dy }));
}

function circleCrossings(p, q) {
  const [x0, y0] = p.c, [x1, y1] = q.c;
  const d = Math.hypot(x1 - x0, y1 - y0);
  if (d < 1e-12 || d > p.r + q.r || d < Math.abs(p.r - q.r)) return [];
  const a = (p.r * p.r - q.r * q.r + d * d) / (2 * d);
  const h = Math.sqrt(Math.max(0, p.r * p.r - a * a));
  const mx = x0 + a * (x1 - x0) / d, my = y0 + a * (y1 - y0) / d;
  const ox = -h * (y1 - y0) / d, oy = h * (x1 - x0) / d;
  return h < 1e-12 ? [{ x: mx, y: my }]
    : [{ x: mx + ox, y: my + oy }, { x: mx - ox, y: my - oy }];
}

function pieceCrossings(p, q) {
  let hits;
  if (p.seg && q.seg) hits = lineCrossings(p, q);
  else if (p.seg) hits = lineCircleCrossings(p, q);
  else if (q.seg) hits = lineCircleCrossings(q, p);
  else hits = circleCrossings(p, q);
  return hits.filter((h) => onPiece(p, h) && onPiece(q, h));
}

/** Où deux entités se croisent : `[{ x, y }]` (lignes, cercles, arcs ;
 *  une spline ou une ellipse, par sa polyligne). */
export function entityCrossings(e1, e2) {
  const out = [];
  for (const p of pieces(e1)) {
    for (const q of pieces(e2)) out.push(...pieceCrossings(p, q));
  }
  return out;
}

/** Où l'axe horizontal ("H", y = value) ou vertical ("V", x = value)
 *  coupe l'entité. */
export function axisCrossings(entity, hv, value) {
  const axis = { infinite: true, seg: hv === "H"
    ? [[0, value], [1, value]] : [[value, 0], [value, 1]] };
  return pieces(entity).flatMap((piece) => pieceCrossings(axis, piece))
    .map((h) => (hv === "H" ? { x: h.x, y: value } : { x: value, y: h.y }));
}

/**
 * Où tombe le curseur. Dans l'ordre : un point existant (à l'écran) ; le
 * milieu, un quadrant ou un croisement d'une entité survolée ; l'axe
 * horizontal ou vertical depuis le point précédent de la chaîne ; la
 * courbe survolée (sur l'axe de la chaîne s'il la coupe là) ; puis
 * l'alignement sur un point existant (un repère, sans relation), puis la
 * grille.
 *
 * `local` : le curseur dans l'esquisse ; `cursor` : en pixels écran.
 * `toScreen(x, y)` rend le pixel `{ x, y }` d'un point de l'esquisse.
 * `points` : les points d'esquisse (sketchSnapPoints) ; `entities` : les
 * entités visibles, pour les milieux, quadrants, croisements et courbes.
 * `chain` : le point précédent d'une ligne en cours, ou null.
 * `gridStep` : le pas de la grille si elle accroche, sinon null.
 * `suspended` (Ctrl maintenu) : le point reste où est le curseur.
 *
 * Rend `{ x, y, onPoint, target, kind, wake, guides, hv, suspended }` :
 * `onPoint` le point d'esquisse accroché, `target` la cible à envoyer au
 * moteur et `kind` sa sorte ("point", "midpoint", "quadrant",
 * "intersection", "on"), `wake` les points remarquables de l'entité
 * survolée (à montrer), `guides` les points d'où partent les lignes
 * d'aide, `hv` "H" ou "V" quand la chaîne s'aligne.
 */
export function snapSketchPoint(local, cursor, {
  points, entities = [], toScreen, chain = null, gridStep = null,
  suspended = false,
}) {
  const none = { onPoint: null, target: null, kind: null, wake: [] };
  if (suspended) {
    return { x: local.x, y: local.y, ...none, guides: [], hv: null,
             suspended: true };
  }
  for (const p of points) {
    const s = toScreen(p.x, p.y);
    if (Math.hypot(s.x - cursor.x, s.y - cursor.y) < SNAP_PX) {
      return { x: p.x, y: p.y, ...none, onPoint: p, kind: "point",
               target: { geo: p.geo, point: p.point }, guides: [], hv: null };
    }
  }
  // Pixels écran par unité d'esquisse : les axes de l'esquisse ne suivent
  // pas forcément ceux de l'écran.
  const s0 = toScreen(0, 0), s1 = toScreen(1, 0);
  const scale = Math.hypot(s1.x - s0.x, s1.y - s0.y) || 1;
  const screenDistance = (p) => {
    const s = toScreen(p.x, p.y);
    return Math.hypot(s.x - cursor.x, s.y - cursor.y);
  };
  const near = entities
    .map((entity) => ({ entity,
      d: distanceToEntity(local.x, local.y, entity) * scale }))
    .filter(({ d }) => d < SNAP_PX)
    .sort((a, b) => a.d - b.d)
    .map(({ entity }) => entity);
  const wake = near.length ? entityFeatures(near[0]) : [];
  const special = near.flatMap(entityFeatures);
  for (let i = 0; i < near.length; i++) {
    for (let j = i + 1; j < near.length; j++) {
      for (const hit of entityCrossings(near[i], near[j])) {
        special.push({ ...hit, kind: "intersection", target: {
          kind: "intersection", geos: [near[i].id, near[j].id] } });
      }
    }
  }
  let best = null, bestD = SNAP_PX;
  for (const candidate of special) {
    const d = screenDistance(candidate);
    if (d < bestD) { best = candidate; bestD = d; }
  }
  if (best) {
    return { x: best.x, y: best.y, ...none, kind: best.kind,
             target: best.target, wake, guides: [], hv: null };
  }
  let { x, y } = local;
  let hv = null;
  const guides = [];
  if (chain) {
    const sHere = toScreen(x, y);
    const sAxisV = toScreen(chain.x, y);
    const sAxisH = toScreen(x, chain.y);
    if (Math.hypot(sHere.x - sAxisV.x, sHere.y - sAxisV.y) < SNAP_PX) {
      x = chain.x;
      hv = "V";
    } else if (Math.hypot(sHere.x - sAxisH.x, sHere.y - sAxisH.y) < SNAP_PX) {
      y = chain.y;
      hv = "H";
    }
  }
  const curve = near.find((entity) =>
    distanceToEntity(local.x, local.y, entity) * scale < ON_CURVE_PX);
  if (curve) {
    const on = { kind: "on", target: { kind: "on", geo: curve.id } };
    if (!hv) {
      const q = nearestOnEntity(curve, local.x, local.y);
      if (q) return { ...q, ...none, ...on, wake, guides: [], hv: null };
    } else {
      // Sur la courbe ET dans l'axe de la chaîne : là où l'axe la coupe.
      let hit = null, hitD = SNAP_PX;
      for (const h of axisCrossings(curve, hv, hv === "H" ? chain.y : chain.x)) {
        const d = screenDistance(h);
        if (d < hitD) { hit = h; hitD = d; }
      }
      if (hit) {
        return { ...hit, ...none, ...on, wake, guides: [chain], hv };
      }
    }
  }
  const tol = (SNAP_PX * 0.7) / scale;
  let alignX = null, alignY = null;
  for (const p of points) {
    if (chain && p.x === chain.x && p.y === chain.y) continue;
    if (!alignX && hv !== "V" && Math.abs(p.x - x) < tol) alignX = p;
    if (!alignY && hv !== "H" && Math.abs(p.y - y) < tol) alignY = p;
  }
  if (alignX) { x = alignX.x; guides.push(alignX); }
  if (alignY) { y = alignY.y; guides.push(alignY); }
  if (hv && chain) guides.push(chain);
  if (gridStep) {
    if (!guides.some((g) => g.x === x)) x = Math.round(x / gridStep) * gridStep;
    if (!guides.some((g) => g.y === y)) y = Math.round(y / gridStep) * gridStep;
  }
  return { x, y, ...none, wake, guides, hv };
}

/**
 * La cible qu'un clic `{ x, y, target?, onPoint?, suspended? }` a
 * accrochée, ou null. Un clic Ctrl n'accroche rien. Le moteur trouve seul
 * un point existant exactement au même endroit (la fin de la ligne
 * précédente d'une chaîne) : l'état de l'interface peut avoir un tracé de
 * retard.
 */
export function snapTarget(click) {
  if (!click || click.suspended) return null;
  if (click.target) return click.target;
  if (!click.onPoint) return null;
  return { geo: click.onPoint.geo, point: click.onPoint.point };
}

/** La cible si c'est un point d'esquisse (pas un milieu, une courbe…). */
function pointTarget(click) {
  const target = snapTarget(click);
  return target && !target.kind ? target : null;
}

/** `snaps` sans les rôles vides : le moteur n'accroche que ceux-là. */
function compact(snaps) {
  return Object.fromEntries(Object.entries(snaps).filter(([, value]) =>
    value != null && !(Array.isArray(value) && !value.length)));
}

/** Les points d'esquisse posés sur la courbe tracée. */
function targets(clicks) {
  return (clicks ?? []).map(pointTarget).filter(Boolean);
}

/** Ligne de `a` à `b`. */
export function lineSnaps(a, b) {
  return compact({ start: snapTarget(a), end: snapTarget(b) });
}

/** Point d'esquisse posé par le clic `p`. */
export function pointSnaps(p) {
  return compact({ at: snapTarget(p) });
}

/** Cercle : son centre et les clics posés sur lui. */
export function circleSnaps(center, on = []) {
  return compact({ center: snapTarget(center), on: targets(on) });
}

/** Arc : centre, bouts (angle a1 puis a2), clics posés sur l'arc. */
export function arcSnaps({ center = null, start = null, end = null, on = [] }) {
  return compact({ center: snapTarget(center), start: snapTarget(start),
                   end: snapTarget(end), on: targets(on) });
}

/** Le clic est-il sur le cercle (c, r) ? (le bout d'un arc par son centre) */
export function onCircle(click, c, r) {
  return Math.abs(Math.hypot(click.x - c.x, click.y - c.y) - r) < SNAP_TOL;
}

/** Rectangle : coins (x1, y1) et (x2, y2), et son centre s'il en a un
 *  (un point d'esquisse : les coins restent symétriques autour de lui). */
export function rectSnaps({ corner1 = null, corner2 = null, center = null }) {
  return compact({ corner1: snapTarget(corner1), corner2: snapTarget(corner2),
                   center: pointTarget(center) });
}
