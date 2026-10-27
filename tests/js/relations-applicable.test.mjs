import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  applicableRelations, clickSelection, pickLabel, relationOrder, samePick,
} from "../../app/geom2d.js";
import { setLang } from "../../app/i18n.js";

const entities = [
  { id: 0, type: "line" }, { id: 1, type: "line" },
  { id: 2, type: "circle" }, { id: 3, type: "arc" },
  { id: 4, type: "point" }, { id: -3, type: "line", external: true },
];

describe("relations proposées selon la sélection", () => {
  it("une ligne : horizontale, verticale, fixe", () => {
    assert.deepEqual(applicableRelations([{ geo: 0 }], entities),
      ["horizontal", "vertical", "fixed"]);
    assert.deepEqual(applicableRelations([{ geo: 2 }], entities), ["fixed"]);
  });

  it("deux lignes, deux cercles, ligne et cercle", () => {
    assert.deepEqual(applicableRelations([{ geo: 0 }, { geo: 1 }], entities),
      ["parallel", "perpendicular", "equal", "collinear"]);
    assert.deepEqual(applicableRelations([{ geo: 2 }, { geo: 3 }], entities),
      ["equal", "concentric", "tangent", "coradial"]);
    assert.deepEqual(applicableRelations([{ geo: 0 }, { geo: 2 }], entities),
      ["tangent"]);
  });

  it("points : coïncidence, alignement, milieu, symétrie", () => {
    assert.deepEqual(applicableRelations(
      [{ geo: 0, point: 2 }, { geo: 1, point: 1 }], entities),
      ["coincident", "horizontal", "vertical"]);
    // L'origine (-1, point 1) compte comme un point.
    assert.deepEqual(applicableRelations(
      [{ geo: 2, point: 3 }, { geo: -1, point: 1 }], entities),
      ["coincident", "horizontal", "vertical"]);
    assert.deepEqual(applicableRelations(
      [{ geo: 2, point: 3 }, { geo: 0 }], entities), ["midpoint", "onobject"]);
    assert.deepEqual(applicableRelations(
      [{ geo: 0, point: 1 }, { geo: 2 }], entities), ["onobject"]);
    assert.deepEqual(applicableRelations(
      [{ geo: 2, point: 3 }, { geo: 0 }, { geo: 1 }], entities),
      ["intersection"]);
    assert.deepEqual(applicableRelations(
      [{ geo: 0, point: 1 }, { geo: 1, point: 1 }, { geo: 0 }], entities),
      ["symmetric"]);
    // L'axe cliqué d'abord : les points passent devant (relationOrder).
    assert.deepEqual(applicableRelations(
      [{ geo: 0 }, { geo: 0, point: 1 }, { geo: 1, point: 1 }], entities),
      ["symmetric"]);
    assert.deepEqual(applicableRelations(
      [{ geo: 0 }, { geo: 2, point: 3 }, { geo: 1 }], entities),
      ["intersection"]);
  });

  it("un point seul ne se fixe que s'il est un point d'esquisse", () => {
    // Fixer l'extrémité bloquerait toute la ligne.
    assert.deepEqual(applicableRelations([{ geo: 0, point: 1 }], entities), []);
    assert.deepEqual(applicableRelations([{ geo: -1, point: 1 }], entities), []);
    assert.deepEqual(applicableRelations([{ geo: 4, point: 1 }], entities),
      ["fixed"]);
  });
});

describe("sélection au clic", () => {
  const line = { geo: 0 }, end = { geo: 0, point: 2 }, other = { geo: 1 };

  it("un point n'est pas son entité", () => {
    assert.equal(samePick(end, { geo: 0, point: 2 }), true);
    assert.equal(samePick(end, line), false);
    assert.equal(samePick(line, { geo: 0 }), true);
  });

  it("un clic choisit seul, Ctrl ajoute ou retire", () => {
    assert.deepEqual(clickSelection([line], other, false), [other]);
    assert.deepEqual(clickSelection([line], end, true), [line, end]);
    assert.deepEqual(clickSelection([line, end], end, true), [line]);
  });

  it("le vide désélectionne, sauf avec Ctrl", () => {
    assert.deepEqual(clickSelection([line, end], null, false), []);
    assert.deepEqual(clickSelection([line, end], null, true), [line, end]);
  });

  it("l'ordre des relations met les points d'abord", () => {
    assert.deepEqual(relationOrder([line, end, other, { geo: 2, point: 3 }]),
      [end, { geo: 2, point: 3 }, line, other]);
  });

  it("nomme ce qui est choisi", () => {
    setLang("fr");
    assert.equal(pickLabel({ geo: 0 }, entities), "Ligne 1");
    assert.equal(pickLabel({ geo: 0, point: 2 }, entities), "Extrémité de Ligne 1");
    assert.equal(pickLabel({ geo: 2, point: 3 }, entities), "Centre de Cercle 3");
    assert.equal(pickLabel({ geo: 4, point: 1 }, entities), "Point 5");
    assert.equal(pickLabel({ geo: -3 }, entities), "Référence 1");
    assert.equal(pickLabel({ geo: -1, point: 1 }, entities), "Origine");
    setLang("en");
    assert.equal(pickLabel({ geo: 0, point: 1 }, entities), "Endpoint of Line 1");
    assert.equal(pickLabel({ geo: 2, point: 3 }, entities), "Center of Circle 3");
    setLang("fr");
  });
});
