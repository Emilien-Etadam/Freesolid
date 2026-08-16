import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { chainClickAction } from "../../app/geom2d.js";

const SNAP_PX = 12;

describe("chainClickAction", () => {
  it("ajoute le premier point (pas de précédent)", () => {
    assert.equal(
      chainClickAction(null, { x: 10, y: 10 }, SNAP_PX),
      "add");
  });

  it("termine si le clic tombe sur le point précédent", () => {
    assert.equal(
      chainClickAction({ x: 40, y: 80 }, { x: 40, y: 80 }, SNAP_PX),
      "finish");
  });

  it("termine un double-clic typique (1 px d'écart)", () => {
    assert.equal(
      chainClickAction({ x: 100, y: 200 }, { x: 101, y: 200 }, SNAP_PX),
      "finish");
  });

  it("termine juste sous le seuil de snap", () => {
    assert.equal(
      chainClickAction({ x: 0, y: 0 }, { x: SNAP_PX - 0.01, y: 0 }, SNAP_PX),
      "finish");
  });

  it("ajoute au seuil exact — les petits segments voulus restent possibles", () => {
    assert.equal(
      chainClickAction({ x: 0, y: 0 }, { x: SNAP_PX, y: 0 }, SNAP_PX),
      "add");
  });

  it("ajoute un clic clairement au-delà du snap", () => {
    assert.equal(
      chainClickAction({ x: 0, y: 0 }, { x: 40, y: 30 }, SNAP_PX),
      "add");
  });
});
