import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { displayRows, nextTab, TABS } from "../../app/managertabs.js";

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

describe("displayRows", () => {
  it("donne un corps par solide, chacun avec son masquage et sa couleur", () => {
    const rows = displayRows({
      bodies: [
        { name: "Body", label: "Extrusion", has_solid: true, hidden: false,
          color: "#888888", solids: [
            { label: "Extrusion", color: null, hidden: true },
            { label: "Bloc", color: "#cc3333", hidden: false }] },
        { name: "Body001", label: "Cylindre", has_solid: true, hidden: false },
      ],
      surfaces: [{ name: "Surface", label: "Surface", hidden: false }],
    });
    assert.deepEqual(rows.map((r) => [r.label, r.solid, r.hidden, r.color ?? null]), [
      ["Extrusion", 0, true, "#888888"],
      ["Bloc", 1, false, "#cc3333"],
      ["Cylindre", undefined, false, null],
      ["Surface", undefined, false, null],
    ]);
  });

  it("masque tous les solides d'un corps masqué en entier", () => {
    const rows = displayRows({ bodies: [{ name: "Body", label: "E",
      has_solid: true, hidden: true, solids: [
        { label: "E[1]", color: null, hidden: false },
        { label: "E[2]", color: null, hidden: false }] }] });
    assert.deepEqual(rows.map((r) => r.hidden), [true, true]);
  });
});
