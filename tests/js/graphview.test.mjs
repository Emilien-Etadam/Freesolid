import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { graphLabelText } from "../../app/graphview.js";

describe("graphLabelText", () => {
  it("laisse un libellé court intact", () => {
    assert.equal(graphLabelText("Bossage"), "Bossage");
    assert.equal(graphLabelText(""), "");
  });

  it("tronque au-delà de 16 caractères", () => {
    assert.equal(graphLabelText("1234567890123456"), "1234567890123456");
    assert.equal(graphLabelText("12345678901234567"), "123456789012345…");
  });
});
