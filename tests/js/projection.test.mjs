import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { perspectiveEye, perspectiveFrustum } from "../../app/projection.js";

describe("projection perspective", () => {
  it("l'œil voit la même hauteur au centre que la vue orthographique", () => {
    const eye = perspectiveEye(100, 30);
    assert.ok(Math.abs(2 * eye * Math.tan(Math.PI / 12) - 100) < 1e-9);
  });

  it("frustum : proportions conservées, recul de l'œil", () => {
    const f = perspectiveFrustum({ width: 160, height: 100, rigDistance: 50 });
    assert.ok(Math.abs((f.right - f.left) / (f.top - f.bottom) - 1.6) < 1e-9);
    // À la distance de l'œil, le frustum couvre exactement 100 de haut.
    assert.ok(Math.abs((f.top - f.bottom) * f.eye / f.near - 100) < 1e-9);
    assert.ok(Math.abs(f.back - (f.eye - 50)) < 1e-9);
    assert.ok(f.near > 0 && f.far > f.eye);
  });
});
