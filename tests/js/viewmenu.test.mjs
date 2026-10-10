import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { existsSync } from "node:fs";

import {
  contextToolbarKeys, menuIcon, placeViewMenu, viewMenuItems, viewMenuLabel,
} from "../../app/viewmenu.js";

const keys = (items) => items.filter((i) => i.key).map((i) => i.key);
const bar = (items) => items.find((i) => i.bar)?.bar ?? [];

describe("viewMenuItems", () => {
  it("dans le vide : la vue seulement (annuler, rétablir : accès rapide)", () => {
    const k = keys(viewMenuItems({}));
    assert.deepEqual(k, ["zoom-fit", "orient", "origin"]);
  });

  it("sur une face : rangée d'icônes, puis la fonction, puis la vue", () => {
    const items = viewMenuItems({
      hit: { kind: "face", feature: { name: "Pad", label: "Extrusion", sketch: "Sketch" } },
    });
    assert.ok(items[0].bar, "la rangée d'icônes vient en tête");
    assert.deepEqual(bar(items),
      ["sketch-on-face", "normal-to", "fillet", "chamfer", "shell", "measure"]);
    assert.deepEqual(keys(items), ["edit-feature", "edit-sketch", "rollback",
      "delete-feature", "zoom-fit", "orient", "origin"]);
    assert.ok(items.some((i) => i.header === "Extrusion"));
    assert.ok(items.find((i) => i.key === "delete-feature").danger);
    // Le menu d'une face tient en une dizaine de lignes (19 avant).
    assert.ok(items.length <= 11, String(items.length));
  });

  it("face d'une fonction sans esquisse : pas de « Modifier l'esquisse »", () => {
    const k = keys(viewMenuItems({
      hit: { kind: "face", feature: { name: "Fillet", label: "Congé" } } }));
    assert.ok(!k.includes("edit-sketch"));
  });

  it("sur une arête : congé, chanfrein, mesure", () => {
    assert.deepEqual(bar(viewMenuItems({ hit: { kind: "edge" } })),
      ["fillet", "chamfer", "measure"]);
  });

  it("sur une esquisse : modifier et les fonctions qui la consomment", () => {
    const items = viewMenuItems({ hit: { kind: "sketch", label: "Esquisse2" } });
    assert.equal(items[0].header, "Esquisse2");
    assert.deepEqual(bar(items), ["edit-sketch", "pad", "pocket", "revolve"]);
  });

  it("chaque action a une icône présente dans app/icons", () => {
    const hits = [{ kind: "edge" }, { kind: "sketch" }, { kind: "surface" },
      { kind: "face", feature: { name: "Pad", label: "P", sketch: "S" } }];
    const all = new Set();
    for (const ctx of [...hits.map((hit) => ({ hit })), { mode: "sketch" }]) {
      const items = viewMenuItems(ctx);
      for (const key of [...keys(items), ...bar(items)]) all.add(key);
    }
    for (const key of all) {
      const file = menuIcon(key);
      assert.ok(file, key);
      assert.ok(existsSync(new URL("../../app/icons/" + file, import.meta.url)), file);
    }
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
