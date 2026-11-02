import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  extrudeBuild, extrudeEditInitial, extrudeEditProblem, extrudeEditValues,
  extrudeGroups, extrudeInvalid, holeEditInitial, holeEditValues, holeGroups,
  shellEditGroups, shellEditValues,
} from "../../app/features.js";

describe("extrudeBuild", () => {
  it("borgne : profondeur positive", () => {
    assert.deepEqual(extrudeBuild("add_pad", { cond: "borgne", length: "-12" }),
      { op: "add_pad", params: { reversed: false, cond: "borgne", length: 12 } });
    assert.equal(extrudeBuild("add_pad", { cond: "borgne", length: "0" }), null);
  });

  it("plan milieu : condition borgne + midplane", () => {
    const b = extrudeBuild("add_pad", { cond: "milieu", length: 20 });
    assert.equal(b.params.midplane, true);
    assert.equal(b.params.cond, "borgne");
  });

  it("jusqu'à la face : il faut une face", () => {
    assert.equal(extrudeBuild("add_pocket", { cond: "face" }), null);
    const b = extrudeBuild("add_pocket",
      { cond: "face", face: { kind: "face", face: 3 }, offset: "1,5" });
    assert.equal(b.params.face, 3);
    assert.equal(b.params.offset, 1.5);
    assert.equal(b.params.length, undefined);
  });

  it("paroi mince : un côté, plan milieu, deux côtés", () => {
    const base = { cond: "borgne", length: 10, thin: true, thinT: "2" };
    assert.deepEqual(extrudeBuild("add_pad", base).params.thin,
      { type: "un", thickness: 2, reversed: false });
    assert.deepEqual(extrudeBuild("add_pad",
      { ...base, thinType: "milieu", thinReversed: true }).params.thin,
      { type: "milieu", thickness: 2, reversed: false });
    assert.deepEqual(extrudeBuild("add_pocket",
      { ...base, thinType: "deux", thinT2: "1,5" }).params.thin,
      { type: "deux", thickness: 2, thickness2: 1.5, reversed: false });
    assert.equal(extrudeBuild("add_pad", { ...base, thinT: "0" }), null);
    assert.equal(extrudeInvalid({ ...base, thinT: "0" }),
      "Épaisseur de paroi invalide");
    assert.equal(extrudeBuild("add_pad", { cond: "borgne", length: 10 })
      .params.thin, undefined);
  });

  it("extrémités fermées : extrusion borgne seulement", () => {
    const v = { cond: "borgne", length: 10, thin: true, thinT: 2,
                thinCaps: true, thinCapT: "1,5" };
    assert.equal(extrudeBuild("add_pad", v).params.thin.caps, 1.5);
    assert.equal(extrudeBuild("add_pocket", v).params.thin.caps, undefined);
    assert.equal(extrudeBuild("add_pad", { ...v, cond: "suivant" })
      .params.thin.caps, undefined);
    assert.equal(extrudeBuild("add_pad", { ...v, taper: 3 })
      .params.thin.caps, undefined);
    assert.equal(extrudeBuild("add_pad", { ...v, thinCapT: 0 }), null);
    const rows = extrudeGroups("pad").flatMap((g) => g.rows);
    assert.ok(rows.some((r) => r.key === "thinCaps"));
    assert.ok(!extrudeGroups("pocket").flatMap((g) => g.rows)
      .some((r) => r.key === "thinCaps"));
  });

  it("à travers tout : pas de profondeur", () => {
    assert.deepEqual(extrudeBuild("add_pocket", { cond: "travers" }).params,
      { reversed: false, cond: "travers" });
  });

  it("deuxième direction et dépouilles", () => {
    const b = extrudeBuild("add_pad", {
      cond: "borgne", length: 10, taper: 2,
      dir2: true, cond2: "borgne", length2: 4, taper2: 1,
    });
    assert.deepEqual(b.params, {
      reversed: false, cond: "borgne", length: 10, taper: 2,
      cond2: "borgne", length2: 4, taper2: 1,
    });
  });

  it("le plan milieu ignore la deuxième direction", () => {
    const b = extrudeBuild("add_pad",
      { cond: "milieu", length: 10, dir2: true, cond2: "borgne", length2: 4 });
    assert.equal(b.params.cond2, undefined);
  });

  it("message d'erreur selon la condition", () => {
    assert.match(extrudeInvalid({ cond: "face" }), /face/);
    assert.equal(extrudeInvalid({ cond: "borgne" }), "Profondeur invalide");
  });

  it("l'enlèvement commence par « à travers tout », le bossage par « borgne »", () => {
    assert.equal(extrudeGroups("pocket")[0].rows[0].value, "travers");
    assert.equal(extrudeGroups("pad")[0].rows[0].value, "borgne");
  });
});

describe("coque", async () => {
  const { shellBuild } = await import("../../app/features.js");
  it("plusieurs faces, vers l'extérieur sur demande", () => {
    const v = { faces: { kind: "face", items: [{ face: 3 }, { face: 5 }] },
                thickness: "1,5", outward: true };
    assert.deepEqual(shellBuild(v), { op: "add_thickness",
      params: { faces: [3, 5], thickness: 1.5, outward: true } });
  });
  it("sans face ou sans épaisseur : rien", () => {
    assert.equal(shellBuild({ faces: { items: [] }, thickness: 2 }), null);
    assert.equal(shellBuild({ faces: { items: [{ face: 1 }] }, thickness: 0 }),
      null);
  });
});

/** Une extrusion de l'arbre, telle que le moteur l'envoie. */
function feature(extrude = {}, extra = {}) {
  return {
    name: "Pad", type_key: "pad",
    extrude: { cond: "borgne", midplane: false, reversed: false, taper: 0,
               offset: 0, cond2: null, taper2: 0, face: false, ...extrude },
    params: [{ key: "length", value: 10 }],
    ...extra,
  };
}

/** Les valeurs du panneau à l'ouverture : celles de ses lignes. */
function opened(f, kind = "pad") {
  const v = {};
  for (const group of extrudeGroups(kind, extrudeEditInitial(f))) {
    for (const row of group.rows) v[row.key] = row.value;
  }
  return v;
}

describe("réédition de l'extrusion", () => {
  it("rouvre le panneau tel quel : rien à envoyer", () => {
    for (const f of [
      feature(),
      feature({ cond: "suivant", reversed: true, taper: -3 }),
      feature({ midplane: true }),
      feature({ cond2: "borgne", taper2: 2 },
              { params: [{ key: "length", value: 8 },
                         { key: "length2", value: 4 }] }),
      feature({}, { params: [{ key: "length", value: 10, expr: "2*L" }] }),
    ]) {
      assert.deepEqual(extrudeEditValues(opened(f), f), {});
    }
  });

  it("envoie la condition, le sens et la dépouille qui changent", () => {
    const f = feature();
    assert.deepEqual(extrudeEditValues(
      { ...opened(f), cond: "suivant", reversed: true, taper: 4,
        taperOut: true }, f),
      { cond: "suivant", reversed: true, taper: -4 });
    assert.deepEqual(extrudeEditValues(
      { ...opened(f), cond: "milieu", reversed: true, length: "20" }, f),
      { midplane: true, length: 20 });
  });

  it("ouvrir le côté 2 envoie sa profondeur, même inchangée", () => {
    const f = feature();
    assert.deepEqual(extrudeEditValues(
      { ...opened(f), dir2: true, cond2: "borgne" }, f),
      { cond2: "borgne", length2: 10 });
    const two = feature({ cond2: "borgne" });
    assert.deepEqual(extrudeEditValues({ ...opened(two), dir2: false }, two),
      { cond2: null });
  });

  it("refuse une profondeur vide et le dit", () => {
    const f = feature();
    const v = { ...opened(f), length: "" };
    assert.equal(extrudeEditValues(v, f), null);
    assert.equal(extrudeEditProblem(v, f), "Profondeur invalide");
  });

  it("ne re-choisit pas la face d'arrivée", () => {
    const rows = (f) => extrudeGroups("pad", extrudeEditInitial(f))
      .flatMap((g) => g.rows);
    const conds = (f) => rows(f).find((r) => r.key === "cond").options
      .map(([c]) => c);
    assert.ok(!rows(feature()).some((r) => r.key === "face"));
    assert.ok(!conds(feature()).includes("face"));
    const toFace = feature({ cond: "face", offset: 1.5, face: true });
    assert.ok(conds(toFace).includes("face"));
    assert.deepEqual(extrudeEditValues(
      { ...opened(toFace), offset: "2" }, toFace), { offset: 2 });
  });

  it("paroi mince : épaisseurs et côté, extrémités fermées borgnes", () => {
    const thin = { type: "un", thickness: 2, thickness2: 0, reversed: false,
                   caps: 0 };
    const f = feature({}, { thin, params: [{ key: "length", value: 10 },
                                           { key: "thinT", value: 2 }] });
    assert.deepEqual(extrudeEditValues(
      { ...opened(f), thinReversed: true, thinT: "3" }, f),
      { thinT: 3, thinReversed: true });
    const bad = { ...opened(f), thinT: "" };
    assert.equal(extrudeEditProblem(bad, f), "Épaisseur de paroi invalide");
    const capped = feature({}, { thin: { ...thin, caps: 1 } });
    const groups = extrudeGroups("pad", extrudeEditInitial(capped));
    const keys = groups.flatMap((g) => g.rows.map((r) => r.key));
    assert.ok(!keys.includes("taper") && keys.includes("thinCapT"));
    assert.deepEqual(groups[0].rows[0].options.map(([c]) => c),
      ["borgne", "milieu"]);
  });
});

/** Les valeurs d'un panneau à l'ouverture. */
function rowValues(groups) {
  const v = {};
  for (const group of groups) {
    for (const row of group.rows) v[row.key] = row.value;
  }
  return v;
}

describe("réédition de la coque", () => {
  const shell = { name: "Thickness", type_key: "thickness",
                  shell: { outward: false },
                  params: [{ key: "thickness", value: 2 }] };
  it("rien à envoyer à l'ouverture ; le sens et l'épaisseur changent", () => {
    const v = rowValues(shellEditGroups(shell));
    assert.deepEqual(shellEditValues(v, shell), {});
    assert.deepEqual(shellEditValues({ ...v, outward: true, thickness: "3" },
                                     shell), { thickness: 3, outward: true });
    assert.equal(shellEditValues({ ...v, thickness: "" }, shell), null);
  });
});

describe("réédition du perçage", () => {
  const hole = (state, params) => ({
    name: "Hole", type_key: "hole",
    hole: { cut: "none", cond: "travers", depth: null, cutDiameter: null,
            cutDepth: null, cutAngle: null, ...state },
    params: params ?? [{ key: "diameter", value: 6 }],
  });
  const opened = (f) => rowValues(holeGroups(holeEditInitial(f)));

  it("rien à envoyer à l'ouverture", () => {
    for (const f of [
      hole(),
      hole({ cut: "lamage", cond: "borgne", depth: 8, cutDiameter: 10,
             cutDepth: 3 },
           [{ key: "diameter", value: 6 }, { key: "depth", value: 8 },
            { key: "cutDiameter", value: 10 }, { key: "cutDepth", value: 3 }]),
    ]) {
      assert.deepEqual(holeEditValues(opened(f), f), {});
    }
  });

  it("un nouveau type renvoie ses cotes de tête, une fin borgne sa profondeur", () => {
    const f = hole();
    assert.deepEqual(holeEditValues(
      { ...opened(f), cut: "fraisage", cond: "borgne" }, f),
      { cut: "fraisage", cond: "borgne", depth: 15, cutDiameter: 11,
        cutAngle: 90 });
    assert.deepEqual(holeEditValues({ ...opened(f), cut: "lamage" }, f),
      { cut: "lamage", cutDiameter: 11, cutDepth: 3 });
  });

  it("une tête plus petite que le trou est refusée", () => {
    const f = hole();
    assert.equal(holeEditValues(
      { ...opened(f), cut: "lamage", cutDiameter: 5 }, f), null);
  });

  it("le panneau de réédition n'a pas de positions", () => {
    const keys = holeGroups(holeEditInitial(hole()))
      .flatMap((g) => g.rows.map((r) => r.key));
    assert.ok(!keys.includes("pos"));
    assert.ok(keys.includes("cut") && keys.includes("cond"));
  });
});
