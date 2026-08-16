import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  arc,
  circle,
  constraint,
  fixtureEntities,
  line,
  mockSolver,
  sketch,
  translated,
  withoutDrag,
} from "./harness.mjs";

async function loadAndCapture(state, drag = { geo: 0, pos: 1, x: 1, y: 2 }) {
  const { solver, mock } = await mockSolver();
  assert.equal(solver.load(state), true, "load() devrait réussir");
  const updates = solver.drag(drag.geo, drag.pos, drag.x, drag.y);
  assert.ok(updates, "drag() devrait renvoyer des mises à jour");
  return { solver, mock, updates };
}

describe("table translate", () => {
  const entities = fixtureEntities();

  const cases = [
    {
      name: "Coincident",
      constraint: constraint("Coincident", [0, 1], [2, 1]),
      expected: [
        { id: "c0", type: "p2p_coincident", p1_id: "g0p2", p2_id: "g1p1" },
      ],
    },
    {
      name: "Horizontal ligne",
      constraint: constraint("Horizontal", [0], [0]),
      expected: [
        { id: "c0", type: "horizontal_l", l_id: "g0" },
      ],
    },
    {
      name: "Horizontal point-point",
      constraint: constraint("Horizontal", [0, 1], [1, 1]),
      expected: [
        { id: "c0", type: "horizontal_pp", p1_id: "g0p1", p2_id: "g1p1" },
      ],
    },
    {
      name: "Vertical ligne",
      constraint: constraint("Vertical", [1], [0]),
      expected: [
        { id: "c0", type: "vertical_l", l_id: "g1" },
      ],
    },
    {
      name: "Vertical point-point",
      constraint: constraint("Vertical", [0, 1], [1, 2]),
      expected: [
        { id: "c0", type: "vertical_pp", p1_id: "g0p1", p2_id: "g1p2" },
      ],
    },
    {
      name: "Parallel",
      constraint: constraint("Parallel", [0, 1], [0, 0]),
      expected: [
        { id: "c0", type: "parallel", l1_id: "g0", l2_id: "g1" },
      ],
    },
    {
      name: "Perpendicular",
      constraint: constraint("Perpendicular", [0, 1], [0, 0]),
      expected: [
        { id: "c0", type: "perpendicular_ll", l1_id: "g0", l2_id: "g1" },
      ],
    },
    {
      name: "Tangent ligne-ligne",
      constraint: constraint("Tangent", [0, 1], [0, 0]),
      expected: [
        { id: "c0a", type: "point_on_line_pl", p_id: "g1p1", l_id: "g0" },
        { id: "c0b", type: "point_on_line_pl", p_id: "g1p2", l_id: "g0" },
      ],
    },
    {
      name: "Tangent ligne-cercle",
      constraint: constraint("Tangent", [0, 2], [0, 0]),
      expected: [
        { id: "c0", type: "tangent_lc", l_id: "g0", c_id: "g2" },
      ],
    },
    {
      name: "Tangent cercle-ligne",
      constraint: constraint("Tangent", [2, 0], [0, 0]),
      expected: [
        { id: "c0", type: "tangent_lc", l_id: "g0", c_id: "g2" },
      ],
    },
    {
      name: "Tangent ligne-arc",
      constraint: constraint("Tangent", [0, 3], [0, 0]),
      expected: [
        { id: "c0", type: "tangent_la", l_id: "g0", a_id: "g3" },
      ],
    },
    {
      name: "Tangent arc-ligne",
      constraint: constraint("Tangent", [3, 0], [0, 0]),
      expected: [
        { id: "c0", type: "tangent_la", l_id: "g0", a_id: "g3" },
      ],
    },
    {
      name: "Tangent cercle-cercle",
      constraint: constraint("Tangent", [2, 4], [0, 0]),
      expected: [
        { id: "c0", type: "tangent_cc", c1_id: "g2", c2_id: "g4" },
      ],
    },
    {
      name: "Equal longueurs",
      constraint: constraint("Equal", [0, 1], [0, 0]),
      expected: [
        { id: "c0", type: "equal_length", l1_id: "g0", l2_id: "g1" },
      ],
    },
    {
      name: "Equal rayons cc",
      constraint: constraint("Equal", [2, 4], [0, 0]),
      expected: [
        { id: "c0", type: "equal_radius_cc", c1_id: "g2", c2_id: "g4" },
      ],
    },
    {
      name: "Equal rayons aa",
      constraint: constraint("Equal", [3, 3], [0, 0]),
      expected: [
        { id: "c0", type: "equal_radius_aa", a1_id: "g3", a2_id: "g3" },
      ],
    },
    {
      name: "Equal rayons ca",
      constraint: constraint("Equal", [2, 3], [0, 0]),
      expected: [
        { id: "c0", type: "equal_radius_ca", c1_id: "g2", a2_id: "g3" },
      ],
    },
    {
      name: "Equal rayons ac",
      constraint: constraint("Equal", [3, 2], [0, 0]),
      expected: [
        { id: "c0", type: "equal_radius_ca", c1_id: "g2", a2_id: "g3" },
      ],
    },
    {
      name: "Distance p2p",
      constraint: constraint("Distance", [0, 1], [1, 1], { value: 40 }),
      expected: [
        { id: "c0", type: "p2p_distance",
          p1_id: "g0p1", p2_id: "g1p1", distance: 40 },
      ],
    },
    {
      name: "Distance p2l (point vers axe X)",
      constraint: constraint("Distance", [0, -1], [1, 0], { value: 5 }),
      expected: [
        { id: "c0", type: "p2l_distance",
          p_id: "g0p1", l_id: "gx", distance: 5 },
      ],
    },
    {
      name: "Distance longueur de ligne",
      constraint: constraint("Distance", [0], [0], { value: 40 }),
      expected: [
        { id: "c0", type: "p2p_distance",
          p1_id: "g0p1", p2_id: "g0p2", distance: 40 },
      ],
    },
    {
      name: "DistanceX difference",
      constraint: constraint("DistanceX", [0, 1], [1, 1], { value: 40 }),
      expected: [
        { id: "c0", type: "difference",
          param1: { o_id: "g0p1", prop: "x" },
          param2: { o_id: "g1p1", prop: "x" },
          difference: 40 },
      ],
    },
    {
      name: "DistanceX coordinate",
      constraint: constraint("DistanceX", [0], [1], { value: 10 }),
      expected: [
        { id: "c0", type: "coordinate_x", p_id: "g0p1", x: 10 },
      ],
    },
    {
      name: "DistanceY difference",
      constraint: constraint("DistanceY", [0, 1], [1, 2], { value: 30 }),
      expected: [
        { id: "c0", type: "difference",
          param1: { o_id: "g0p1", prop: "y" },
          param2: { o_id: "g1p2", prop: "y" },
          difference: 30 },
      ],
    },
    {
      name: "DistanceY coordinate",
      constraint: constraint("DistanceY", [0], [2], { value: 7 }),
      expected: [
        { id: "c0", type: "coordinate_y", p_id: "g0p2", y: 7 },
      ],
    },
    {
      name: "Radius cercle",
      constraint: constraint("Radius", [2], [0], { value: 10 }),
      expected: [
        { id: "c0", type: "circle_radius", c_id: "g2", radius: 10 },
      ],
    },
    {
      name: "Radius arc",
      constraint: constraint("Radius", [3], [0], { value: 8 }),
      expected: [
        { id: "c0", type: "arc_radius", a_id: "g3", radius: 8 },
      ],
    },
    {
      name: "Diameter",
      constraint: constraint("Diameter", [2], [0], { value: 20 }),
      expected: [
        { id: "c0", type: "circle_diameter", c_id: "g2", diameter: 20 },
      ],
    },
    {
      name: "Angle",
      constraint: constraint("Angle", [0, 1], [0, 0], { value: 1.5708 }),
      expected: [
        { id: "c0", type: "l2l_angle_ll",
          l1_id: "g0", l2_id: "g1", angle: 1.5708 },
      ],
    },
    {
      name: "Symmetric",
      constraint: constraint("Symmetric", [0, 1, 1], [1, 2, 0]),
      expected: [
        { id: "c0", type: "p2p_symmetric_ppl",
          p1_id: "g0p1", p2_id: "g1p2", l_id: "g1" },
      ],
    },
    {
      name: "PointOnObject ligne",
      constraint: constraint("PointOnObject", [0, 1], [1, 0]),
      expected: [
        { id: "c0", type: "point_on_line_pl", p_id: "g0p1", l_id: "g1" },
      ],
    },
    {
      name: "PointOnObject cercle",
      constraint: constraint("PointOnObject", [0, 2], [1, 0]),
      expected: [
        { id: "c0", type: "point_on_circle", p_id: "g0p1", c_id: "g2" },
      ],
    },
    {
      name: "PointOnObject arc",
      constraint: constraint("PointOnObject", [0, 3], [1, 0]),
      expected: [
        { id: "c0", type: "point_on_arc", p_id: "g0p1", a_id: "g3" },
      ],
    },
  ];

  for (const item of cases) {
    it(item.name, async () => {
      const { mock } = await loadAndCapture(
        sketch(entities, [item.constraint]));
      assert.deepEqual(translated(mock.pushed), item.expected);
    });
  }

  it("Block → aucune primitive, points marqués fixed", async () => {
    const { mock } = await loadAndCapture(
      sketch(entities, [constraint("Block", [0], [0])]));
    assert.deepEqual(translated(mock.pushed), []);
    const p1 = mock.pushed.find((p) => p.id === "g0p1");
    const p2 = mock.pushed.find((p) => p.id === "g0p2");
    assert.equal(p1.fixed, true);
    assert.equal(p2.fixed, true);
    const other = mock.pushed.find((p) => p.id === "g1p1");
    assert.equal(other.fixed, false);
  });
});

describe("politique de refus", () => {
  const entities = fixtureEntities();

  it("type inconnu → load false", async () => {
    const { solver } = await mockSolver();
    assert.equal(
      solver.load(sketch(entities, [constraint("InternalAlignment", [0], [0])])),
      false);
  });

  it("coïncidence vers un point d'axe irrésolu → load false", async () => {
    const { solver } = await mockSolver();
    // (-1, 2) n'est pas l'origine : pointRef rend null → translate null
    assert.equal(
      solver.load(sketch(entities, [
        constraint("Coincident", [0, -1], [1, 2]),
      ])),
      false);
  });

  it("entité poly → load false", async () => {
    const { solver } = await mockSolver();
    assert.equal(
      solver.load(sketch(
        [{ id: 0, type: "poly", points: [[0, 0], [1, 1]] }],
        [])),
      false);
  });

  it("entité other → load false", async () => {
    const { solver } = await mockSolver();
    assert.equal(
      solver.load(sketch(
        [{ id: 0, type: "other", kind: "Part::GeomBSplineCurve" }],
        [])),
      false);
  });

  it("driving: false est ignorée (y compris type inconnu)", async () => {
    const { solver, mock } = await mockSolver();
    assert.equal(
      solver.load(sketch(entities, [
        constraint("InternalAlignment", [0], [0], { driving: false }),
        constraint("Horizontal", [0], [0]),
      ])),
      true);
    const updates = solver.drag(0, 1, 1, 2);
    assert.ok(updates);
    assert.deepEqual(translated(mock.pushed), [
      { id: "c1", type: "horizontal_l", l_id: "g0" },
    ]);
  });

  it("cote de référence Distance n'est pas poussée", async () => {
    const { mock } = await loadAndCapture(sketch(entities, [
      constraint("Distance", [0], [0], { value: 40, driving: false }),
      constraint("Horizontal", [0], [0]),
    ]));
    assert.deepEqual(translated(mock.pushed), [
      { id: "c1", type: "horizontal_l", l_id: "g0" },
    ]);
  });
});

describe("repère origin / gx / gy", () => {
  it("origin, gx, gy présents, origin et points d'axes fixed", async () => {
    const { mock } = await loadAndCapture(
      sketch([line(0, [0, 0], [10, 0])], []));
    const byId = Object.fromEntries(
      withoutDrag(mock.pushed).map((p) => [p.id, p]));
    assert.equal(byId.origin.type, "point");
    assert.equal(byId.origin.fixed, true);
    assert.deepEqual([byId.origin.x, byId.origin.y], [0, 0]);
    assert.equal(byId.gx.type, "line");
    assert.equal(byId.gy.type, "line");
    assert.equal(byId.axp1.fixed, true);
    assert.equal(byId.axp2.fixed, true);
    assert.equal(byId.ayp1.fixed, true);
    assert.equal(byId.ayp2.fixed, true);
  });

  it("(-1, 1) → origin ; -1 → gx ; -2 → gy", async () => {
    const { mock } = await loadAndCapture(sketch(
      [line(0, [0, 0], [10, 0]), line(1, [0, 0], [0, 10])],
      [
        constraint("Coincident", [0, -1], [1, 1]),
        constraint("Horizontal", [-1], [0]),
        constraint("Vertical", [-2], [0]),
      ]));
    assert.deepEqual(translated(mock.pushed), [
      { id: "c0", type: "p2p_coincident", p1_id: "g0p1", p2_id: "origin" },
      { id: "c1", type: "horizontal_l", l_id: "gx" },
      { id: "c2", type: "vertical_l", l_id: "gy" },
    ]);
  });
});

describe("drag", () => {
  const state = sketch([line(0, [0, 0], [40, 0])], []);

  it("pose coordinate_x/y temporaires sur le point tiré", async () => {
    const { mock } = await loadAndCapture(state, {
      geo: 0, pos: 2, x: 12.5, y: -4,
    });
    const dragx = mock.pushed.find((p) => p.id === "dragx");
    const dragy = mock.pushed.find((p) => p.id === "dragy");
    assert.deepEqual(dragx, {
      id: "dragx", type: "coordinate_x", p_id: "g0p2",
      x: 12.5, temporary: true, driving: true,
    });
    assert.deepEqual(dragy, {
      id: "dragy", type: "coordinate_y", p_id: "g0p2",
      y: -4, temporary: true, driving: true,
    });
  });

  it("solve() > 1 → null sans casser le modèle", async () => {
    const { solver, mock } = await mockSolver();
    assert.equal(solver.load(state), true);
    mock.setSolveResult(2);
    assert.equal(solver.drag(0, 1, 3, 4), null);
    mock.setSolveResult(0);
    mock.resetSolveCalls();
    const again = solver.drag(0, 1, 5, 6);
    assert.ok(again, "le modèle doit rester chargeable");
    assert.equal(mock.solveCalls, 1);
  });

  it("exception → modèle invalidé, drag suivant → null", async () => {
    const { solver, mock } = await mockSolver();
    assert.equal(solver.load(state), true);
    mock.setThrowOnSolve(true);
    assert.equal(solver.drag(0, 1, 3, 4), null);
    mock.setThrowOnSolve(false);
    mock.resetSolveCalls();
    assert.equal(solver.drag(0, 1, 5, 6), null);
    assert.equal(mock.solveCalls, 0);
  });

  it("point 0 (courbe entière) : p1 piloté + vecteur figé", async () => {
    const { mock } = await loadAndCapture(state, {
      geo: 0, pos: 0, x: 10, y: 5,
    });
    const dragx = mock.pushed.find((p) => p.id === "dragx");
    const dragy = mock.pushed.find((p) => p.id === "dragy");
    const dragdx = mock.pushed.find((p) => p.id === "dragdx");
    const dragdy = mock.pushed.find((p) => p.id === "dragdy");
    assert.deepEqual(dragx, {
      id: "dragx", type: "coordinate_x", p_id: "g0p1",
      x: 10, temporary: true, driving: true,
    });
    assert.deepEqual(dragy, {
      id: "dragy", type: "coordinate_y", p_id: "g0p1",
      y: 5, temporary: true, driving: true,
    });
    // Ligne [0,0]→[40,0] : vecteur (40, 0) figé, pas de coordinate_* sur p2.
    assert.equal(mock.pushed.find((p) => p.id === "dragx2"), undefined);
    assert.equal(mock.pushed.find((p) => p.id === "dragy2"), undefined);
    assert.deepEqual(dragdx, {
      id: "dragdx", type: "difference",
      param1: { o_id: "g0p1", prop: "x" },
      param2: { o_id: "g0p2", prop: "x" },
      difference: 40, temporary: true, driving: true,
    });
    assert.deepEqual(dragdy, {
      id: "dragdy", type: "difference",
      param1: { o_id: "g0p1", prop: "y" },
      param2: { o_id: "g0p2", prop: "y" },
      difference: 0, temporary: true, driving: true,
    });
  });

  it("point 0 sur cercle : translation du centre", async () => {
    const circ = sketch([circle(0, [5, 5], 3)], []);
    const { mock } = await loadAndCapture(circ, {
      geo: 0, pos: 0, x: 8, y: 9,
    });
    assert.deepEqual(mock.pushed.find((p) => p.id === "dragx"), {
      id: "dragx", type: "coordinate_x", p_id: "g0p3",
      x: 8, temporary: true, driving: true,
    });
    assert.deepEqual(mock.pushed.find((p) => p.id === "dragy"), {
      id: "dragy", type: "coordinate_y", p_id: "g0p3",
      y: 9, temporary: true, driving: true,
    });
    assert.equal(mock.pushed.find((p) => p.id === "dragx2"), undefined);
  });
});

// Garde anti-dérive : un type listé dans le prompt mais oublié du tableau
// ci-dessus ferait passer silencieusement. Arc n'est pas une contrainte
// mais on vérifie qu'un arc se charge (primitives + arc_rules).
describe("géométrie arc", () => {
  it("un arc pousse centre, extrémités, arc et arc_rules", async () => {
    const { mock } = await loadAndCapture(sketch(
      [arc(0, [0, 0], 10, [10, 0], [0, 10])],
      []));
    const ids = mock.pushed.map((p) => p.id);
    assert.ok(ids.includes("g0p3"));
    assert.ok(ids.includes("g0p1"));
    assert.ok(ids.includes("g0p2"));
    assert.equal(mock.pushed.find((p) => p.id === "g0").type, "arc");
    assert.equal(mock.pushed.find((p) => p.id === "g0rules").type, "arc_rules");
  });

  it("un cercle pousse le centre en p3", async () => {
    const { mock } = await loadAndCapture(sketch(
      [circle(0, [5, 5], 3)],
      []));
    const c = mock.pushed.find((p) => p.id === "g0p3");
    assert.equal(c.type, "point");
    assert.deepEqual([c.x, c.y], [5, 5]);
    assert.equal(mock.pushed.find((p) => p.id === "g0").type, "circle");
  });
});
