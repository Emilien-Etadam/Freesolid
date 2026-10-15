import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { cubeFaceMatrices, triadAxes, CUBE_FACES } from "../../app/orientcube.js";
import { VIEWS } from "../../app/viewcube.js";

// Matrice de vue (colonnes, comme three.js) d'une caméra regardant le long
// de -direction avec `up` : lignes = droite, haut, arrière.
function viewMatrix(direction, up) {
  const norm = (v) => { const l = Math.hypot(...v); return v.map((c) => c / l); };
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
                           a[0] * b[1] - a[1] * b[0]];
  const z = norm(direction);
  const x = norm(cross(up, z));
  const y = cross(z, x);
  return [x[0], y[0], z[0], 0, x[1], y[1], z[1], 0, x[2], y[2], z[2], 0, 0, 0, 0, 1];
}

describe("cube d'orientation", () => {
  it("chaque vue standard montre sa face, de face", () => {
    for (const face of CUBE_FACES) {
      const { direction, up } = VIEWS[face.view];
      const faces = cubeFaceMatrices(viewMatrix(direction, up), 56);
      const mine = faces.find((f) => f.view === face.view);
      assert.ok(mine.facing, face.view);
      assert.equal(mine.matrix, "matrix3d(1,0,0,0,0,1,0,0,0,0,1,0,0,0,28,1)", face.view);
      assert.equal(faces.filter((f) => f.facing).length, 1, face.view);
    }
  });

  it("en iso, trois faces visibles : face, droite, dessus", () => {
    const { direction, up } = VIEWS["view-iso"];
    const visible = cubeFaceMatrices(viewMatrix(direction, up), 56)
      .filter((f) => f.facing).map((f) => f.view).sort();
    assert.deepEqual(visible, ["view-front", "view-right", "view-top"]);
  });

  it("trièdre : Z vers le haut de l'écran en vue de face", () => {
    const { direction, up } = VIEWS["view-front"];
    const axes = triadAxes(viewMatrix(direction, up));
    const z = axes.find((a) => a.name === "Z");
    const x = axes.find((a) => a.name === "X");
    assert.ok(z.y < -0.99 && Math.abs(z.x) < 1e-9);
    assert.ok(x.x > 0.99);
    assert.equal(axes[0].name, "Y"); // l'axe qui s'éloigne, dessiné dessous
  });
});
