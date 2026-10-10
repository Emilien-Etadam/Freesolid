// Consigne de sélection : neutre, et non répétée si la ligne du panneau
// dit déjà quoi choisir. Une valeur invalide reste une erreur.

import { describe, it, afterEach } from "node:test";
import assert from "node:assert/strict";

import { FEATURES } from "../../app/features.js";
import { setLang } from "../../app/i18n.js";
import { panelNotice, selectionLineGuides } from "../../app/panel.js";

afterEach(() => setLang("fr"));

const feature = (button) => FEATURES.find((entry) => entry.button === button);

describe("panelNotice", () => {
  it("une consigne disparaît si la ligne de sélection la dit déjà", () => {
    const guide = { text: "Congé : cliquez d'abord dans la zone graphique", tone: "guide" };
    assert.equal(panelNotice(guide, { selectionGuides: true }), null);
  });

  it("une consigne sans ligne de sélection reste neutre", () => {
    const guide = { text: "Congé : cliquez d'abord dans la zone graphique", tone: "guide" };
    assert.deepEqual(panelNotice(guide), { text: guide.text, tone: "guide" });
  });

  it("une valeur invalide reste une erreur, même avec une ligne de sélection", () => {
    assert.deepEqual(
      panelNotice("Valeur invalide", { selectionGuides: true }),
      { text: "Valeur invalide", tone: "error" },
    );
  });

  it("ignore un avis vide", () => {
    assert.equal(panelNotice(null), null);
    assert.equal(panelNotice(""), null);
    assert.equal(panelNotice({ text: "", tone: "guide" }), null);
  });
});

describe("fonction sans sélection", () => {
  it("le congé donne une consigne, le rayon invalide une erreur", () => {
    const fillet = feature("btn-fillet");
    const guide = fillet.invalid({ sel: null, radius: 3 }, {});
    assert.equal(guide.tone, "guide");
    assert.equal(guide.text, "Congé : cliquez d'abord dans la zone graphique");
    const groups = fillet.groups({ selection: () => null });
    assert.equal(selectionLineGuides(groups, { sel: null }), true);
    assert.equal(panelNotice(guide, { selectionGuides: true }), null);
    assert.equal(
      fillet.invalid({ sel: { kind: "edges", edges: [1] }, radius: 0 }, {}),
      "Valeur invalide",
    );
  });

  it("la consigne du congé est traduite en anglais", () => {
    setLang("en");
    const guide = feature("btn-fillet").invalid({ sel: null, radius: 3 }, {});
    assert.equal(guide.tone, "guide");
    assert.equal(guide.text, "Fillet: click in the graphics area first");
  });

  it("le chanfrein sans sélection ne parle pas d'une distance invalide", () => {
    const notice = feature("btn-chamfer").invalid(
      { sel: null, kind: "egale", size: 0 }, {});
    assert.equal(notice.tone, "guide");
    assert.equal(
      feature("btn-chamfer").invalid(
        { sel: { kind: "edges", edges: [2] }, kind: "egale", size: 0 }, {}),
      "Distance de chanfrein invalide",
    );
  });

  it("la coque sans face est une consigne déjà dite par sa ligne", () => {
    const shell = feature("btn-shell");
    const guide = shell.invalid({ faces: { items: [] }, thickness: 2 });
    assert.equal(guide.tone, "guide");
    const groups = shell.groups({ selection: () => null });
    assert.equal(selectionLineGuides(groups, { faces: groups[0].rows[0].value }), true);
    assert.equal(panelNotice(guide, { selectionGuides: true }), null);
    assert.equal(
      shell.invalid({ faces: { items: [{ face: 1 }] }, thickness: 0 }),
      "Épaisseur invalide",
    );
  });
});
