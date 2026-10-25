import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { availableSketches } from "../../app/features.js";

describe("availableSketches", () => {
  it("ne retient que les esquisses libres non reculées", () => {
    const tree = {
      features: [
        { name: "Pad", type_key: "pad" },
        { name: "Sketch", type_key: "sketch" },
        { name: "Sketch001", type_key: "sketch",
          rolled_back: true },
        { name: "Sketch002", type_key: "sketch",
          rolled_back: false },
      ],
    };
    assert.deepEqual(
      availableSketches(tree).map((item) => item.name),
      ["Sketch", "Sketch002"],
    );
  });
});
