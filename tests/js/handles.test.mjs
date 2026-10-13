import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { axisParam } from "../../app/handles.js";

describe("poignée le long d'un axe", () => {
  it("donne la position sur l'axe vue par le rayon", () => {
    // Axe Z depuis l'origine, rayon horizontal qui croise z = 7.
    assert.equal(axisParam([10, 0, 7], [-1, 0, 0], [0, 0, 0], [0, 0, 1]), 7);
    // Rayon oblique : le point le plus proche reste z = 3.
    const t = axisParam([5, 5, 3], [-1, -1, 0], [0, 0, 0], [0, 0, 1]);
    assert.ok(Math.abs(t - 3) < 1e-9);
  });

  it("rien quand le rayon suit l'axe", () => {
    assert.equal(axisParam([0, 0, 10], [0, 0, -1], [0, 0, 0], [0, 0, 1]), null);
  });
});
