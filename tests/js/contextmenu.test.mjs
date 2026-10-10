import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  canModifyMenuTarget, isBodyMenuTarget, isFrozenSurface,
} from "../../app/contextmenu.js";

describe("cible du menu de l'arbre", () => {
  it("un corps se reconnaît à sa propriété active", () => {
    assert.equal(isBodyMenuTarget(null), false);
    assert.equal(isBodyMenuTarget(undefined), false);
    assert.equal(isBodyMenuTarget({}), false);
    assert.equal(isBodyMenuTarget({ active: true }), true);
    assert.equal(isBodyMenuTarget({ active: false }), true);
    assert.equal(isBodyMenuTarget({ active: "yes" }), false);
  });

  it("une surface figée n'est ni un graphe ni une répétition", () => {
    assert.equal(isFrozenSurface(null), false);
    assert.equal(isFrozenSurface({ type: "PartDesign::Pad" }), false);
    assert.equal(isFrozenSurface({ static: true }), true);
    assert.equal(isFrozenSurface({ type: "Part::Feature" }), true);
    assert.equal(isFrozenSurface({ static: true, graph: {} }), false);
    assert.equal(isFrozenSurface({ type: "Part::Feature", repeat: {} }), false);
  });

  it("modifie une esquisse, une fonction ou une surface", () => {
    assert.equal(canModifyMenuTarget(null), false);
    assert.equal(canModifyMenuTarget({}), false);
    assert.equal(canModifyMenuTarget({ active: false, type: "PartDesign::Body" }), false);
    assert.equal(canModifyMenuTarget({ type: "PartDesign::Plane" }), false);
    assert.equal(canModifyMenuTarget({ type: "Part::Feature" }), false);
    assert.equal(canModifyMenuTarget({ type: "Sketcher::SketchObject" }), true);
    assert.equal(canModifyMenuTarget({ type: "PartDesign::Pad" }), true);
    assert.equal(canModifyMenuTarget({ type: "Part::Extrusion" }), true);
    assert.equal(canModifyMenuTarget({ type: "Surface::Filling" }), true);
    assert.equal(canModifyMenuTarget({ type: "App::Link" }), false);
    assert.equal(canModifyMenuTarget({ type: "PartDesign::Pad", graph: {} }), true);
  });
});
