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
