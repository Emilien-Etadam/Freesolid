// Règle clean-room : aucun nom de produit ni terme maison d'un éditeur de
// CAO commerciale dans le code de l'interface, ses textes ou ses
// commentaires. engine/ a son propre garde-fou (tests/test_cleanroom.py).

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";

const APP = new URL("../../app/", import.meta.url);
const FORBIDDEN = /solidworks|dassault|catia|propertymanager|featuremanager|commandmanager/i;

function files() {
  const out = ["index.html", "ribbon.json", "lang/en.json"];
  for (const name of readdirSync(APP)) if (name.endsWith(".js")) out.push(name);
  return out;
}

describe("clean-room", () => {
  it("app/ ne nomme aucun produit de CAO commerciale", () => {
    const hits = [];
    for (const name of files()) {
      const lines = readFileSync(new URL(name, APP), "utf8").split("\n");
      lines.forEach((line, i) => {
        if (FORBIDDEN.test(line)) hits.push(`${name}:${i + 1}: ${line.trim()}`);
      });
    }
    assert.deepEqual(hits, []);
  });
});
