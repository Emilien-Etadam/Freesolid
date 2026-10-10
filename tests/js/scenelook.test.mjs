import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { gridFade, gridSpacing } from "../../app/scenelook.js";

describe("grille de la scène", () => {
  it("pas en 1, 2 ou 5 × 10^n, environ un dixième du rayon", () => {
    assert.equal(gridSpacing(90), 10);
    assert.equal(gridSpacing(45), 5);
    assert.equal(gridSpacing(15), 2);
    assert.equal(gridSpacing(400), 50);
    assert.equal(gridSpacing(2500), 500);
  });

  it("jamais sous 1 mm, même pour une pièce minuscule ou vide", () => {
    assert.equal(gridSpacing(0.2), 1);
    assert.equal(gridSpacing(0), 1);
  });

  it("le fondu part au-delà de la pièce et finit plus loin", () => {
    const { start, end } = gridFade(90);
    assert.ok(start > 90 && end > start);
    // Petite pièce : la grille garde une étendue lisible.
    assert.ok(gridFade(1).end >= 80);
  });
});
