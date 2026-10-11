// Clic de position sur une face (centres de perçage) : il s'aimante au
// centre d'un cercle ou d'un arc, ou à un sommet, s'il en passe un tout
// près à l'écran et dans le plan de la face. Sans Three.js.

const KEY_DIGITS = 4;

/**
 * Points remarquables des arêtes de la pièce.
 * `edges` : `{positions, indices, groups}` (protocole `pack_edges`) ;
 * un groupe peut porter `center` (cercle, arc).
 * Le sommet d'un cercle fermé n'en est pas un à l'œil : il est ignoré.
 */
export function edgeSnapPoints(edges) {
  const points = [];
  const seen = new Set();
  const positions = edges?.positions ?? [];
  const indices = edges?.indices ?? [];
  const add = (x, y, z, kind) => {
    const key = [x, y, z].map((v) => v.toFixed(KEY_DIGITS)).join(",");
    if (seen.has(key)) return;
    seen.add(key);
    points.push({ x, y, z, kind });
  };
  const at = (i) => [positions[3 * i], positions[3 * i + 1], positions[3 * i + 2]];
  for (const group of edges?.groups ?? []) {
    if (group.center) add(...group.center, "center");
    if (!group.count) continue;
    const first = at(indices[group.start]);
    const last = at(indices[group.start + group.count - 1]);
    const closed = Math.hypot(first[0] - last[0], first[1] - last[1],
      first[2] - last[2]) < 1e-6;
    if (closed && group.center) continue;
    add(...first, "vertex");
    if (!closed) add(...last, "vertex");
  }
  return points;
}

/**
 * Le point remarquable le plus proche à l'écran du point cliqué `hit`
 * (moins de `tolerancePx` pixels, dans le plan de normale `normal`), ou
 * `hit` tel quel. `project(p)` rend le pixel `{x, y}` d'un point 3D.
 * Le résultat porte `snapped` : "center", "vertex" ou null.
 */
export function snapFacePoint(hit, normal, points, project,
  { tolerancePx = 12, planeTolerance = 0.01 } = {}) {
  const screen = project(hit);
  let best = null;
  let bestDistance = tolerancePx;
  for (const point of points ?? []) {
    if (normal) {
      const offset = (point.x - hit.x) * normal[0]
        + (point.y - hit.y) * normal[1] + (point.z - hit.z) * normal[2];
      if (Math.abs(offset) > planeTolerance) continue;
    }
    const pixel = project(point);
    const distance = Math.hypot(pixel.x - screen.x, pixel.y - screen.y);
    // À égalité, un centre l'emporte sur un sommet : c'est lui qu'on vise.
    if (distance < bestDistance
        || (distance === bestDistance && best && point.kind === "center")) {
      best = point;
      bestDistance = distance;
    }
  }
  if (!best) return { x: hit.x, y: hit.y, z: hit.z, snapped: null };
  return { x: best.x, y: best.y, z: best.z, snapped: best.kind };
}
