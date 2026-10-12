// Outils de tracé à clics comptés : géométrie et ops (sans Three.js).
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { CLICK_TOOLS, OPEN_TOOLS, circumcircle, conicPoints, conicRho,
  ellipseThrough, endpointDirection, parabolaPoints, polesSplinePoints,
  rect3Corners, tangentArc } from "../../app/sketchtools.js";

const near = (a, b, eps = 1e-9) => Math.abs(a - b) < eps;

describe("outils de tracé : géométrie", () => {
  it("cercle par trois points, refus s'ils sont alignés", () => {
    const k = circumcircle({ x: 10, y: 0 }, { x: 0, y: 10 }, { x: -10, y: 0 });
    assert.ok(near(k.x, 0) && near(k.y, 0) && near(k.r, 10));
    assert.equal(circumcircle({ x: 0, y: 0 }, { x: 1, y: 1 }, { x: 2, y: 2 }), null);
  });

  it("arc tangent : même centre que le moteur, à gauche comme à droite", () => {
    const left = tangentArc({ x: 10, y: 0 }, { x: 1, y: 0 }, { x: 10, y: 20 });
    assert.ok(near(left.cx, 10) && near(left.cy, 10) && near(left.r, 10));
    const right = tangentArc({ x: 10, y: 0 }, { x: 1, y: 0 }, { x: 10, y: -20 });
    assert.ok(near(right.cy, -10) && right.a1 < right.a2);
    assert.equal(tangentArc({ x: 0, y: 0 }, { x: 1, y: 0 }, { x: 5, y: 0 }), null);
  });

  it("direction au bout d'une ligne et d'un arc", () => {
    const line = { type: "line", p1: [0, 0], p2: [10, 0] };
    assert.deepEqual(endpointDirection(line, 2), { x: 10, y: 0 });
    assert.deepEqual(endpointDirection(line, 1), { x: -10, y: 0 });
    const arc = { type: "arc", c: [0, 0], p1: [10, 0], p2: [0, 10] };
    assert.deepEqual(endpointDirection(arc, 2), { x: -10, y: 0 });
    assert.deepEqual(endpointDirection(arc, 1), { x: 0, y: -10 });
    assert.equal(endpointDirection({ type: "circle" }, 1), null);
  });

  it("rectangle 3 points d'équerre, parallélogramme tel quel", () => {
    const p = [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 13, y: 5 }];
    assert.deepEqual(rect3Corners(...p)[2], { x: 10, y: 5 });
    assert.deepEqual(rect3Corners(...p, true)[2], { x: 13, y: 5 });
  });

  it("ellipse par un point de la courbe : le point est bien dessus", () => {
    const e = ellipseThrough({ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 6, y: 4 });
    assert.ok(near((6 / e.rx) ** 2 + (4 / e.ry) ** 2, 1));
    assert.ok(near(e.rx * Math.cos(e.t), 6) && near(e.ry * Math.sin(e.t), 4));
  });

  it("parabole : sommet, foyer, bouts sur la courbe", () => {
    const pts = parabolaPoints({ x: 0, y: 0 }, { x: 0, y: 5 },
      { x: -10, y: 0 }, { x: 10, y: 0 }, 4);
    assert.ok(near(pts[0].y, 5) && near(pts[2].y, 0) && near(pts[4].x, 10));
  });

  it("conique : rho depuis le galbe, bouts tenus", () => {
    const p0 = { x: 0, y: 0 }, p2 = { x: 20, y: 0 }, apex = { x: 10, y: 10 };
    assert.ok(near(conicRho(p0, p2, apex, { x: 10, y: 5 }), 0.5));
    assert.equal(conicRho(p0, p2, apex, { x: 10, y: 50 }), 0.95);
    const pts = conicPoints(p0, p2, apex, 0.5, 2);
    assert.deepEqual([pts[0], pts[2]], [p0, p2]);
    assert.ok(near(pts[1].y, 5));
  });

  it("spline par pôles : passe par le premier et le dernier pôle", () => {
    const poles = [{ x: 0, y: 0 }, { x: 5, y: 10 }, { x: 10, y: 0 }, { x: 15, y: 10 }];
    const pts = polesSplinePoints(poles, 8);
    assert.deepEqual(pts[0], { x: 0, y: 0 });
    assert.ok(near(pts[8].x, 15) && near(pts[8].y, 10));
  });
});

describe("outils de tracé : ops", () => {
  const P = (x, y) => ({ x, y });

  it("chaque outil a une consigne par clic et construit son op", () => {
    for (const [name, spec] of Object.entries(CLICK_TOOLS)) {
      assert.equal(spec.prompts.length, spec.clicks, name);
    }
    assert.deepEqual(CLICK_TOOLS.centerline.build([P(0, 0), P(0, 9)]).params,
      { x1: 0, y1: 0, x2: 0, y2: 9, construction: true });
    assert.equal(CLICK_TOOLS.circle3.build([P(0, 0), P(1, 1), P(2, 2)]).error,
      "Cercle : les trois points sont alignés");
    const slot = CLICK_TOOLS.slotc.build([P(0, 0), P(10, 0), P(10, 3)]);
    assert.deepEqual(slot.params, { x1: -10, y1: 0, x2: 10, y2: 0, width: 6 });
    const arc = CLICK_TOOLS.arcslot.build([P(0, 0), P(20, 0), P(0, 20), P(22, 0)]);
    assert.equal(arc.op, "sketch_add_arc_slot");
    assert.ok(near(arc.params.width, 4) && near(arc.params.a2, Math.PI / 2));
    const tarc = CLICK_TOOLS.tarc.build([{ x: 1, y: 2, geo: 3, point: 2 }, P(5, 5)]);
    assert.deepEqual(tarc.params, { geo: 3, point: 2, x: 5, y: 5 });
  });

  it("les aperçus suivent le curseur dès le premier clic", () => {
    for (const [name, spec] of Object.entries(CLICK_TOOLS)) {
      if (spec.clicks < 2) continue;
      const first = name === "tarc"
        ? { x: 0, y: 0, dir: { x: 1, y: 0 } } : P(0, 0);
      assert.ok(spec.preview([first], P(7, 3)).length >= 2, name);
    }
    assert.ok(OPEN_TOOLS.splinecp.preview([P(0, 0), P(5, 5)], P(10, 0)).length > 3);
  });
});

describe("aides : grille et peigne", () => {
  it("le pas de grille est rond et suit la vue", async () => {
    const { gridStep } = await import("../../app/sketchtools.js");
    assert.equal(gridStep(400), 10);
    assert.equal(gridStep(40), 1);
    assert.equal(gridStep(80), 2);
    assert.equal(gridStep(200), 5);
  });

  it("peigne : nul sur une droite, dents égales sur un cercle", async () => {
    const { curvatureComb } = await import("../../app/sketchtools.js");
    assert.deepEqual(curvatureComb([[[0, 0], [1, 0], [2, 0]]], 5), []);
    const circle = Array.from({ length: 13 }, (_, i) =>
      [10 * Math.cos(i * Math.PI / 6), 10 * Math.sin(i * Math.PI / 6)]);
    const teeth = curvatureComb([circle], 5);
    const lengths = teeth.map(([p, q]) => Math.hypot(q[0] - p[0], q[1] - p[1]));
    assert.ok(lengths.every((l) => Math.abs(l - 5) < 1e-9));
  });
});

describe("variantes : rectangle par le centre, polygone inscrit, rainure 3 points", () => {
  it("rectangle 3 points par le centre : symétrique autour du centre", async () => {
    const { centerRect3Points, rect3Corners: corners } =
      await import("../../app/sketchtools.js");
    const k = centerRect3Points({ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 3, y: 4 });
    const q = corners(...k);
    const cx = q.reduce((s, p) => s + p.x, 0) / 4;
    const cy = q.reduce((s, p) => s + p.y, 0) / 4;
    assert.ok(Math.abs(cx) < 1e-9 && Math.abs(cy) < 1e-9);
    assert.deepEqual(q.map((p) => [Math.abs(p.x), Math.abs(p.y)]),
      [[10, 4], [10, 4], [10, 4], [10, 4]]);
  });

  it("polygone inscrit : l'apothème est la distance au clic", async () => {
    const { polygonVertexFromApothem } = await import("../../app/sketchtools.js");
    const v = polygonVertexFromApothem({ x: 0, y: 0 }, { x: 10, y: 0 }, 4);
    assert.ok(Math.abs(Math.hypot(v.x, v.y) - 10 * Math.SQRT2) < 1e-9);
  });

  it("rainure en arc 3 points : même op que la rainure par centre", () => {
    const P = (x, y) => ({ x, y });
    const out = CLICK_TOOLS.arcslot3.build([P(20, 0), P(0, 20),
      P(20 * Math.SQRT1_2, 20 * Math.SQRT1_2), P(22, 0)]);
    assert.equal(out.op, "sketch_add_arc_slot");
    assert.ok(Math.abs(out.params.r - 20) < 1e-9
      && Math.abs(out.params.width - 4) < 1e-9);
  });
});

describe("calques d'esquisse", () => {
  it("masque les entités des calques invisibles", async () => {
    const { hiddenByLayers } = await import("../../app/sketchtools.js");
    const entities = [{ id: 0, layer: "Axes" }, { id: 1, layer: "Cotes" },
      { id: 2 }];
    const hidden = hiddenByLayers(entities,
      [{ name: "Axes", visible: false }, { name: "Cotes", visible: true }]);
    assert.deepEqual([...hidden], [0]);
  });

  it("le panneau rend la liste : renommage noté, suppression, ajout", async () => {
    const { layersFromPanel } = await import("../../app/sketchtools.js");
    const layers = [{ name: "A", color: "", visible: true },
      { name: "B", color: "#e05252", visible: true }];
    assert.deepEqual(layersFromPanel({ name0: "Axes", delete1: true,
      newName: "C" }, layers), [
      { name: "Axes", color: "", visible: true, rename: "A" },
      { name: "C", color: "", visible: true }]);
    assert.equal(layersFromPanel({ name0: "B" }, layers), null);
  });
});
