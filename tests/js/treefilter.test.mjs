// Filtre de l'arbre de création : casse, accents, parents, barre.

import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { filterTreeLines, foldText } from "../../app/treefilter.js";

// Corps volumiques ▸ Pièce ; Bossage1 ▸ Esquisse1 ; barre ; Enlèvement1.
const LINES = [
  { label: "▾Corps volumiques (1)", parent: -1 },
  { label: "Pièce", parent: 0 },
  { label: "▾Bossage1", parent: -1 },
  { label: "Esquisse1", parent: 2 },
  { label: "▲ barre de retour arrière ▲", parent: -1, keep: true },
  { label: "Enlèvement1", parent: -1 },
];

const shown = (query) => filterTreeLines(LINES, query)
  .flatMap((visible, i) => (visible ? [i] : []));

describe("foldText", () => {
  it("ignore la casse et les accents", () => {
    assert.equal(foldText("ÉnLèVement Çà"), "enlevement ca");
    assert.equal(foldText(null), "");
  });
});

describe("filterTreeLines", () => {
  it("filtre vide : tout paraît", () => {
    assert.deepEqual(shown(""), [0, 1, 2, 3, 4, 5]);
    assert.deepEqual(shown("   "), [0, 1, 2, 3, 4, 5]);
  });

  it("garde ce qui correspond, sans casse ni accents, et la barre", () => {
    assert.deepEqual(shown("ENLEVEMENT"), [4, 5]);
    assert.deepEqual(shown("bossage"), [2, 4]);
  });

  it("garde le parent d'un enfant qui correspond", () => {
    assert.deepEqual(shown("esquisse"), [2, 3, 4]);
    assert.deepEqual(shown("piece"), [0, 1, 4]);
  });

  it("remonte jusqu'au premier niveau", () => {
    const lines = [
      { label: "Dossier", parent: -1 },
      { label: "Congé", parent: 0 },
      { label: "Esquisse7", parent: 1 },
    ];
    assert.deepEqual(filterTreeLines(lines, "7"), [true, true, true]);
    assert.deepEqual(filterTreeLines(lines, "conge"), [true, true, false]);
  });

  it("rien ne correspond : la barre seule", () => {
    assert.deepEqual(shown("zzz"), [4]);
  });
});
