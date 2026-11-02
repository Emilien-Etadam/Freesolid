import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  canModifyMenuTarget, isBodyMenuTarget, isHideableTarget, solidParam,
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

  it("« Modifier » quand le double-clic rouvre quelque chose", () => {
    assert.equal(canModifyMenuTarget(null), false);
    assert.equal(canModifyMenuTarget({}), false);
    assert.equal(canModifyMenuTarget({ active: false, type_key: "body" }), false);
    assert.equal(canModifyMenuTarget({ type_key: "component", grounded: true }),
      false);
    assert.equal(canModifyMenuTarget({ type_key: "sketch" }), true);
    assert.equal(canModifyMenuTarget({ type_key: "pad", has_params: true }), true);
    // Pas de cote, pas d'éditeur à lui : le double-clic n'ouvrirait rien.
    assert.equal(canModifyMenuTarget({ type_key: "mirror", has_params: false }),
      false);
    assert.equal(canModifyMenuTarget(
      { type_key: "datum_plane", has_params: false }), false);
    assert.equal(canModifyMenuTarget(
      { type_key: "pad", graph: {}, has_params: false }), true);
    // Réseau de corps, suppression de corps : le double-clic les rouvre.
    assert.equal(canModifyMenuTarget({ type_key: "body_pattern" }), true);
    assert.equal(canModifyMenuTarget(
      { type_key: "remove_bodies", has_params: false }), true);
    // Surfaces : figées non, spline 3D oui même figée.
    const surface = { surface: true };
    assert.equal(canModifyMenuTarget({ type_key: "shape", static: true },
      surface), false);
    assert.equal(canModifyMenuTarget(
      { type_key: "shape", static: true, curve: {} }, surface), true);
    assert.equal(canModifyMenuTarget(
      { type_key: "surface_loft", has_params: false }, surface), false);
    assert.equal(canModifyMenuTarget(
      { type_key: "surface_extrude", has_params: true }, surface), true);
  });

  it("une ligne du dossier des surfaces se masque, courbe composite comprise", () => {
    const composite = { name: "Binder", type_key: "binder" };
    assert.equal(isHideableTarget(composite), false);
    assert.equal(isHideableTarget(composite, { surface: true }), true);
    assert.equal(isHideableTarget({ name: "Body", active: true }), true);
    assert.equal(isHideableTarget({ name: "Pad", type_key: "pad" }), false);
  });
});

describe("solidParam", () => {
  it("la ligne d'un solide envoie son rang, un corps entier rien", () => {
    assert.deepEqual(solidParam({ name: "Body", active: true, solid: 0 }), { solid: 0 });
    assert.deepEqual(solidParam({ name: "Body", active: true, solid: 2 }), { solid: 2 });
    assert.deepEqual(solidParam({ name: "Body", active: true }), {});
    assert.deepEqual(solidParam(null), {});
  });
});
