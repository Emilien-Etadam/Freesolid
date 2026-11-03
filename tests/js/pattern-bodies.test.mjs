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
      { name: "Body", label: "Plaque", active: true, has_solid: true },
      { name: "Body001", label: "Dessous", active: false, has_solid: true },
      { name: "Body002", label: "Capot", active: false, has_solid: true },
    ],
  },
};
/** La valeur d'une zone de corps remplie par des clics. */
const zone = (...names) => ({ kind: "body",
  items: names.map((name) => ({ kind: "body", name, label: name })) });
const entry = (button) => FEATURES.find((e) => e.button === button);
const LINEAR = { target: "features", dirKind: "axis", axis: "X",
                 reversed: false, mode: "spacing", length: "20", count: "3" };

describe("répéter des corps", () => {
  it("les corps de la zone partent vers add_body_pattern", () => {
    const built = entry("btn-linpattern").build({
      ...LINEAR, target: "bodies", sources: zone("Body", "Body002") }, CTX);
    assert.equal(built.op, "add_body_pattern");
    assert.deepEqual(built.params, {
      kind: "linear", bodies: ["Body", "Body002"], reversed: false,
      axis: "X", length: 20, count: 3, spacing: true });
  });

  it("circulaire et symétrie donnent leur genre", () => {
    const polar = entry("btn-polpattern").build({
      target: "bodies", dirKind: "axis", axis: "Z", angle: "360",
      count: "4", sources: zone("Body") }, CTX);
    assert.equal(polar.params.kind, "polar");
    assert.equal(polar.params.angle, 360);
    const mirror = entry("btn-mirror").build(
      { target: "bodies", plane: "XY", sources: zone("Body001") }, CTX);
    assert.deepEqual(mirror, { op: "add_body_pattern",
      params: { kind: "mirror", bodies: ["Body001"], plane: "XY" } });
  });

  it("zone vide : pas d'op, le panneau dit pourquoi", () => {
    const mirror = entry("btn-mirror");
    const v = { target: "bodies", plane: "YZ", sources: zone() };
    assert.equal(mirror.build(v, CTX), null);
    assert.equal(mirror.invalid(v), "Choisissez au moins un corps à répéter");
    // Un corps cliqué deux fois (deux de ses solides) ne compte qu'une fois.
    assert.deepEqual(patternBodiesParams({ sources: zone("A", "A") }), ["A"]);
  });

  it("la zone part du corps actif, les groupes suivent le choix", () => {
    const groups = entry("btn-linpattern").groups(CTX);
    const bodies = groups.find((g) => g.label === "Corps à répéter");
    const [row] = bodies.rows;
    assert.deepEqual([row.type, row.key, row.accepts, row.multiple],
                     ["selection", "sources", ["body"], true]);
    assert.deepEqual(row.value.items.map((i) => i.name), ["Body"]);
    // Un corps sans solide ne se répète pas.
    const empty = { lastTree: { bodies: [
      { name: "Body", label: "Plaque", active: true, has_solid: false },
      { name: "Body001", label: "Dessous", active: false, has_solid: true }] } };
    const [emptyRow] = entry("btn-linpattern").groups(empty)
      .find((g) => g.label === "Corps à répéter").rows;
    assert.deepEqual(emptyRow.value.items, []);
    assert.equal(emptyRow.allows({ kind: "body", name: "Body" }), false);
    assert.equal(emptyRow.allows({ kind: "body", name: "Body001" }), true);
    const features = groups.find((g) => g.label === "Fonctions à répéter");
    const scope = groups.find((g) => g.label === "Corps concernés");
    assert.equal(groupShown(bodies, { target: "bodies" }), true);
    assert.equal(groupShown(features, { target: "bodies" }), false);
    assert.equal(groupShown(scope, { target: "bodies" }), false);
    assert.equal(groupShown(features, { target: "features" }), true);
    // Zone de fonctions cachée : elle ne réclame plus de clic ; la zone
    // des corps, vide, en réclame un.
    assert.equal(selectionLineGuides(groups,
      { target: "bodies", sources: row.value }), false);
    assert.equal(selectionLineGuides(groups,
      { target: "bodies", sources: zone() }), true);
    assert.equal(selectionLineGuides(groups, { target: "features" }), true);
  });
});

describe("corps concernés", () => {
  it("corps traversés par défaut : pas de scope, le moteur les trouve", () => {
    const [group] = entry("btn-linpattern").groups(CTX)
      .filter((g) => g.label === "Corps concernés");
    assert.equal(group.rows[0].value, "crossed");
    const built = entry("btn-linpattern").build(LINEAR, CTX);
    assert.equal(built.op, "add_linear_pattern");
    assert.equal("scope" in built.params, false);
    assert.deepEqual(patternScopeParams({ scopeMode: "crossed" }, CTX), {});
  });

  it("corps actif seulement : un scope vide", () => {
    const built = entry("btn-linpattern").build(
      { ...LINEAR, scopeMode: "active" }, CTX);
    assert.deepEqual(built.params.scope, []);
  });

  it("tous les corps, ou ceux de la zone", () => {
    assert.deepEqual(patternScopeParams({ scopeMode: "all" }, CTX),
      { scope: ["Body001", "Body002"] });
    assert.deepEqual(patternScopeParams({ scopeMode: "selected",
      scopeBodies: zone("Body002") }, CTX), { scope: ["Body002"] });
    // Le corps actif n'est pas un « autre corps » : la zone le refuse.
    const [group] = entry("btn-linpattern").groups(CTX)
      .filter((g) => g.label === "Corps concernés");
    const scopeZone = group.rows.find((r) => r.key === "scopeBodies");
    assert.equal(scopeZone.allows({ kind: "body", name: "Body" }), false);
    assert.equal(scopeZone.allows({ kind: "body", name: "Body002" }), true);
    assert.equal(scopeZone.showIf({ scopeMode: "selected" }), true);
    assert.equal(scopeZone.showIf({ scopeMode: "all" }), false);
    assert.deepEqual(patternScopeParams({ scopeMode: "selected" }, CTX),
      { scope: [] });
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
