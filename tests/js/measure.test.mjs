import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { measurePick } from "../../app/measure.js";

const edges = [{ edgeId: 4 }, { edgeId: 9 }];
const faces = [{ faceId: 2 }];

describe("measurePick", () => {
  it("prend l'arête survolée avant la face", () => {
    assert.deepEqual(measurePick(1, edges, 0, faces), { kind: "edge", id: 9 });
  });

  it("prend la face quand aucune arête n'est survolée", () => {
    assert.deepEqual(measurePick(-1, edges, 0, faces), { kind: "face", id: 2 });
  });

  it("ne vise rien dans le vide", () => {
    assert.equal(measurePick(-1, edges, -1, faces), null);
  });
});
