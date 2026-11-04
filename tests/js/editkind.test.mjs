// Ce que le double-clic rouvre : un seul endroit décide, le menu
// « Modifier » le suit (app/editkind.js).

import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  featureEditor, isFrozen, isSurfaceRow, surfaceEditor,
} from "../../app/editkind.js";

describe("éditeur d'une fonction", () => {
  it("chaque genre a le sien, les cotes en dernier", () => {
    assert.equal(featureEditor({ type_key: "pad", edits: "Pattern" }), "edits");
    assert.equal(featureEditor({ type_key: "pad", graph: {} }), "graph");
    assert.equal(featureEditor({ type_key: "sketch" }), "sketch");
    assert.equal(featureEditor({ type_key: "feature", vertex_chamfer: [1] }),
      "vertex_chamfer");
    assert.equal(featureEditor({ type_key: "pocket", text: {} }), "text");
    assert.equal(featureEditor({ type_key: "feature", surface_cut: {} }),
      "surface_cut");
    assert.equal(featureEditor({ type_key: "chamfer", chamfer: {} }), "chamfer");
    assert.equal(featureEditor({ type_key: "groove", revolution: {} }),
      "revolution");
    assert.equal(featureEditor({ type_key: "pocket", extrude: {} }), "extrude");
    assert.equal(featureEditor({ type_key: "thickness", shell: {} }), "shell");
    assert.equal(featureEditor({ type_key: "hole", hole: {} }), "hole");
    // Perçage taraudé : le moteur n'envoie pas `hole`, les cotes suffisent.
    assert.equal(featureEditor({ type_key: "hole", has_params: true }),
      "params");
    // Une gravure est un enlèvement : son panneau d'abord.
    assert.equal(featureEditor({ type_key: "pocket", text: {}, extrude: {} }),
      "text");
    assert.equal(featureEditor({ type_key: "remove_bodies" }), "remove_bodies");
    assert.equal(featureEditor({ type_key: "pad", has_params: true }), "params");
  });

  it("sans cote ni éditeur : rien ; sans avis du moteur : on tente", () => {
    assert.equal(featureEditor({ type_key: "mirror", has_params: false }), null);
    // Une symétrie d'enlèvements se rouvre pour ses corps creusés.
    assert.equal(featureEditor({ type_key: "mirror", has_params: false,
                                 cut: [] }), "params");
    // Copie d'une symétrie de corps : la symétrie n'a pas de cote.
    assert.equal(featureEditor({ type_key: "feature", edits: "Pattern",
      edits_has_params: false }), null);
    assert.equal(featureEditor({ type_key: "feature", edits: "Pattern",
      edits_has_params: true }), "edits");
    assert.equal(featureEditor({ type_key: "loft", has_params: false }), null);
    // Un lissage, un balayage se rouvrent pour leurs corps fondus ou creusés.
    assert.equal(featureEditor({ type_key: "loft", has_params: false,
                                 fused: [] }), "params");
    assert.equal(featureEditor({ type_key: "sweep_cut", has_params: false,
                                 cut: [] }), "params");
    assert.equal(featureEditor({ type_key: "pad" }), "params");
    assert.equal(featureEditor({ type_key: "body", active: true }), null);
    assert.equal(featureEditor(null), null);
    assert.equal(featureEditor({}), null);
  });
});

describe("éditeur d'une surface", () => {
  it("courbes, opérations, puis les cotes", () => {
    assert.equal(surfaceEditor({ curve: {}, static: true }), "curve3d");
    assert.equal(surfaceEditor({ sketch3d: {} }), "sketch3d");
    for (const kind of ["extend", "trim", "offset", "flatten", "freeform"]) {
      assert.equal(surfaceEditor({ surface: { kind } }), kind);
    }
    assert.equal(surfaceEditor({ surface: { kind: "fillet" } }), "surface_fillet");
    assert.equal(surfaceEditor({ surface: { kind: "freeform", moves: [1] } }),
      "poles");
    assert.equal(surfaceEditor({ type_key: "surface_extrude", has_params: true }),
      "params");
  });

  it("une surface figée ou sans cote ne se réédite pas", () => {
    assert.equal(surfaceEditor({ type_key: "shape", static: true }), null);
    assert.equal(surfaceEditor({ type_key: "surface_radiate",
                                 has_params: true }), "radiate");
    assert.equal(surfaceEditor({ type_key: "surface_radiate",
                                 has_params: false }), null);
    assert.equal(surfaceEditor({ type_key: "surface_loft", has_params: false }),
      null);
    assert.equal(surfaceEditor({ type_key: "surface", surface: { kind: "split" },
      has_params: false }), null);
    assert.equal(surfaceEditor(undefined), null);
    assert.equal(isFrozen({ static: true }), true);
    assert.equal(isFrozen({ type_key: "surface_extrude" }), false);
  });

  it("une ligne est une surface quand l'arbre la range parmi elles", () => {
    const tree = { surfaces: [{ name: "Binder" }] };
    assert.equal(isSurfaceRow(tree, "Binder"), true);
    assert.equal(isSurfaceRow(tree, "Pad"), false);
    assert.equal(isSurfaceRow(null, "Binder"), false);
  });
});
