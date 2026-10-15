import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  controls, sample, curvatureComb, fromBeziers, handleTips, dragTip,
  insertPoint, removePoint, simplify, relax, nearestOnCurve, deviation,
  pinTangent,
} from "../../app/splinemath.js";

const CASES = JSON.parse(readFileSync(new URL("../splinemath_cases.json", import.meta.url)));
const near = (a, b, tol = 1e-9) => a.every((v, k) => Math.abs(v - b[k]) <= tol);

describe("spline : même calcul que le moteur", () => {
  for (const c of CASES) {
    it(c.name, () => {
      const got = controls(c.points, c.closed, c.tangents);
      assert.equal(got.length, c.controls.length);
      got.forEach((span, i) => span.forEach((p, k) => assert.ok(near(p, c.controls[i][k]))));
    });
  }
});

describe("spline : édition", () => {
  const pts = CASES[3].points;

  it("l'échantillonnage passe par les points", () => {
    const line = sample(pts, { perSpan: 8 });
    assert.equal(line.length, 5 * 8 + 1);
    assert.ok(near(line[8], pts[1]));
    assert.deepEqual(sample([[0, 0], [1, 0]]), [[0, 0, 0], [1, 0, 0]]);
    assert.equal(sample(pts, { spline: false }).length, pts.length);
  });

  it("insérer un point ne change pas la forme", () => {
    const { points, tangents, index } = insertPoint(pts, false, null, 2, 0.4);
    assert.equal(points.length, pts.length + 1);
    assert.equal(index, 3);
    assert.ok(deviation({ points: pts }, { points, tangents }) < 1e-3);
  });

  it("retirer un point", () => {
    const { points, tangents } = removePoint(pts, [null, { dir: [1, 0, 0], in: 1, out: 1 }], 1);
    assert.equal(points.length, pts.length - 1);
    assert.equal(tangents[1], null);
  });

  it("tirer une poignée : direction commune, rapport gardé ou non", () => {
    const tip = handleTips(pts, false, null, 2).out;
    const target = [tip[0], tip[1] + 2, tip[2]];
    const both = dragTip(pts, false, null, 2, "out", target);
    const alone = dragTip(pts, false, null, 2, "out", target, { alone: true });
    assert.ok(near(both[2].dir, alone[2].dir));
    assert.ok(Math.abs(both[2].out - alone[2].out) < 1e-12);
    assert.notEqual(both[2].in, alone[2].in);
    assert.ok(near(handleTips(pts, false, alone, 2).out, target, 1e-9));
    // Au bout d'une courbe ouverte, une seule poignée.
    assert.equal(handleTips(pts, false, null, 0).in, null);
  });

  it("figer une pente ne change rien", () => {
    const pinned = pinTangent(pts, false, null, 2);
    assert.ok(pinned[2]);
    assert.ok(deviation({ points: pts }, { points: pts, tangents: pinned }) < 1e-9);
  });

  it("aller-retour par les arcs de Bézier", () => {
    const c = CASES[5];
    const back = fromBeziers(controls(c.points, false, c.tangents));
    assert.deepEqual(back.tangents.map(Boolean), [false, false, true, false, false]);
  });

  it("simplifier garde la courbe dans la tolérance", () => {
    const dense = sample(pts, { perSpan: 3 });
    const simple = simplify(dense, false, null, 0.05);
    assert.ok(simple.points.length < dense.length);
    assert.ok(deviation({ points: dense }, { points: simple.points, tangents: simple.tangents }) <= 0.05 + 1e-9);
  });

  it("lisser rapproche les points intérieurs, garde les bouts", () => {
    const zig = [[0, 0, 0], [1, 1, 0], [2, -1, 0], [3, 0, 0]];
    const out = relax(zig, false, 0.5);
    assert.deepEqual(out[0], zig[0]);
    assert.deepEqual(out[3], zig[3]);
    assert.ok(Math.abs(out[1][1]) < 1);
  });

  it("peigne : dents nulles sur un segment, du côté convexe sinon", () => {
    const flat = curvatureComb([[0, 0], [5, 0], [10, 0]]);
    assert.ok(flat.every(([p, q]) => near(p, q)));
    const arch = curvatureComb([[0, 0], [5, 5], [10, 0]], { scale: 10 });
    const top = arch[Math.floor(arch.length / 2)];
    assert.ok(top[1][1] > top[0][1]); // centre en bas, dent vers le haut
  });

  it("point le plus proche sur la courbe", () => {
    const hit = nearestOnCurve(pts, false, null, pts[2]);
    assert.ok(hit.dist < 1e-6);
  });
});
