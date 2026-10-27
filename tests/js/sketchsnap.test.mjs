// Magnétisme de l'esquisse : où tombe un clic, ce qu'il envoie au moteur.
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  ORIGIN_GEO, SNAP_PX, arcSnaps, circleSnaps, lineSnaps, onCircle,
  pointSnaps, rectSnaps, sketchEndpoints, sketchSnapPoints, snapSketchPoint,
  snapTarget,
} from "../../app/sketchsnap.js";

// Vue de dessus, 1 mm = 10 px : le pixel d'un point est (10x, -10y).
const toScreen = (x, y) => ({ x: x * 10, y: -y * 10 });
const cursorAt = (x, y) => toScreen(x, y);

const ENTITIES = [
  { id: 0, type: "line", p1: [10, -20], p2: [30, -20] },
  { id: 1, type: "circle", c: [50, 30], r: 5 },
  { id: 2, type: "arc", c: [80, 0], p1: [85, 0], p2: [80, 5] },
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
    assert.ok(h.guides.includes(chain));
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
    assert.deepEqual(s, { x: 50.3, y: 30, onPoint: null, guides: [],
      hv: null, suspended: true });
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
