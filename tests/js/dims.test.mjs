import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  dimEditPayload, dimLabel, sketchDimAnchor,
} from "../../app/dims.js";

describe("cotes — libellé et ancrage", () => {
  it("dimLabel préfixe Σ et le nom", () => {
    assert.equal(dimLabel({ type: "Distance", value: 10, name: "", expr: "" }),
      "10.00");
    assert.equal(dimLabel({
      type: "Distance", value: 60, name: "largeur", expr: "2*30",
    }), "Σ largeur = 60.00");
  });

  it("une cote d'angle s'affiche en degrés", () => {
    assert.equal(dimLabel({ type: "Angle", value: Math.PI / 2, name: "" }),
      "90.0°");
  });

  it("sketchDimAnchor pose la cote au milieu d'une ligne", () => {
    const dim = { geo: 0 };
    const entities = [{ id: 0, type: "line", p1: [0, 0], p2: [10, 0] }];
    assert.deepEqual(sketchDimAnchor(dim, entities), { x: 5, y: 4 });
  });

  it("sketchDimAnchor pose la cote sur un cercle", () => {
    const dim = { geo: 1 };
    const entities = [{ id: 1, type: "circle", c: [0, 0], r: 10 }];
    assert.deepEqual(sketchDimAnchor(dim, entities), { x: 7, y: 7 });
  });
});

describe("cotes — payload d'édition", () => {
  it("une virgule française devient une valeur", () => {
    const extra = dimEditPayload(
      { value: "12,5" },
      { kind: "param", name: "" },
      { shown: "10", isSketchAngle: false },
    );
    assert.equal(extra.value, 12.5);
    assert.equal(extra.expr, undefined);
  });

  it("une expression n'est pas parsée comme nombre", () => {
    const extra = dimEditPayload(
      { value: "Variables.Largeur / 2" },
      { kind: "sketch", name: "largeur" },
      { shown: "10", isSketchAngle: false },
    );
    assert.equal(extra.expr, "Variables.Largeur / 2");
  });

  it("un angle d'esquisse part en radians", () => {
    const extra = dimEditPayload(
      { value: "90" },
      { kind: "sketch", name: "" },
      { shown: "45.00", isSketchAngle: true },
    );
    assert.equal(extra.value, Math.PI / 2);
  });
});
