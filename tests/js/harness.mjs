// Harnais partagé du banc Node de app/solver.js.
// Le serveur envoie toujours geos/pos de longueur 3 (null / 0 si absent).

import { createLocalSolver } from "../../app/solver.js";

export function constraint(type, geos, pos, extra = {}) {
  const [g1 = null, g2 = null, g3 = null] = geos;
  const [p1 = 0, p2 = 0, p3 = 0] = pos;
  return {
    type,
    geos: [g1, g2, g3],
    pos: [p1, p2, p3],
    value: extra.value ?? 0,
    driving: extra.driving ?? true,
  };
}

export function line(id, p1, p2) {
  return { id, type: "line", p1, p2 };
}

export function circle(id, c, r) {
  return { id, type: "circle", c, r };
}

export function arc(id, c, r, p1, p2) {
  return { id, type: "arc", c, r, p1, p2 };
}

export function sketch(entities, constraints) {
  return { entities, constraints };
}

/** Géométrie minimale : 2 droites, 2 cercles, 1 arc — couvre toute la table. */
export function fixtureEntities() {
  return [
    line(0, [0, 0], [40, 0]),
    line(1, [40, 0], [40, 30]),
    circle(2, [20, 15], 10),
    arc(3, [0, 0], 8, [8, 0], [0, 8]),
    circle(4, [50, 15], 6),
  ];
}

const GEO_TYPES = new Set(["point", "line", "circle", "arc", "arc_rules"]);

export function isConstraintPrimitive(primitive) {
  return !GEO_TYPES.has(primitive.type);
}

export function withoutDrag(primitives) {
  return primitives.filter(
    (primitive) => !String(primitive.id).startsWith("drag"));
}

export function translated(pushed) {
  return withoutDrag(pushed).filter(isConstraintPrimitive);
}

export function createMockModule(options = {}) {
  let solveResult = options.solveResult ?? 0;
  let throwOnSolve = false;
  let pushed = [];
  let solveCalls = 0;
  const store = new Map();

  const wrapper = {
    clear_data() {
      pushed = [];
      store.clear();
    },
    push_primitives_and_params(primitives) {
      pushed = primitives.map((primitive) => ({ ...primitive }));
      for (const primitive of primitives) {
        store.set(primitive.id, { ...primitive });
      }
    },
    solve() {
      solveCalls += 1;
      if (throwOnSolve) throw new Error("solve mock boom");
      return solveResult;
    },
    apply_solution() {},
    sketch_index: {
      get_primitive(id) {
        return store.get(id);
      },
    },
  };

  return {
    wrapper,
    make_gcs_wrapper: async () => wrapper,
    get pushed() {
      return pushed;
    },
    get solveCalls() {
      return solveCalls;
    },
    setSolveResult(value) {
      solveResult = value;
    },
    setThrowOnSolve(value) {
      throwOnSolve = value;
    },
    resetSolveCalls() {
      solveCalls = 0;
    },
  };
}

export async function mockSolver(options = {}) {
  const mock = createMockModule(options);
  const solver = createLocalSolver(async () => mock);
  const ok = await solver.ensureInit();
  if (!ok) throw new Error("ensureInit mock a échoué");
  return { solver, mock };
}

export async function wasmSolver() {
  const solver = createLocalSolver(
    () => import("../../app/vendor/planegcs/index.js"));
  const ok = await solver.ensureInit();
  if (!ok) throw new Error("WASM planegcs indisponible");
  return solver;
}

export function dist(a, b) {
  const dx = a[0] - b[0];
  const dy = a[1] - b[1];
  return Math.hypot(dx, dy);
}
