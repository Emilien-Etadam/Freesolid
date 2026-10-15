import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { nextTab, TABS } from "../../app/managertabs.js";

describe("gestionnaire à onglets", () => {
  it("un panneau qui s'ouvre prend la main, sa fermeture rend l'arbre", () => {
    assert.equal(nextTab("tree", { panelOpen: true, panelWasOpen: false }), "props");
    assert.equal(nextTab("configs", { panelOpen: true, panelWasOpen: false }), "props");
    assert.equal(nextTab("props", { panelOpen: false, panelWasOpen: true }), "tree");
  });

  it("le choix de l'utilisateur tient sinon", () => {
    assert.equal(nextTab("tree", { panelOpen: true, panelWasOpen: true }), "tree");
    assert.equal(nextTab("display", { panelOpen: false, panelWasOpen: false }), "display");
    assert.deepEqual(TABS.map(([k]) => k), ["tree", "props", "configs", "display"]);
  });
});
