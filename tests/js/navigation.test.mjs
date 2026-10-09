import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  boxMode,
  coverBounds,
  isDrag,
  middleAction,
  normalizeRect,
  pickInBox,
  readReverseWheel,
  segmentHitsRect,
  nudgeView,
  sketchLocalPoints,
  writeReverseWheel,
  zoomSpeedFor,
} from "../../app/navigation.js";

function memoryStorage() {
  const data = new Map();
  return {
    getItem: (k) => (data.has(k) ? data.get(k) : null),
    setItem: (k, v) => data.set(k, String(v)),
  };
}

describe("middleAction", () => {
  it("milieu seul : rotation", () => {
    assert.equal(middleAction({}), "rotate");
  });
  it("Ctrl + milieu : panoramique", () => {
    assert.equal(middleAction({ ctrlKey: true }), "pan");
    assert.equal(middleAction({ metaKey: true }), "pan");
  });
  it("Maj + milieu : zoom", () => {
    assert.equal(middleAction({ shiftKey: true }), "dolly");
  });
  it("rotation bloquée (esquisse) : le milieu fait du panoramique", () => {
    assert.equal(middleAction({}, { rotateLocked: true }), "pan");
  });
});

describe("sens de la molette", () => {
  it("par défaut, molette vers l'avant = zoom arrière (vitesse négative)", () => {
    assert.ok(zoomSpeedFor(false) < 0);
    assert.ok(zoomSpeedFor(true) > 0);
  });
  it("le réglage se relit", () => {
    const storage = memoryStorage();
    assert.equal(readReverseWheel(storage), false);
    writeReverseWheel(storage, true);
    assert.equal(readReverseWheel(storage), true);
  });
  it("stockage indisponible : réglage par défaut", () => {
    const broken = { getItem: () => { throw new Error("x"); } };
    assert.equal(readReverseWheel(broken), false);
    assert.equal(readReverseWheel(null), false);
  });
});

describe("sélection par cadre", () => {
  it("un petit déplacement reste un clic", () => {
    assert.equal(isDrag({ x: 0, y: 0 }, { x: 3, y: 3 }), false);
    assert.equal(isDrag({ x: 0, y: 0 }, { x: 10, y: 0 }), true);
  });
  it("gauche → droite : fenêtre ; droite → gauche : capture", () => {
    assert.equal(boxMode({ x: 10, y: 10 }, { x: 50, y: 0 }), "window");
    assert.equal(boxMode({ x: 50, y: 10 }, { x: 10, y: 40 }), "crossing");
  });
  it("normalise le rectangle quel que soit le sens", () => {
    assert.deepEqual(normalizeRect({ x: 50, y: 40 }, { x: 10, y: 0 }),
      { left: 10, right: 50, top: 0, bottom: 40 });
  });
  it("segment qui traverse le rectangle sans extrémité dedans", () => {
    const r = { left: 0, right: 10, top: 0, bottom: 10 };
    assert.equal(segmentHitsRect({ x: -5, y: 5 }, { x: 15, y: 5 }, r), true);
    assert.equal(segmentHitsRect({ x: -5, y: -5 }, { x: -1, y: 20 }, r), false);
  });
  it("fenêtre : seulement ce qui est entièrement dedans", () => {
    const r = { left: 0, right: 100, top: 0, bottom: 100 };
    const items = [
      { id: "dedans", points: [{ x: 10, y: 10 }, { x: 90, y: 90 }] },
      { id: "à cheval", points: [{ x: 50, y: 50 }, { x: 150, y: 50 }] },
      { id: "dehors", points: [{ x: 200, y: 200 }, { x: 300, y: 200 }] },
    ];
    assert.deepEqual(pickInBox(items, r, "window"), ["dedans"]);
    assert.deepEqual(pickInBox(items, r, "crossing"), ["dedans", "à cheval"]);
  });
  it("capture : un segment qui traverse suffit", () => {
    const r = { left: 0, right: 10, top: 0, bottom: 10 };
    const items = [{ id: 1, points: [{ x: -10, y: 5 }, { x: 20, y: 5 }] }];
    assert.deepEqual(pickInBox(items, r, "crossing"), [1]);
    assert.deepEqual(pickInBox(items, r, "window"), []);
  });
});

describe("cadrage d'esquisse", () => {
  it("englobe une ligne et le rayon d'un cercle", () => {
    const points = sketchLocalPoints([
      { type: "line", p1: [0, 0], p2: [40, 0] },
      { type: "circle", c: [10, 10], r: 5 },
    ]);
    assert.deepEqual(points[0], [0, 0]);
    assert.ok(points.some((p) => p[0] === 5 && p[1] === 10));
    assert.ok(points.some((p) => p[0] === 15 && p[1] === 10));
  });

  it("couvre les points et une sphère éloignée", () => {
    assert.equal(coverBounds([], []), null);
    const covered = coverBounds(
      [[0, 0, 0], [10, 0, 0]],
      [{ center: [0, 100, 0], radius: 10 }]);
    assert.ok(covered.center[1] > 40);
    assert.ok(covered.radius > 50);
  });
});

function closeTo(actual, expected, epsilon = 1e-6) {
  assert.equal(actual.length, expected.length);
  for (let i = 0; i < expected.length; i++) {
    assert.ok(Math.abs(actual[i] - expected[i]) < epsilon,
      `${actual} ≠ ${expected}`);
  }
}

describe("flèches de la vue", () => {
  const view = {
    position: [0, -10, 0],
    target: [0, 0, 0],
    up: [0, 0, 1],
    viewHeight: 100,
  };

  it("tourne de 15° autour de la verticale de l'écran", () => {
    const next = nudgeView({ ...view, key: "ArrowLeft" });
    const s = Math.sin(15 * Math.PI / 180);
    const c = Math.cos(15 * Math.PI / 180);
    closeTo(next.position, [10 * s, -10 * c, 0]);
    closeTo(next.target, [0, 0, 0]);
    closeTo(next.up, [0, 0, 1]);
  });

  it("tourne autour de l'horizontale de l'écran", () => {
    const next = nudgeView({ ...view, key: "ArrowUp" });
    assert.ok(next.position[2] > 1);
    closeTo(next.target, [0, 0, 0]);
  });

  it("Ctrl décale d'un dixième de la hauteur visible", () => {
    const next = nudgeView({ ...view, key: "ArrowLeft", ctrl: true });
    closeTo(next.position, [-10, -10, 0]);
    closeTo(next.target, [-10, 0, 0]);
    closeTo(sub(next.position, next.target), sub(view.position, view.target));
  });

  it("Alt tourne dans le plan de l'écran", () => {
    const next = nudgeView({ ...view, key: "ArrowLeft", alt: true });
    closeTo(next.position, view.position);
    assert.ok(next.up[0] < -0.2);
    assert.equal(nudgeView({ ...view, key: "ArrowUp", alt: true }), null);
  });

  it("en esquisse, seul le panoramique reste", () => {
    assert.equal(
      nudgeView({ ...view, key: "ArrowLeft" }, { rotateLocked: true }), null);
    assert.equal(
      nudgeView({ ...view, key: "ArrowLeft", alt: true }, { rotateLocked: true }),
      null);
    const next = nudgeView(
      { ...view, key: "ArrowRight", ctrl: true }, { rotateLocked: true });
    closeTo(next.position, [10, -10, 0]);
  });
});

function sub(a, b) {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}
