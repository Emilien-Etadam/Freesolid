// Révolution : l'axe choisi part avec la fonction et se réédite.

import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  revolutionAxisOptions, revolutionCreationParams, revolutionEditValues,
} from "../../app/features.js";

const sketch = {
  lines: [
    { id: 0, construction: false, x1: 0, y1: 0, x2: 10, y2: 0 },
    { id: 3, construction: true, x1: 5, y1: 0, x2: 5, y2: 10 },
  ],
};

describe("création de la révolution", () => {
  it("place les lignes de construction avant les lignes réelles", () => {
    const values = revolutionAxisOptions(sketch).map(([value]) => value);
    assert.deepEqual(values.slice(0, 4),
      ["vertical", "horizontal", "line:3", "line:0"]);
    assert.deepEqual(values.slice(-3), ["X", "Y", "Z"]);
  });

  it("omet l'axe vertical et n'envoie le plan milieu qu'à la place de l'inversion", () => {
    assert.deepEqual(
      revolutionCreationParams({ angle: 360, axis: "vertical", cond: "one" },
        "add_revolution"),
      { op: "add_revolution", params: { angle: 360 } });
    assert.deepEqual(
      revolutionCreationParams({
        angle: 180, axis: "line:3", cond: "milieu", reversed: true,
      }, "add_groove"),
      { op: "add_groove", params: { angle: 180, axis: "line:3", midplane: true } });
  });

  it("refuse un angle nul ou au-delà de 360", () => {
    assert.equal(revolutionCreationParams(
      { angle: 0, axis: "vertical", cond: "one" }, "add_revolution"), null);
    assert.equal(revolutionCreationParams(
      { angle: 361, axis: "X", cond: "one" }, "add_revolution"), null);
    assert.deepEqual(
      revolutionCreationParams(
        { angle: 90, axis: "X", cond: "one", reversed: true }, "add_revolution"),
      { op: "add_revolution", params: { angle: 90, axis: "X", reversed: true } });
  });
});

describe("réédition de la révolution", () => {
  const revolution = {
    axis: "line:3", angle: 360, reversed: false, midplane: false,
  };
  const params = [{ key: "angle", value: 360 }];

  it("ne renvoie rien si les champs n'ont pas changé", () => {
    assert.deepEqual(revolutionEditValues({
      angle: 360, axis: "line:3", cond: "one", reversed: false,
    }, revolution, params), {});
  });

  it("envoie l'axe, l'angle et le plan milieu quand ils changent", () => {
    assert.deepEqual(revolutionEditValues({
      angle: "180", axis: "vertical", cond: "milieu", reversed: true,
    }, revolution, params), {
      angle: 180, axis: "vertical", reversed: false, midplane: true,
    });
  });

  it("conserve une expression d'angle", () => {
    const expressed = [{ key: "angle", value: 360, expr: "2*Tours" }];
    assert.deepEqual(revolutionEditValues({
      angle: "2*Tours", axis: "line:3", cond: "one", reversed: false,
    }, revolution, expressed), {});
    assert.deepEqual(revolutionEditValues({
      angle: "3*Tours", axis: "line:3", cond: "one", reversed: false,
    }, revolution, expressed), { angle: "3*Tours" });
  });
});
