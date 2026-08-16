import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { entityKindTitle, entityPropertyLines } from "../../app/geom2d.js";

describe("entityKindTitle", () => {
  it("nomme les types d'esquisse en français", () => {
    assert.equal(entityKindTitle({ type: "line" }), "Ligne");
    assert.equal(entityKindTitle({ type: "circle" }), "Cercle");
    assert.equal(entityKindTitle({ type: "arc" }), "Arc");
    assert.equal(entityKindTitle({ type: "poly", kind: "spline" }), "Spline");
    assert.equal(entityKindTitle({ type: "poly", kind: "ellipse" }), "Ellipse");
    assert.equal(entityKindTitle({ type: "poly" }), "Polyligne");
  });
});

describe("entityPropertyLines", () => {
  it("donne longueur et extrémités d'une ligne au 1/100 mm", () => {
    const lines = entityPropertyLines({
      type: "line", p1: [0, 10], p2: [80, 10],
    });
    assert.equal(lines[0], "Longueur : 80.00 mm");
    assert.equal(lines[1], "Départ : (0.00, 10.00) mm");
    assert.equal(lines[2], "Arrivée : (80.00, 10.00) mm");
  });

  it("donne centre, rayon et diamètre d'un cercle", () => {
    const lines = entityPropertyLines({
      type: "circle", c: [5, -2], r: 12.5,
    });
    assert.deepEqual(lines, [
      "Centre : (5.00, -2.00) mm",
      "Rayon : 12.50 mm",
      "Diamètre : 25.00 mm",
    ]);
  });

  it("donne l'angle balayé d'un quart d'arc", () => {
    const lines = entityPropertyLines({
      type: "arc", c: [0, 0], r: 10, p1: [10, 0], p2: [0, 10],
    });
    assert.equal(lines[0], "Centre : (0.00, 0.00) mm");
    assert.equal(lines[1], "Rayon : 10.00 mm");
    assert.equal(lines[2], "Angle balayé : 90.00 °");
  });

  it("donne centre et rayons d'une ellipse", () => {
    const lines = entityPropertyLines({
      type: "poly", kind: "ellipse", c: [50, 0], rx: 12, ry: 6,
    });
    assert.deepEqual(lines, [
      "Centre : (50.00, 0.00) mm",
      "Grand rayon : 12.00 mm",
      "Petit rayon : 6.00 mm",
    ]);
  });

  it("compte les points d'une spline", () => {
    const lines = entityPropertyLines({
      type: "poly", kind: "spline", npoints: 4,
      points: [[0, 0], [1, 1], [2, 0], [3, 1]],
    });
    assert.deepEqual(lines, ["Nombre de points : 4"]);
  });
});
