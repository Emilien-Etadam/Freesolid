import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { numericDrawTarget, numericFields } from "../../app/geom2d.js";

const near = (p, x, y) => Math.abs(p.x - x) < 1e-9 && Math.abs(p.y - y) < 1e-9;

describe("saisie numérique pendant le tracé", () => {
  it("ligne : longueur vers le curseur, ou angle tapé", () => {
    assert.ok(near(numericDrawTarget("line", { x: 0, y: 0 }, { x: 0, y: 5 }, 20),
      0, 20));
    assert.ok(near(numericDrawTarget("line", { x: 1, y: 1 }, { x: 9, y: 9 }, 10, 180),
      -9, 1));
  });

  it("cercle : rayon", () => {
    const p = numericDrawTarget("circle", { x: 2, y: 2 }, { x: 2, y: -7 }, 4);
    assert.ok(near(p, 2, -2));
  });

  it("rectangle : largeur et hauteur du côté du curseur", () => {
    assert.ok(near(numericDrawTarget("rect", { x: 0, y: 0 }, { x: -1, y: 3 }, 40, 20),
      -40, 20));
    // Hauteur absente : celle du curseur.
    assert.ok(near(numericDrawTarget("rect", { x: 0, y: 0 }, { x: 5, y: 7 }, 40),
      40, 7));
    // Par le centre : dimensions totales.
    assert.ok(near(numericDrawTarget("rectc", { x: 0, y: 0 }, { x: 1, y: 1 }, 40, 20),
      20, 10));
  });

  it("valeur nulle ou outil sans saisie : rien", () => {
    assert.equal(numericDrawTarget("line", { x: 0, y: 0 }, null, 0), null);
    assert.equal(numericDrawTarget("arc", { x: 0, y: 0 }, null, 5), null);
    assert.deepEqual(numericFields("circle"), ["Rayon"]);
    assert.deepEqual(numericFields("select"), []);
  });
});
