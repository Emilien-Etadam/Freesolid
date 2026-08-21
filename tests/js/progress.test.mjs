import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  COMBINE_CONFIRM_MIN_SECONDS,
  COMBINE_SECONDS_PER_STONE,
  combineConfirmMessage,
  estimateCombineSeconds,
  formatProgressStatus,
} from "../../app/progress.js";

describe("estimateCombineSeconds", () => {
  it("reproduit la mesure P035 : 200 pierres → 43 s", () => {
    assert.equal(estimateCombineSeconds(200), 43);
    assert.equal(COMBINE_SECONDS_PER_STONE, 43 / 200);
  });

  it("ne promet rien pour un compte vide", () => {
    assert.equal(estimateCombineSeconds(0), 0);
    assert.equal(estimateCombineSeconds(-4), 0);
  });
});

describe("combineConfirmMessage", () => {
  const tree = {
    gems: [{ name: "Semis", count: 200 }, { name: "Petit", count: 3 }],
  };

  it("annonce le nombre et l'estimation, sans pourcentage", () => {
    const message = combineConfirmMessage(tree, "Semis");
    assert.equal(
      message, "200 pierres — environ 43 secondes. Continuer ?");
    assert.equal(message.includes("%"), false);
  });

  it("se tait sous le seuil de quelques secondes", () => {
    assert.ok(estimateCombineSeconds(3) < COMBINE_CONFIRM_MIN_SECONDS);
    assert.equal(combineConfirmMessage(tree, "Petit"), null);
  });

  it("ignore un corps outil qui n'est pas un semis", () => {
    assert.equal(combineConfirmMessage(tree, "Body001"), null);
    assert.equal(combineConfirmMessage({}, "Semis"), null);
  });
});

describe("formatProgressStatus", () => {
  it("compte les pierres pendant le compound", () => {
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
});
