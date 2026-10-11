import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  VIEW_KEYS, VIEWS, orthoZoomFor, placeOrientBox,
} from "../../app/viewcube.js";

describe("orthoZoomFor", () => {
  it("cadre une sphère avec la marge, sans dépasser la plus petite dimension", () => {
    const square = orthoZoomFor(100, 800, 800, 200);
    assert.equal(square, 200 / (2 * 100 * 1.25));
    const wide = orthoZoomFor(100, 1600, 800, 200);
    assert.equal(wide, square);
  });

  it("ne divise pas par zéro si la vue n'a pas encore de taille", () => {
    assert.ok(orthoZoomFor(10, 0, 0, 200) > 0);
  });
});

describe("placeOrientBox", () => {
  const host = { left: 100, top: 80, width: 800, height: 600 };
  const box = { width: 200, height: 160 };

  it("centre la boîte sur le pointeur", () => {
    const place = placeOrientBox({ x: 500, y: 400 }, host, box);
    assert.equal(place.left, 500 - 100 - 100);
    assert.equal(place.top, 400 - 80 - 80);
  });

  it("reste dans la fenêtre près des bords", () => {
    const place = placeOrientBox({ x: 100, y: 80 }, host, box);
    assert.equal(place.left, 4);
    assert.equal(place.top, 4);
    const far = placeOrientBox({ x: 2000, y: 2000 }, host, box);
    assert.equal(far.left, 800 - 200 - 4);
    assert.equal(far.top, 600 - 160 - 4);
  });
});

describe("vues standard", () => {
  it("relie Ctrl+1 à Ctrl+7 aux vues, face en tête", () => {
    assert.equal(VIEW_KEYS[1], "view-front");
    assert.equal(VIEW_KEYS[7], "view-iso");
    assert.deepEqual(VIEWS["view-front"].direction, [0, -1, 0]);
    assert.equal(VIEWS["view-fit"].direction, null);
  });
});
