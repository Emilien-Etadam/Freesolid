// Cube d'orientation (en haut à droite de la vue) et trièdre (en bas à
// gauche). Le cube est en CSS 3D : chaque face reçoit la rotation de la
// caméra, les faces de dos se cachent ; un clic sur une face cadre la vue
// standard. Le trièdre projette les trois axes du monde. Les calculs sont
// purs (cubeFaceMatrices, triadAxes) ; l'affichage suit la caméra image
// par image, seulement quand elle a bougé.

import { t } from "./i18n.js";
import { VIEWS } from "./viewcube.js";

// Repère de chaque face, vue de face : u vers la droite, v vers le bas
// de l'écran, w la normale (vers la caméra de cette vue). Mêmes vues que
// VIEWS (Z en haut, la face avant regarde -Y).
export const CUBE_FACES = [
  { view: "view-front", label: "Face", u: [1, 0, 0], v: [0, 0, -1], w: [0, -1, 0] },
  { view: "view-back", label: "Arrière", u: [-1, 0, 0], v: [0, 0, -1], w: [0, 1, 0] },
  { view: "view-right", label: "Droite", u: [0, 1, 0], v: [0, 0, -1], w: [1, 0, 0] },
  { view: "view-left", label: "Gauche", u: [0, -1, 0], v: [0, 0, -1], w: [-1, 0, 0] },
  { view: "view-top", label: "Dessus", u: [1, 0, 0], v: [0, -1, 0], w: [0, 0, 1] },
  { view: "view-bottom", label: "Dessous", u: [1, 0, 0], v: [0, 1, 0], w: [0, 0, -1] },
];

/** Rotation monde → écran CSS (x à droite, y vers le bas, z vers
 *  l'observateur) tirée de la matrice de vue three.js (colonnes). */
export function cssRotation(viewElements) {
  const e = viewElements;
  const row = (r) => [e[r], e[4 + r], e[8 + r]];
  const [x, y, z] = [row(0), row(1), row(2)];
  return [x, y.map((c) => -c), z];
}

const apply = (rot, v) => rot.map((row) => row[0] * v[0] + row[1] * v[1] + row[2] * v[2]);

/** matrix3d de chaque face (cube d'arête `size`), et si elle fait face à
 *  l'observateur. */
export function cubeFaceMatrices(viewElements, size) {
  const rot = cssRotation(viewElements);
  return CUBE_FACES.map((face) => {
    const u = apply(rot, face.u);
    const v = apply(rot, face.v);
    const w = apply(rot, face.w);
    const half = size / 2;
    const m = [u[0], u[1], u[2], 0, v[0], v[1], v[2], 0, w[0], w[1], w[2], 0,
               w[0] * half, w[1] * half, w[2] * half, 1];
    const fmt = (n) => (Math.abs(n) < 1e-9 ? 0 : Math.round(n * 1e6) / 1e6);
    return { ...face, matrix: `matrix3d(${m.map(fmt).join(",")})`, facing: w[2] > 1e-6 };
  });
}

/** Axes X, Y, Z à l'écran : direction 2D (y vers le bas) et profondeur,
 *  les plus lointains d'abord (pour les dessiner dessous). */
export function triadAxes(viewElements) {
  const rot = cssRotation(viewElements);
  return [["X", [1, 0, 0]], ["Y", [0, 1, 0]], ["Z", [0, 0, 1]]]
    .map(([name, axis]) => {
      const [x, y, z] = apply(rot, axis);
      return { name, x, y, depth: z };
    })
    .sort((a, b) => a.depth - b.depth);
}

export function installOrientCube(ctx) {
  const host = document.getElementById("viewport");
  const { camera } = ctx;
  if (!host || !camera) return null;
  const SIZE = 56;

  const cube = document.createElement("div");
  cube.id = "orient-cube";
  cube.setAttribute("role", "group");
  cube.setAttribute("aria-label", t("Cube d'orientation"));
  const faces = CUBE_FACES.map((face) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "cube-face";
    btn.dataset.view = face.view;
    btn.textContent = t(face.label);
    btn.title = t("Vue {v}", { v: t(face.label) });
    btn.addEventListener("click", () => {
      const view = VIEWS[face.view];
      ctx.frameView?.(view.direction, view.up);
    });
    cube.appendChild(btn);
    return btn;
  });
  const home = document.createElement("button");
  home.type = "button";
  home.className = "cube-home";
  home.title = t("Vue isométrique (Ctrl+7)");
  home.setAttribute("aria-label", t("Vue isométrique"));
  home.innerHTML = '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M8 2 14 5.5v5L8 14 2 10.5v-5z M2 5.5 8 9l6-3.5M8 9v5" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>';
  home.addEventListener("click", () => {
    const view = VIEWS["view-iso"];
    ctx.frameView?.(view.direction, view.up);
  });
  cube.appendChild(home);
  host.appendChild(cube);

  const triad = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  triad.id = "triad";
  triad.setAttribute("viewBox", "-32 -32 64 64");
  triad.setAttribute("aria-hidden", "true");
  host.appendChild(triad);

  let last = "";
  function update() {
    camera.updateMatrixWorld();
    const view = camera.matrixWorldInverse.elements;
    const key = Array.from(view.slice(0, 11), (n) => n.toFixed(4)).join(",");
    if (key === last) return;
    last = key;
    cubeFaceMatrices(view, SIZE).forEach((face, i) => {
      faces[i].style.transform = face.matrix;
      faces[i].classList.toggle("back", !face.facing);
    });
    const colors = { X: "var(--scene-axis-x)", Y: "var(--scene-axis-y)",
                     Z: "var(--scene-axis-z)" };
    triad.replaceChildren(...triadAxes(view).flatMap((axis) => {
      const ns = "http://www.w3.org/2000/svg";
      const line = document.createElementNS(ns, "line");
      line.setAttribute("x1", "0");
      line.setAttribute("y1", "0");
      line.setAttribute("x2", String(axis.x * 20));
      line.setAttribute("y2", String(axis.y * 20));
      line.setAttribute("class", "axis-" + axis.name.toLowerCase());
      line.style.stroke = colors[axis.name];
      const label = document.createElementNS(ns, "text");
      label.setAttribute("x", String(axis.x * 27));
      label.setAttribute("y", String(axis.y * 27 + 3.5));
      label.setAttribute("class", "axis-label");
      label.style.fill = colors[axis.name];
      label.textContent = axis.name;
      return [line, label];
    }));
  }
  (function loop() {
    update();
    requestAnimationFrame(loop);
  })();
  return { update };
}
