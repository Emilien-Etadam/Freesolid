import assert from "node:assert/strict";
import { describe, it } from "node:test";
import LAYOUT from "../../app/ribbon.json" with { type: "json" };
import {
  commandLabel, commandSearch, placeNearPointer, ribbonCommands,
  shortcutOffers,
} from "../../app/shortcutbar.js";

const TOOLS = [
  { kind: "tool", tool: "line", label: "Ligne" },
  { kind: "tool", tool: "dim", label: "Cotation" },
  { kind: "tool", tool: "spline", label: "Spline" },
];

describe("boîte de raccourcis", () => {
  const commands = ribbonCommands(LAYOUT);

  it("hors esquisse propose esquisse, extrusion, enlèvement, congé, chanfrein et les répétitions", () => {
    const offers = shortcutOffers({
      sketch: false, query: "", commands, sketchTools: TOOLS,
    });
    assert.deepEqual(offers.map((offer) => offer.id), [
      "btn-sketch", "btn-pad", "btn-pocket", "btn-fillet", "btn-chamfer",
      "btn-linpattern", "btn-polpattern", "btn-repeat-variable",
    ]);
  });

  it("en esquisse propose le tracé et la cotation, spline comprise", () => {
    const offers = shortcutOffers({
      sketch: true, query: "", commands, sketchTools: TOOLS,
    });
    assert.deepEqual(offers.map((offer) => offer.tool), ["line", "dim", "spline"]);
  });

  it("trouve congé en français et fillet en anglais", () => {
    const fr = shortcutOffers({
      sketch: false, query: "congé", commands, sketchTools: TOOLS,
    });
    assert.ok(fr.some((offer) => offer.id === "btn-fillet"));
    const en = shortcutOffers({
      sketch: true, query: "fillet", commands, sketchTools: TOOLS,
      translate: (label) => (label === "Congé" ? "Fillet" : label),
    });
    assert.ok(en.some((offer) => offer.id === "btn-fillet"));
    assert.equal(en.some((offer) => offer.id === "btn-pad"), false);
  });

  it("raccourcit un titre sans perdre le nom", () => {
    assert.equal(commandLabel("Ligne (L)"), "Ligne");
    assert.equal(commandLabel("Spline — points cliqués, Entrée pour terminer"),
      "Spline");
    assert.equal(commandLabel("", "line"), "line");
  });

  it("la recherche du haut nomme l'onglet et cache l'esquisse", () => {
    const sketchTools = [
      { kind: "tool", tool: "line", label: "Ligne" },
    ];
    assert.equal(commands.some((command) => command.tab === "Fonctions"), true);
    assert.deepEqual(commandSearch({
      query: "  ", commands, sketchTools, sketch: false,
    }), []);
    const fillet = commandSearch({
      query: "congé", commands, sketchTools, sketch: false,
    });
    assert.ok(fillet.some((command) =>
      command.id === "btn-fillet" && command.tab === "Fonctions"));
    assert.equal(commandSearch({
      query: "ligne", commands, sketchTools, sketch: false,
    }).some((command) => command.tool === "line"), false);
    const drawing = commandSearch({
      query: "ligne", commands, sketchTools, sketch: true,
    });
    assert.ok(drawing.some((command) =>
      command.tool === "line" && command.tab === "Esquisse"));
    const english = commandSearch({
      query: "fillet", commands, sketchTools, sketch: false,
      translate: (label) => (label === "Congé" ? "Fillet" : label),
    });
    assert.ok(english.some((command) => command.id === "btn-fillet"));
  });

  it("se pose sous le pointeur et reste dans l'écran", () => {
    assert.deepEqual(
      placeNearPointer({ x: 40, y: 50 }, { width: 100, height: 80 },
        { width: 800, height: 600 }),
      { left: 40, top: 64 });
    const corner = placeNearPointer({ x: 790, y: 590 },
      { width: 100, height: 80 }, { width: 800, height: 600 });
    assert.equal(corner.left, 692);
    assert.equal(corner.top, 512);
  });
});
