import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { breadcrumbTrail, findFeature } from "../../app/breadcrumbs.js";

const tree = {
  body: "Équerre-support",
  features: [
    { name: "Pad", label: "Socle", type_key: "pad",
      children: [{ name: "Sketch", label: "Esquisse 1", type_key: "sketch" }] },
    { name: "Folder", label: "Perçages", type: "folder",
      features: [{ name: "Hole", label: "Perçages M6", type_key: "hole" }] },
  ],
};
const groups = [{ faceId: 0, feature: "Pad" }, { faceId: 5, feature: "Hole" }, { faceId: 7 }];

describe("fil de la sélection", () => {
  it("pièce › fonction › esquisse › face", () => {
    const trail = breadcrumbTrail(tree, groups, 0);
    assert.deepEqual(trail.map((s) => s.kind), ["part", "feature", "sketch", "face"]);
    assert.deepEqual(trail.map((s) => s.label),
      ["Équerre-support", "Socle", "Esquisse 1", "Face 0"]);
    assert.equal(trail[1].icon, "nodes_extrude");
  });

  it("une fonction rangée dans un dossier, une face sans fonction", () => {
    assert.deepEqual(breadcrumbTrail(tree, groups, 5).map((s) => s.label),
      ["Équerre-support", "Perçages M6", "Face 5"]);
    assert.deepEqual(breadcrumbTrail(tree, groups, 7).map((s) => s.kind), ["part", "face"]);
    assert.equal(findFeature(tree.features, "Hole").label, "Perçages M6");
  });

  it("une face venue d'un corps fondu : la fonction de ce corps", () => {
    const fused = { ...tree, other_features: [
      { name: "Pad001", label: "Bloc B", type_key: "pad", body: "Body001" }] };
    assert.deepEqual(
      breadcrumbTrail(fused, [{ faceId: 9, feature: "Pad001" }], 9)
        .map((s) => s.label),
      ["Équerre-support", "Bloc B", "Face 9"]);
  });

  it("rien sans face choisie", () => {
    assert.deepEqual(breadcrumbTrail(tree, groups, null), []);
    assert.deepEqual(breadcrumbTrail(null, groups, 0), []);
  });
});
