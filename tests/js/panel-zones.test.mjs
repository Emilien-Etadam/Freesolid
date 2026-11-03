import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { bodyPicking, objectZone, zonePick, zoneTakes } from "../../app/panel.js";

describe("zones de sélection", () => {
  const bodies = { type: "selection", key: "bodies", accepts: ["body"],
                   multiple: true, allows: (pick) => pick.name !== "Body" };

  it("une zone d'objets ne prend que des corps et des surfaces", () => {
    assert.equal(objectZone(bodies), true);
    assert.equal(objectZone({ type: "selection", accepts: ["body", "surface"] }),
                 true);
    assert.equal(objectZone({ type: "selection", accepts: ["body", "face"] }),
                 false);
    // Sans `accepts`, une zone attend une face.
    assert.equal(objectZone({ type: "selection" }), false);
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

  it("la vue vise des corps quand la zone active en prend", () => {
    const edge = { type: "selection", key: "edge", accepts: ["edges"] };
    const features = { type: "selection", key: "features",
                       accepts: ["feature"], multiple: true };
    assert.equal(bodyPicking([], null), false);
    assert.equal(bodyPicking([edge], null), false);
    // Sans zone active : seulement si rien d'autre n'attend la vue — une
    // zone de fonctions se remplit dans l'arbre.
    assert.equal(bodyPicking([bodies], null), true);
    assert.equal(bodyPicking([features, bodies], null), true);
    assert.equal(bodyPicking([edge, bodies], null), false);
    // La zone active tranche.
    assert.equal(bodyPicking([edge, bodies], "bodies"), true);
    assert.equal(bodyPicking([edge, bodies], "edge"), false);
    // Une zone active masquée ne compte plus.
    assert.equal(bodyPicking([bodies], "edge"), true);
  });

  it("un solide cliqué compte pour son corps, sauf zone de solides", () => {
    const solid = { kind: "body", name: "Body", label: "Extrusion[2]",
                    solid: 1, bodyLabel: "Extrusion" };
    assert.deepEqual(zonePick(bodies, "body", solid),
      { kind: "body", name: "Body", label: "Extrusion" });
    assert.deepEqual(zonePick({ ...bodies, solids: true }, "body", solid), solid);
    const whole = { kind: "body", name: "Body001", label: "Congé" };
    assert.equal(zonePick(bodies, "body", whole), whole);
    const surface = { kind: "surface", name: "Surface", label: "S" };
    assert.equal(zonePick(bodies, "surface", surface), surface);
  });
});
