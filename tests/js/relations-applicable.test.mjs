import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { applicableRelations } from "../../app/geom2d.js";

const entities = [
  { id: 0, type: "line" }, { id: 1, type: "line" },
  { id: 2, type: "circle" }, { id: 3, type: "arc" },
];

describe("relations proposées selon la sélection", () => {
  it("une ligne : horizontale, verticale, fixe", () => {
    assert.deepEqual(applicableRelations([{ geo: 0 }], entities),
      ["horizontal", "vertical", "fixed"]);
    assert.deepEqual(applicableRelations([{ geo: 2 }], entities), ["fixed"]);
  });

  it("deux lignes, deux cercles, ligne et cercle", () => {
    assert.deepEqual(applicableRelations([{ geo: 0 }, { geo: 1 }], entities),
      ["parallel", "perpendicular", "equal", "collinear"]);
    assert.deepEqual(applicableRelations([{ geo: 2 }, { geo: 3 }], entities),
      ["equal", "concentric", "tangent"]);
    assert.deepEqual(applicableRelations([{ geo: 0 }, { geo: 2 }], entities),
      ["tangent"]);
  });

  it("points : coïncidence, milieu, symétrie", () => {
    assert.deepEqual(applicableRelations(
      [{ geo: 0, point: 2 }, { geo: 1, point: 1 }], entities), ["coincident"]);
    assert.deepEqual(applicableRelations(
      [{ geo: 2, point: 3 }, { geo: 0 }], entities), ["midpoint"]);
    assert.deepEqual(applicableRelations(
      [{ geo: 0, point: 1 }, { geo: 1, point: 1 }, { geo: 0 }], entities),
      ["symmetric"]);
    assert.deepEqual(applicableRelations(
      [{ geo: 0 }, { geo: 0, point: 1 }, { geo: 1, point: 1 }], entities), []);
  });
});
