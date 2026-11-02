import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  barSlots,
  barStepTarget,
  chronologicalHistory,
  countTreeErrors,
  sameBarTarget,
  splitHistoryAroundBar,
  undoStepLabel,
} from "../../app/history.js";

function feat(name, order, typeKey = "pad") {
  return { name, label: name, type_key: typeKey, order };
}

function sketch(name, order, rolled_back = false) {
  return {
    name, label: name, type_key: "sketch", order, rolled_back,
  };
}

function surface(name, order, rolled_back = false) {
  return {
    name, label: name, type_key: "surface_extrude", order, rolled_back,
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
  it("plusieurs corps — chaque fonction suit le drapeau du moteur", () => {
    // Corps actif (tip) et autre corps entrelacés : Pad001, né après la
    // barre, passe dessous même si son rang précède Pocket.
    const features = [
      { ...feat("Pad", 1), rolled_back: false },
      { ...feat("Pocket", 3, "pocket"), rolled_back: false },
    ];
    const others = [
      { ...feat("Pad001", 2), body: "Body001", rolled_back: true },
      { ...feat("Pad002", 0), body: "Body001", rolled_back: false },
    ];
    const split = splitHistoryAroundBar([...features, ...others], [], "Pocket");
    assert.deepEqual(split.before.map((row) => row.item.name),
      ["Pad002", "Pad", "Pocket"]);
    assert.deepEqual(split.after.map((row) => row.item.name), ["Pad001"]);
  });

  it("solides seuls — barre après le tip", () => {
    const features = [feat("Pad", 1), feat("Pocket", 2, "pocket")];
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
    const features = [feat("Pad", 1), feat("Fillet", 5, "fillet")];
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
      feat("Sketch", 1, "sketch"),
      feat("DatumPlane", 2, "datum_plane"),
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
  it("ne prend pas les propriétés héritées d'Object.prototype pour des libellés", () => {
    assert.equal(undoStepLabel("constructor"), "Modification");
    assert.equal(undoStepLabel("toString"), "Modification");
    assert.equal(undoStepLabel("__proto__"), "Modification");
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

// Bossage (Pad) sur son esquisse, enlèvement (Pocket) sur la sienne : les
// esquisses précèdent leur fonction dans l'ordre du document.
function padPocket({ unabsorbed = false, folder } = {}) {
  const pad = { ...feat("Pad", 1), children: [sketch("Sketch", 0)] };
  const pocket = { ...feat("Pocket", 3, "pocket"),
    children: [{ ...sketch("Sketch001", 2), ...(unabsorbed ? { unabsorbed } : {}) }] };
  if (folder) pocket.folder = folder;
  return [pad, pocket];
}

const names = (rows) => rows.map((row) => row.item.name);
const targets = ({ slots }) => slots.map((slot) =>
  (slot.target.op === "tip_to_end" ? "fin" : slot.target.feature ?? "haut"));

describe("esquisse sortie par la barre (unabsorbed)", () => {
  it("passe au-dessus de la barre, sa fonction dessous sans elle", () => {
    const split = splitHistoryAroundBar(padPocket({ unabsorbed: true }), [], "Pad");
    assert.deepEqual(names(split.before), ["Pad", "Sketch001"]);
    assert.equal(split.before[1].parent, "Pocket");
    assert.deepEqual(names(split.after), ["Pocket"]);
    assert.deepEqual(split.after[0].item.children, []);
  });

  it("ne touche pas l'arbre reçu", () => {
    const features = padPocket({ unabsorbed: true });
    splitHistoryAroundBar(features, [], "Pad");
    assert.equal(features[1].children.length, 1);
  });

  it("barre en tête : l'esquisse sortie suffit à la poser au milieu", () => {
    const [, pocket] = padPocket({ unabsorbed: true });
    const split = splitHistoryAroundBar([pocket], [], null);
    assert.equal(split.bar, "middle");
    assert.deepEqual(names(split.before), ["Sketch001"]);
  });
});

describe("arbre à plat (flat)", () => {
  it("chaque esquisse enfant est une ligne à son rang, du côté de sa fonction", () => {
    const split = splitHistoryAroundBar(padPocket(), [], "Pad", { flat: true });
    assert.deepEqual(names(split.before), ["Sketch", "Pad"]);
    assert.deepEqual(names(split.after), ["Sketch001", "Pocket"]);
    assert.deepEqual(split.before[1].item.children, []);
  });

  it("une esquisse sortie reste au-dessus de la barre", () => {
    const split = splitHistoryAroundBar(
      padPocket({ unabsorbed: true }), [], "Pad", { flat: true });
    assert.deepEqual(names(split.before), ["Sketch", "Pad", "Sketch001"]);
    assert.deepEqual(names(split.after), ["Pocket"]);
  });

  it("une esquisse partagée ne paraît qu'une fois", () => {
    const shared = { ...sketch("Shared", 0) };
    const features = [
      { ...feat("Pad", 1), children: [shared] },
      { ...feat("Pocket", 2, "pocket"),
        children: [{ ...shared, shared: ["Bossage"] }] },
    ];
    const split = splitHistoryAroundBar(features, [], "Pocket", { flat: true });
    assert.deepEqual(names(split.before), ["Shared", "Pad", "Pocket"]);
  });

  it("les surfaces gardent leurs esquisses", () => {
    const surf = { ...surface("Surf", 5), children: [sketch("SkSurf", 4)] };
    const split = splitHistoryAroundBar([feat("Pad", 1)], [surf], "Pad", { flat: true });
    assert.deepEqual(names(split.before), ["Pad", "Surf"]);
    assert.equal(split.before[1].item.children.length, 1);
  });
});

describe("barSlots", () => {
  it("haut, une position par ligne, l'état final en bas", () => {
    const split = splitHistoryAroundBar(padPocket(), [], "Pad");
    const slots = barSlots(split);
    assert.deepEqual(targets(slots), ["haut", "Pad", "fin"]);
    assert.deepEqual(slots.slots.map((slot) => slot.line), [null, "Pad", "Pocket"]);
    assert.equal(slots.current, 1);
  });

  it("fonction dépliée : la barre peut passer entre elle et son esquisse", () => {
    const split = splitHistoryAroundBar(padPocket(), [], "Pocket");
    const slots = barSlots(split, { expanded: (name) => name === "Pocket" });
    assert.deepEqual(targets(slots), ["haut", "Pad", "Sketch001", "fin"]);
    assert.deepEqual(slots.slots.map((slot) => slot.line),
      [null, "Pad", "Pocket", "Pocket/Sketch001"]);
    assert.equal(slots.current, 3);
  });

  it("une esquisse partagée ⇄ ne crée pas de position entre elle et sa fonction", () => {
    const features = padPocket();
    features[1].children[0].shared = ["Bossage"];
    const split = splitHistoryAroundBar(features, [], "Pocket");
    const slots = barSlots(split, { expanded: () => true });
    assert.deepEqual(targets(slots), ["haut", "Sketch", "Pad", "fin"]);
  });

  it("esquisse sortie : la barre est juste après elle", () => {
    const split = splitHistoryAroundBar(padPocket({ unabsorbed: true }), [], "Pad");
    const slots = barSlots(split);
    assert.deepEqual(targets(slots), ["haut", "Pad", "Sketch001", "fin"]);
    assert.equal(slots.current, 2);
  });

  it("dossier replié : une seule position, après sa dernière ligne", () => {
    const features = [
      feat("Pad", 1),
      { ...feat("Pocket", 2, "pocket"), folder: "Trous" },
      { ...feat("Hole", 3, "hole"), folder: "Trous" },
      feat("Fillet", 4, "fillet"),
    ];
    const split = splitHistoryAroundBar(features, [], "Fillet");
    const closed = barSlots(split, { folderOpen: () => false });
    assert.deepEqual(targets(closed), ["haut", "Pad", "Hole", "fin"]);
    assert.equal(closed.slots[2].line, "folder:Trous");
    assert.equal(closed.current, 3);
    const open = barSlots(split, { folderOpen: () => true });
    assert.deepEqual(targets(open), ["haut", "Pad", "Pocket", "Hole", "fin"]);
    // Arbre à plat : pas de dossier, même replié.
    const flat = barSlots(splitHistoryAroundBar(features, [], "Fillet", { flat: true }),
      { folderOpen: () => false, flat: true });
    assert.deepEqual(targets(flat), ["haut", "Pad", "Pocket", "Hole", "fin"]);
  });

  it("barre en tête, et historique vide", () => {
    const split = splitHistoryAroundBar(padPocket(), [], null);
    const slots = barSlots(split);
    assert.equal(slots.current, 0);
    assert.deepEqual(targets(slots), ["haut", "Pad", "fin"]);
    assert.deepEqual(barSlots(splitHistoryAroundBar([], [], null)),
      { slots: [], current: -1 });
  });
});

describe("sameBarTarget", () => {
  it("compare deux positions par leur appel au moteur", () => {
    assert.ok(sameBarTarget({ op: "set_tip", feature: "Pad" },
      { op: "set_tip", feature: "Pad" }));
    assert.ok(sameBarTarget({ op: "set_tip" }, { op: "set_tip", feature: undefined }));
    assert.ok(!sameBarTarget({ op: "set_tip", feature: "Pad" }, { op: "tip_to_end" }));
    assert.ok(!sameBarTarget(null, { op: "tip_to_end" }));
  });
});

describe("barStepTarget", () => {
  const slots = barSlots(splitHistoryAroundBar(padPocket(), [], "Pad"));

  it("avance et recule d'une position, rien au bout", () => {
    assert.deepEqual(barStepTarget(slots, 1), { op: "tip_to_end" });
    assert.deepEqual(barStepTarget(slots, -1), { op: "set_tip" });
    assert.equal(barStepTarget({ ...slots, current: 0 }, -1), null);
    assert.equal(barStepTarget({ ...slots, current: 2 }, 1), null);
    assert.equal(barStepTarget({ slots: [], current: -1 }, 1), null);
  });
});
