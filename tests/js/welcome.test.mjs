import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  fileTitle, rememberRecent, tipForDay, TIPS,
} from "../../app/welcome.js";

function memory() {
  const saved = new Map();
  return {
    getItem: (key) => saved.get(key) ?? null,
    setItem: (key, value) => saved.set(key, value),
  };
}

describe("accueil", () => {
  it("met le fichier ouvert en tête et oublie le doublon", () => {
    const storage = memory();
    rememberRecent(storage, "C:\\a.FCStd");
    rememberRecent(storage, "C:\\b.FCStd");
    const list = rememberRecent(storage, "C:\\a.FCStd");
    assert.deepEqual(list, ["C:\\a.FCStd", "C:\\b.FCStd"]);
  });

  it("ne garde que huit chemins", () => {
    const storage = memory();
    for (let i = 0; i < 10; i += 1) rememberRecent(storage, `f${i}.FCStd`);
    const list = rememberRecent(storage, "dernier.FCStd");
    assert.equal(list.length, 8);
    assert.equal(list[0], "dernier.FCStd");
    assert.equal(list.includes("f0.FCStd"), false);
  });

  it("choisit l'astuce selon le jour, et la même deux fois", () => {
    const day = new Date(2026, 0, 15);
    assert.equal(tipForDay(day), tipForDay(day));
    assert.ok(TIPS.includes(tipForDay(day)));
    const other = tipForDay(new Date(2026, 0, 16));
    assert.notEqual(tipForDay(day), other);
  });

  it("nomme le fichier, pas tout le chemin", () => {
    assert.equal(fileTitle("C:\\pieces\\a.FCStd"), "a.FCStd");
    assert.equal(fileTitle("/home/pc/a.FCStd"), "a.FCStd");
  });
});
