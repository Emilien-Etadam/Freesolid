import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  chronologicalHistory,
  countTreeErrors,
  splitHistoryAroundBar,
  undoStepLabel,
} from "../../app/history.js";

function feat(name, order, type = "PartDesign::Pad") {
  return { name, label: name, type, order };
}

function sketch(name, order, rolled_back = false) {
  return {
    name, label: name, type: "Sketcher::SketchObject", order, rolled_back,
  };
}

function surface(name, order, rolled_back = false) {
  return {
    name, label: name, type: "Part::Extrusion", order, rolled_back,
  };
}

describe("chronologicalHistory", () => {
  it("fusionne fonctions et surfaces par order", () => {
    const rows = chronologicalHistory(
      [feat("Pad", 5), sketch("Sketch", 8)],
      [surface("Surf", 6)],
    );
    assert.deepEqual(rows.map((row) => row.item.name),
      ["Pad", "Surf", "Sketch"]);
    assert.equal(rows[1].surface, true);
  });
});

describe("splitHistoryAroundBar", () => {
  it("solides seuls — barre après le tip", () => {
    const features = [feat("Pad", 1), feat("Pocket", 2, "PartDesign::Pocket")];
    const split = splitHistoryAroundBar(features, [], "Pad");
    assert.equal(split.bar, "middle");
    assert.deepEqual(split.before.map((row) => row.item.name), ["Pad"]);
    assert.deepEqual(split.after.map((row) => row.item.name), ["Pocket"]);
  });

  it("surface reculée après le tip", () => {
    const features = [feat("Pad", 1)];
    const surfaces = [surface("Surf", 4, true)];
    const split = splitHistoryAroundBar(features, surfaces, "Pad");
    assert.deepEqual(split.before.map((row) => row.item.name), ["Pad"]);
    assert.deepEqual(split.after.map((row) => row.item.name), ["Surf"]);
    assert.equal(split.after[0].surface, true);
  });

  it("esquisse reculée après le tip", () => {
    const features = [feat("Pad", 1), sketch("Sketch", 3, true)];
    const split = splitHistoryAroundBar(features, [], "Pad");
    assert.deepEqual(split.before.map((row) => row.item.name), ["Pad"]);
    assert.deepEqual(split.after.map((row) => row.item.name), ["Sketch"]);
  });

  it("historique sans fonction volumique", () => {
    const features = [sketch("Sketch", 2, false)];
    const surfaces = [surface("Surf", 4, false)];
    const split = splitHistoryAroundBar(features, surfaces, null);
    assert.equal(split.bar, "middle");
    assert.deepEqual(split.before.map((row) => row.item.name),
      ["Sketch", "Surf"]);
    assert.deepEqual(split.after, []);
  });

  it("barre en tête — tip absent, fonctions présentes", () => {
    const features = [feat("Pad", 1), sketch("Sketch", 3, true)];
    const surfaces = [surface("Surf", 4, true)];
    const split = splitHistoryAroundBar(features, surfaces, null);
    assert.equal(split.bar, "start");
    assert.deepEqual(split.before, []);
    assert.deepEqual(split.after.map((row) => row.item.name),
      ["Pad", "Sketch", "Surf"]);
  });

  it("barre en bout — rien de reculé", () => {
    const features = [feat("Pad", 1), sketch("Sketch", 3, false)];
    const surfaces = [surface("Surf", 4, false)];
    const split = splitHistoryAroundBar(features, surfaces, "Pad");
    assert.equal(split.bar, "middle");
    assert.deepEqual(split.before.map((row) => row.item.name),
      ["Pad", "Sketch", "Surf"]);
    assert.deepEqual(split.after, []);
  });

  it("aucune ligne d'historique", () => {
    const split = splitHistoryAroundBar([], [], null);
    assert.equal(split.bar, "none");
    assert.deepEqual(split.before, []);
    assert.deepEqual(split.after, []);
  });

  it("objet créé barre reculée apparaît au-dessus", () => {
    const features = [feat("Pad", 1), feat("Fillet", 5, "PartDesign::Fillet")];
    const surfaces = [surface("Surf", 8, false)];
    const split = splitHistoryAroundBar(features, surfaces, "Pad");
    assert.deepEqual(split.before.map((row) => row.item.name),
      ["Pad", "Surf"]);
    assert.deepEqual(split.after.map((row) => row.item.name), ["Fillet"]);
  });
});

describe("plan de référence", () => {
  it("sans solide, il reste au-dessus de la barre, comme une esquisse", () => {
    const features = [
      feat("Sketch", 1, "Sketcher::SketchObject"),
      feat("DatumPlane", 2, "PartDesign::Plane"),
    ];
    const split = splitHistoryAroundBar(features, [], null);
    assert.deepEqual(split.before.map((row) => row.item.name),
      ["Sketch", "DatumPlane"]);
    assert.deepEqual(split.after, []);
  });
});

describe("sketchTreeLabel", () => {
  it("préfixe (-) une esquisse encore libre, (+) une esquisse en trop", async () => {
    const { sketchTreeLabel } = await import("../../app/history.js");
    assert.equal(sketchTreeLabel("Esquisse1", "under"), "(-) Esquisse1");
    assert.equal(sketchTreeLabel("Esquisse1", "over"), "(+) Esquisse1");
    assert.equal(sketchTreeLabel("Esquisse1", "full"), "Esquisse1");
    assert.equal(sketchTreeLabel("Esquisse1", undefined), "Esquisse1");
  });
});

describe("undoStepLabel", () => {
  it("nomme les pas connus, sinon par famille", () => {
    assert.equal(undoStepLabel("add_pad"), "Extrusion");
    assert.equal(undoStepLabel("set_comment"), "Commentaire");
    assert.equal(undoStepLabel("sketch_add_line"), "Modification d'esquisse");
    assert.equal(undoStepLabel("surface_sew"), "Surface");
    assert.equal(undoStepLabel("add_something_new"), "Fonction");
    assert.equal(undoStepLabel("Autre"), "Modification");
  });
});

describe("countTreeErrors", () => {
  it("compte chaque ligne en erreur une fois, enfants et surfaces compris", () => {
    const sketch = { name: "S", error: true };
    assert.equal(countTreeErrors({
      features: [{ name: "Pad", error: false, children: [sketch] },
                 { name: "Pocket", error: false, children: [sketch] },
                 { name: "Fillet", error: true }],
      surfaces: [{ name: "Surf", error: true }],
    }), 3);
    assert.equal(countTreeErrors(null), 0);
  });
});
