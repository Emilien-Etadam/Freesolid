// Protocole neutre : l'interface lit le genre d'un objet (`type_key`), jamais
// le type propre au modeleur. Aucune chaîne « Espace::Type » de FreeCAD
// (« PartDesign::Pad », « Sketcher:: »…) dans le code de app/.
// La table des genres et ses familles : tests/test_type_keys.py.

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";

import {
  BODY_FEATURE_KEYS, SURFACE_KEYS, isBodyFeatureKey, isSurfaceKey,
} from "../../app/typekeys.js";

const APP = new URL("../../app/", import.meta.url);
// Un mot capitalisé suivi de « :: » : l'espace de noms d'un type FreeCAD.
const FREECAD_TYPE = /\b[A-Z][A-Za-z0-9]+::/;

function jsFiles() {
  const out = [];
  // Récursif (features/…), sauf vendor/ qui n'est pas à nous.
  for (const name of readdirSync(APP, { recursive: true })) {
    if (name.endsWith(".js") && !/^vendor[\\/]/.test(name)) out.push(name);
  }
  return out;
}

describe("protocole neutre", () => {
  it("app/ ne contient aucun type FreeCAD « Espace::Type »", () => {
    const hits = [];
    for (const name of jsFiles()) {
      const lines = readFileSync(new URL(name, APP), "utf8").split("\n");
      lines.forEach((line, i) => {
        if (FREECAD_TYPE.test(line)) hits.push(`${name}:${i + 1}: ${line.trim()}`);
      });
    }
    assert.deepEqual(hits, []);
  });

  it("la garde reconnaît un type FreeCAD", () => {
    assert.ok(FREECAD_TYPE.test('feature.type === "PartDesign::Pad"'));
    assert.ok(FREECAD_TYPE.test('type.startsWith("Surface::")'));
    assert.ok(!FREECAD_TYPE.test('row.dataset.type = "cylindre"'));
    assert.ok(!FREECAD_TYPE.test("div.checked::before { content: none; }"));
  });
});

describe("familles de genres", () => {
  it("fonction de corps, surface : deux familles disjointes", () => {
    assert.ok(isBodyFeatureKey("pad"));
    assert.ok(isBodyFeatureKey("datum_plane"));
    assert.ok(isSurfaceKey("surface_extrude"));
    assert.ok(isSurfaceKey("shape"));
    assert.ok(!isBodyFeatureKey("sketch") && !isSurfaceKey("sketch"));
    assert.ok(!isBodyFeatureKey(undefined) && !isSurfaceKey(undefined));
    for (const key of BODY_FEATURE_KEYS) assert.ok(!SURFACE_KEYS.has(key), key);
  });

  it("un genre que la table ne nomme pas garde sa famille", () => {
    assert.ok(isBodyFeatureKey("feature"));
    assert.ok(isSurfaceKey("surface"));
  });
});
