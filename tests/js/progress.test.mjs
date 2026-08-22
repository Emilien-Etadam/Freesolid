import { beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  COMBINE_CONFIRM_MIN_SECONDS,
  COMBINE_CONFIRM_MIN_STONES,
  COMBINE_MEMORY_WARN_STONES,
  combineConfirmMessage,
  currentCombineSample,
  estimateCombineSeconds,
  formatProgressStatus,
  noteProgressForCalibration,
  rememberCombineFinished,
  resetCombineSample,
} from "../../app/progress.js";

beforeEach(() => {
  resetCombineSample();
});

const POINT_SECONDS = /environ \d+ secondes?/;

describe("estimateCombineSeconds", () => {
  it("sans mesure locale, ne promet aucun point", () => {
    assert.equal(estimateCombineSeconds(200), null);
    assert.equal(estimateCombineSeconds(10), null);
    assert.equal(estimateCombineSeconds(0), null);
    assert.equal(estimateCombineSeconds(-4), null);
  });

  it("calibre sur l'échantillon, sans extrapoler trop loin", () => {
    const sample = { count: 25, totalSeconds: 0.74, compoundSeconds: 0.09 };
    assert.equal(estimateCombineSeconds(25, sample), 1);
    assert.equal(estimateCombineSeconds(30, sample), 1);
    assert.equal(estimateCombineSeconds(50, sample), null);
    assert.equal(estimateCombineSeconds(200, sample), null);
  });

  it("déduit le booléen du débit de compound mesuré", () => {
    const sample = { count: 20, totalSeconds: 12, compoundSeconds: 2 };
    // compound 0,1 s/pierre × 20 × (1 + 5) = 12 → pour 24 : 14,4 → 14
    assert.equal(estimateCombineSeconds(24, sample), 14);
  });
});

describe("combineConfirmMessage — aucune mesure locale", () => {
  const tree = {
    gems: [
      { name: "Semis", count: 200 },
      { name: "Moyen", count: 40 },
      { name: "Petit", count: 3 },
    ],
  };

  it("annonce une fourchette, jamais un point", () => {
    const message = combineConfirmMessage(tree, "Moyen", null);
    assert.match(message, /40 pierres/);
    assert.match(message, /plusieurs dizaines de secondes/);
    assert.match(message, /quelques minutes/);
    assert.equal(POINT_SECONDS.test(message), false);
    assert.equal(message.includes("%"), false);
  });

  it("200 pierres : le risque mémoire, pas une durée", () => {
    const message = combineConfirmMessage(tree, "Semis", null);
    assert.match(message, /200 pierres/);
    assert.match(message, /plusieurs Go de mémoire/);
    assert.match(message, /Enregistrez/);
    assert.match(message, /barre de reprise/);
    assert.match(message, /lots plus petits/);
    assert.equal(POINT_SECONDS.test(message), false);
    assert.ok(COMBINE_MEMORY_WARN_STONES <= 200);
  });

  it("se tait sous le seuil d'effectif, sans inventer de secondes", () => {
    assert.ok(3 < COMBINE_CONFIRM_MIN_STONES);
    assert.equal(combineConfirmMessage(tree, "Petit", null), null);
    assert.equal(estimateCombineSeconds(3, null), null);
  });

  it("ignore un corps outil qui n'est pas un semis", () => {
    assert.equal(combineConfirmMessage(tree, "Body001", null), null);
    assert.equal(combineConfirmMessage({}, "Semis", null), null);
  });
});

describe("combineConfirmMessage — mesure de session", () => {
  const tree = {
    gems: [{ name: "Semis", count: 25 }, { name: "Gros", count: 200 }],
  };

  it("se tait si la mesure locale reste sous quelques secondes", () => {
    const sample = { count: 25, totalSeconds: 0.74, compoundSeconds: 0.09 };
    assert.ok(estimateCombineSeconds(25, sample) < COMBINE_CONFIRM_MIN_SECONDS);
    assert.equal(combineConfirmMessage(tree, "Semis", sample), null);
  });

  it("cite la mesure locale, pas une constante, pour un effectif voisin", () => {
    const sample = { count: 32, totalSeconds: 18, compoundSeconds: 2 };
    const nearby = {
      gems: [{ name: "Semis", count: 32 }],
    };
    const message = combineConfirmMessage(nearby, "Semis", sample);
    assert.equal(
      message,
      "32 pierres — environ 18 secondes, d'après la dernière "
        + "combinaison sur cette machine. Continuer ?",
    );
  });

  it("ne convertit pas 25 pierres rapides en promesse pour 200", () => {
    const sample = { count: 25, totalSeconds: 0.74, compoundSeconds: 0.09 };
    const message = combineConfirmMessage(tree, "Gros", sample);
    assert.match(message, /plusieurs Go de mémoire/);
    assert.equal(POINT_SECONDS.test(message), false);
  });

  it("retient le débit du compound pendant l'op, puis s'en sert", () => {
    noteProgressForCalibration({
      op: "add_boolean",
      phase: "Construction du compound",
      fait: 32,
      total: 32,
      depuis: 1000,
    }, 1002);
    rememberCombineFinished(32, 18);
    const held = currentCombineSample();
    assert.equal(held.count, 32);
    assert.equal(held.totalSeconds, 18);
    assert.equal(held.compoundSeconds, 2);
    const nearby = { gems: [{ name: "Semis", count: 32 }] };
    const message = combineConfirmMessage(nearby, "Semis");
    assert.match(message, /environ 18 secondes/);
    assert.match(message, /cette machine/);
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
