import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  baseName, existingName, joinPath, nativeFileDialog, nativeFilters,
  needsOverwrite, parentDir, pickNative, visibleEntries, withAllowedExtension,
  withExtension, writeFileDir,
} from "../../app/filedialog.js";

const ENTRIES = [
  { name: "pieces", kind: "dir" },
  { name: "a.FCStd", kind: "file" },
  { name: "b.stl", kind: "file" },
  { name: "c.step", kind: "file" },
  { name: "fermoir.SLDPRT", kind: "file" },
  { name: "cube.X_T", kind: "file" },
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

  it("ouvre le fichier sous le nom que le dossier lui donne", () => {
    const typed = withExtension("fermoir.sldprt", [".SLDPRT"]);
    assert.equal(existingName(ENTRIES, typed), "fermoir.SLDPRT");
    assert.equal(existingName(ENTRIES, withExtension("cube.x_t", [".x_t", ".x_b"])),
      "cube.X_T");
    assert.equal(existingName(ENTRIES, "pieces"), "");
    assert.equal(existingName(ENTRIES, "absent.x_t"), "");
  });

  it("montre les pièces SLDPRT et Parasolid quelle que soit la casse", () => {
    const shown = visibleEntries(ENTRIES, [".SLDPRT", ".x_t", ".x_b"]);
    assert.deepEqual(shown.map((entry) => entry.name),
      ["pieces", "fermoir.SLDPRT", "cube.X_T"]);
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

function memoryStorage(start = {}) {
  const saved = new Map(Object.entries(start));
  return {
    saved,
    setItem: (key, value) => saved.set(key, value),
    getItem: (key) => saved.get(key) ?? null,
  };
}

const OPEN = {
  title: "Ouvrir", mustExist: true, overwrite: false, defaultName: "",
  filters: [
    { label: "STEP", extensions: [".step", ".stp"] },
    { label: "Tous les fichiers autorisés", all: true, extensions: [".FCStd", ".step"] },
  ],
};
const SAVE = {
  title: "Exporter", mustExist: false, overwrite: true, defaultName: "piece.stl",
  filters: [
    { label: "Maillage (.stl)", extensions: [".stl"] },
    { label: "3MF", extensions: [".3mf"] },
  ],
};

describe("dialogue natif (application de bureau)", () => {
  it("n'existe que dans la fenêtre Tauri", () => {
    const dialog = { open() {}, save() {} };
    assert.equal(nativeFileDialog({ __TAURI__: { dialog } }), dialog);
    assert.equal(nativeFileDialog({ __TAURI__: {} }), null);
    assert.equal(nativeFileDialog({}), null);
    assert.equal(nativeFileDialog(undefined), null);
  });

  it("donne les filtres sans point, dans toutes les casses, « tous » d'abord", () => {
    assert.deepEqual(nativeFilters(OPEN.filters), [
      { name: "Tous les fichiers autorisés",
        extensions: ["FCStd", "fcstd", "FCSTD", "step", "STEP"] },
      { name: "STEP", extensions: ["step", "STEP", "stp", "STP"] },
    ]);
  });

  it("coupe un chemin quel que soit le système", () => {
    assert.equal(parentDir("/home/pc/a.step"), "/home/pc");
    assert.equal(parentDir("/a.step"), "/");
    assert.equal(parentDir("D:\\Pièces\\a.step"), "D:\\Pièces");
    assert.equal(parentDir("D:\\a.step"), "D:\\");
    assert.equal(parentDir("a.step"), "");
    assert.equal(baseName("D:\\Pièces\\a.step"), "a.step");
    assert.equal(baseName("/a.step"), "a.step");
  });

  it("complète l'extension que le système n'a pas mise", () => {
    assert.equal(withAllowedExtension("/w/piece", [".stl", ".3mf"]), "/w/piece.stl");
    assert.equal(withAllowedExtension("/w/piece.3MF", [".stl", ".3mf"]), "/w/piece.3MF");
    assert.equal(withAllowedExtension("/w.v2/piece", [".FCStd"]), "/w.v2/piece.FCStd");
  });

  it("ouvre depuis le dernier dossier et le retient", async () => {
    const storage = memoryStorage({ "freesolid.filedir": "D:\\Pièces" });
    let asked = null;
    const dialog = {
      open: async (options) => { asked = options; return "E:\\Clé\\fermoir.SLDPRT"; },
    };
    assert.equal(await pickNative(dialog, OPEN, { storage }), "E:\\Clé\\fermoir.SLDPRT");
    assert.equal(asked.defaultPath, "D:\\Pièces");
    assert.equal(asked.multiple, false);
    assert.equal(asked.filters[0].name, "Tous les fichiers autorisés");
    assert.equal(storage.saved.get("freesolid.filedir"), "E:\\Clé");
  });

  it("rend null quand on annule, sans toucher au dernier dossier", async () => {
    const storage = memoryStorage({ "freesolid.filedir": "/d" });
    assert.equal(await pickNative({ open: async () => null }, OPEN, { storage }), null);
    assert.equal(storage.saved.get("freesolid.filedir"), "/d");
  });

  it("enregistre avec l'extension complétée, et demande avant d'écraser", async () => {
    const storage = memoryStorage();
    const dialog = { save: async () => "/media/cle/piece" };
    const listDir = async () => ({ entries: [{ name: "piece.stl", kind: "file" }] });
    const asked = [];
    assert.equal(await pickNative(dialog, SAVE, {
      storage, listDir, ask: (name) => { asked.push(name); return false; },
    }), null);
    assert.deepEqual(asked, ["piece.stl"]);
    assert.equal(await pickNative(dialog, SAVE, {
      storage, listDir, ask: () => true,
    }), "/media/cle/piece.stl");
    assert.equal(storage.saved.get("freesolid.filedir"), "/media/cle");
    // Nom complet tapé : le système a déjà demandé, on ne redemande pas.
    const complete = { save: async () => "/media/cle/piece.stl" };
    assert.equal(await pickNative(complete, SAVE, {
      storage, listDir, ask: () => assert.fail("déjà confirmé par le système"),
    }), "/media/cle/piece.stl");
  });
});
