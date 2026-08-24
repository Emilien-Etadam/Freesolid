import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  GEM_DIAMETRE_DISABLED_TITLE,
  GEM_DIAMETRE_MINUS_TITLE,
  GEM_DIAMETRE_PLUS_TITLE,
  GEM_STEP_MM,
  formatMmFr,
  gemDiametreDeltaFromButton,
  gemDiametreDeltaFromKey,
  gemRibbonState,
} from "../../plugins/bijouterie/ui/gem-controls.js";

function key(partial) {
  return {
    ctrlKey: false, metaKey: false, altKey: false,
    key: "", code: "",
    ...partial,
  };
}

describe("gemDiametreDeltaFromKey / FromButton", () => {
  it("Ø − et Ø + appellent le même pas que ↓ et ↑", () => {
    assert.equal(
      gemDiametreDeltaFromButton("plus"),
      gemDiametreDeltaFromKey(key({ key: "ArrowUp", code: "ArrowUp" })),
    );
    assert.equal(
      gemDiametreDeltaFromButton("minus"),
      gemDiametreDeltaFromKey(key({ key: "ArrowDown", code: "ArrowDown" })),
    );
    assert.equal(gemDiametreDeltaFromButton("plus"), GEM_STEP_MM);
    assert.equal(gemDiametreDeltaFromButton("minus"), -GEM_STEP_MM);
  });

  it("le pavé numérique reste, la rangée du haut ne fait plus rien", () => {
    assert.equal(
      gemDiametreDeltaFromKey(key({ key: "+", code: "NumpadAdd" })),
      GEM_STEP_MM,
    );
    assert.equal(
      gemDiametreDeltaFromKey(key({ key: "-", code: "NumpadSubtract" })),
      -GEM_STEP_MM,
    );
    assert.equal(
      gemDiametreDeltaFromKey(key({ key: "+", code: "Equal" })),
      0,
    );
    assert.equal(
      gemDiametreDeltaFromKey(key({ key: "-", code: "Minus" })),
      0,
    );
    assert.equal(
      gemDiametreDeltaFromKey(key({ key: "+", code: "Minus" })),
      0,
    );
  });

  it("ignore les modificateurs et une touche inconnue", () => {
    assert.equal(
      gemDiametreDeltaFromKey(key({ key: "ArrowUp", ctrlKey: true })),
      0,
    );
    assert.equal(gemDiametreDeltaFromButton("wat"), 0);
    assert.equal(gemDiametreDeltaFromKey(null), 0);
  });
});

describe("gemRibbonState", () => {
  it("sans sélection, les deux boutons sont disabled et le libellé est Ø —", () => {
    const state = gemRibbonState(false, 1.5);
    assert.equal(state.disabled, true);
    assert.equal(state.label, "Ø —");
    assert.equal(state.minusTitle, GEM_DIAMETRE_DISABLED_TITLE);
    assert.equal(state.plusTitle, GEM_DIAMETRE_DISABLED_TITLE);
  });

  it("le libellé suit la sélection", () => {
    const on = gemRibbonState(true, 1.5);
    assert.equal(on.disabled, false);
    assert.equal(on.label, "Ø 1,50 mm");
    assert.equal(on.minusTitle, GEM_DIAMETRE_MINUS_TITLE);
    assert.equal(on.plusTitle, GEM_DIAMETRE_PLUS_TITLE);
    assert.match(on.minusTitle, /↓/);
    assert.match(on.plusTitle, /↑/);

    const other = gemRibbonState(true, 2);
    assert.equal(other.label, "Ø 2,00 mm");

    const empty = gemRibbonState(true, NaN);
    assert.equal(empty.disabled, false);
    assert.equal(empty.label, "Ø —");
  });
});

describe("formatMmFr", () => {
  it("écrit la virgule française, et un tiret si non fini", () => {
    assert.equal(formatMmFr(1.5), "1,50");
    assert.equal(formatMmFr(NaN), "—");
  });
});
