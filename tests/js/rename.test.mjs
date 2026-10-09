import assert from "node:assert/strict";
import { test } from "node:test";
import { RENAME_GAP_MS, renameClickAction } from "../../app/rename.js";

test("le premier clic sélectionne", () => {
  assert.equal(renameClickAction({
    previousAt: null, sameRow: false, now: 1000,
  }), "select");
});

test("un second clic rapide n'est pas un renommage", () => {
  assert.equal(renameClickAction({
    previousAt: 1000, sameRow: true, now: 1000 + RENAME_GAP_MS - 1,
  }), "ignore");
});

test("un second clic lent renomme la même ligne", () => {
  assert.equal(renameClickAction({
    previousAt: 1000, sameRow: true, now: 1000 + RENAME_GAP_MS,
  }), "rename");
});

test("une autre ligne est une sélection", () => {
  assert.equal(renameClickAction({
    previousAt: 1000, sameRow: false, now: 2000,
  }), "select");
});

test("un glisser ou un déplacement ignore le clic", () => {
  assert.equal(renameClickAction({
    previousAt: 1000, sameRow: true, now: 2000, dragging: true,
  }), "ignore");
  assert.equal(renameClickAction({
    previousAt: 1000, sameRow: true, now: 2000, moved: true,
  }), "ignore");
});
