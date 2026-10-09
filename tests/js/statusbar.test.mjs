import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  coordsText, editModeText, measureText, sketchEntityLength,
} from "../../app/statusbar.js";

describe("barre d'état", () => {
  it("coordonnées en esquisse (2D) et dans la pièce (3D)", () => {
    assert.equal(coordsText({ x: 12.345, y: -0.001 }), "X 12.35  Y 0.00 mm");
    assert.equal(coordsText({ x: 1, y: 2, z: 3 }),
      "X 1.00  Y 2.00  Z 3.00 mm");
    assert.equal(coordsText(null), "");
  });

  it("longueur d'une entité d'esquisse", () => {
    assert.equal(sketchEntityLength({ type: "line", p1: [0, 0], p2: [3, 4] }), 5);
    assert.ok(Math.abs(sketchEntityLength({ type: "circle", c: [0, 0], r: 1 })
      - 2 * Math.PI) < 1e-9);
    const quarter = sketchEntityLength(
      { type: "arc", c: [0, 0], r: 2, p1: [2, 0], p2: [0, 2] });
    assert.ok(Math.abs(quarter - Math.PI) < 1e-9);
    assert.ok(Number.isNaN(sketchEntityLength({ type: "poly" })));
  });

  it("mesure : une longueur, ou la somme de plusieurs", () => {
    assert.equal(measureText([40]), "Longueur : 40.00 mm");
    assert.equal(measureText([40, 20, NaN]),
      "Longueur totale : 60.00 mm (2 entités)");
    assert.equal(measureText([]), "");
  });

  it("mode d'édition : esquisse, puis assemblage, puis pièce", () => {
    assert.equal(editModeText({ sketch: "Esquisse1", part: "P" }),
      "Édition : esquisse « Esquisse1 »");
    assert.equal(editModeText({ assembly: true }), "Édition : assemblage");
    assert.equal(editModeText({ part: "Plaque" }), "Édition : pièce « Plaque »");
    assert.equal(editModeText({}), "");
  });
});
