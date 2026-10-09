// Navigation à la souris et sélection par cadre — module pur.
//
// Convention des modeleurs paramétriques de bureau :
//   - bouton du milieu glissé : rotation ; Ctrl + milieu : panoramique ;
//     Maj + milieu : zoom ;
//   - molette : zoom vers le curseur, molette vers l'avant = zoom arrière
//     (réglable : Paramètres → inverser) ;
//   - bouton gauche glissé dans le vide : sélection par cadre — de gauche
//     à droite, ce qui est entièrement dedans ; de droite à gauche, ce que
//     le cadre touche ;
//   - bouton droit : laissé au menu contextuel.
// main.js et sketch.js branchent ces décisions ; aucun DOM ici.

export const REVERSE_WHEEL_KEY = "freesolid.reverseWheel";

/** Geste du bouton du milieu selon les touches tenues. `rotateLocked` :
 *  l'esquisse bloque la rotation, le milieu y fait donc du panoramique. */
export function middleAction(mods = {}, { rotateLocked = false } = {}) {
  if (mods.shiftKey) return "dolly";
  if (mods.ctrlKey || mods.metaKey) return "pan";
  return rotateLocked ? "pan" : "rotate";
}

/** zoomSpeed d'OrbitControls : négatif inverse le sens de la molette.
 *  Par défaut (reversed = false), molette vers l'avant = zoom arrière. */
export function zoomSpeedFor(reversed) {
  return reversed ? 1 : -1;
}

export function readReverseWheel(storage) {
  try {
    return storage?.getItem(REVERSE_WHEEL_KEY) === "1";
  } catch {
    return false;
  }
}

export function writeReverseWheel(storage, reversed) {
  try {
    storage?.setItem(REVERSE_WHEEL_KEY, reversed ? "1" : "0");
    return true;
  } catch {
    return false;
  }
}

/** Un appui qui a voyagé de plus de `threshold` px est un glisser. */
export function isDrag(start, end, threshold = 5) {
  if (!start || !end) return false;
  return Math.hypot(end.x - start.x, end.y - start.y) > threshold;
}

/** Fenêtre (gauche → droite) ou capture (droite → gauche). */
export function boxMode(start, end) {
  return end.x >= start.x ? "window" : "crossing";
}

export function normalizeRect(a, b) {
  return {
    left: Math.min(a.x, b.x), right: Math.max(a.x, b.x),
    top: Math.min(a.y, b.y), bottom: Math.max(a.y, b.y),
  };
}

function inside(p, r) {
  return p.x >= r.left && p.x <= r.right && p.y >= r.top && p.y <= r.bottom;
}

/** Le segment [a, b] coupe-t-il le rectangle ? (Liang–Barsky) */
export function segmentHitsRect(a, b, r) {
  if (inside(a, r) || inside(b, r)) return true;
  const dx = b.x - a.x, dy = b.y - a.y;
  let t0 = 0, t1 = 1;
  const edges = [
    [-dx, a.x - r.left], [dx, r.right - a.x],
    [-dy, a.y - r.top], [dy, r.bottom - a.y],
  ];
  for (const [p, q] of edges) {
    if (p === 0) {
      if (q < 0) return false;
    } else {
      const t = q / p;
      if (p < 0) {
        if (t > t1) return false;
        if (t > t0) t0 = t;
      } else {
        if (t < t0) return false;
        if (t < t1) t1 = t;
      }
    }
  }
  return t0 <= t1;
}

/**
 * Identifiants retenus par le cadre. `items` : [{ id, points: [{x, y}] }]
 * en pixels écran, les points formant une polyligne. « window » : tous les
 * points dedans ; « crossing » : un point dedans ou un segment qui coupe.
 */
export function pickInBox(items, rect, mode) {
  const picked = [];
  for (const item of items) {
    const pts = item.points ?? [];
    if (!pts.length) continue;
    let keep;
    if (mode === "window") {
      keep = pts.every((p) => inside(p, rect));
    } else {
      keep = pts.some((p) => inside(p, rect));
      for (let i = 1; !keep && i < pts.length; i++) {
        keep = segmentHitsRect(pts[i - 1], pts[i], rect);
      }
    }
    if (keep) picked.push(item.id);
  }
  return picked;
}

function push2(out, point) {
  if (!Array.isArray(point) || point.length < 2) return;
  const x = Number(point[0]);
  const y = Number(point[1]);
  if (Number.isFinite(x) && Number.isFinite(y)) out.push([x, y]);
}

/** Points locaux qui englobent la géométrie d'esquisse (lignes, arcs,
 *  cercles, polylignes). Le cercle et l'arc prennent le rayon, pas seulement
 *  le centre. */
export function sketchLocalPoints(entities) {
  const points = [];
  for (const entity of entities ?? []) {
    if (!entity || typeof entity !== "object") continue;
    if (entity.type === "line") {
      push2(points, entity.p1);
      push2(points, entity.p2);
    } else if (entity.type === "circle" || entity.type === "arc") {
      const center = entity.c;
      const radius = Number(entity.r);
      if (Array.isArray(center) && center.length >= 2
          && Number.isFinite(radius) && radius >= 0) {
        const x = Number(center[0]);
        const y = Number(center[1]);
        if (Number.isFinite(x) && Number.isFinite(y)) {
          points.push([x - radius, y], [x + radius, y],
            [x, y - radius], [x, y + radius]);
        }
      }
      if (entity.type === "arc") {
        push2(points, entity.p1);
        push2(points, entity.p2);
      }
    } else if (entity.type === "poly") {
      for (const point of entity.points ?? []) push2(points, point);
    }
  }
  return points;
}

/** Sphère couvrant des points [x,y,z] et des sphères {center, radius}.
 *  null s'il n'y a rien à cadrer. */
export function coverBounds(points, spheres = []) {
  const samples = [];
  for (const point of points ?? []) {
    if (!Array.isArray(point) || point.length < 3) continue;
    const sample = [Number(point[0]), Number(point[1]), Number(point[2])];
    if (sample.every(Number.isFinite)) samples.push(sample);
  }
  for (const sphere of spheres ?? []) {
    const center = sphere?.center;
    const radius = Number(sphere?.radius);
    if (!Array.isArray(center) || center.length < 3
        || !Number.isFinite(radius) || radius < 0) continue;
    const c = [Number(center[0]), Number(center[1]), Number(center[2])];
    if (!c.every(Number.isFinite)) continue;
    samples.push(
      [c[0] + radius, c[1], c[2]], [c[0] - radius, c[1], c[2]],
      [c[0], c[1] + radius, c[2]], [c[0], c[1] - radius, c[2]],
      [c[0], c[1], c[2] + radius], [c[0], c[1], c[2] - radius]);
  }
  if (!samples.length) return null;
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (const sample of samples) {
    for (let axis = 0; axis < 3; axis++) {
      min[axis] = Math.min(min[axis], sample[axis]);
      max[axis] = Math.max(max[axis], sample[axis]);
    }
  }
  const center = [
    (min[0] + max[0]) / 2,
    (min[1] + max[1]) / 2,
    (min[2] + max[2]) / 2,
  ];
  let radius = 0;
  for (const sample of samples) {
    radius = Math.max(radius, Math.hypot(
      sample[0] - center[0], sample[1] - center[1], sample[2] - center[2]));
  }
  return { center, radius: Math.max(radius, 1) };
}
