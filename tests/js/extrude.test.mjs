import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { extrudeBuild, extrudeGroups, extrudeInvalid } from "../../app/features.js";

describe("extrudeBuild", () => {
  it("borgne : profondeur positive", () => {
    assert.deepEqual(extrudeBuild("add_pad", { cond: "borgne", length: "-12" }),
      { op: "add_pad", params: { reversed: false, cond: "borgne", length: 12 } });
    assert.equal(extrudeBuild("add_pad", { cond: "borgne", length: "0" }), null);
  });

  it("plan milieu : condition borgne + midplane", () => {
    const b = extrudeBuild("add_pad", { cond: "milieu", length: 20 });
    assert.equal(b.params.midplane, true);
    assert.equal(b.params.cond, "borgne");
  });

  it("jusqu'à la face : il faut une face", () => {
    assert.equal(extrudeBuild("add_pocket", { cond: "face" }), null);
    const b = extrudeBuild("add_pocket",
      { cond: "face", face: { kind: "face", face: 3 }, offset: "1,5" });
    assert.equal(b.params.face, 3);
    assert.equal(b.params.offset, 1.5);
    assert.equal(b.params.length, undefined);
  });

  it("à travers tout : pas de profondeur", () => {
    assert.deepEqual(extrudeBuild("add_pocket", { cond: "travers" }).params,
      { reversed: false, cond: "travers" });
  });

  it("deuxième direction et dépouilles", () => {
    const b = extrudeBuild("add_pad", {
      cond: "borgne", length: 10, taper: 2,
      dir2: true, cond2: "borgne", length2: 4, taper2: 1,
    });
    assert.deepEqual(b.params, {
      reversed: false, cond: "borgne", length: 10, taper: 2,
      cond2: "borgne", length2: 4, taper2: 1,
    });
  });

  it("le plan milieu ignore la deuxième direction", () => {
    const b = extrudeBuild("add_pad",
      { cond: "milieu", length: 10, dir2: true, cond2: "borgne", length2: 4 });
    assert.equal(b.params.cond2, undefined);
  });

  it("message d'erreur selon la condition", () => {
    assert.match(extrudeInvalid({ cond: "face" }), /face/);
    assert.equal(extrudeInvalid({ cond: "borgne" }), "Profondeur invalide");
  });

  it("l'enlèvement commence par « à travers tout », le bossage par « borgne »", () => {
    assert.equal(extrudeGroups("pocket")[0].rows[0].value, "travers");
    assert.equal(extrudeGroups("pad")[0].rows[0].value, "borgne");
  });
});
