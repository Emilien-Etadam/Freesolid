import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { explodeStep } from "../../app/assembly.js";

describe("explodeStep", () => {
  it("avance vers la cible d'un pas, sans la dépasser", () => {
    assert.equal(explodeStep(0, 1), 0.06);
    assert.equal(explodeStep(0.97, 1), 1);
    assert.equal(explodeStep(1, 0), 0.94);
  });

  it("reste en place une fois arrivé", () => {
    assert.equal(explodeStep(1, 1), 1);
    assert.equal(explodeStep(0, 0), 0);
  });
});
