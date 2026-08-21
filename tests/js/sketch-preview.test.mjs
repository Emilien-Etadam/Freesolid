import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  isDrivingConstraint,
  circlePoints, ellipsePoints, slotPoints, polygonPoints,
  sketchPreviewPoints,
} from "../../app/geom2d.js";

function nearly(a, b, eps = 1e-6) {
  return Math.abs(a - b) < eps;
}

describe("isDrivingConstraint", () => {
  it("reconnaît une cote à valeur", () => {
    assert.equal(isDrivingConstraint({ type: "Radius", value: 5 }), true);
    assert.equal(isDrivingConstraint({ type: "Distance", value: 12.5 }), true);
    assert.equal(isDrivingConstraint({ type: "Angle", value: 1.57 }), true);
  });

  it("refuse une relation sèche", () => {
    assert.equal(isDrivingConstraint({ type: "Horizontal" }), false);
    assert.equal(isDrivingConstraint({ type: "Tangent" }), false);
    assert.equal(isDrivingConstraint({ type: "Coincident" }), false);
    assert.equal(isDrivingConstraint({ type: "Radius" }), false);
  });
});

describe("polylignes d'aperçu", () => {
  it("ferme un cercle autour du centre", () => {
    const pts = circlePoints(10, 20, 5);
    assert.equal(pts.length, 49);
    assert.ok(nearly(pts[0].x, pts[pts.length - 1].x));
    assert.ok(nearly(pts[0].y, pts[pts.length - 1].y));
    assert.ok(pts.some((p) => nearly(p.x, 15) && nearly(p.y, 20)));
  });

  it("trace une ellipse alignée sur les axes", () => {
    const pts = ellipsePoints(0, 0, 10, 4, 0);
    assert.ok(pts.some((p) => nearly(p.x, 10) && nearly(p.y, 0)));
    assert.ok(pts.some((p) => nearly(p.x, 0) && nearly(p.y, 4)));
  });

  it("fait un oblong de deux caps et deux flancs", () => {
    const pts = slotPoints({ x: 0, y: 0 }, { x: 20, y: 0 }, 8, 8);
    assert.ok(pts.length > 8);
    const xs = pts.map((p) => p.x);
    const ys = pts.map((p) => p.y);
    assert.ok(Math.min(...xs) < -3);
    assert.ok(Math.max(...xs) > 23);
    assert.ok(Math.min(...ys) < -3);
    assert.ok(Math.max(...ys) > 3);
  });

  it("ferme un hexagone sur le sommet donné", () => {
    const pts = polygonPoints(0, 0, 10, 0, 6);
    assert.equal(pts.length, 7);
    assert.ok(nearly(pts[0].x, 10) && nearly(pts[0].y, 0));
    assert.ok(nearly(pts[6].x, 10) && nearly(pts[6].y, 0));
  });
});

describe("sketchPreviewPoints", () => {
  const cursor = { x: 10, y: 0 };

  it("suit le snap d'un cercle depuis le centre posé", () => {
    const pts = sketchPreviewPoints("circle", { x: 0, y: 0 }, cursor);
    assert.ok(pts.some((p) => nearly(p.x, 10) && nearly(p.y, 0)));
  });

  it("montre le grand rayon d'ellipse puis l'ellipse complète", () => {
    const first = sketchPreviewPoints(
      "ellipse", { c: { x: 0, y: 0 } }, cursor);
    assert.ok(first.some((p) => nearly(p.x, 10) && nearly(p.y, 0)));
    const full = sketchPreviewPoints("ellipse", {
      c: { x: 0, y: 0 }, major: { x: 10, y: 0 },
    }, { x: 0, y: 4 });
    assert.ok(full.some((p) => nearly(p.x, 0, 0.2) && nearly(p.y, 4, 0.2)));
  });

  it("relie les deux centres d'oblong avant la largeur", () => {
    const pts = sketchPreviewPoints(
      "slot", { a: { x: 0, y: 0 } }, { x: 20, y: 0 });
    assert.deepEqual(pts, [{ x: 0, y: 0 }, { x: 20, y: 0 }]);
  });

  it("trace l'arc depuis le départ jusqu'au curseur", () => {
    const pts = sketchPreviewPoints("arc", {
      c: { x: 0, y: 0 }, start: { x: 10, y: 0 },
    }, { x: 0, y: 10 });
    assert.ok(nearly(pts[0].x, 10) && nearly(pts[0].y, 0));
    const last = pts[pts.length - 1];
    assert.ok(nearly(last.x, 0) && nearly(last.y, 10));
  });

  it("attend le centre du polygone avant de tracer", () => {
    assert.deepEqual(
      sketchPreviewPoints("polygon", { sides: 6 }, cursor), []);
    const pts = sketchPreviewPoints(
      "polygon", { sides: 4, c: { x: 0, y: 0 } }, { x: 5, y: 5 });
    assert.equal(pts.length, 5);
  });

  it("ne trace rien sans ancrage", () => {
    assert.deepEqual(sketchPreviewPoints("circle", null, cursor), []);
  });
});
