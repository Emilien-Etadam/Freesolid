import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { eventToNdc, ndcToScreen } from "../../app/screen.js";

const rect = { left: 10, top: 20, width: 200, height: 100 };

describe("projection écran", () => {
  it("le centre NDC tombe au centre du canevas", () => {
    assert.deepEqual(ndcToScreen(0, 0, rect), { x: 110, y: 70 });
  });

  it("le coin NDC haut-droit est le coin haut-droit du canevas", () => {
    assert.deepEqual(ndcToScreen(1, 1, rect), { x: 210, y: 20 });
    assert.deepEqual(ndcToScreen(-1, -1, rect), { x: 10, y: 120 });
  });

  it("un clic au centre du canevas est l'origine NDC", () => {
    assert.deepEqual(eventToNdc(110, 70, rect), { x: 0, y: 0 });
    assert.deepEqual(eventToNdc(10, 20, rect), { x: -1, y: 1 });
  });

  it("l'aller-retour pixel → NDC → pixel retrouve le point", () => {
    const ndc = eventToNdc(80, 90, rect);
    assert.deepEqual(ndcToScreen(ndc.x, ndc.y, rect), { x: 80, y: 90 });
  });
});
