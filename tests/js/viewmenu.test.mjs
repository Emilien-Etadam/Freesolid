import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  contextToolbarKeys, placeViewMenu, viewMenuItems, viewMenuLabel,
} from "../../app/viewmenu.js";

const keys = (items) => items.filter((i) => i.key).map((i) => i.key);

describe("viewMenuItems", () => {
  it("dans le vide : la vue et l'édition seulement", () => {
    const k = keys(viewMenuItems({}));
    assert.deepEqual(k, ["zoom-fit", "orient", "origin", "undo", "redo", "rebuild"]);
  });

  it("sur une face : esquisse, normal à, habillages, puis la fonction", () => {
    const items = viewMenuItems({
      hit: { kind: "face", feature: { name: "Pad", label: "Bossage", sketch: "Sketch" } },
    });
    const k = keys(items);
    assert.ok(k.indexOf("sketch-on-face") < k.indexOf("edit-feature"));
    for (const key of ["normal-to", "fillet", "chamfer", "edit-sketch", "delete-feature"]) {
      assert.ok(k.includes(key), key);
    }
    assert.ok(items.some((i) => i.header === "Bossage"));
    assert.ok(items.find((i) => i.key === "delete-feature").danger);
  });

  it("face d'une fonction sans esquisse : pas de « Modifier l'esquisse »", () => {
    const k = keys(viewMenuItems({
      hit: { kind: "face", feature: { name: "Fillet", label: "Congé" } } }));
    assert.ok(!k.includes("edit-sketch"));
  });

  it("sur une arête : congé, chanfrein, mesure", () => {
    const k = keys(viewMenuItems({ hit: { kind: "edge" } }));
    assert.deepEqual(k.slice(0, 3), ["fillet", "chamfer", "measure"]);
  });

  it("sur une esquisse : modifier et les fonctions qui la consomment", () => {
    const k = keys(viewMenuItems({ hit: { kind: "sketch", label: "Esquisse2" } }));
    assert.deepEqual(k.slice(0, 4), ["edit-sketch", "pad", "pocket", "revolve"]);
  });

  it("le libellé de l'origine suit son état", () => {
    const shown = viewMenuItems({ originShown: true }).find((i) => i.key === "origin");
    assert.equal(shown.label, "Masquer l'origine");
  });

  it("barre contextuelle : actions courantes selon la sélection", () => {
    assert.deepEqual(contextToolbarKeys({ kind: "edge" }),
      ["fillet", "chamfer", "measure"]);
    assert.ok(contextToolbarKeys({ kind: "face", feature: { name: "Pad" } })
      .includes("edit-feature"));
    assert.ok(!contextToolbarKeys({ kind: "face" }).includes("edit-feature"));
    assert.deepEqual(contextToolbarKeys(null), []);
    // Chaque clé de la barre existe dans le menu (même action, même libellé).
    for (const hit of [{ kind: "edge" }, { kind: "sketch" },
                       { kind: "face", feature: { name: "Pad", label: "P" } }]) {
      for (const key of contextToolbarKeys(hit)) {
        assert.notEqual(viewMenuLabel(key, { hit }), key, key);
      }
    }
  });

  it("en esquisse : outils de tracé et sortie", () => {
    const k = keys(viewMenuItems({ mode: "sketch" }));
    assert.ok(k.includes("sk-line") && k.includes("sk-finish") && k.includes("sk-cancel"));
    assert.ok(!k.includes("fillet"));
  });
});

const VIEW = {
  viewportWidth: 1366,
  viewportHeight: 768,
  topLimit: 120,
};

function place(partial) {
  return placeViewMenu({ width: 220, height: 280, ...VIEW, ...partial });
}

describe("placeViewMenu", () => {
  it("s'ouvre sous le pointeur quand il tient", () => {
    const at = place({ x: 400, y: 200, height: 180 });
    assert.equal(at.left, 400);
    assert.equal(at.top, 200);
    assert.ok(at.maxHeight >= 180);
    assert.ok(at.top >= VIEW.topLimit);
  });

  it("s'ouvre au-dessus quand la place manque en dessous", () => {
    const at = place({ x: 400, y: 700, height: 180 });
    assert.equal(at.top, 520);
    assert.ok(at.top >= VIEW.topLimit);
    assert.ok(at.top + 180 <= 700);
  });

  it("défile sans recouvrir le ruban s'il ne tient nulle part", () => {
    const low = place({ x: 80, y: 640, height: 900 });
    assert.equal(low.top, 124);
    assert.equal(low.maxHeight, 516);
    assert.ok(low.top >= VIEW.topLimit);
    assert.ok(low.maxHeight < 900);

    const high = place({ x: 80, y: 400, height: 900 });
    assert.equal(high.top, 400);
    assert.equal(high.maxHeight, 364);
    assert.ok(high.top >= VIEW.topLimit);
    assert.ok(high.top + high.maxHeight <= VIEW.viewportHeight);
  });

  it("reste dans la fenêtre près du bord droit", () => {
    const at = place({ x: 1300, y: 300, height: 100 });
    assert.equal(at.left, 1366 - 220 - 4);
    assert.ok(at.left >= 0);
  });
});
