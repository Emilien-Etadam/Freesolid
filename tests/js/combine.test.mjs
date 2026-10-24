import { afterEach, describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  addCombineTools,
  combineConfirm,
  combineFinished,
  combineToolOptions,
  resetCombineTools,
} from "../../app/combine.js";

afterEach(() => {
  resetCombineTools();
});

const TREE = {
  bodies: [
    { name: "Body", label: "Pièce", active: true },
    { name: "Body001", label: "Outil", active: false },
  ],
  pieces: [{ name: "Piece", label: "Pièce rapportée" }],
};

describe("combineToolOptions", () => {
  it("sans plugin : les corps inactifs seulement", () => {
    assert.deepEqual(combineToolOptions(TREE), [["Body001", "Outil"]]);
    assert.deepEqual(combineToolOptions(null), []);
  });

  it("ajoute les outils des plugins, après les corps", () => {
    addCombineTools({
      options: (tree) => tree.pieces.map((p) => [p.name, p.label]),
    });
    assert.deepEqual(combineToolOptions(TREE), [
      ["Body001", "Outil"],
      ["Piece", "Pièce rapportée"],
    ]);
  });

  it("un plugin cassé ou une entrée mal formée n'empêche rien", () => {
    addCombineTools({ options: () => { throw new Error("boum"); } });
    addCombineTools({ options: () => [["", "vide"], "texte", ["Seul"]] });
    addCombineTools({});
    assert.deepEqual(combineToolOptions(TREE), [
      ["Body001", "Outil"],
      ["Seul", "Seul"],
    ]);
  });
});

describe("combineConfirm", () => {
  it("se tait sans plugin, rend la première question sinon", () => {
    assert.equal(combineConfirm(TREE, "Body001"), null);
    addCombineTools({ options: () => [], confirm: () => null });
    addCombineTools({ options: () => [], confirm: () => { throw new Error(); } });
    addCombineTools({
      options: () => [],
      confirm: (_tree, tool) => (tool === "Piece" ? "Long. Continuer ?" : null),
    });
    assert.equal(combineConfirm(TREE, "Body001"), null);
    assert.equal(combineConfirm(TREE, "Piece"), "Long. Continuer ?");
  });
});

describe("combineFinished", () => {
  it("prévient chaque plugin, avec l'arbre d'avant", () => {
    const seen = [];
    addCombineTools({
      options: () => [],
      finished: () => { throw new Error("boum"); },
    });
    addCombineTools({
      options: () => [],
      finished: (tree, tool, seconds) => seen.push([tree, tool, seconds]),
    });
    combineFinished(TREE, "Piece", 2.5);
    assert.deepEqual(seen, [[TREE, "Piece", 2.5]]);
  });
});
