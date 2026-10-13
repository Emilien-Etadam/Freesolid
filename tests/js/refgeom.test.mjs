import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { referenceBuild, referenceItems } from "../../app/refgeom.js";

describe("géométrie de référence", () => {
  it("garde les axes, points et repères placés, hors barre de retour", () => {
    const m = Array(16).fill(0);
    const items = referenceItems({ features: [
      { name: "A", type: "PartDesign::Line", placement: m },
      { name: "B", type: "PartDesign::Point", placement: m, rolled_back: true },
      { name: "P", type: "PartDesign::Plane", placement: m },
      { name: "Pad", type: "PartDesign::Pad",
        children: [{ name: "C", type: "PartDesign::CoordinateSystem", placement: m }] },
    ] });
    assert.deepEqual(items.map((i) => [i.name, i.shape]), [["A", "axis"], ["C", "cs"]]);
  });

  it("traduit le panneau en paramètres de l'op", () => {
    assert.deepEqual(referenceBuild("axis", { by: "Y" }),
      { op: "add_datum_axis", params: { axis: "Y" } });
    assert.deepEqual(referenceBuild("axis", { by: "edge", edge: { edges: [4] } }),
      { op: "add_datum_axis", params: { edge: 4 } });
    assert.equal(referenceBuild("axis", { by: "edge" }), null);
    assert.deepEqual(referenceBuild("point",
      { by: "vertex", vertex: { kind: "vertex", x: 1, y: 2, z: 3 } }),
      { op: "add_datum_point", params: { vertex: [1, 2, 3] } });
    assert.deepEqual(referenceBuild("cs", { by: "xyz", x: "1", y: 0, z: -2 }),
      { op: "add_datum_cs", params: { point: [1, 0, -2] } });
    assert.equal(referenceBuild("cs", { by: "xyz", x: "a", y: 0, z: 0 }), null);
  });
});
