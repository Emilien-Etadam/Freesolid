import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { findFeatureInTree } from "../../app/picking.js";

describe("findFeatureInTree", () => {
  const tree = {
    features: [
      { name: "Pad", children: [{ name: "Sketch" }] },
    ],
    surfaces: [{ name: "Surface" }],
  };

  it("trouve une fonction, son enfant, ou une surface", () => {
    assert.equal(findFeatureInTree(tree, "Pad").name, "Pad");
    assert.equal(findFeatureInTree(tree, "Sketch").name, "Sketch");
    assert.equal(findFeatureInTree(tree, "Surface").name, "Surface");
  });

  it("rend null sans nom, sans arbre, ou si rien ne correspond", () => {
    assert.equal(findFeatureInTree(tree, ""), null);
    assert.equal(findFeatureInTree(null, "Pad"), null);
    assert.equal(findFeatureInTree(tree, "Absent"), null);
    assert.equal(findFeatureInTree({}, "Pad"), null);
  });
});
