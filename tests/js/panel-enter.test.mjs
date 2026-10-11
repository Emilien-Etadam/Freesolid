import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { enterAction } from "../../app/panel.js";

describe("Entrée dans le panneau", () => {
  it("une valeur tapée est d'abord appliquée, sans fermer", () => {
    assert.equal(enterAction({ tag: "INPUT", edited: true }), "commit");
  });

  it("un second appui valide la fonction", () => {
    assert.equal(enterAction({ tag: "INPUT", edited: false }), "apply");
    assert.equal(enterAction({ tag: "BUTTON", edited: false }), "apply");
  });

  it("liste déroulante et panneau sans validation : rien", () => {
    assert.equal(enterAction({ tag: "SELECT", edited: true }), "none");
    assert.equal(enterAction({ tag: "INPUT", edited: false, noApply: true }),
      "none");
    assert.equal(enterAction({ tag: "INPUT", edited: true, noApply: true }),
      "commit");
  });
});
