import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { formatProgressStatus } from "../../app/progress.js";
import { setLang } from "../../app/i18n.js";

describe("formatProgressStatus", () => {
  it("compte les éléments d'une boucle comptable", () => {
    assert.equal(
      formatProgressStatus({
        op: "add_boolean",
        phase: "Construction du compound",
        fait: 47,
        total: 200,
        depuis: 1000,
      }, 1012),
      "Construction du compound — 47 / 200 (12 s)",
    );
  });

  it("n'invente pas de pourcentage pour la soustraction", () => {
    const text = formatProgressStatus({
      op: "add_boolean",
      phase: "Soustraire",
      fait: 0,
      total: 0,
      depuis: 1000,
    }, 1028);
    assert.equal(text, "Soustraire (28 s)");
    assert.equal(text.includes("%"), false);
  });

  it("nomme la reconstruction et le maillage", () => {
    assert.equal(
      formatProgressStatus({
        op: "add_boolean", phase: "Reconstruction de l'arbre",
        fait: 0, total: 0, depuis: 10,
      }, 12),
      "Reconstruction de l'arbre (2 s)",
    );
    assert.equal(
      formatProgressStatus({
        op: "tessellate", phase: "Maillage",
        fait: 0, total: 0, depuis: 10,
      }, 11),
      "Maillage (1 s)",
    );
  });

  it("reste muet à l'arrêt", () => {
    assert.equal(formatProgressStatus({
      op: null, phase: "", fait: 0, total: 0, depuis: 0,
    }, 100), "");
    assert.equal(formatProgressStatus(null, 100), "");
  });

  it("traduit le repli « Combiner » ; la phase arrive traduite du moteur", () => {
    const progress = { op: "add_boolean", phase: "", fait: 3, total: 10, depuis: 0 };
    assert.equal(formatProgressStatus(progress, 0), "Combiner — 3 / 10");
    setLang("en");
    try {
      assert.equal(formatProgressStatus(progress, 0), "Combine — 3 / 10");
    } finally {
      setLang("fr");
    }
  });
});
