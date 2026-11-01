// Supprimer des corps : les cases du panneau suivent le dossier, et
// « Supprimer » sur une ligne de dossier vise ce que la ligne montre.

import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  removalCandidates,
  removalKey,
  removalTargets,
  removeBodiesBuild,
} from "../../app/features/combiner.js";
import { FEATURES } from "../../app/features.js";
import { folderRemovalTarget } from "../../app/contextmenu.js";

const tree = {
  bodies: [
    { name: "Body", label: "Extrusion", active: true, has_solid: true,
      solids: [{ label: "Extrusion[1]" }, { label: "Extrusion[2]" }] },
    { name: "Body001", label: "Congé", active: false, has_solid: true },
    { name: "Body002", label: "Corps", active: false, has_solid: false },
  ],
  surfaces: [
    { name: "Surface", label: "Surface extrudée" },
    { name: "Surface001", label: "Ôtée", removed: true },
    { name: "Surface002", label: "Ajustée", consumed: true },
    { name: "Surface003", label: "Reculée", rolled_back: true },
  ],
};

describe("supprimer des corps", () => {
  it("une case par solide, par corps plein et par surface du dossier", () => {
    assert.deepEqual(removalCandidates(tree), [
      { name: "Body", solid: 0, label: "Extrusion[1]" },
      { name: "Body", solid: 1, label: "Extrusion[2]" },
      { name: "Body001", label: "Congé" },
      { name: "Surface", label: "Surface extrudée", surface: true },
    ]);
    assert.deepEqual(removalCandidates(null), []);
  });

  it("les cases cochées donnent les cibles, solide compris", () => {
    const v = {
      mode: "remove",
      [removalKey({ name: "Body", solid: 1 })]: true,
      [removalKey({ name: "Body001" })]: false,
      [removalKey({ name: "Surface" })]: true,
    };
    assert.deepEqual(removalTargets(v, tree),
      [{ name: "Body", solid: 1 }, { name: "Surface" }]);
    assert.deepEqual(removeBodiesBuild(v, { lastTree: tree }), {
      op: "add_remove_bodies",
      params: { targets: [{ name: "Body", solid: 1 }, { name: "Surface" }],
                keep: false },
    });
    assert.equal(removeBodiesBuild({ ...v, mode: "keep" },
      { lastTree: tree }).params.keep, true);
    assert.equal(removeBodiesBuild({ mode: "remove" }, { lastTree: tree }),
      null);
  });

  it("le panneau se refuse à une pièce sans corps", () => {
    const entry = FEATURES.find((e) => e.op === "add_remove_bodies");
    assert.equal(entry.button, "btn-remove-bodies");
    assert.equal(entry.guard({ lastTree: tree }), null);
    assert.ok(entry.guard({ lastTree: { bodies: [], surfaces: [] } }));
    const labels = entry.groups({ lastTree: tree }).map((g) => g.label);
    assert.deepEqual(labels,
      ["Opération", "Corps volumiques", "Corps surfaciques"]);
  });

  it("« Supprimer » sur une ligne de dossier vise le corps, le solide ou la surface", () => {
    const [body, other, empty] = tree.bodies;
    assert.deepEqual(folderRemovalTarget(other), { name: "Body001" });
    assert.deepEqual(folderRemovalTarget({ ...body, solid: 1 }),
      { name: "Body", solid: 1 });
    // Un corps vide n'a rien à ôter : il se supprime pour de bon.
    assert.equal(folderRemovalTarget(empty), null);
    assert.deepEqual(folderRemovalTarget({ ...tree.surfaces[0], inFolder: true }),
      { name: "Surface" });
    // La ligne d'histoire d'une surface ou d'une fonction : pas de fonction.
    assert.equal(folderRemovalTarget(tree.surfaces[0]), null);
    assert.equal(folderRemovalTarget({ name: "Pad", type_key: "pad" }), null);
  });
});
