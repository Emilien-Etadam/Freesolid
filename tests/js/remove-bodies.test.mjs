// Supprimer des corps : la zone du panneau prend ce que le dossier montre,
// et « Supprimer » sur une ligne de dossier vise ce que la ligne montre.

import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  removalCandidates,
  removalItem,
  removalMatch,
  removalTargets,
  removeBodiesBuild,
  removeBodiesGroups,
  removeBodiesParams,
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
  it("un candidat par solide, par corps plein et par surface du dossier", () => {
    assert.deepEqual(removalCandidates(tree), [
      { name: "Body", solid: 0, label: "Extrusion[1]" },
      { name: "Body", solid: 1, label: "Extrusion[2]" },
      { name: "Body001", label: "Congé" },
      { name: "Surface", label: "Surface extrudée", surface: true },
    ]);
    assert.deepEqual(removalCandidates(null), []);
  });

  it("un clic vise un candidat : solide par solide, sinon le corps", () => {
    const candidates = removalCandidates(tree);
    assert.deepEqual(removalMatch({ name: "Body", solid: 1 }, candidates),
      { name: "Body", solid: 1, label: "Extrusion[2]" });
    // Le corps à deux solides ne se vise pas en entier ; le corps vide
    // et la surface reculée ne sont pas des candidats.
    assert.equal(removalMatch({ name: "Body" }, candidates), null);
    assert.equal(removalMatch({ name: "Body002" }, candidates), null);
    assert.equal(removalMatch({ name: "Surface003" }, candidates), null);
    assert.equal(removalMatch(null, candidates), null);
    assert.deepEqual(removalItem(candidates[1]),
      { kind: "body", name: "Body", label: "Extrusion[2]", solid: 1 });
    assert.deepEqual(removalItem(candidates[3]),
      { kind: "surface", name: "Surface", label: "Surface extrudée" });
  });

  it("la zone donne les cibles, solide compris, dans l'ordre des clics", () => {
    const v = {
      mode: "remove",
      targets: { kind: "body", items: [
        { kind: "surface", name: "Surface", label: "Surface extrudée" },
        { kind: "body", name: "Body", label: "Extrusion[2]", solid: 1 },
        // Disparu du dossier depuis le clic : ignoré.
        { kind: "body", name: "Body009", label: "Ancien" },
      ] },
    };
    assert.deepEqual(removalTargets(v, removalCandidates(tree)),
      [{ name: "Surface" }, { name: "Body", solid: 1 }]);
    assert.deepEqual(removeBodiesBuild(v, { lastTree: tree }), {
      op: "add_remove_bodies",
      params: { targets: [{ name: "Surface" }, { name: "Body", solid: 1 }],
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
    assert.deepEqual(labels, ["Opération", "Corps"]);
    const [row] = entry.groups({ lastTree: tree })[1].rows;
    assert.deepEqual([row.type, row.key, row.accepts, row.multiple, row.solids],
                     ["selection", "targets", ["body", "surface"], true, true]);
    assert.equal(row.allows({ kind: "body", name: "Body001" }), true);
    assert.equal(row.allows({ kind: "body", name: "Body002" }), false);
    assert.deepEqual(row.value.items, []);
  });

  it("la réédition rouvre le même panneau, zone et mode du moteur", () => {
    // remove_bodies_info : les corps au rang de la fonction, cochés.
    const candidates = [
      { name: "Body", solid: 0, label: "Extrusion[1]", checked: false },
      { name: "Body", solid: 1, label: "Extrusion[2]", checked: true },
      { name: "Surface", label: "Surface extrudée", surface: true,
        checked: true },
    ];
    const groups = removeBodiesGroups(candidates, true);
    assert.equal(groups[0].rows[0].value, "keep");
    const [row] = groups[1].rows;
    assert.deepEqual(row.value.items, [
      { kind: "body", name: "Body", label: "Extrusion[2]", solid: 1 },
      { kind: "surface", name: "Surface", label: "Surface extrudée" },
    ]);
    const v = Object.fromEntries(groups.flatMap((g) => g.rows)
      .map((r) => [r.key, r.value]));
    assert.deepEqual(removeBodiesParams(v, candidates), {
      targets: [{ name: "Body", solid: 1 }, { name: "Surface" }],
      keep: true,
    });
    assert.equal(removeBodiesParams({ mode: "remove" }, candidates), null);
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
