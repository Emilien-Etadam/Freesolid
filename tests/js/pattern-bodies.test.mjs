// Répéter des corps entiers, corps concernés : ce que les panneaux de
// répétition envoient au moteur.

import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { FEATURES } from "../../app/features.js";
import {
  patternBodiesParams,
  patternScopeParams,
} from "../../app/features/repetitions.js";
import { groupShown, selectionLineGuides } from "../../app/panel.js";

const CTX = {
  lastTree: {
    bodies: [
      { name: "Body", label: "Plaque", active: true },
      { name: "Body001", label: "Dessous", active: false },
      { name: "Body002", label: "Capot", active: false },
    ],
  },
};
const entry = (button) => FEATURES.find((e) => e.button === button);
const LINEAR = { target: "features", dirKind: "axis", axis: "X",
                 reversed: false, mode: "spacing", length: "20", count: "3" };

describe("répéter des corps", () => {
  it("les corps cochés partent vers add_body_pattern", () => {
    const built = entry("btn-linpattern").build({
      ...LINEAR, target: "bodies", "src:Body": true, "src:Body002": true,
      "src:Body001": false }, CTX);
    assert.equal(built.op, "add_body_pattern");
    assert.deepEqual(built.params, {
      kind: "linear", bodies: ["Body", "Body002"], reversed: false,
      axis: "X", length: 20, count: 3, spacing: true });
  });

  it("circulaire et symétrie donnent leur genre", () => {
    const polar = entry("btn-polpattern").build({
      target: "bodies", dirKind: "axis", axis: "Z", angle: "360",
      count: "4", "src:Body": true }, CTX);
    assert.equal(polar.params.kind, "polar");
    assert.equal(polar.params.angle, 360);
    const mirror = entry("btn-mirror").build(
      { target: "bodies", plane: "XY", "src:Body001": true }, CTX);
    assert.deepEqual(mirror, { op: "add_body_pattern",
      params: { kind: "mirror", bodies: ["Body001"], plane: "XY" } });
  });

  it("aucun corps coché : pas d'op, le panneau dit pourquoi", () => {
    const mirror = entry("btn-mirror");
    const v = { target: "bodies", plane: "YZ", "src:Body": false };
    assert.equal(mirror.build(v, CTX), null);
    assert.equal(mirror.invalid(v), "Cochez au moins un corps à répéter");
    assert.equal(patternBodiesParams({ "src:A": true, other: true }).length, 1);
  });

  it("le corps actif est coché d'emblée, les groupes suivent le choix", () => {
    const groups = entry("btn-linpattern").groups(CTX);
    const bodies = groups.find((g) => g.label === "Corps à répéter");
    assert.deepEqual(bodies.rows.map((r) => [r.key, r.value]),
      [["src:Body", true], ["src:Body001", false], ["src:Body002", false]]);
    const features = groups.find((g) => g.label === "Fonctions à répéter");
    const scope = groups.find((g) => g.label === "Corps concernés");
    assert.equal(groupShown(bodies, { target: "bodies" }), true);
    assert.equal(groupShown(features, { target: "bodies" }), false);
    assert.equal(groupShown(scope, { target: "bodies" }), false);
    assert.equal(groupShown(features, { target: "features" }), true);
    // Zone de fonctions cachée : elle ne réclame plus de clic.
    assert.equal(selectionLineGuides(groups, { target: "bodies" }), false);
    assert.equal(selectionLineGuides(groups, { target: "features" }), true);
  });
});

describe("corps concernés", () => {
  it("corps actif seulement : pas de scope", () => {
    const built = entry("btn-linpattern").build(
      { ...LINEAR, scopeMode: "active" }, CTX);
    assert.equal(built.op, "add_linear_pattern");
    assert.equal("scope" in built.params, false);
  });

  it("tous les corps, ou ceux cochés", () => {
    assert.deepEqual(patternScopeParams({ scopeMode: "all" }, CTX),
      { scope: ["Body001", "Body002"] });
    assert.deepEqual(patternScopeParams({ scopeMode: "selected",
      "scope:Body002": true }, CTX), { scope: ["Body002"] });
    assert.deepEqual(patternScopeParams({ scopeMode: "selected" }, CTX), {});
    const built = entry("btn-polpattern").build({
      target: "features", dirKind: "axis", axis: "Z", angle: "360",
      count: "4", scopeMode: "all" }, CTX);
    assert.deepEqual(built.params.scope, ["Body001", "Body002"]);
  });

  it("une pièce d'un seul corps n'a pas ce groupe", () => {
    const single = { lastTree: { bodies: [CTX.lastTree.bodies[0]] } };
    const labels = entry("btn-mirror").groups(single).map((g) => g.label);
    assert.equal(labels.includes("Corps concernés"), false);
    assert.equal(labels.includes("Corps à répéter"), true);
  });
});
