import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { editableSpline, lift, flatten } from "../../app/splineedit2d.js";

describe("spline d'esquisse éditable", () => {
  const entity = { id: 3, kind: "spline", spline: { points: [[0, 0], [5, 5], [10, 0]],
    closed: false, tangents: [null, { dir: [1, 0], in: 1, out: 2 }, null] } };

  it("reconnaît une spline qui porte sa définition", () => {
    assert.equal(editableSpline(entity), entity);
    assert.equal(editableSpline({ kind: "spline", npoints: 7 }), null);
    assert.equal(editableSpline({ kind: "ellipse" }), null);
    assert.equal(editableSpline(null), null);
  });

  it("passe en 3D pour le calcul et revient à plat pour le moteur", () => {
    const up = lift(entity.spline);
    assert.deepEqual(up.points[1], [5, 5, 0]);
    assert.deepEqual(up.tangents[1].dir, [1, 0, 0]);
    const flat = flatten(up);
    assert.deepEqual(flat.points, entity.spline.points);
    assert.deepEqual(flat.tangents[1], { dir: [1, 0], in: 1, out: 2 });
    assert.equal(flat.tangents[0], null);
  });
});
