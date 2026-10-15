// La table unique des icônes : chaque rôle désigne un fichier, et aucun
// autre module ne construit une URL d'icône par lui-même.

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { ICONS, iconSrc } from "../../app/icons.js";

const appDir = fileURLToPath(new URL("../../app/", import.meta.url));

describe("table des icônes", () => {
  it("chaque rôle nomme un fichier présent, qui se nomme aussi lui-même", () => {
    for (const [role, file] of Object.entries(ICONS)) {
      assert.ok(file.endsWith(".svg"), file);
      assert.equal(iconSrc(role), "icons/" + file);
      assert.ok(existsSync(join(appDir, "icons", file)), file);
      const stem = file.slice(0, -4);
      // Un brouillon fs_x n'est désigné que par son rôle x ; une icône
      // reprise (FreeCAD, Nodes) se nomme aussi par son nom d'origine.
      if (stem.startsWith("fs_")) {
        assert.equal(role, stem.slice(3), file);
      } else {
        assert.equal(iconSrc(file), "icons/" + file);
        assert.equal(iconSrc("icons/" + file), "icons/" + file);
      }
    }
  });

  it("une commande garde l'icône de FreeCAD ou de Nodes qu'elle avait", () => {
    assert.equal(iconSrc("pocket"), "icons/PartDesign_Pocket.svg");
    assert.equal(iconSrc("rel_tangent"), "icons/Constraint_Tangent.svg");
    assert.equal(iconSrc("nodes_extrude"), "icons/nodes_extrude.svg");
    assert.equal(iconSrc("spline3d"), "icons/nodes_polyline.svg");
    assert.equal(iconSrc("datum_axis"), "icons/fs_datum_axis.svg");
  });

  it("refuse un chemin, une adresse ou un rôle inconnu", () => {
    assert.equal(iconSrc("../evil.svg"), "");
    assert.equal(iconSrc("icons/../evil.svg"), "");
    assert.equal(iconSrc("https://evil.example/x.svg"), "");
    assert.equal(iconSrc("C:\\icons\\x.svg"), "");
    assert.equal(iconSrc(""), "");
    assert.equal(iconSrc("inconnu"), "");
  });

  it("couvre les noms de fichiers que le moteur envoie encore", () => {
    const vocab = readFileSync(
      fileURLToPath(new URL("../../engine/vocab.py", import.meta.url)), "utf8");
    const values = new Set(Object.values(ICONS));
    const names = new Set();
    for (const match of vocab.matchAll(/"([A-Za-z0-9_.-]+\.svg)"/g)) {
      names.add(match[1]);
    }
    for (const name of names) assert.ok(values.has(name), name);
  });

  it("aucun autre fichier de l'interface ne nomme une icône", () => {
    const hits = [];
    function walk(dir) {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const path = join(dir, entry.name);
        if (entry.isDirectory()) {
          if (entry.name === "icons") continue;
          walk(path);
          continue;
        }
        if (!/\.(js|html|json)$/.test(entry.name) || entry.name === "icons.js") {
          continue;
        }
        const text = readFileSync(path, "utf8");
        if (/\.svg/.test(text) || /["']icons\//.test(text)) hits.push(entry.name);
      }
    }
    walk(appDir);
    assert.deepEqual(hits, []);
  });
});
