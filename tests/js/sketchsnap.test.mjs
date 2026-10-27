// Magnétisme de l'esquisse : où tombe un clic, ce qu'il envoie au moteur.
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  ON_CURVE_PX, ORIGIN_GEO, SNAP_PX, arcSnaps, chainDirections, circleSnaps,
  crossingsAlong, tangentPoints,
  entityCrossings, entityFeatures, lineSnaps, nearestOnEntity, onCircle,
  pointSnaps, rectSnaps, sketchEndpoints, sketchSnapPoints, snapSketchPoint,
  snapTarget,
} from "../../app/sketchsnap.js";

// Vue de dessus, 1 mm = 10 px : le pixel d'un point est (10x, -10y).
const toScreen = (x, y) => ({ x: x * 10, y: -y * 10 });
const cursorAt = (x, y) => toScreen(x, y);

const ENTITIES = [
  { id: 0, type: "line", p1: [10, -20], p2: [30, -20] },
  { id: 1, type: "circle", c: [50, 30], r: 5 },
  { id: 2, type: "arc", c: [80, 0], r: 5, p1: [85, 0], p2: [80, 5] },
  { id: 3, type: "point", p1: [-40, 10] },
  { id: 4, type: "poly", kind: "spline", points: [[0, 50], [5, 55], [10, 50]] },
];

function snapAt(x, y, opts = {}) {
  return snapSketchPoint({ x, y }, cursorAt(x, y), {
    points: sketchSnapPoints(ENTITIES), toScreen, ...opts });
}

describe("points d'accrochage", () => {
  it("bouts, centres, points et bouts de spline, numérotés comme Sketcher", () => {
    const got = [...sketchEndpoints(ENTITIES)].map((p) => [p.geo, p.point]);
    assert.deepEqual(got, [
      [0, 1], [0, 2], [1, 3], [2, 1], [2, 2], [2, 3], [3, 1], [4, 1], [4, 2]]);
  });

  it("un calque masqué n'offre rien ; l'origine est toujours là", () => {
    const pts = sketchSnapPoints(ENTITIES, new Set([0, 1, 2, 3, 4]));
    assert.deepEqual(pts, [{ geo: ORIGIN_GEO, point: 1, x: 0, y: 0 }]);
  });

  it("une spline fermée n'a qu'un bout", () => {
    const closed = [{ id: 7, type: "poly", kind: "spline",
      points: [[0, 0], [5, 5], [0, 0]] }];
    assert.deepEqual([...sketchEndpoints(closed)].map((p) => p.point), [1]);
  });
});

describe("où tombe le curseur", () => {
  it("à moins de SNAP_PX d'un centre de cercle, il s'y accroche", () => {
    const near = (SNAP_PX - 1) / 10;
    const s = snapAt(50 + near, 30);
    assert.deepEqual([s.x, s.y], [50, 30]);
    assert.deepEqual([s.onPoint.geo, s.onPoint.point], [1, 3]);
  });

  it("au-delà, rien n'accroche", () => {
    const s = snapAt(50 + (SNAP_PX + 1) / 10, 33);
    assert.equal(s.onPoint, null);
  });

  it("l'origine accroche aussi", () => {
    const s = snapSketchPoint({ x: 0.3, y: -0.2 }, cursorAt(0.3, -0.2), {
      points: sketchSnapPoints([]), toScreen });
    assert.deepEqual(s.onPoint, { geo: ORIGIN_GEO, point: 1, x: 0, y: 0 });
  });

  it("la chaîne s'aligne à l'horizontale ou à la verticale", () => {
    const chain = { x: 100, y: 100 };
    const h = snapAt(130, 100.5, { chain });
    assert.equal(h.hv, "H");
    assert.equal(h.y, 100);
    assert.deepEqual(h.rays.map((r) => [r.x1, r.y1, r.relation]),
      [[100, 100, true]]);
    const v = snapAt(100.4, 140, { chain });
    assert.equal(v.hv, "V");
    assert.equal(v.x, 100);
  });

  it("l'alignement sur un point existant donne un repère, sans cible", () => {
    const s = snapAt(-40.5, 70);
    assert.equal(s.x, -40);
    assert.equal(s.onPoint, null);
    assert.deepEqual(s.guides.map((g) => [g.geo, g.point]), [[3, 1]]);
  });

  it("la grille arrondit, sauf sur l'axe d'un repère", () => {
    const s = snapAt(33.3, 71.6, { gridStep: 5 });
    assert.deepEqual([s.x, s.y], [35, 70]);
    const kept = snapAt(-40.5, 71.6, { gridStep: 5 });
    assert.deepEqual([kept.x, kept.y], [-40, 70]);
  });

  it("Ctrl maintenu : le point reste sous le curseur, sans accrochage", () => {
    const s = snapAt(50.3, 30, { suspended: true, chain: { x: 0, y: 30 },
      gridStep: 5 });
    assert.deepEqual(s, { x: 50.3, y: 30, onPoint: null, target: null,
      kind: null, direction: null, hover: null, wake: [], guides: [],
      rays: [], hv: null, suspended: true });
  });
});

const near = (a, b, eps = 1e-9) => Math.abs(a - b) < eps;

function snapNear(x, y, entities, opts = {}) {
  return snapSketchPoint({ x, y }, cursorAt(x, y), {
    points: sketchSnapPoints(entities), entities, toScreen, ...opts });
}

describe("points remarquables et courbes", () => {
  it("milieu d'une ligne, milieu et quadrants couverts d'un arc", () => {
    assert.deepEqual(entityFeatures(ENTITIES[0]).map((f) => [f.kind, f.x, f.y]),
      [["midpoint", 20, -20]]);
    const arc = entityFeatures(ENTITIES[2]);
    assert.deepEqual(arc.map((f) => f.kind), ["midpoint", "quadrant", "quadrant"]);
    assert.ok(near(arc[0].x, 80 + 5 * Math.SQRT1_2) && near(arc[0].y, 5 * Math.SQRT1_2));
    assert.deepEqual(arc.slice(1).map((f) => f.target.quadrant), [0, 1]);
    const circle = entityFeatures(ENTITIES[1]);
    assert.deepEqual(circle.map((f) => [f.target.quadrant, f.x, f.y]),
      [[0, 55, 30], [1, 50, 35], [2, 45, 30], [3, 50, 25]]);
  });

  it("le point le plus proche sur une ligne, un cercle, un arc", () => {
    assert.deepEqual(nearestOnEntity(ENTITIES[0], 25, -10), { x: 25, y: -20 });
    const q = nearestOnEntity(ENTITIES[1], 60, 30);
    assert.ok(near(q.x, 55) && near(q.y, 30));
    assert.equal(nearestOnEntity(ENTITIES[2], 70, -5), null); // hors balayage
  });

  it("croisements : deux lignes, une ligne et un cercle, deux cercles", () => {
    const a = { id: 10, type: "line", p1: [0, 0], p2: [30, 30] };
    const b = { id: 11, type: "line", p1: [0, 20], p2: [40, -20] };
    assert.deepEqual(entityCrossings(a, b), [{ x: 10, y: 10 }]);
    const short = { id: 12, type: "line", p1: [0, 20], p2: [5, 15] };
    assert.deepEqual(entityCrossings(a, short), []);
    const c = { id: 13, type: "circle", c: [0, 0], r: 10 };
    const h = { id: 14, type: "line", p1: [-20, 5], p2: [20, 5] };
    const xs = entityCrossings(h, c).map((p) => p.x).sort((u, v) => u - v);
    assert.ok(near(xs[0], -Math.sqrt(75)) && near(xs[1], Math.sqrt(75)));
    const d = { id: 15, type: "circle", c: [10, 0], r: 10 };
    assert.equal(entityCrossings(c, d).length, 2);
    // Un arc ne garde que les croisements de son balayage.
    const arc = { id: 16, type: "arc", c: [0, 0], r: 10, p1: [10, 0], p2: [0, 10] };
    assert.equal(entityCrossings(h, arc).length, 1);
  });

  it("l'axe d'une chaîne coupe une courbe", () => {
    const hits = crossingsAlong(ENTITIES[1], { x: 30, y: 32.5 }, { x: 1, y: 0 });
    assert.equal(hits.length, 2);
    assert.ok(hits.every((p) => near(p.y, 32.5)));
  });
});

describe("accrocher un milieu, un quadrant, un croisement, une courbe", () => {
  it("le milieu d'une ligne", () => {
    const s = snapNear(20.6, -19.7, ENTITIES);
    assert.deepEqual([s.x, s.y, s.kind], [20, -20, "midpoint"]);
    assert.deepEqual(s.target, { kind: "midpoint", geo: 0 });
    assert.equal(s.onPoint, null);
  });

  it("un quadrant de cercle", () => {
    const s = snapNear(55.4, 30.3, ENTITIES);
    assert.deepEqual([s.x, s.y], [55, 30]);
    assert.deepEqual(s.target, { kind: "quadrant", geo: 1, quadrant: 0 });
  });

  it("le croisement de deux entités survolées", () => {
    const lines = [{ id: 10, type: "line", p1: [0, 0], p2: [30, 30] },
      { id: 11, type: "line", p1: [0, 20], p2: [40, -20] }];
    const s = snapNear(10.5, 10.2, lines);
    assert.deepEqual([s.x, s.y, s.kind], [10, 10, "intersection"]);
    assert.deepEqual(s.target, { kind: "intersection", geos: [10, 11] });
  });

  it("sur la courbe, près d'elle seulement", () => {
    const a = Math.PI / 6;
    const out = 0.5; // 5 px dehors
    const s = snapNear(50 + (5 + out) * Math.cos(a), 30 + (5 + out) * Math.sin(a),
      ENTITIES);
    assert.equal(s.kind, "on");
    assert.deepEqual(s.target, { kind: "on", geo: 1 });
    assert.ok(near(Math.hypot(s.x - 50, s.y - 30), 5));
    const far = (ON_CURVE_PX + 1) / 10;
    const t = snapNear(50 + (5 + far) * Math.cos(a), 30 + (5 + far) * Math.sin(a),
      ENTITIES);
    assert.equal(t.target, null);
    assert.ok(t.wake.length, "la courbe survolée montre ses points remarquables");
  });

  it("sur la courbe et dans l'axe de la chaîne : là où l'axe la coupe", () => {
    const chain = { x: 30, y: 32.5 };
    const s = snapNear(54.5, 32.9, ENTITIES, { chain });
    assert.equal(s.hv, "H");
    assert.equal(s.y, 32.5);
    assert.ok(near(s.x, 50 + Math.sqrt(25 - 2.5 * 2.5)));
    assert.deepEqual(s.target, { kind: "on", geo: 1 });
  });

  it("un point existant passe avant tout", () => {
    const s = snapNear(85.3, 0.2, ENTITIES);
    assert.deepEqual(s.target, { geo: 2, point: 1 });
    assert.equal(s.kind, "point");
  });
});

describe("directions depuis la chaîne", () => {
  // Le curseur à `t` mm de `from` le long de `dir`, décalé de `off` mm.
  const along = (from, dir, t, off = 0.3) => ({
    x: from.x + t * dir.x - off * dir.y, y: from.y + t * dir.y + off * dir.x });
  const unitOf = (x, y) => ({ x: x / Math.hypot(x, y), y: y / Math.hypot(x, y) });
  const onLine = (s, from, dir) =>
    near((s.x - from.x) * dir.y - (s.y - from.y) * dir.x, 0);

  it("perpendiculaire à la ligne précédente", () => {
    const prev = { id: 20, type: "line", p1: [0, 0], p2: [30, 10] };
    const chain = { x: 30, y: 10 };
    const dir = unitOf(-1, 3);
    const c = along(chain, dir, 20);
    const s = snapNear(c.x, c.y, [prev], { chain });
    assert.deepEqual(s.direction, { kind: "perpendicular", geo: 20 });
    assert.ok(onLine(s, chain, dir));
    assert.equal(s.rays[0].relation, true);
  });

  it("parallèle à une ligne survolée avant, pas sans elle", () => {
    const woke = { id: 21, type: "line", p1: [50, -50], p2: [90, -30] };
    const chain = { x: 0, y: 0 };
    const c = along(chain, unitOf(2, 1), 30, 0.4);
    const s = snapNear(c.x, c.y, [woke], { chain, woken: [21] });
    assert.deepEqual(s.direction, { kind: "parallel", geo: 21 });
    assert.equal(snapNear(c.x, c.y, [woke], { chain }).direction, null);
  });

  it("tangente au bout d'un arc, même quand elle est horizontale", () => {
    const a = Math.PI / 3;
    const arc = { id: 22, type: "arc", c: [0, 0], r: 10, p1: [10, 0],
                  p2: [10 * Math.cos(a), 10 * Math.sin(a)] };
    const chain = { x: arc.p2[0], y: arc.p2[1] };
    const dir = { x: -Math.sin(a), y: Math.cos(a) };
    const c = along(chain, dir, 15);
    const s = snapNear(c.x, c.y, [arc], { chain });
    assert.deepEqual(s.direction, { kind: "tangent", geo: 22 });
    assert.ok(onLine(s, chain, dir));
    const top = { ...arc, p2: [0, 10] };
    const dirs = chainDirections({ x: 0, y: 10 }, [top]);
    assert.deepEqual(dirs[0].direction, { kind: "tangent", geo: 22 });
    assert.ok(!dirs.some((d) => d.hv === "H"), "l'horizontale cède à la tangente");
  });

  it("tangente à un cercle depuis un premier point posé dessus", () => {
    const circle = { id: 23, type: "circle", c: [0, 0], r: 10 };
    const chain = { x: 10, y: 0, target: { kind: "on", geo: 23 } };
    assert.deepEqual(chainDirections(chain, [circle])[0].direction,
      { kind: "tangent", geo: 23 });
  });

  it("le point où la ligne toucherait un cercle en tangente", () => {
    const circle = { id: 23, type: "circle", c: [50, 0], r: 10 };
    const [t] = tangentPoints(circle, { x: 0, y: 0 });
    assert.ok(near(Math.hypot(t.x - 50, t.y), 10));
    assert.ok(near(t.x * (t.x - 50) + t.y * t.y, 0)); // rayon ⟂ ligne
    const s = snapNear(t.x + 0.2, t.y + 0.3, [circle], { chain: { x: 0, y: 0 } });
    assert.deepEqual(s.target, { kind: "on", geo: 23 });
    assert.deepEqual(s.direction, { kind: "tangent", geo: 23 });
  });

  it("un pas d'angle : un repère sans relation, à quelques degrés seulement", () => {
    const chain = { x: 0, y: 0 };
    const at = (deg) => ({ x: 40 * Math.cos(deg * Math.PI / 180),
                           y: 40 * Math.sin(deg * Math.PI / 180) });
    const c = at(30.5);
    const s = snapNear(c.x, c.y, [], { chain, angleStep: 15 });
    assert.ok(near(Math.atan2(s.y, s.x) * 180 / Math.PI, 30));
    assert.equal(s.direction, null);
    assert.equal(s.rays[0].relation, false);
    const d = at(32);
    const t = snapNear(d.x, d.y, [], { chain, angleStep: 15 });
    assert.deepEqual([t.x, t.y], [d.x, d.y]);
    assert.deepEqual(t.rays, []);
  });

  it("depuis une ligne existante, l'angle se compte depuis elle", () => {
    const prev = { id: 20, type: "line", p1: [-10, -10], p2: [0, 0] };
    const dirs = chainDirections({ x: 0, y: 0 }, [prev], { angleStep: 15 })
      .filter((d) => d.angle);
    const angles = dirs.map((d) => Math.round(Math.atan2(d.dir.y, d.dir.x) * 180 / Math.PI));
    assert.ok(angles.includes(60), "45° + 15°");
    assert.ok(!angles.includes(30));
  });

  it("Maj : une longueur ronde, dans la direction trouvée", () => {
    const chain = { x: 0, y: 0 };
    const s = snapNear(23.4, 0.3, [], { chain, lengthStep: 5 });
    assert.deepEqual([s.x, s.y, s.hv], [25, 0, "H"]);
    const free = snapNear(17.1, 17.6, [], { chain, lengthStep: 5 });
    assert.ok(near(Math.hypot(free.x, free.y), 25));
  });

  it("une direction oblique échappe à la grille", () => {
    const prev = { id: 20, type: "line", p1: [0, 0], p2: [30, 10] };
    const chain = { x: 30, y: 10 };
    const dir = unitOf(-1, 3);
    const c = along(chain, dir, 20);
    const s = snapNear(c.x, c.y, [prev], { chain, gridStep: 5 });
    assert.ok(onLine(s, chain, dir));
  });
});

describe("ce que le tracé envoie au moteur", () => {
  const center = snapAt(50, 30);
  const free = snapAt(33, 71);

  it("une cible par point accroché, rien pour un clic libre", () => {
    assert.deepEqual(snapTarget(center), { geo: 1, point: 3 });
    assert.equal(snapTarget(free), null);
    assert.equal(snapTarget({ ...center, suspended: true }), null);
  });

  it("ligne : départ et arrivée ; les rôles vides partent", () => {
    assert.deepEqual(lineSnaps(center, free), { start: { geo: 1, point: 3 } });
    assert.deepEqual(lineSnaps(free, free), {});
    assert.deepEqual(pointSnaps(center), { at: { geo: 1, point: 3 } });
  });

  it("cercle : son centre et les clics posés dessus", () => {
    const origin = snapAt(0.1, 0);
    assert.deepEqual(circleSnaps(center, [free, origin]), {
      center: { geo: 1, point: 3 }, on: [{ geo: ORIGIN_GEO, point: 1 }] });
    assert.deepEqual(circleSnaps(null, [free]), {});
  });

  it("arc : centre et bouts ; le bout d'arrivée seulement s'il est au rayon", () => {
    const c = { x: 0, y: 0 };
    assert.ok(onCircle({ x: 3, y: 4 }, c, 5));
    assert.ok(!onCircle({ x: 3, y: 4.1 }, c, 5));
    assert.deepEqual(arcSnaps({ center, start: free, end: null, on: [center] }), {
      center: { geo: 1, point: 3 }, on: [{ geo: 1, point: 3 }] });
  });

  it("milieu et courbe partent tels quels ; un point posé sur la courbe tracée, non", () => {
    const mid = snapNear(20.6, -19.7, ENTITIES);
    assert.deepEqual(lineSnaps(mid, free), { start: { kind: "midpoint", geo: 0 } });
    assert.deepEqual(circleSnaps(mid, [mid, center]), {
      center: { kind: "midpoint", geo: 0 }, on: [{ geo: 1, point: 3 }] });
    assert.deepEqual(rectSnaps({ corner1: mid, center: mid }), {
      corner1: { kind: "midpoint", geo: 0 } });
  });

  it("ligne : la direction du second clic", () => {
    const end = { x: 1, y: 2, target: null,
                  direction: { kind: "tangent", geo: 4 } };
    assert.deepEqual(lineSnaps(free, end),
      { direction: { kind: "tangent", geo: 4 } });
    assert.deepEqual(lineSnaps(free, { ...end, suspended: true }), {});
  });

  it("rectangle : coins et centre", () => {
    assert.deepEqual(rectSnaps({ corner2: center, center: snapAt(0, 0) }), {
      corner2: { geo: 1, point: 3 }, center: { geo: ORIGIN_GEO, point: 1 } });
  });
});

describe("outils à clics", () => {
  it("point, ligne d'axe et cercle 3 points disent ce qu'ils ont accroché", async () => {
    const { CLICK_TOOLS } = await import("../../app/sketchtools.js");
    const center = snapAt(50, 30);
    const free = snapAt(33, 71);
    assert.deepEqual(CLICK_TOOLS.point.snaps([center]),
      { at: { geo: 1, point: 3 } });
    assert.deepEqual(CLICK_TOOLS.centerline.snaps([free, center]),
      { end: { geo: 1, point: 3 } });
    assert.deepEqual(CLICK_TOOLS.circle3.snaps([free, center, free]),
      { on: [{ geo: 1, point: 3 }] });
  });
});
