import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  joinPath, needsOverwrite, visibleEntries, withExtension, writeFileDir,
} from "../../app/filedialog.js";

const ENTRIES = [
  { name: "pieces", kind: "dir" },
  { name: "a.FCStd", kind: "file" },
  { name: "b.stl", kind: "file" },
  { name: "c.step", kind: "file" },
];

describe("dialogue de fichiers", () => {
  it("montre les dossiers et seulement le filtre", () => {
    const shown = visibleEntries(ENTRIES, [".fcstd"]);
    assert.deepEqual(shown.map((entry) => entry.name), ["pieces", "a.FCStd"]);
  });

  it("ajoute l'extension du filtre et refuse un chemin", () => {
    assert.equal(withExtension("piece", [".FCStd"]), "piece.FCStd");
    assert.equal(withExtension("piece.fcstd", [".FCStd"]), "piece.FCStd");
    assert.equal(withExtension("piece.STL", [".stl", ".3mf"]), "piece.stl");
    assert.equal(withExtension("piece.stl", [".step", ".stp"]), "piece.step");
    assert.equal(withExtension("../secret.FCStd", [".fcstd"]), "");
    assert.equal(withExtension("a/b.FCStd", [".fcstd"]), "");
  });

  it("joint le dossier et le nom", () => {
    assert.equal(joinPath("/home/pc", "a.FCStd"), "/home/pc/a.FCStd");
    assert.equal(joinPath("C:\\Users\\PC", "a.FCStd"), "C:\\Users\\PC\\a.FCStd");
  });

  it("signale un fichier déjà présent, quelle que soit la casse", () => {
    assert.equal(needsOverwrite(ENTRIES, "a.fcstd"), true);
    assert.equal(needsOverwrite(ENTRIES, "neuf.fcstd"), false);
  });

  it("mémorise le dernier dossier", () => {
    const saved = new Map();
    const storage = {
      setItem: (key, value) => saved.set(key, value),
      getItem: (key) => saved.get(key) ?? null,
    };
    assert.equal(writeFileDir(storage, "C:\\pieces"), true);
    assert.equal(saved.get("freesolid.filedir"), "C:\\pieces");
  });
});
