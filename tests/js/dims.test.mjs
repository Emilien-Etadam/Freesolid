import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  dimEditPayload, dimGeometry, dimLabel, filletRadiusLabel, sketchDimAnchor,
} from "../../app/dims.js";
import { setDisplayDecimals } from "../../app/num.js";

describe("cotes — libellé et ancrage", () => {
  it("dimLabel préfixe Σ et le nom", () => {
    assert.equal(dimLabel({ type: "Distance", value: 10, name: "", expr: "" }),
      "10.00");
    assert.equal(dimLabel({
      type: "Distance", value: 60, name: "largeur", expr: "2*30",
    }), "Σ largeur = 60.00");
  });

  it("la bulle de congé écrit R = et garde une expression", () => {
    assert.equal(filletRadiusLabel(3), "R = 3.00");
    assert.equal(filletRadiusLabel("3,5"), "R = 3.50");
    assert.equal(filletRadiusLabel("2*Largeur"), "R = 2*Largeur");
    assert.equal(filletRadiusLabel("  "), null);
  });

  it("une cote d'angle s'affiche en degrés", () => {
    assert.equal(dimLabel({ type: "Angle", value: Math.PI / 2, name: "" }),
      "90.0°");
  });

  it("les cotes prennent les décimales du document", () => {
    setDisplayDecimals({ length: 3, angle: 0 });
    try {
      assert.equal(dimLabel({ type: "Distance", value: 10, name: "" }), "10.000");
      assert.equal(dimLabel({ type: "Angle", value: Math.PI / 2, name: "" }), "90°");
      assert.equal(filletRadiusLabel("2.5"), "R = 2.500");
    } finally {
      setDisplayDecimals();
    }
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

describe("cotes : longueur d'arc, angle à l'axe, référence", () => {
  const arc = { id: 0, type: "arc", c: [0, 0], r: 10, p1: [10, 0], p2: [0, 10] };
  const line = { id: 1, type: "line", p1: [0, 0], p2: [10, 10] };

  it("une cote de référence s'affiche entre parenthèses, l'arc avec ⌒", () => {
    assert.equal(dimLabel({ type: "Distance", value: 15.7, kind: "arc_length" }),
      "⌒15.70");
    assert.equal(dimLabel({ type: "Distance", value: 5, driving: false }),
      "(5.00)");
  });

  it("la longueur d'arc suit l'arc, l'angle à l'axe part de l'horizontale", () => {
    const g = dimGeometry({ type: "Distance", geo: 0 },
      { geos: [0, null], pos: [0, 0] }, [arc], 2);
    assert.ok(g.segments.length > 20 && g.arrows.length === 2);
    assert.ok(Math.hypot(g.label.x, g.label.y) > 10);
    const a = dimGeometry({ type: "Angle", geo: 1 },
      { geos: [1, null], pos: [0, 0] }, [line], 2);
    assert.ok(a.segments.length >= 24 && a.arrows.length === 2);
  });

  it("la case « référence » bascule le pilotage", () => {
    const dim = { kind: "sketch", name: "", driving: true, value: 5 };
    assert.deepEqual(dimEditPayload({ value: "5", driven: true }, dim,
      { shown: "5", isSketchAngle: false }), { driving: false });
    assert.deepEqual(dimEditPayload({ value: "5", driven: false }, dim,
      { shown: "5", isSketchAngle: false }), {});
  });
});
