// Géométrie 2D partagée esquisse / solveur local.

// Sweep CCW p1 → p2 autour de c, comme le moteur stocke les arcs.
export function arcAngles(entity) {
  const a1 = Math.atan2(entity.p1[1] - entity.c[1],
                        entity.p1[0] - entity.c[0]);
  let a2 = Math.atan2(entity.p2[1] - entity.c[1],
                      entity.p2[0] - entity.c[0]);
  if (a2 <= a1) a2 += Math.PI * 2;
  return { a1, a2 };
}

/** Distance point → segment [a, b] (a, b = [x, y]). */
export function distancePointSegment(px, py, a, b) {
  const abx = b[0] - a[0], aby = b[1] - a[1];
  const len2 = abx * abx + aby * aby;
  if (len2 < 1e-18) return Math.hypot(px - a[0], py - a[1]);
  let t = ((px - a[0]) * abx + (py - a[1]) * aby) / len2;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (a[0] + t * abx), py - (a[1] + t * aby));
}

/** Distance réelle à l'entité en coordonnées locales d'esquisse. */
export function distanceToEntity(x, y, entity) {
  if (entity.type === "line") {
    return distancePointSegment(x, y, entity.p1, entity.p2);
  }
  if (entity.type === "circle") {
    return Math.abs(Math.hypot(x - entity.c[0], y - entity.c[1]) - entity.r);
  }
  if (entity.type === "arc") {
    const { a1, a2 } = arcAngles(entity);
    const ang = Math.atan2(y - entity.c[1], x - entity.c[0]);
    let a = ang;
    while (a < a1) a += Math.PI * 2;
    while (a > a2) a -= Math.PI * 2;
    if (a >= a1 && a <= a2) {
      return Math.abs(Math.hypot(x - entity.c[0], y - entity.c[1]) - entity.r);
    }
    // Hors balayage : plus proche extrémité.
    return Math.min(
      Math.hypot(x - entity.p1[0], y - entity.p1[1]),
      Math.hypot(x - entity.p2[0], y - entity.p2[1]));
  }
  if (entity.type === "poly" && entity.points?.length > 1) {
    let best = Infinity;
    for (let i = 0; i < entity.points.length - 1; i++) {
      const d = distancePointSegment(
        x, y, entity.points[i], entity.points[i + 1]);
      if (d < best) best = d;
    }
    return best;
  }
  return Infinity;
}

/**
 * Clic en chaîne (ligne / spline) : "add" le point, ou "finish" si le
 * curseur est dans le seuil de snap du précédent.
 *
 * prev / next sont en pixels écran (même espace que SNAP_PX).
 * prev null = premier point de la chaîne → toujours "add".
 * Seuil strict (< snapPx), identique au snap des extrémités.
 */
export function chainClickAction(prev, next, snapPx) {
  if (prev == null) return "add";
  return Math.hypot(next.x - prev.x, next.y - prev.y) < snapPx
    ? "finish"
    : "add";
}

/** Cote pilotante (valeur éditable), par opposition à une relation sèche. */
const DRIVING_CONSTRAINTS = new Set([
  "Distance", "DistanceX", "DistanceY", "Radius", "Diameter", "Angle",
]);

export function isDrivingConstraint(constraint) {
  return Boolean(constraint)
    && DRIVING_CONSTRAINTS.has(constraint.type)
    && Number.isFinite(constraint.value);
}

function fmtMm(value) {
  return Number(value).toFixed(2);
}

export function circlePoints(cx, cy, r, segments = 48) {
  if (!(r > 0)) return [];
  const pts = [];
  for (let i = 0; i <= segments; i++) {
    const a = (i / segments) * Math.PI * 2;
    pts.push({ x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) });
  }
  return pts;
}

export function arcPoints(cx, cy, r, a1, a2, segments = 32) {
  if (!(r > 0)) return [];
  let sweep = a2 - a1;
  if (sweep <= 0) sweep += Math.PI * 2;
  const pts = [];
  for (let i = 0; i <= segments; i++) {
    const a = a1 + (i / segments) * sweep;
    pts.push({ x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) });
  }
  return pts;
}

export function ellipsePoints(cx, cy, rx, ry, angle, segments = 48) {
  if (!(rx > 0) || !(ry > 0)) return [];
  const cos = Math.cos(angle), sin = Math.sin(angle);
  const pts = [];
  for (let i = 0; i <= segments; i++) {
    const a = (i / segments) * Math.PI * 2;
    const lx = rx * Math.cos(a), ly = ry * Math.sin(a);
    pts.push({
      x: cx + lx * cos - ly * sin,
      y: cy + lx * sin + ly * cos,
    });
  }
  return pts;
}

function normalizeAngle(angle, origin) {
  let a = angle;
  while (a < origin) a += Math.PI * 2;
  while (a >= origin + Math.PI * 2) a -= Math.PI * 2;
  return a;
}

function semicircleThrough(cx, cy, r, from, through, segments) {
  const mid = normalizeAngle(through, from);
  if (mid > 0 && mid < Math.PI) {
    return arcPoints(cx, cy, r, from, from + Math.PI, segments);
  }
  return arcPoints(cx, cy, r, from + Math.PI, from + Math.PI * 2, segments);
}

/** Oblong : deux demi-cercles et deux segments, centres `a`/`b`, largeur. */
export function slotPoints(a, b, width, segments = 16) {
  const dx = b.x - a.x, dy = b.y - a.y;
  const len = Math.hypot(dx, dy);
  if (len <= 0 || !(width > 0)) return [];
  const ux = dx / len, uy = dy / len;
  const px = -uy, py = ux;
  const r = width / 2;
  const aL = { x: a.x + px * r, y: a.y + py * r };
  const bL = { x: b.x + px * r, y: b.y + py * r };
  const aR = { x: a.x - px * r, y: a.y - py * r };
  const angP = Math.atan2(py, px);
  const angM = Math.atan2(-py, -px);
  const angU = Math.atan2(uy, ux);
  const angMU = Math.atan2(-uy, -ux);
  const capB = semicircleThrough(b.x, b.y, r, angP, angU, segments);
  const capA = semicircleThrough(a.x, a.y, r, angM, angMU, segments);
  return [aL, bL, ...capB.slice(1), aR, ...capA.slice(1)];
}

export function polygonPoints(cx, cy, vx, vy, sides) {
  if (!(sides >= 3)) return [];
  const radius = Math.hypot(vx - cx, vy - cy);
  if (!(radius > 0)) return [];
  const a0 = Math.atan2(vy - cy, vx - cx);
  const pts = [];
  for (let i = 0; i <= sides; i++) {
    const a = a0 + (i / sides) * Math.PI * 2;
    pts.push({ x: cx + radius * Math.cos(a), y: cy + radius * Math.sin(a) });
  }
  return pts;
}

/**
 * Polyligne d'aperçu d'outil d'esquisse, en coordonnées locales.
 * `pending` est le point d'ancrage déjà posé (`pendingCircle`, etc.).
 */
export function sketchPreviewPoints(tool, pending, cursor) {
  if (!pending || !cursor) return [];
  if (tool === "circle") {
    return circlePoints(pending.x, pending.y,
      Math.hypot(cursor.x - pending.x, cursor.y - pending.y));
  }
  if (tool === "ellipse") {
    if (!pending.c) return [];
    if (!pending.major) {
      return circlePoints(pending.c.x, pending.c.y,
        Math.hypot(cursor.x - pending.c.x, cursor.y - pending.c.y));
    }
    const { c, major } = pending;
    const rx = Math.hypot(major.x - c.x, major.y - c.y);
    if (!(rx > 0)) return [];
    const angle = Math.atan2(major.y - c.y, major.x - c.x);
    const ux = (major.x - c.x) / rx, uy = (major.y - c.y) / rx;
    const ry = Math.abs(
      ux * (cursor.y - c.y) - uy * (cursor.x - c.x));
    return ellipsePoints(c.x, c.y, rx, ry, angle);
  }
  if (tool === "slot") {
    if (!pending.a) return [];
    if (!pending.b) return [pending.a, cursor];
    const { a, b } = pending;
    const len = Math.hypot(b.x - a.x, b.y - a.y);
    if (len <= 0) return [];
    const width = 2 * Math.abs(
      ((b.x - a.x) * (a.y - cursor.y)
        - (b.y - a.y) * (a.x - cursor.x)) / len);
    return slotPoints(a, b, width);
  }
  if (tool === "arc") {
    if (!pending.c) return [];
    if (!pending.start) {
      return circlePoints(pending.c.x, pending.c.y,
        Math.hypot(cursor.x - pending.c.x, cursor.y - pending.c.y));
    }
    const { c, start } = pending;
    const r = Math.hypot(start.x - c.x, start.y - c.y);
    if (!(r > 0)) return [];
    const a1 = Math.atan2(start.y - c.y, start.x - c.x);
    let a2 = Math.atan2(cursor.y - c.y, cursor.x - c.x);
    if (a2 <= a1) a2 += Math.PI * 2;
    return arcPoints(c.x, c.y, r, a1, a2);
  }
  if (tool === "polygon") {
    if (!pending.c || pending.sides == null) return [];
    return polygonPoints(
      pending.c.x, pending.c.y, cursor.x, cursor.y, pending.sides);
  }
  return [];
}

function fmtXy(point) {
  return `(${fmtMm(point[0])}, ${fmtMm(point[1])})`;
}

/** Titre PropertyManager — vocabulaire SolidWorks 2025, en français. */
export function entityKindTitle(entity) {
  if (!entity) return "Entité";
  if (entity.type === "line") return "Ligne";
  if (entity.type === "circle") return "Cercle";
  if (entity.type === "arc") return "Arc";
  if (entity.type === "poly") {
    if (entity.kind === "ellipse") return "Ellipse";
    if (entity.kind === "spline") return "Spline";
    return "Polyligne";
  }
  return "Entité";
}

/**
 * Propriétés d'entité en lecture seule (mm au 1/100, angle au 1/100 °).
 * L'édition numérique passe par la cotation intelligente.
 */
export function entityPropertyLines(entity) {
  if (!entity) return [];
  if (entity.type === "line" && entity.p1 && entity.p2) {
    const length = Math.hypot(
      entity.p2[0] - entity.p1[0], entity.p2[1] - entity.p1[1]);
    return [
      `Longueur : ${fmtMm(length)} mm`,
      `Départ : ${fmtXy(entity.p1)} mm`,
      `Arrivée : ${fmtXy(entity.p2)} mm`,
    ];
  }
  if (entity.type === "circle" && entity.c && entity.r != null) {
    return [
      `Centre : ${fmtXy(entity.c)} mm`,
      `Rayon : ${fmtMm(entity.r)} mm`,
      `Diamètre : ${fmtMm(entity.r * 2)} mm`,
    ];
  }
  if (entity.type === "arc" && entity.c && entity.r != null
      && entity.p1 && entity.p2) {
    const { a1, a2 } = arcAngles(entity);
    const sweepDeg = (a2 - a1) * 180 / Math.PI;
    return [
      `Centre : ${fmtXy(entity.c)} mm`,
      `Rayon : ${fmtMm(entity.r)} mm`,
      `Angle balayé : ${fmtMm(sweepDeg)} °`,
    ];
  }
  if (entity.type === "poly" && entity.kind === "ellipse") {
    const lines = [];
    if (entity.c) lines.push(`Centre : ${fmtXy(entity.c)} mm`);
    if (entity.rx != null) lines.push(`Grand rayon : ${fmtMm(entity.rx)} mm`);
    if (entity.ry != null) lines.push(`Petit rayon : ${fmtMm(entity.ry)} mm`);
    return lines;
  }
  if (entity.type === "poly") {
    const n = entity.npoints ?? entity.points?.length ?? 0;
    return [`Nombre de points : ${n}`];
  }
  return [];
}
