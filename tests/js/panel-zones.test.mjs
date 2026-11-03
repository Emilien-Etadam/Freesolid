import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { bodyZone, zoneTakes } from "../../app/panel.js";

describe("zones de sélection", () => {
  const bodies = { type: "selection", key: "bodies", accepts: ["body"],
                   multiple: true, allows: (pick) => pick.name !== "Body" };

  it("une zone de corps ne prend que des corps", () => {
    assert.equal(bodyZone(bodies), true);
    assert.equal(bodyZone({ type: "selection", accepts: ["body", "face"] }), false);
    // Sans `accepts`, une zone attend une face.
    assert.equal(bodyZone({ type: "selection" }), false);
  });

  it("allows écarte un choix, showIf masque la zone", () => {
    assert.equal(zoneTakes(bodies, "body", { name: "Body001" }, {}), true);
    assert.equal(zoneTakes(bodies, "body", { name: "Body" }, {}), false);
    assert.equal(zoneTakes(bodies, "face", { face: 3 }, {}), false);
    // Sans choix (la zone accepte-t-elle ce genre ?), allows ne joue pas.
    assert.equal(zoneTakes(bodies, "body", null, {}), true);
    const hidden = { ...bodies, showIf: (v) => v.mode === "selected" };
    assert.equal(zoneTakes(hidden, "body", { name: "Body001" }, {}), false);
    assert.equal(zoneTakes(hidden, "body", { name: "Body001" },
                           { mode: "selected" }), true);
  });
});
