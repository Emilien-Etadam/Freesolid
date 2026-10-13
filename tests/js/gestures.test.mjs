import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { PART_GESTURES, SKETCH_GESTURES, gestureSlot } from "../../app/gestures.js";

describe("gestes de la souris", () => {
  it("droite, haut, gauche, bas ; rien au centre", () => {
    assert.equal(gestureSlot(60, 0), 0);
    assert.equal(gestureSlot(0, -60), 1);
    assert.equal(gestureSlot(-60, 5), 2);
    assert.equal(gestureSlot(3, 60), 3);
    assert.equal(gestureSlot(10, 10), -1);
  });

  it("quatre commandes par couronne", () => {
    assert.equal(PART_GESTURES.length, 4);
    assert.equal(SKETCH_GESTURES.length, 4);
  });
});
