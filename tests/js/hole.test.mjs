import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { holePositions } from "../../app/features.js";

describe("perçage : positions cliquées", () => {
  it("aucune position : la dernière esquisse sert", () => {
    assert.equal(holePositions(null), null);
    assert.equal(holePositions({ items: [] }), null);
  });

  it("des centres sur une face → face et points monde", () => {
    const sel = { items: [
      { kind: "point", face: 4, x: 10, y: 20, z: 8 },
      { kind: "point", face: 4, x: 40, y: 20, z: 8 },
    ] };
    assert.deepEqual(holePositions(sel),
      { face: 4, points: [[10, 20, 8], [40, 20, 8]] });
  });

  it("des centres sur deux faces sont refusés", () => {
    const sel = { items: [
      { kind: "point", face: 4, x: 0, y: 0, z: 0 },
      { kind: "point", face: 6, x: 1, y: 1, z: 1 },
    ] };
    assert.ok(holePositions(sel).error);
  });
});
