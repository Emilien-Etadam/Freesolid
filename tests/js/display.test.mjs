import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  defaultDisplay, readDisplay, writeDisplay, displayEffects, DISPLAY_KEY,
} from "../../app/display.js";

function memory() {
  const data = new Map();
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, String(value)),
  };
}

describe("réglage d'affichage", () => {
  it("part de l'ombré + arêtes, sans plans ni origine", () => {
    assert.deepEqual(defaultDisplay(), {
      style: "shaded-edges", planes: false, origin: false,
      sketches: true, edges: true, perspective: false,
    });
    assert.deepEqual(readDisplay(null), defaultDisplay());
  });

  it("ignore un style inconnu et conserve les booléens valides", () => {
    const storage = memory();
    storage.setItem(DISPLAY_KEY, JSON.stringify({
      style: "cartoon", planes: true, origin: "oui", sketches: false,
    }));
    assert.deepEqual(readDisplay(storage), {
      style: "shaded-edges", planes: true, origin: false,
      sketches: false, edges: true, perspective: false,
    });
  });

  it("survit à un aller-retour", () => {
    const storage = memory();
    writeDisplay(storage, {
      style: "hidden", planes: true, origin: true, sketches: false, edges: false,
      perspective: true,
    });
    assert.deepEqual(readDisplay(storage).style, "hidden");
    assert.equal(readDisplay(storage).perspective, true);
    assert.equal(readDisplay(storage).planes, true);
    assert.equal(readDisplay(storage).edges, false);
  });
});

describe("effets sur la scène", () => {
  it("masque les arêtes en ombré sans arêtes", () => {
    const fx = displayEffects({ ...defaultDisplay(), style: "shaded" });
    assert.equal(fx.faces, true);
    assert.equal(fx.edges, false);
    assert.equal(fx.ghostEdges, false);
  });

  it("le filaire ne montre que les arêtes", () => {
    const fx = displayEffects({ ...defaultDisplay(), style: "wireframe" });
    assert.equal(fx.faces, false);
    assert.equal(fx.edges, true);
    assert.equal(fx.mask, false);
  });

  it("les lignes cachées estompent ce qui est derrière le solide", () => {
    const fx = displayEffects({ ...defaultDisplay(), style: "hidden" });
    assert.equal(fx.mask, true);
    assert.equal(fx.ghostEdges, true);
    assert.equal(fx.edges, true);
  });

  it("le choix « arêtes » éteint l'aperçu même en filaire", () => {
    const fx = displayEffects({
      ...defaultDisplay(), style: "wireframe", edges: false,
    });
    assert.equal(fx.edges, false);
  });
});
