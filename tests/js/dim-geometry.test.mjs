import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { arrowSegments, dimGeometry, dimLabel } from "../../app/dims.js";

const close = (a, b, eps = 1e-9) => Math.abs(a - b) < eps;

describe("dimLabel — symboles", () => {
  it("Ø pour un diamètre, R pour un rayon", () => {
    assert.equal(dimLabel({ type: "Diameter", value: 20 }), "Ø20.00");
    assert.equal(dimLabel({ type: "Radius", value: 5 }), "R5.00");
  });
});

describe("dimGeometry", () => {
  // Rectangle 0..10 × 0..6 : le bas est la ligne 0.
  const rect = [
    { id: 0, type: "line", p1: [0, 0], p2: [10, 0] },
    { id: 1, type: "line", p1: [10, 0], p2: [10, 6] },
    { id: 2, type: "line", p1: [10, 6], p2: [0, 6] },
    { id: 3, type: "line", p1: [0, 6], p2: [0, 0] },
  ];

  it("longueur d'une ligne : cote alignée, décalée hors de la pièce", () => {
    const g = dimGeometry({ type: "Distance", geo: 0 },
      { geos: [0, null, null], pos: [0, 0, 0] }, rect, 1);
    assert.equal(g.segments.length, 3);   // deux attaches + la ligne de cote
    assert.equal(g.arrows.length, 2);
    // Le bas du rectangle : la cote part vers le bas (y < 0).
    assert.ok(g.label.y < 0);
    assert.ok(close(g.label.x, 5));
    // Les flèches pointent vers l'extérieur, le long de la ligne.
    assert.ok(close(g.arrows[0].dx, -1) && close(g.arrows[1].dx, 1));
  });

  it("deux points : cote alignée entre eux", () => {
    const g = dimGeometry({ type: "Distance", geo: 0 },
      { geos: [0, 2, null], pos: [1, 1, 0] }, rect, 1);
    assert.equal(g.arrows.length, 2);
    assert.equal(g.segments.length, 3);
  });

  it("point → ligne : cote directe jusqu'au pied de la perpendiculaire", () => {
    const g = dimGeometry({ type: "Distance", geo: 2 },
      { geos: [2, 0, null], pos: [1, 0, 0] }, rect, 1);
    assert.deepEqual(g.segments[0], [10, 6, 10, 0]);
  });

  it("rayon d'un arc : une flèche sur l'arc", () => {
    const arc = [{ id: 0, type: "arc", c: [0, 0], r: 5, p1: [5, 0], p2: [0, 5] }];
    const g = dimGeometry({ type: "Radius", geo: 0 },
      { geos: [0, null, null], pos: [0, 0, 0] }, arc, 1);
    assert.equal(g.arrows.length, 1);
    const a = g.arrows[0];
    assert.ok(close(Math.hypot(a.x, a.y), 5));
  });

  it("diamètre d'un cercle : deux flèches opposées", () => {
    const circle = [{ id: 0, type: "circle", c: [0, 0], r: 5 }];
    const g = dimGeometry({ type: "Diameter", geo: 0 },
      { geos: [0, null, null], pos: [0, 0, 0] }, circle, 1);
    assert.equal(g.arrows.length, 2);
    assert.ok(close(g.arrows[0].x, -g.arrows[1].x));
  });

  it("angle entre deux lignes : un arc et deux flèches", () => {
    const lines = [
      { id: 0, type: "line", p1: [0, 0], p2: [10, 0] },
      { id: 1, type: "line", p1: [0, 0], p2: [0, 10] },
    ];
    const g = dimGeometry({ type: "Angle", geo: 0, value: Math.PI / 2 },
      { geos: [0, 1, null], pos: [0, 0, 0] }, lines, 1);
    assert.ok(g.segments.length >= 8);
    assert.equal(g.arrows.length, 2);
    assert.ok(g.label.x > 0 && g.label.y > 0);   // dans le quadrant
  });

  it("cas non prévu : seul le libellé, à l'ancrage historique", () => {
    const g = dimGeometry({ type: "DistanceX", geo: 0 }, null, rect, 1);
    assert.deepEqual(g, { label: { x: 5, y: 4 }, segments: [], arrows: [] });
  });

  it("une pointe de flèche fait deux traits de la bonne longueur", () => {
    const segs = arrowSegments({ x: 0, y: 0, dx: 1, dy: 0 }, 2);
    assert.equal(segs.length, 2);
    for (const [x1, y1, x2, y2] of segs) {
      assert.ok(close(Math.hypot(x2 - x1, y2 - y1), 2));
      assert.ok(x2 < 0);   // les traits partent en arrière de la pointe
    }
  });
});
