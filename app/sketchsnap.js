// Magnétisme de l'esquisse : où tombe un clic, et ce qu'il accroche.
// Pur (sans Three.js) : sketch.js fournit la projection à l'écran.
//
// L'interface décide : un clic accroché au centre d'un cercle devient une
// cible { geo, point } que le tracé envoie au moteur dans `snaps`
// (engine/sketchsnap.py), qui pose la relation dans la même opération.
// Un tracé de l'interface envoie toujours `snaps`, même vide.

/** Rayon d'accrochage, en pixels écran. */
export const SNAP_PX = 12;
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

/**
 * Où tombe le curseur. Dans l'ordre : un point existant (à l'écran), l'axe
 * horizontal ou vertical depuis le point précédent de la chaîne, puis
 * l'alignement sur un point existant (un repère, sans relation), puis la
 * grille.
 *
 * `local` : le curseur dans l'esquisse ; `cursor` : en pixels écran.
 * `toScreen(x, y)` rend le pixel `{ x, y }` d'un point de l'esquisse.
 * `chain` : le point précédent d'une ligne en cours, ou null.
 * `gridStep` : le pas de la grille si elle accroche, sinon null.
 * `suspended` (Ctrl maintenu) : le point reste où est le curseur.
 *
 * Rend `{ x, y, onPoint, guides, hv, suspended }` : `onPoint` le point
 * accroché, `guides` les points d'où partent les lignes d'aide, `hv` "H"
 * ou "V" quand la chaîne s'aligne.
 */
export function snapSketchPoint(local, cursor, {
  points, toScreen, chain = null, gridStep = null, suspended = false,
}) {
  if (suspended) {
    return { x: local.x, y: local.y, onPoint: null, guides: [], hv: null,
             suspended: true };
  }
  for (const p of points) {
    const s = toScreen(p.x, p.y);
    if (Math.hypot(s.x - cursor.x, s.y - cursor.y) < SNAP_PX) {
      return { x: p.x, y: p.y, onPoint: p, guides: [], hv: null };
    }
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
  // Tolérance en unités d'esquisse : les axes de l'esquisse ne suivent
  // pas forcément ceux de l'écran.
  const s0 = toScreen(0, 0), s1 = toScreen(1, 0);
  const tol = (SNAP_PX * 0.7) / (Math.hypot(s1.x - s0.x, s1.y - s0.y) || 1);
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
  return { x, y, onPoint: null, guides, hv };
}

/**
 * Le point d'esquisse qu'un clic `{ x, y, onPoint?, suspended? }` a
 * accroché, en cible `{ geo, point }`, ou null. Un clic Ctrl n'accroche
 * rien. Le moteur trouve seul un point existant exactement au même
 * endroit (la fin de la ligne précédente d'une chaîne) : l'état de
 * l'interface peut avoir un tracé de retard.
 */
export function snapTarget(click) {
  if (!click?.onPoint || click.suspended) return null;
  return { geo: click.onPoint.geo, point: click.onPoint.point };
}

/** `snaps` sans les rôles vides : le moteur n'accroche que ceux-là. */
function compact(snaps) {
  return Object.fromEntries(Object.entries(snaps).filter(([, value]) =>
    value != null && !(Array.isArray(value) && !value.length)));
}

function targets(clicks) {
  return (clicks ?? []).map(snapTarget).filter(Boolean);
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

/** Rectangle : coins (x1, y1) et (x2, y2), et son centre s'il en a un. */
export function rectSnaps({ corner1 = null, corner2 = null, center = null }) {
  return compact({ corner1: snapTarget(corner1), corner2: snapTarget(corner2),
                   center: snapTarget(center) });
}
