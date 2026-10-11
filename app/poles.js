// Forme libre par points de contrôle : les grilles de pôles de toutes les
// faces d'une surface s'affichent dans la vue ; chaque pôle cliqué rejoint
// la liste avec son déplacement (dx, dy, dz), corrigeable au clavier.
// L'aperçu montre les pôles déplacés ; le moteur reconstruit la surface à
// l'OK. Une ligne : [face, i, j, dx, dy, dz] (face base 0, i/j base 1).

import { t } from "./i18n.js";

/** Grilles avec les pôles déplacés (les grilles d'entrée restent). */
export function movedPoles(grids, moves) {
  const out = grids.map((g) => ({ ...g,
    poles: g.poles.map((row) => row.map((p) => [...p])) }));
  for (const [f, i, j, dx, dy, dz] of moves ?? []) {
    const grid = out.find((g) => g.face === f);
    const p = grid?.poles[i - 1]?.[j - 1];
    if (!p) continue;
    grid.poles[i - 1][j - 1] = [p[0] + dx, p[1] + dy, p[2] + dz];
  }
  return out;
}

/** Pôles réglés reportés d'une grille à une autre : même place relative
 *  sur leur face ; un doublon (grille plus grossière) est écarté. */
export function remapMoves(moves, oldGrids, newGrids) {
  const out = [];
  for (const [f, i, j, ...delta] of moves ?? []) {
    const before = oldGrids.find((g) => g.face === f)?.grid;
    const after = newGrids.find((g) => g.face === f)?.grid;
    if (!before || !after) continue;
    const scale = (k, from, to) =>
      1 + Math.round((k - 1) * (to - 1) / Math.max(from - 1, 1));
    const ni = scale(i, before[0], after[0]);
    const nj = scale(j, before[1], after[1]);
    if (out.some((m) => m[0] === f && m[1] === ni && m[2] === nj)) continue;
    out.push([f, ni, nj, ...delta]);
  }
  return out;
}

/** Indice du pôle (à l'écran) le plus proche du clic, -1 au-delà de
 *  `reach` pixels. */
export function nearestPole(screen, click, reach = 10) {
  let best = -1;
  let bestDist = reach;
  screen.forEach(([x, y], index) => {
    const dist = Math.hypot(x - click[0], y - click[1]);
    if (dist <= bestDist) {
      best = index;
      bestDist = dist;
    }
  });
  return best;
}

/** Paramètres de l'op, ou null s'il manque la surface ou un déplacement. */
export function polesParams(v) {
  const moves = (v.moves ?? []).filter((m) => m.length === 6
    && (m[3] || m[4] || m[5]));
  if (!v.surface || !moves.length) return null;
  return { surface: v.surface.name, grid: Number(v.grid) || 6, moves };
}

/** Nom d'une ligne : face et indices du pôle. */
export function poleName([f, i, j]) {
  return `F${f + 1} · ${i}, ${j}`;
}

export function installPoles(ctx) {
  const { THREE, camera, renderer, scene, panel, call, refresh, say } = ctx;
  const raycaster = new THREE.Raycaster();
  const group = new THREE.Group();
  group.renderOrder = 20;
  let tool = null; // { edit, values, grids, key }
  let press = null;

  const baseMaterial = new THREE.PointsMaterial({
    color: ctx.sceneTheme.curve, size: 8, sizeAttenuation: false,
    depthTest: false });
  const movedMaterial = new THREE.PointsMaterial({
    color: ctx.sceneTheme.accent, size: 10, sizeAttenuation: false,
    depthTest: false });
  const netMaterial = new THREE.LineBasicMaterial({
    color: ctx.sceneTheme.curve, transparent: true, opacity: 0.45,
    depthTest: false });

  function clear() {
    for (const child of [...group.children]) {
      child.geometry?.dispose();
      group.remove(child);
    }
  }

  /** Tous les pôles d'origine, à plat : { face, i, j, p }. */
  function flatPoles() {
    return (tool?.grids ?? []).flatMap((g) => g.poles.flatMap((row, i) =>
      row.map((p, j) => ({ face: g.face, i: i + 1, j: j + 1, p }))));
  }

  function draw() {
    clear();
    if (!tool?.grids) return;
    const vec = (p) => new THREE.Vector3(...p);
    group.add(new THREE.Points(new THREE.BufferGeometry().setFromPoints(
      flatPoles().map((x) => vec(x.p))), baseMaterial));
    const segments = [];
    const changed = [];
    const moved = movedPoles(tool.grids, tool.values.moves);
    for (const g of moved) {
      const nu = g.poles.length;
      const nv = g.poles[0]?.length ?? 0;
      for (let i = 0; i < nu; i++) {
        for (let j = 0; j < nv; j++) {
          if (i + 1 < nu) segments.push(vec(g.poles[i][j]), vec(g.poles[i + 1][j]));
          if (j + 1 < nv) segments.push(vec(g.poles[i][j]), vec(g.poles[i][j + 1]));
        }
      }
    }
    for (const [f, i, j] of tool.values.moves ?? []) {
      const p = moved.find((g) => g.face === f)?.poles[i - 1]?.[j - 1];
      if (p) changed.push(vec(p));
    }
    group.add(new THREE.LineSegments(
      new THREE.BufferGeometry().setFromPoints(segments), netMaterial));
    if (changed.length) {
      group.add(new THREE.Points(
        new THREE.BufferGeometry().setFromPoints(changed), movedMaterial));
    }
  }

  async function loadGrid() {
    const v = tool.values;
    const grid = Number(v.grid) || 6;
    const key = JSON.stringify([v.surface?.name, grid]);
    if (!v.surface || key === tool.key) return;
    tool.key = key;
    try {
      const answer = await call("surface_control_points", {
        surface: v.surface.name, grid });
      if (!tool || tool.key !== key) return;
      const before = tool.grids;
      tool.grids = answer.faces;
      if (before && (tool.values.moves ?? []).length) {
        // Grille changée : chaque pôle réglé garde sa place sur la face.
        panel.restore({ moves: remapMoves(tool.values.moves, before,
                                          tool.grids) });
      }
      draw();
      say(t("Cliquez les points de contrôle à déplacer."));
    } catch (error) {
      say(String(error.message ?? error), true);
    }
  }

  function setRay(event) {
    const rect = renderer.domElement.getBoundingClientRect();
    raycaster.setFromCamera(new THREE.Vector2(
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      -((event.clientY - rect.top) / rect.height) * 2 + 1), camera);
  }

  function onDown(event) {
    if (tool && event.button === 0) press = { x: event.clientX, y: event.clientY };
  }

  function onUp(event) {
    if (!tool || !press || event.button !== 0) return;
    const travel = Math.hypot(event.clientX - press.x, event.clientY - press.y);
    press = null;
    if (travel > 5) return;
    if (!tool.values.surface) {
      // Premier clic : la surface à déformer.
      setRay(event);
      const hit = raycaster.intersectObjects(ctx.surfaceMeshes, false)[0];
      if (!hit) return;
      const { name, label } = hit.object.userData.surface;
      panel.restore({ surface: { kind: "surface", name, label } });
      return;
    }
    if (!tool.grids) return;
    const rect = renderer.domElement.getBoundingClientRect();
    const poles = flatPoles();
    const index = nearestPole(poles.map(({ p }) => {
      const v = new THREE.Vector3(...p).project(camera);
      return [(v.x + 1) / 2 * rect.width, (1 - v.y) / 2 * rect.height];
    }), [event.clientX - rect.left, event.clientY - rect.top]);
    if (index < 0) return;
    const { face, i, j } = poles[index];
    const moves = [...(tool.values.moves ?? [])];
    if (moves.some((m) => m[0] === face && m[1] === i && m[2] === j)) return;
    moves.push([face, i, j, 0, 0, 5]);
    panel.restore({ moves });
    say(t("Point de contrôle {i}, {j} — réglez son déplacement.", { i, j }));
  }

  function stop() {
    if (!tool) return;
    tool = null;
    clear();
    group.removeFromParent();
    renderer.domElement.removeEventListener("pointerdown", onDown);
    renderer.domElement.removeEventListener("pointerup", onUp);
  }

  /** Ouvre l'outil ; `surface` (entrée d'arbre d'une forme libre à
   *  points de contrôle) le réédite. */
  function open(surface = null) {
    stop();
    const spec = surface?.surface;
    // Réédition : les grilles se lisent sur la surface d'origine.
    const source = spec?.source
      ? { kind: "surface", name: spec.source } : null;
    tool = { edit: surface, key: null, grids: null, values: {
      surface: source, grid: spec?.grid ?? 6, moves: spec?.moves ?? [] } };
    scene.add(group);
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);
    panel.open({
      icon: "surface_poles",
      title: surface ? surface.label : t("Points de contrôle"),
      autoFocus: false,
      groups: [
        { label: t("Surface"), rows: surface ? [{ type: "note", readonly: true,
          text: t("Les déplacements s'appliquent à la surface d'origine.") }]
          : [{ type: "selection", key: "surface", accepts: ["surface"],
               hint: t("Cliquez la surface à déformer") }] },
        { label: t("Grille"), rows: [{ type: "number", key: "grid",
          label: t("Pôles par côté"), value: tool.values.grid, min: 4,
          step: 1 }] },
        { label: t("Points déplacés"), rows: [{ type: "points", key: "moves",
          value: tool.values.moves, head: 3, headText: poleName,
          titles: ["dX", "dY", "dZ"],
          empty: t("Cliquez des points de contrôle dans la vue") }] },
      ],
      note: t("Chaque point de contrôle déplacé tire la surface vers lui ; "
        + "les autres restent en place."),
      onChange: (v) => {
        if (!tool) return;
        tool.values = { ...tool.values, ...v };
        if (surface) tool.values.surface = source;
        loadGrid();
        draw();
      },
      onClose: () => stop(),
      onApply: (v) => {
        const values = { ...tool?.values, ...v };
        if (surface) {
          const params = polesParams({ ...values, surface: source });
          if (params) {
            refresh(call("edit_surface_freeform", { surface: surface.name,
              moves: params.moves, grid: params.grid }));
          }
          return;
        }
        const params = polesParams(values);
        if (!params) {
          say(t("Points de contrôle : une surface et au moins un point "
            + "déplacé"), true);
          return;
        }
        refresh(call("surface_freeform", params));
      },
    });
    loadGrid();
  }

  return {
    open,
    get active() { return tool !== null; },
  };
}
