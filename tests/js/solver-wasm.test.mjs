import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  circle,
  constraint,
  dist,
  line,
  sketch,
  wasmSolver,
} from "./harness.mjs";

const EPS = 0.05;

function corners(entities) {
  // Après coïncidences : p1/p2 des 4 droites d'un rectangle
  // 0 bas, 1 droite, 2 haut, 3 gauche.
  const [bottom, right, top, left] = entities;
  return {
    sw: bottom.p1,
    se: bottom.p2,
    ne: right.p2,
    nw: top.p2,
    bottom, right, top, left,
  };
}

function rectangleEntities(w, h) {
  return [
    line(0, [0, 0], [w, 0]),
    line(1, [w, 0], [w, h]),
    line(2, [w, h], [0, h]),
    line(3, [0, h], [0, 0]),
  ];
}

function cornerCoincident() {
  return [
    constraint("Coincident", [0, 1], [2, 1]),
    constraint("Coincident", [1, 2], [2, 1]),
    constraint("Coincident", [2, 3], [2, 1]),
    constraint("Coincident", [3, 0], [2, 1]),
  ];
}

function constrainedRectangle(w, h) {
  return sketch(rectangleEntities(w, h), [
    ...cornerCoincident(),
    constraint("Horizontal", [0], [0]),
    constraint("Horizontal", [2], [0]),
    constraint("Vertical", [1], [0]),
    constraint("Vertical", [3], [0]),
    constraint("Distance", [0], [0], { value: w }),
    constraint("Distance", [1], [0], { value: h }),
  ]);
}

function freeRectangle(w, h) {
  return sketch(rectangleEntities(w, h), cornerCoincident());
}

function almost(actual, expected, message) {
  assert.ok(
    Math.abs(actual - expected) < EPS,
    `${message}: ${actual} ≉ ${expected} (±${EPS})`);
}

describe("WASM planegcs", () => {
  it("rectangle contraint : drag d'un coin, cotes 40/30 et H/V tenues", async () => {
    const solver = await wasmSolver();
    const state = constrainedRectangle(40, 30);
    assert.equal(solver.load(state), true);
    const updates = solver.drag(0, 2, 55, 10);
    assert.ok(updates, "le solveur doit converger");
    const { sw, se, ne, nw, bottom, right } = corners(updates);
    almost(dist(sw, se), 40, "largeur");
    almost(dist(se, ne), 30, "hauteur");
    almost(bottom.p1[1], bottom.p2[1], "bas horizontal");
    almost(right.p1[0], right.p2[0], "droite verticale");
    almost(se[0], 55, "coin tiré X");
    almost(se[1], 10, "coin tiré Y");
    almost(nw[0], sw[0], "gauche verticale");
    almost(nw[1], ne[1], "haut horizontal");
  });

  it("rectangle libre : le coin suit la souris", async () => {
    const solver = await wasmSolver();
    const state = freeRectangle(40, 30);
    assert.equal(solver.load(state), true);
    const target = [12, 17];
    const updates = solver.drag(0, 1, target[0], target[1]);
    assert.ok(updates, "le solveur doit converger");
    const { sw } = corners(updates);
    almost(sw[0], target[0], "coin X");
    almost(sw[1], target[1], "coin Y");
  });

  it("cercle tangent : rayon et tangence tenus", async () => {
    const solver = await wasmSolver();
    // Droite y = 0 bloquée ; cercle (20, 10) r = 10 tangent par construction.
    // 1 ddl restant : glissement le long de la droite. Drag du centre
    // sur la variété (28, 10).
    const state = sketch(
      [
        line(0, [0, 0], [40, 0]),
        circle(1, [20, 10], 10),
      ],
      [
        constraint("Block", [0], [0]),
        constraint("Tangent", [0, 1], [0, 0]),
        constraint("Radius", [1], [0], { value: 10 }),
      ]);
    assert.equal(solver.load(state), true);
    const updates = solver.drag(1, 3, 28, 10);
    assert.ok(updates, "le solveur doit converger");
    const circ = updates.find((e) => e.id === 1);
    const seg = updates.find((e) => e.id === 0);
    almost(circ.r, 10, "rayon");
    const lineY = seg.p1[1];
    almost(Math.abs(circ.c[1] - lineY), circ.r, "tangence (|cy − y_ligne| = r)");
    almost(circ.c[0], 28, "centre glissé en X");
  });
});
