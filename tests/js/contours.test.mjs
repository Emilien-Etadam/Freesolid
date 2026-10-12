// Contours choisis d'une esquisse partagée : rangées et paramètres.
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { checkedContours, contourLabel, contourRows } from "../../app/features.js";

describe("contours d'une esquisse", () => {
  it("une case par contour, cochée selon ceux déjà pris", () => {
    const rows = contourRows([[40, 30, 0], [10, 10, 0]], [1]);
    assert.deepEqual(rows.map((r) => [r.key, r.value]),
      [["contour0", false], ["contour1", true]]);
    assert.equal(contourLabel(0, [40, 30, 0]), "Contour 1 — 40 × 30 mm");
  });

  it("tous cochés : le profil entier ; aucun : liste vide", () => {
    assert.equal(checkedContours({ contour0: true, contour1: true }, 2), null);
    assert.deepEqual(checkedContours({ contour0: false, contour1: true }, 2), [1]);
    assert.deepEqual(checkedContours({ contour0: false, contour1: false }, 2), []);
  });
});
