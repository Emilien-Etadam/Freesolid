// Forme libre par points de contrôle : fonctions pures (sans Three.js).
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { movedPoles, nearestPole, polesParams } from "../../app/poles.js";

const GRID = [[[0, 0, 0], [0, 10, 0]], [[10, 0, 0], [10, 10, 0]]];

describe("points de contrôle", () => {
  it("déplace le pôle désigné (indices base 1) sans toucher la grille", () => {
    const out = movedPoles(GRID, [[2, 1, 0, 0, 5]]);
    assert.deepEqual(out[1][0], [10, 0, 5]);
    assert.deepEqual(out[0][0], [0, 0, 0]);
    assert.deepEqual(GRID[1][0], [10, 0, 0]);
  });

  it("ignore un pôle hors de la grille", () => {
    assert.deepEqual(movedPoles(GRID, [[9, 9, 1, 1, 1]]), GRID);
  });

  it("choisit le pôle le plus proche à l'écran, rien au-delà de la portée", () => {
    const screen = [[0, 0], [20, 0], [24, 3]];
    assert.equal(nearestPole(screen, [22, 1]), 1);
    assert.equal(nearestPole(screen, [23, 3]), 2);
    assert.equal(nearestPole(screen, [100, 100]), -1);
  });

  it("construit l'op : surface, face, grille et déplacements non nuls", () => {
    assert.deepEqual(polesParams({
      surface: { name: "S", face: 1 }, grid: "8",
      moves: [[3, 3, 0, 0, 6], [2, 2, 0, 0, 0]] }),
    { surface: "S", face: 1, grid: 8, moves: [[3, 3, 0, 0, 6]] });
    assert.equal(polesParams({ surface: null, moves: [[1, 1, 0, 0, 1]] }),
      null);
    assert.equal(polesParams({ surface: { name: "S" }, moves: [] }), null);
  });
});
