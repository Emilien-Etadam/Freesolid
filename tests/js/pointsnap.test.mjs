import { test } from "node:test";
import assert from "node:assert/strict";

import { edgeSnapPoints, snapFacePoint } from "../../app/pointsnap.js";

// Vue de dessus, 1 mm = 10 px : le pixel d'un point est (10x, -10y).
const project = (p) => ({ x: p.x * 10, y: -p.y * 10 });
const UP = [0, 0, 1];

function circleEdges() {
  // Un cercle fermé de rayon 20 à z = 32 (centre exact donné par le
  // moteur) et un segment ouvert de (30, 0, 32) à (30, 10, 32).
  const positions = [];
  const steps = 8;
  for (let i = 0; i <= steps; i++) {
    const a = (i / steps) * 2 * Math.PI;
    positions.push(20 * Math.cos(a), 20 * Math.sin(a), 32);
  }
  positions.push(30, 0, 32, 30, 10, 32);
  const indices = [];
  for (let i = 0; i < steps; i++) indices.push(i, i + 1);
  indices.push(steps + 1, steps + 2);
  return {
    positions, indices,
    groups: [
      { edgeId: 0, start: 0, count: 2 * steps, center: [0, 0, 32] },
      { edgeId: 1, start: 2 * steps, count: 2 },
    ],
  };
}

test("points remarquables : centre du cercle, extrémités du segment", () => {
  const points = edgeSnapPoints(circleEdges());
  assert.deepEqual(points.map((p) => p.kind), ["center", "vertex", "vertex"]);
  assert.deepEqual([points[0].x, points[0].y, points[0].z], [0, 0, 32]);
});

test("un clic près du centre s'y aimante", () => {
  const points = edgeSnapPoints(circleEdges());
  const snapped = snapFacePoint({ x: 0.6, y: -0.5, z: 32 }, UP, points, project);
  assert.equal(snapped.snapped, "center");
  assert.deepEqual([snapped.x, snapped.y, snapped.z], [0, 0, 32]);
});

test("un clic loin de tout reste où il est", () => {
  const points = edgeSnapPoints(circleEdges());
  const snapped = snapFacePoint({ x: 8, y: 5, z: 32 }, UP, points, project);
  assert.equal(snapped.snapped, null);
  assert.deepEqual([snapped.x, snapped.y], [8, 5]);
});

test("un point hors du plan de la face ne compte pas", () => {
  const points = [{ x: 0, y: 0, z: 12, kind: "center" }];
  const snapped = snapFacePoint({ x: 0.3, y: 0, z: 32 }, UP, points, project);
  assert.equal(snapped.snapped, null);
});

test("sans arêtes, le clic est rendu tel quel", () => {
  assert.deepEqual(edgeSnapPoints(null), []);
  const snapped = snapFacePoint({ x: 1, y: 2, z: 3 }, null, [], project);
  assert.deepEqual(snapped, { x: 1, y: 2, z: 3, snapped: null });
});
