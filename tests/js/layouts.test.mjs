import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  LAYOUTS, currentPaneIndex, layoutPanes, paneRect,
} from "../../app/layouts.js";

describe("dispositions multi-fenêtres", () => {
  it("chaque disposition couvre la zone, sans recouvrement", () => {
    for (const [name, panes] of Object.entries(LAYOUTS)) {
      const area = panes.reduce((sum, p) => sum + p.w * p.h, 0);
      assert.equal(area, 1, name);
      assert.equal(panes.filter((p) => p.view === "current").length, 1, name);
    }
  });

  it("à quatre : dessus au-dessus de la face, droite à sa droite", () => {
    const panes = layoutPanes("four");
    const at = (view) => panes.find((p) => p.view === view);
    assert.equal(at("view-top").x, at("view-front").x);
    assert.ok(at("view-top").y < at("view-front").y);
    assert.equal(at("view-right").y, at("view-front").y);
    assert.ok(at("view-right").x > at("view-front").x);
    assert.equal(currentPaneIndex(panes), 1);
  });

  it("nom inconnu : une seule fenêtre, copies indépendantes", () => {
    const panes = layoutPanes("six");
    assert.equal(panes.length, 1);
    panes[0].x = 9;
    assert.equal(LAYOUTS.single[0].x, 0);
  });

  it("rectangles en pixels séparés par un trait", () => {
    const [a, b] = layoutPanes("two-v").map((p) => paneRect(p, 801, 400));
    assert.deepEqual(a, { left: 0, top: 0, width: 400, height: 400 });
    assert.equal(b.left, 402);
    assert.equal(b.left + b.width, 801);
    assert.deepEqual(paneRect(LAYOUTS.single[0], 800, 450),
      { left: 0, top: 0, width: 800, height: 450 });
  });
});
