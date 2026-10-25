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
    assert.equal(isFrozenSurface({ type_key: "pad" }), false);
    assert.equal(isFrozenSurface({ static: true }), true);
    assert.equal(isFrozenSurface({ type_key: "shape" }), true);
    assert.equal(isFrozenSurface({ static: true, graph: {} }), false);
    assert.equal(isFrozenSurface({ type_key: "shape", repeat: {} }), false);
  });

  it("modifie une esquisse, une fonction ou une surface", () => {
    assert.equal(canModifyMenuTarget(null), false);
    assert.equal(canModifyMenuTarget({}), false);
    assert.equal(canModifyMenuTarget({ active: false, type_key: "body" }), false);
    assert.equal(canModifyMenuTarget({ type_key: "datum_plane" }), false);
    assert.equal(canModifyMenuTarget({ type_key: "shape" }), false);
    assert.equal(canModifyMenuTarget({ type_key: "sketch" }), true);
    assert.equal(canModifyMenuTarget({ type_key: "pad" }), true);
    assert.equal(canModifyMenuTarget({ type_key: "surface_extrude" }), true);
    assert.equal(canModifyMenuTarget({ type_key: "surface_fill" }), true);
    assert.equal(canModifyMenuTarget({ type_key: "component" }), false);
    assert.equal(canModifyMenuTarget({ type_key: "pad", graph: {} }), true);
  });
});
