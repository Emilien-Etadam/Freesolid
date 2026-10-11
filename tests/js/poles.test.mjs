// Forme libre par points de contrôle : fonctions pures (sans Three.js).
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { movedPoles, nearestPole, poleName, polesParams, remapMoves }
  from "../../app/poles.js";

const GRIDS = [
  { face: 0, grid: [2, 2], poles: [[[0, 0, 0], [0, 10, 0]],
                                   [[10, 0, 0], [10, 10, 0]]] },
  { face: 1, grid: [2, 2], poles: [[[0, 0, 5], [0, 10, 5]],
                                   [[10, 0, 5], [10, 10, 5]]] },
];

describe("points de contrôle", () => {
  it("déplace le pôle désigné de sa face, sans toucher les grilles", () => {
    const out = movedPoles(GRIDS, [[1, 2, 1, 0, 0, 5]]);
    assert.deepEqual(out[1].poles[1][0], [10, 0, 10]);
    assert.deepEqual(out[0].poles[1][0], [10, 0, 0]);
    assert.deepEqual(GRIDS[1].poles[1][0], [10, 0, 5]);
  });

  it("ignore un pôle hors de la grille ou d'une face inconnue", () => {
    assert.deepEqual(movedPoles(GRIDS, [[0, 9, 9, 1, 1, 1],
      [7, 1, 1, 1, 1, 1]]), GRIDS);
  });

  it("reporte les pôles réglés sur une grille plus fine, puis plus grossière", () => {
    const small = [{ face: 0, grid: [6, 6] }, { face: 1, grid: [6, 6] }];
    const big = [{ face: 0, grid: [11, 11] }, { face: 1, grid: [11, 11] }];
    assert.deepEqual(remapMoves([[0, 3, 3, 0, 0, 6], [1, 6, 1, 1, 0, 0]],
      small, big), [[0, 5, 5, 0, 0, 6], [1, 11, 1, 1, 0, 0]]);
    // Deux pôles voisins qui tombent au même endroit : un seul reste.
    assert.deepEqual(remapMoves([[0, 4, 4, 0, 0, 1], [0, 5, 5, 0, 0, 2]],
      big, small), [[0, 3, 3, 0, 0, 1]]);
  });

  it("choisit le pôle le plus proche à l'écran, rien au-delà de la portée", () => {
    const screen = [[0, 0], [20, 0], [24, 3]];
    assert.equal(nearestPole(screen, [22, 1]), 1);
    assert.equal(nearestPole(screen, [23, 3]), 2);
    assert.equal(nearestPole(screen, [100, 100]), -1);
  });

  it("construit l'op : surface, grille et déplacements non nuls", () => {
    assert.deepEqual(polesParams({
      surface: { name: "S" }, grid: "8",
      moves: [[1, 3, 3, 0, 0, 6], [0, 2, 2, 0, 0, 0]] }),
    { surface: "S", grid: 8, moves: [[1, 3, 3, 0, 0, 6]] });
    assert.equal(polesParams({ surface: null, moves: [[0, 1, 1, 0, 0, 1]] }),
      null);
    assert.equal(polesParams({ surface: { name: "S" }, moves: [] }), null);
  });

  it("nomme une ligne par sa face (base 1) et ses indices", () => {
    assert.equal(poleName([1, 3, 4, 0, 0, 1]), "F2 · 3, 4");
  });
});
