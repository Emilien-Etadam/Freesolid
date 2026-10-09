// Chanfrein : le type décide des champs, la réédition renvoie les cotes utiles.

import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  chamferRows, chamferCreationParams, chamferEditValues, chamferProblem,
} from "../../app/features.js";

describe("création du chanfrein", () => {
  it("distance égale n'envoie que la distance", () => {
    assert.deepEqual(
      chamferCreationParams({ kind: "egale", size: "2", size2: 9, angle: 10, flip: true }),
      { size: 2, chamfer_type: "egale" });
  });

  it("deux distances exige la seconde et transmet l'inversion", () => {
    assert.equal(chamferCreationParams({ kind: "deux", size: 2, size2: 0 }), null);
    assert.deepEqual(
      chamferCreationParams({ kind: "deux", size: 2, size2: "5", flip: true }),
      { size: 2, size2: 5, chamfer_type: "deux", flip: true });
  });

  it("distance et angle refuse 0 et 90", () => {
    assert.equal(chamferCreationParams({ kind: "angle", size: 4, angle: 90 }), null);
    assert.equal(chamferCreationParams({ kind: "angle", size: 4, angle: 0 }), null);
    assert.deepEqual(
      chamferCreationParams({ kind: "angle", size: 4, angle: 30, flip: false }),
      { size: 4, angle: 30, chamfer_type: "angle", flip: false });
    assert.equal(chamferProblem({ kind: "angle", size: 4, angle: 90 }),
      "Angle de chanfrein invalide");
  });
});

describe("champs selon le type", () => {
  const rows = chamferRows({ kind: "deux", size: 2, size2: 5, angle: 45, flip: true });

  it("masque la seconde distance et l'angle hors de leur type", () => {
    const size2 = rows.find((row) => row.key === "size2");
    const angle = rows.find((row) => row.key === "angle");
    const flip = rows.find((row) => row.key === "flip");
    assert.equal(size2.showIf({ kind: "deux" }), true);
    assert.equal(size2.showIf({ kind: "egale" }), false);
    assert.equal(size2.showIf({ kind: "angle" }), false);
    assert.equal(angle.showIf({ kind: "angle" }), true);
    assert.equal(angle.showIf({ kind: "deux" }), false);
    assert.equal(flip.showIf({ kind: "egale" }), false);
    assert.equal(flip.showIf({ kind: "angle" }), true);
  });

  it("garde une expression comme texte", () => {
    const edited = chamferRows({ kind: "egale", size: "2*Largeur" });
    const size = edited.find((row) => row.key === "size");
    assert.equal(size.type, "text");
    assert.equal(size.value, "2*Largeur");
  });
});

describe("réédition", () => {
  const chamfer = { type: "deux", size: 2, size2: 5, angle: 45, flip: false };
  const params = [
    { prop: "Size", value: 2 },
    { prop: "Size2", value: 5 },
  ];

  it("n'envoie rien si le formulaire est inchangé", () => {
    assert.deepEqual(chamferEditValues(
      { kind: "deux", size: 2, size2: 5, angle: 45, flip: false },
      chamfer, params), {});
  });

  it("passe au type distance et angle avec l'inversion", () => {
    const values = chamferEditValues(
      { kind: "angle", size: 4, size2: 5, angle: 30, flip: true },
      chamfer, params);
    assert.equal(values.ChamferType, "angle");
    assert.equal(values.Size, 4);
    assert.equal(values.Angle, 30);
    assert.equal(values.FlipDirection, true);
    assert.equal(values.Size2, undefined);
  });

  it("conserve une expression de distance", () => {
    const withExpr = [{ prop: "Size", value: 4, expr: "2*Largeur" }];
    const current = { type: "egale", size: 4, size2: 1, angle: 45, flip: false };
    assert.deepEqual(chamferEditValues(
      { kind: "egale", size: "2*Largeur", flip: false },
      current, withExpr), {});
    const changed = chamferEditValues(
      { kind: "egale", size: "3*Largeur", flip: false },
      current, withExpr);
    assert.equal(changed.Size, "3*Largeur");
    assert.equal(changed.ChamferType, "egale");
  });
});
