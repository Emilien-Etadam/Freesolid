import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  SKETCH_PREFS_KEY, defaultSketchPrefs, normalizeSketchPrefs, readSketchPrefs,
  writeSketchPrefs,
} from "../../app/sketchprefs.js";

function memoryStorage() {
  const data = {};
  return { getItem: (k) => (k in data ? data[k] : null),
           setItem: (k, v) => { data[k] = String(v); }, data };
}

describe("réglages d'affichage de l'esquisse", () => {
  it("par défaut : vue face au plan, symboles et cotes, ni grille ni peigne", () => {
    assert.deepEqual(defaultSketchPrefs(), {
      normalView: true, gridSnap: false, showRelations: true, showDims: true,
      showComb: false,
    });
    assert.deepEqual(readSketchPrefs(memoryStorage()), defaultSketchPrefs());
    assert.deepEqual(readSketchPrefs(null), defaultSketchPrefs());
  });

  it("garde les clés connues et booléennes seulement", () => {
    assert.deepEqual(normalizeSketchPrefs({ gridSnap: true, showDims: "non", x: 1 }),
      { ...defaultSketchPrefs(), gridSnap: true });
  });

  it("le réglage se relit ; une valeur abîmée revient aux défauts", () => {
    const storage = memoryStorage();
    assert.equal(writeSketchPrefs(storage, { normalView: false, showComb: true }), true);
    assert.deepEqual(readSketchPrefs(storage),
      { ...defaultSketchPrefs(), normalView: false, showComb: true });
    storage.setItem(SKETCH_PREFS_KEY, "{abîmé");
    assert.deepEqual(readSketchPrefs(storage), defaultSketchPrefs());
    assert.equal(writeSketchPrefs({ setItem: () => { throw new Error("x"); } }, {}), false);
  });
});
