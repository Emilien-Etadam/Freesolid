// Projection perspective ou orthographique — module pur.
//
// La vue reste pilotée comme une vue orthographique (zoom, panoramique,
// cadrage : main.js raisonne en « hauteur visible au centre de la vue »).
// En perspective, l'œil se place sur l'axe de visée à la distance où cette
// hauteur visible, au centre, est la même : basculer ne change pas la
// taille de la pièce à l'écran, seulement la fuite des lignes.

/** Angle de champ vertical de la perspective, en degrés. */
export const PERSPECTIVE_FOV = 30;

/** Distance œil–centre pour voir ``viewHeight`` au centre de la vue. */
export function perspectiveEye(viewHeight, fovDeg = PERSPECTIVE_FOV) {
  return viewHeight / (2 * Math.tan(fovDeg * Math.PI / 360));
}

/**
 * Frustum perspective équivalent à une vue orthographique : bords au
 * plan proche (``left``…``bottom``), plans proche et lointain, et le
 * recul ``back`` de l'œil par rapport à la caméra (positif : plus loin).
 */
export function perspectiveFrustum({ width, height, rigDistance,
                                     depth = 10000, fovDeg = PERSPECTIVE_FOV }) {
  const eye = perspectiveEye(height, fovDeg);
  const near = Math.max(eye * 0.01, 0.01);
  const halfH = near * height / (2 * eye);
  const halfW = near * width / (2 * eye);
  return { left: -halfW, right: halfW, top: halfH, bottom: -halfH,
           near, far: eye + depth, back: eye - rigDistance, eye };
}
