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

/** Où la droite passant par `origin`, de direction `dir`, coupe
 *  l'entité. */
export function crossingsAlong(entity, origin, dir) {
  const line = { infinite: true, seg: [[origin.x, origin.y],
    [origin.x + dir.x, origin.y + dir.y]] };
  return pieces(entity).flatMap((piece) => pieceCrossings(line, piece));
}

/** Points où une ligne partie de `from` touche le cercle ou l'arc en
 *  tangente. */
export function tangentPoints(entity, from) {
  if (entity?.type !== "circle" && entity?.type !== "arc") return [];
  const [cx, cy] = entity.c;
  const d = Math.hypot(from.x - cx, from.y - cy);
  if (d <= entity.r + 1e-9) return [];
  const base = Math.atan2(from.y - cy, from.x - cx);
  const spread = Math.acos(entity.r / d);
  const sweep = entity.type === "arc" ? arcAngles(entity) : null;
  return [base + spread, base - spread]
    .filter((a) => !sweep || inSweep(a, sweep.a1, sweep.a2))
    .map((a) => ({ x: cx + entity.r * Math.cos(a), y: cy + entity.r * Math.sin(a) }));
}

/** Une direction (parallèle, perpendiculaire, tangente) attire de moins
 *  loin que l'horizontale ou la verticale. */
export const DIRECTION_PX = 8;
/** Un pas d'angle n'est qu'un repère : il attire de près, et seulement à
 *  quelques degrés. */
export const ANGLE_PX = 6;
const ANGLE_TOL = 2.5 * Math.PI / 180;

function unit(x, y) {
  const n = Math.hypot(x, y) || 1;
  return { x: x / n, y: y / n };
}

const parallelDirs = (a, b) => Math.abs(a.x * b.y - a.y * b.x) < 1e-9;

/**
 * Directions qu'une ligne partie du point `chain` peut prendre, la
 * relation qu'elles posent et leur tolérance en pixels :
 *
 * - tangente au cercle ou à l'arc dont `chain` est un bout ou un point ;
 * - horizontale, verticale (le moteur les voit dans la géométrie) ;
 * - parallèle ou perpendiculaire aux lignes de référence : celle qui
 *   finit en `chain` (la ligne précédente), celle où `chain` est posé,
 *   et les lignes survolées récemment (`woken`) ;
 * - les pas de `angleStep` degrés, sans relation, comptés depuis l'axe X
 *   ou depuis la ligne précédente.
 *
 * `chain.target` : où le premier point de la chaîne est posé. Plus loin
 * dans la chaîne, un point posé sur un cercle ne propose pas la
 * tangente : il y est déjà par la ligne précédente, et Sketcher verrait
 * la tangence en plus comme redondante.
 */
export function chainDirections(chain, entities, { woken = [], angleStep = 0 } = {}) {
  const at = (p) => Math.abs(p[0] - chain.x) < 1e-9 && Math.abs(p[1] - chain.y) < 1e-9;
  const byId = new Map(entities.map((e) => [e.id, e]));
  const seat = chain.target ?? null;
  const on = seat?.kind && seat.geo != null ? byId.get(seat.geo) : null;
  const previous = entities.filter((e) => e.type === "line" && (at(e.p1) || at(e.p2)));
  const refs = [...previous];
  if (on?.type === "line") refs.push(on);
  for (const id of woken) {
    const e = byId.get(id);
    if (e?.type === "line") refs.push(e);
  }
  const out = [];
  const add = (candidate) => {
    if (!out.some((c) => parallelDirs(c.dir, candidate.dir))) out.push(candidate);
  };
  // La tangente d'abord : au bout du haut d'un arc, elle est horizontale
  // et c'est elle que l'on veut (le moteur pose l'horizontale en plus).
  for (const e of entities) {
    if (e.type !== "circle" && e.type !== "arc") continue;
    if (!(e === on || (e.type === "arc" && (at(e.p1) || at(e.p2))))) continue;
    const r = unit(chain.x - e.c[0], chain.y - e.c[1]);
    add({ dir: { x: -r.y, y: r.x }, tol: DIRECTION_PX,
          direction: { kind: "tangent", geo: e.id } });
  }
  add({ dir: { x: 1, y: 0 }, hv: "H", tol: SNAP_PX });
  add({ dir: { x: 0, y: 1 }, hv: "V", tol: SNAP_PX });
  for (const ref of new Set(refs)) {
    const d = unit(ref.p2[0] - ref.p1[0], ref.p2[1] - ref.p1[1]);
    add({ dir: d, tol: DIRECTION_PX,
          direction: { kind: "parallel", geo: ref.id } });
    add({ dir: { x: -d.y, y: d.x }, tol: DIRECTION_PX,
          direction: { kind: "perpendicular", geo: ref.id } });
  }
  if (angleStep > 0) {
    const line = previous[0];
    const base = line ? Math.atan2(line.p2[1] - line.p1[1], line.p2[0] - line.p1[0]) : 0;
    const step = angleStep * Math.PI / 180;
    for (let k = 1; k * step < Math.PI - 1e-9; k++) {
      add({ dir: { x: Math.cos(base + k * step), y: Math.sin(base + k * step) },
            tol: ANGLE_PX, angle: true });
    }
  }
  return out;
}

/**
 * Où tombe le curseur. Dans l'ordre : un point existant (à l'écran) ; le
 * milieu, un quadrant ou un croisement d'une entité survolée, ou le point
 * où la ligne en cours la toucherait en tangente ; une direction depuis
 * le point précédent de la chaîne (chainDirections) ; avec Maj, une
 * longueur ronde ; la courbe survolée (là où la direction la coupe, s'il
 * y en a une) ; puis l'alignement sur un point existant (un repère, sans
 * relation), puis la grille.
 *
 * `local` : le curseur dans l'esquisse ; `cursor` : en pixels écran.
 * `toScreen(x, y)` rend le pixel `{ x, y }` d'un point de l'esquisse.
 * `points` : les points d'esquisse (sketchSnapPoints) ; `entities` : les
 * entités visibles, pour les milieux, quadrants, croisements et courbes.
 * `chain` : le point précédent d'une ligne en cours, ou null ; `woken`,
 * `angleStep` : voir chainDirections. `lengthStep` (Maj maintenu) : le
 * pas des longueurs, ou null.
 * `gridStep` : le pas de la grille si elle accroche, sinon null.
 * `suspended` (Ctrl maintenu) : le point reste où est le curseur.
 *
 * Rend `{ x, y, onPoint, target, kind, direction, hover, wake, guides,
 * rays, hv, suspended }` : `onPoint` le point d'esquisse accroché,
 * `target` la cible à envoyer au moteur et `kind` sa sorte ("point",
 * "midpoint", "quadrant", "intersection", "on"), `direction` celle de la
 * ligne ({ kind: "parallel" | "perpendicular" | "tangent", geo }),
 * `hover` l'entité survolée, `wake` ses points remarquables (à montrer),
 * `guides` les points d'où partent les lignes d'alignement, `rays` les
 * lignes d'aide de la direction ({ x1, y1, x2, y2, relation } : avec
 * relation, ou un simple pas d'angle), `hv` "H" ou "V".
 */
export function snapSketchPoint(local, cursor, {
  points, entities = [], toScreen, chain = null, woken = [], angleStep = 0,
  lengthStep = null, gridStep = null, suspended = false,
}) {
  const none = { onPoint: null, target: null, kind: null, direction: null,
                 hover: null, wake: [], guides: [], rays: [], hv: null };
  if (suspended) {
    return { x: local.x, y: local.y, ...none, suspended: true };
  }
  for (const p of points) {
    const s = toScreen(p.x, p.y);
    if (Math.hypot(s.x - cursor.x, s.y - cursor.y) < SNAP_PX) {
      return { x: p.x, y: p.y, ...none, onPoint: p, kind: "point",
               target: { geo: p.geo, point: p.point } };
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
  const seen = { hover: near[0]?.id ?? null,
                 wake: near.length ? entityFeatures(near[0]) : [] };
  // Une ligne d'aide depuis le point de la chaîne, un peu au-delà du point.
  const ray = (p, relation) => {
    const d = unit(p.x - chain.x, p.y - chain.y), over = 40 / scale;
    return { x1: chain.x, y1: chain.y, x2: p.x + d.x * over, y2: p.y + d.y * over,
             relation };
  };
  const special = near.flatMap(entityFeatures);
  for (let i = 0; i < near.length; i++) {
    for (let j = i + 1; j < near.length; j++) {
      for (const hit of entityCrossings(near[i], near[j])) {
        special.push({ ...hit, kind: "intersection", target: {
          kind: "intersection", geos: [near[i].id, near[j].id] } });
      }
    }
    if (chain) {
      for (const hit of tangentPoints(near[i], chain)) {
        special.push({ ...hit, kind: "on", target: { kind: "on", geo: near[i].id },
                       direction: { kind: "tangent", geo: near[i].id } });
      }
    }
  }
  let best = null, bestD = SNAP_PX;
  for (const candidate of special) {
    const d = screenDistance(candidate);
    if (d < bestD) { best = candidate; bestD = d; }
  }
  if (best) {
    return { x: best.x, y: best.y, ...none, ...seen, kind: best.kind,
             target: best.target, direction: best.direction ?? null,
             rays: best.direction ? [ray(best, true)] : [] };
  }
  let { x, y } = local;
  let along = null;
  if (chain) {
    let bestDir = Infinity;
    const vx = local.x - chain.x, vy = local.y - chain.y;
    const reach = Math.hypot(vx, vy);
    for (const c of chainDirections(chain, entities, { woken, angleStep })) {
      const t = vx * c.dir.x + vy * c.dir.y;
      const q = { x: chain.x + t * c.dir.x, y: chain.y + t * c.dir.y };
      const d = screenDistance(q);
      if (d >= c.tol || d >= bestDir) continue;
      if (c.angle && Math.abs(vx * c.dir.y - vy * c.dir.x) > reach * Math.sin(ANGLE_TOL)) {
        continue;
      }
      along = { ...c, q };
      bestDir = d;
    }
    if (along) {
      ({ x, y } = along.q);
      // L'horizontale tombe pile : le moteur la voit dans la géométrie.
      if (along.hv === "H") y = chain.y;
      if (along.hv === "V") x = chain.x;
    }
  }
  const hv = along?.hv ?? null;
  const direction = along?.direction ?? null;
  const relation = !!(hv || direction);
  if (chain && lengthStep) {
    // Maj : une longueur ronde, dans la direction trouvée ou celle du
    // curseur.
    const d = along?.dir ?? unit(x - chain.x, y - chain.y);
    const t = (x - chain.x) * d.x + (y - chain.y) * d.y;
    const n = Math.round(t / lengthStep) || Math.sign(t) || 1;
    x = chain.x + n * lengthStep * d.x;
    y = chain.y + n * lengthStep * d.y;
    if (hv === "H") y = chain.y;
    if (hv === "V") x = chain.x;
    const p = { x, y };
    return { x, y, ...none, ...seen, direction, hv, rays: [ray(p, relation)] };
  }
  const curve = near.find((entity) =>
    distanceToEntity(local.x, local.y, entity) * scale < ON_CURVE_PX);
  if (curve) {
    const on = { kind: "on", target: { kind: "on", geo: curve.id } };
    if (!along) {
      const q = nearestOnEntity(curve, local.x, local.y);
      if (q) return { ...q, ...none, ...seen, ...on };
    } else {
      // Sur la courbe ET dans la direction : là où elle la coupe.
      let hit = null, hitD = SNAP_PX;
      for (const h of crossingsAlong(curve, chain, along.dir)) {
        const d = screenDistance(h);
        if (d < hitD) { hit = h; hitD = d; }
      }
      if (hit) {
        if (hv === "H") hit.y = chain.y;
        if (hv === "V") hit.x = chain.x;
        return { ...hit, ...none, ...seen, ...on, direction, hv,
                 rays: [ray(hit, relation)] };
      }
    }
  }
  if (along && !hv) {
    // Une direction oblique : ni alignement ni grille, qui l'écarteraient.
    return { x, y, ...none, ...seen, direction, rays: [ray({ x, y }, relation)] };
  }
  const guides = [];
  const tol = (SNAP_PX * 0.7) / scale;
  let alignX = null, alignY = null;
  for (const p of points) {
    if (chain && p.x === chain.x && p.y === chain.y) continue;
    if (!alignX && hv !== "V" && Math.abs(p.x - x) < tol) alignX = p;
    if (!alignY && hv !== "H" && Math.abs(p.y - y) < tol) alignY = p;
  }
  if (alignX) { x = alignX.x; guides.push(alignX); }
  if (alignY) { y = alignY.y; guides.push(alignY); }
  if (gridStep) {
    if (hv !== "V" && !guides.some((g) => g.x === x)) x = Math.round(x / gridStep) * gridStep;
    if (hv !== "H" && !guides.some((g) => g.y === y)) y = Math.round(y / gridStep) * gridStep;
  }
  return { x, y, ...none, ...seen, guides, hv,
           rays: along ? [ray({ x, y }, relation)] : [] };
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

/** Ligne de `a` à `b` ; la direction est celle du second clic. */
export function lineSnaps(a, b) {
  return compact({ start: snapTarget(a), end: snapTarget(b),
                   direction: b && !b.suspended ? b.direction ?? null : null });
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
