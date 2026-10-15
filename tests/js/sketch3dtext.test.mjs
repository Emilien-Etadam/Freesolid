import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { dimText, entityText, dimLabel, dimFromPicks, findDim } from "../../app/sketch3dtext.js";

const spec = {
  points: [[0, 0, 0], [10, 0, 0], [10, 10, 0]],
  entities: [{ type: "line", a: 0, b: 1 }, { type: "line", a: 1, b: 2 },
             { type: "point", p: 2 }],
  relations: [{ type: "axis", entity: 0, axis: "X" }],
  dims: [],
};
const line = (index) => ({ kind: "entity", index });
const point = (index) => ({ kind: "point", index });

describe("esquisse 3D : libellés", () => {
  it("écrit les cotes et les entités", () => {
    assert.equal(dimText({ type: "length", value: 30 }), "30");
    assert.equal(dimText({ type: "angle", value: 90.00004 }), "90°");
    assert.match(entityText(spec, 0), /X/);
    assert.match(entityText(spec, 2), /P3/);
    assert.match(dimLabel(spec, { type: "distance", p1: 0, p2: 2, value: 5 }), /P1.*P3/);
  });
});

describe("esquisse 3D : outil Cotation", () => {
  it("une ligne puis le vide : sa longueur", () => {
    assert.deepEqual(dimFromPicks(spec, [], line(0)), { wait: line(0) });
    assert.deepEqual(dimFromPicks(spec, [line(0)], null),
      { dim: { type: "length", entity: 0 } });
  });

  it("deux lignes : leur angle ; deux points : leur distance", () => {
    assert.deepEqual(dimFromPicks(spec, [line(0)], line(1)),
      { dim: { type: "angle", e1: 0, e2: 1 } });
    assert.deepEqual(dimFromPicks(spec, [point(0)], point(2)),
      { dim: { type: "distance", p1: 0, p2: 2 } });
  });

  it("le reste repart de zéro", () => {
    assert.deepEqual(dimFromPicks(spec, [], null), { reset: true });
    assert.deepEqual(dimFromPicks(spec, [point(0)], line(1)), { reset: true });
    assert.deepEqual(dimFromPicks(spec, [], line(2)), { reset: true });
  });
});

describe("esquisse 3D : cote déjà posée", () => {
  it("se retrouve, dans un sens ou dans l'autre", () => {
    const withDims = { ...spec, dims: [{ type: "length", entity: 1, value: 5 },
                                       { type: "angle", e1: 0, e2: 1, value: 90 }] };
    assert.equal(findDim(withDims, { type: "length", entity: 1 }), 0);
    assert.equal(findDim(withDims, { type: "angle", e1: 1, e2: 0 }), 1);
    assert.equal(findDim(withDims, { type: "length", entity: 0 }), -1);
  });
});
