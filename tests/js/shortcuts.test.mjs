import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  assignShortcut, comboOf, parseCombo, readShortcuts, tipParts,
  writeShortcuts,
} from "../../app/shortcuts.js";

describe("raccourcis personnels", () => {
  it("lit l'appui et le texte tapé dans la même forme", () => {
    assert.equal(comboOf({ key: "e", ctrlKey: true, shiftKey: true }),
      "Ctrl+Shift+E");
    assert.equal(comboOf({ key: "Control", ctrlKey: true }), null);
    assert.equal(parseCombo("ctrl+maj+e"), "Ctrl+Shift+E");
    assert.equal(parseCombo("Alt + F3"), "Alt+F3");
    assert.equal(parseCombo("maj+espace"), "Shift+Space");
    assert.equal(parseCombo("Ctrl+"), null);
    assert.equal(parseCombo("e+ctrl"), null);
  });

  it("refuse les touches réservées, déplace une combinaison déjà prise", () => {
    assert.ok(assignShortcut({}, "btn-pad", "Ctrl+Z").error);
    assert.ok(assignShortcut({}, "btn-pad", "F").error);
    assert.ok(assignShortcut({}, "btn-pad", "ctrl+arrowup").error);
    assert.ok(assignShortcut({}, "btn-pad", "n'importe quoi").error);
    let r = assignShortcut({}, "btn-pad", "ctrl+e");
    assert.deepEqual(r.map, { "btn-pad": "Ctrl+E" });
    r = assignShortcut(r.map, "btn-pocket", "Ctrl+E");
    assert.deepEqual(r.map, { "btn-pocket": "Ctrl+E" });
    assert.equal(r.replaced, "btn-pad");
  });

  it("garde les raccourcis valides seulement", () => {
    const data = new Map();
    const store = { getItem: (k) => data.get(k) ?? null,
                    setItem: (k, v) => data.set(k, v) };
    writeShortcuts(store, { "btn-pad": "Ctrl+E", "btn-x": "Ctrl+Z",
                            "btn-y": "pas une touche" });
    assert.deepEqual(readShortcuts(store), { "btn-pad": "Ctrl+E" });
    data.set("freesolid.shortcuts", "{oups");
    assert.deepEqual(readShortcuts(store), {});
  });

  it("découpe l'infobulle : nom, détail, touches", () => {
    assert.deepEqual(tipParts("Zoom au mieux (F)"),
      { name: "Zoom au mieux", detail: "", keys: "F" });
    assert.deepEqual(tipParts("Coque — les faces cliquées deviennent des ouvertures"),
      { name: "Coque", detail: "les faces cliquées deviennent des ouvertures",
        keys: null });
    assert.equal(tipParts("Extrusion", "Ctrl+E").keys, "Ctrl+E");
  });
});
