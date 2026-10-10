import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  arrowTriangle, dimGeometry, dimLabel, dimOffsetAt, pointPairDimKind,
  pointPairDimPath,
} from "../../app/dims.js";

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

  it("centre d'un cercle → origine : cote alignée jusqu'à (0, 0)", () => {
    const hole = [{ id: 0, type: "circle", c: [0, -30], r: 4 }];
    const g = dimGeometry({ type: "Distance", geo: 0 },
      { geos: [0, -1, null], pos: [3, 1, 0] }, hole, 1);
    assert.equal(g.arrows.length, 2);
    const tips = g.arrows.map((a) => [a.x, a.y]);
    assert.ok(tips.some(([x, y]) => close(x, tips[0][0]) && close(Math.abs(y - tips[1][1]), 30)));
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

  it("une pointe de flèche est un triangle plein, en arrière de la pointe", () => {
    const [x1, y1, x2, y2, x3, y3] = arrowTriangle(
      { x: 0, y: 0, dx: 1, dy: 0 }, 9, 1.5);
    assert.deepEqual([x1, y1], [0, 0]);
    assert.ok(close(x2, -9) && close(x3, -9));
    assert.ok(close(Math.abs(y2 - y3), 3));
  });
});

describe("cote entre deux points : le 3e clic choisit le sens", () => {
  const a = { x: 0, y: 0 }, b = { x: 20, y: 12 };
  it("au-dessus ou au-dessous : horizontale", () => {
    assert.equal(pointPairDimKind(a, b, { x: 10, y: 20 }), "DistanceX");
    assert.equal(pointPairDimKind(a, b, { x: 5, y: -4 }), "DistanceX");
  });
  it("à côté : verticale", () => {
    assert.equal(pointPairDimKind(a, b, { x: 30, y: 6 }), "DistanceY");
    assert.equal(pointPairDimKind(a, b, { x: -3, y: 2 }), "DistanceY");
  });
  it("entre les points ou en biais : alignée", () => {
    assert.equal(pointPairDimKind(a, b, { x: 10, y: 6 }), "Distance");
    assert.equal(pointPairDimKind(a, b, { x: 30, y: 30 }), "Distance");
  });
  it("aperçu horizontal : la ligne de cote passe par le curseur", () => {
    const path = pointPairDimPath(a, b, "DistanceX", { x: 10, y: 20 });
    assert.deepEqual(path, [a, { x: 0, y: 20 }, { x: 20, y: 20 }, b]);
  });
  it("cote horizontale posée : tracé parallèle à X entre les deux points", () => {
    const entities = [{ id: 0, type: "line", p1: [0, 0], p2: [20, 12] }];
    const g = dimGeometry({ type: "DistanceX", geo: 0 },
      { geos: [0, 0, null], pos: [1, 2, 0] }, entities, 1);
    assert.deepEqual(g.segments[2], [0, 14, 20, 14]);
    assert.equal(g.arrows.length, 2);
  });
});

describe("cote posée : elle reste où on l'a cliquée", () => {
  const line = [{ id: 0, type: "line", p1: [0, 0], p2: [10, 0] }];
  it("longueur : ligne de cote au décalage retenu, du côté choisi", () => {
    const below = dimGeometry({ type: "Distance", geo: 0, offset: -7 },
      { geos: [0, null, null], pos: [0, 0, 0] }, line, 1);
    assert.deepEqual(below.segments[2], [0, -7, 10, -7]);
    const above = dimGeometry({ type: "Distance", geo: 0, offset: 4 },
      { geos: [0, null, null], pos: [0, 0, 0] }, line, 1);
    assert.deepEqual(above.segments[2], [0, 4, 10, 4]);
  });
  it("horizontale sous les points : attaches vers le bas", () => {
    const pts = [{ id: 0, type: "line", p1: [0, 0], p2: [20, 12] }];
    const g = dimGeometry({ type: "DistanceX", geo: 0, offset: -5 },
      { geos: [0, 0, null], pos: [1, 2, 0] }, pts, 1);
    assert.deepEqual(g.segments[2], [0, -5, 20, -5]);
    assert.ok(g.label.y < -5);
  });
});

describe("cote glissée : décalage sous le curseur", () => {
  const line = [{ id: 0, type: "line", p1: [0, 0], p2: [10, 0] }];
  const own = { geos: [0, null, null], pos: [0, 0, 0] };
  it("longueur d'une ligne : distance signée à la ligne", () => {
    assert.equal(dimOffsetAt({ type: "Distance", geo: 0 }, own, line,
      { x: 3, y: -6 }), -6);
  });
  it("horizontale / verticale depuis l'origine : depuis le 1er point", () => {
    const pt = [{ id: 0, type: "line", p1: [20, 12], p2: [36, 12] }];
    const pair = { geos: [-1, 0, null], pos: [1, 1, 0] };
    assert.equal(dimOffsetAt({ type: "DistanceX", geo: -1 }, pair, pt,
      { x: 5, y: 30 }), 30);
    assert.equal(dimOffsetAt({ type: "DistanceY", geo: -1 }, pair, pt,
      { x: -8, y: 5 }), -8);
  });
  it("diamètre : ne se glisse pas ainsi", () => {
    const circle = [{ id: 0, type: "circle", c: [0, 0], r: 5 }];
    assert.equal(dimOffsetAt({ type: "Diameter", geo: 0 },
      { geos: [0, null, null], pos: [0, 0, 0] }, circle, { x: 1, y: 1 }),
      null);
  });
});
