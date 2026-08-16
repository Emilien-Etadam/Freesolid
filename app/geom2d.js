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

function fmtMm(value) {
  return Number(value).toFixed(2);
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
