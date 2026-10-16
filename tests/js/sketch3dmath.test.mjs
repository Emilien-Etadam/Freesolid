import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { solve, cleanSpec, measure, inferAxis, onAxis, removeItems } from "../../app/sketch3dmath.js";

const CASES = JSON.parse(readFileSync(new URL("../sketch3d_cases.json", import.meta.url)));

describe("esquisse 3D : même solveur que le moteur", () => {
  for (const c of CASES) {
    it(c.name, () => {
      const out = solve(c.spec, c.fixed);
      assert.equal(out.ok, c.expected.ok);
      out.points.forEach((p, i) => p.forEach((v, k) =>
        assert.ok(Math.abs(v - c.expected.points[i][k]) < 1e-6, `${i},${k}: ${v}`)));
    });
  }
});

describe("esquisse 3D : outils", () => {
  it("infère l'axe proche, pas un autre", () => {
    assert.equal(inferAxis([10, 0.5, 0]), "X");
    assert.equal(inferAxis([0.2, 0, -8]), "Z");
    assert.equal(inferAxis([5, 5, 0]), null);
    assert.deepEqual(onAxis([1, 2, 3], [9, 8, 7], "Y"), [1, 8, 3]);
  });

  it("mesure les cotes", () => {
    const spec = cleanSpec(CASES[1].spec);
    const out = solve(spec, [0]);
    assert.ok(Math.abs(measure(spec, out.points, spec.dims[0]) - 90) < 1e-6);
  });

  it("retirer une ligne emporte ses cotes, ses relations et ses points seuls", () => {
    const spec = {
      points: [[0, 0, 0], [10, 0, 0], [10, 10, 0]],
      entities: [{ type: "line", a: 0, b: 1 }, { type: "line", a: 1, b: 2 }],
      dims: [{ type: "length", entity: 1, value: 10 }, { type: "length", entity: 0, value: 10 }],
      relations: [{ type: "axis", entity: 1, axis: "Y" }],
    };
    const out = removeItems(spec, { entities: [1] });
    assert.equal(out.points.length, 2);
    assert.equal(out.entities.length, 1);
    assert.deepEqual(out.dims, [{ type: "length", entity: 0, value: 10 }]);
    assert.deepEqual(out.relations, []);
    const noPoint = removeItems(spec, { points: [1] });
    assert.equal(noPoint.entities.length, 0);
    assert.equal(noPoint.points.length, 0);
  });
});
