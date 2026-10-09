import assert from "node:assert/strict";
import { describe, it } from "node:test";
import LAYOUT from "../../app/ribbon.json" with { type: "json" };
import {
  insertionItems, menuBarModel, reduceMenu,
} from "../../app/menubar.js";

describe("parcours des menus", () => {
  it("s'ouvre au clic et se ferme au second clic", () => {
    assert.equal(reduceMenu(null, { type: "toggle", id: "file" }), "file");
    assert.equal(reduceMenu("file", { type: "toggle", id: "file" }), null);
  });

  it("passe d'un menu à l'autre au survol seulement s'il est déjà ouvert", () => {
    assert.equal(reduceMenu(null, { type: "hover", id: "edit" }), null);
    assert.equal(reduceMenu("file", { type: "hover", id: "edit" }), "edit");
  });

  it("Échap ou un clic à côté ferme", () => {
    assert.equal(reduceMenu("view", { type: "close" }), null);
    assert.equal(reduceMenu(null, { type: "close" }), null);
  });
});

describe("contenu", () => {
  const menus = menuBarModel(LAYOUT);
  const byId = Object.fromEntries(menus.map((menu) => [menu.id, menu]));

  it("pose les six menus dans l'ordre", () => {
    assert.deepEqual(menus.map((menu) => menu.id),
      ["file", "edit", "view", "insert", "tools", "help"]);
  });

  it("affiche le raccourci quand la commande en a un", () => {
    const undo = byId.edit.items.find((entry) => entry.click === "btn-undo");
    const fit = byId.view.items.find((entry) => entry.click === "view-fit");
    const orient = byId.view.items.find((entry) => entry.action === "orient");
    assert.equal(undo.shortcut, "Ctrl+Z");
    assert.equal(fit.shortcut, "F");
    assert.equal(orient.shortcut, "Espace");
  });

  it("Insertion reprend les groupes du ruban, sans les séparateurs", () => {
    const labels = insertionItems(LAYOUT);
    const headings = labels.filter((entry) => entry.heading).map((entry) => entry.heading);
    assert.ok(headings.includes("Habillage"));
    assert.ok(headings.includes("Modélisation"));
    const fillet = labels.find((entry) => entry.click === "btn-fillet");
    const pad = labels.find((entry) => entry.click === "btn-pad");
    assert.equal(fillet.label, "Congé");
    assert.equal(pad.label, "Extrusion");
    assert.equal(labels.some((entry) => entry.sep && entry.click), false);
    const habillage = labels.indexOf(labels.find((entry) => entry.heading === "Habillage"));
    assert.ok(habillage < labels.indexOf(fillet));
    assert.ok(labels.some((entry) => entry.click === "btn-surf-sew"));
  });

  it("Fichier, Outils et Aide déclenchent les boutons existants", () => {
    assert.deepEqual(byId.file.items.map((entry) => entry.click), [
      "btn-new", "btn-open", "btn-save", "btn-export", "btn-drawing",
    ]);
    assert.equal(byId.tools.items.find((entry) => entry.label === "Mesurer").click,
      "btn-measure");
    assert.equal(byId.help.items.find((entry) => entry.label === "À propos").click,
      "btn-settings");
    assert.equal(byId.help.items.find((entry) => entry.action === "report").label,
      "Signaler un problème");
  });
});
