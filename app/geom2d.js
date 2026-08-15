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
