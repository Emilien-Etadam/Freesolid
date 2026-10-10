import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { fmtMm, num, plainNumber, simpleDecimal } from "../../app/num.js";

describe("nombres", () => {
  it("num accepte la virgule et le début d'une expression", () => {
    assert.equal(num("3,5"), 3.5);
    assert.equal(num("2*Largeur"), 2);
    assert.equal(num(""), null);
  });

  it("plainNumber refuse une expression et accepte l'exposant", () => {
    assert.equal(plainNumber("2*Largeur"), null);
    assert.equal(plainNumber("1e2"), 100);
    assert.equal(plainNumber("3,5"), 3.5);
    assert.equal(plainNumber(4), 4);
  });

  it("simpleDecimal reste un décimal écrit, pas une expression", () => {
    assert.equal(simpleDecimal("3,5"), 3.5);
    assert.equal(simpleDecimal("-2.5"), -2.5);
    assert.equal(simpleDecimal("2*Largeur"), null);
    assert.equal(simpleDecimal("1e2"), null);
    assert.equal(simpleDecimal("+5"), null);
  });

  it("fmtMm arrondit à deux décimales et peut avaler un résidu", () => {
    assert.equal(fmtMm(12.345), "12.35");
    assert.equal(fmtMm(-0.001), "-0.00");
    assert.equal(fmtMm(-0.001, { snap: true }), "0.00");
    assert.equal(fmtMm(12.345, { snap: true }), "12.35");
  });
});