import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { linearSecondDirection } from "../../app/features.js";

describe("réseau linéaire, direction 2", () => {
  it("donne l'axe, la distance et le nombre, ou null", () => {
    assert.deepEqual(linearSecondDirection(
      { axis2: "Z", length2: "15", count2: "4", reversed2: true }),
      { axis2: "Z", length2: 15, count2: 4, reversed2: true });
    assert.equal(linearSecondDirection({ length2: 0, count2: 3 }), null);
    assert.equal(linearSecondDirection({ length2: 10, count2: 1 }), null);
  });
});
