// Forme libre par points de contrôle : la grille de pôles d'une face de
// surface s'affiche dans la vue ; chaque pôle cliqué rejoint la liste avec
// son déplacement (dx, dy, dz), corrigeable au clavier. L'aperçu montre
// les pôles déplacés ; le moteur reconstruit la surface à l'OK.

import { t } from "./i18n.js";

/** Pôles déplacés : grille + [[i, j, dx, dy, dz]…] (indices base 1). */
export function movedPoles(poles, moves) {
  const out = poles.map((row) => row.map((p) => [...p]));
  for (const [i, j, dx, dy, dz] of moves ?? []) {
    const p = out[i - 1]?.[j - 1];
    if (!p) continue;
    out[i - 1][j - 1] = [p[0] + dx, p[1] + dy, p[2] + dz];
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
  const moves = (v.moves ?? []).filter((m) => m.length === 5
    && (m[2] || m[3] || m[4]));
  if (!v.surface || !moves.length) return null;
  return { surface: v.surface.name, face: v.surface.face ?? 0,
           grid: Number(v.grid) || 6, moves };
}

export function installPoles(ctx) {
  const { THREE, camera, renderer, scene, panel, call, refresh, say } = ctx;
  const raycaster = new THREE.Raycaster();
  const group = new THREE.Group();
  group.renderOrder = 20;
  let tool = null; // { edit, values, poles, key }
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

  function draw() {
    clear();
    if (!tool?.poles) return;
    const moved = movedPoles(tool.poles, tool.values.moves);
    const flat = moved.flat().map((p) => new THREE.Vector3(...p));
    const base = new THREE.Points(new THREE.BufferGeometry().setFromPoints(
      tool.poles.flat().map((p) => new THREE.Vector3(...p))), baseMaterial);
    base.userData.poles = true;
    group.add(base);
    const segments = [];
    const nu = moved.length;
    const nv = moved[0]?.length ?? 0;
    for (let i = 0; i < nu; i++) {
      for (let j = 0; j < nv; j++) {
        if (i + 1 < nu) segments.push(flat[i * nv + j], flat[(i + 1) * nv + j]);
        if (j + 1 < nv) segments.push(flat[i * nv + j], flat[i * nv + j + 1]);
      }
    }
    group.add(new THREE.LineSegments(
      new THREE.BufferGeometry().setFromPoints(segments), netMaterial));
    const changed = (tool.values.moves ?? []).map(([i, j]) => moved[i - 1]?.[j - 1])
      .filter(Boolean).map((p) => new THREE.Vector3(...p));
    if (changed.length) {
      group.add(new THREE.Points(
        new THREE.BufferGeometry().setFromPoints(changed), movedMaterial));
    }
  }

  async function loadGrid() {
    const v = tool.values;
    const key = JSON.stringify([v.surface?.name, v.surface?.face ?? 0,
      Number(v.grid) || 6]);
    if (!v.surface || key === tool.key) return;
    tool.key = key;
    try {
      const grid = await call("surface_control_points", {
        surface: v.surface.name, face: v.surface.face ?? 0,
        grid: Number(v.grid) || 6 });
      if (!tool || tool.key !== key) return;
      tool.poles = grid.poles;
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
    setRay(event);
    if (!tool.values.surface) {
      // Premier clic : la surface à déformer (et la face cliquée).
      const hit = raycaster.intersectObjects(ctx.surfaceMeshes, false)[0];
      if (!hit) return;
      const groups = hit.object.userData.groups ?? [];
      const at = hit.faceIndex * 3;
      const g = groups.find((x) => at >= x.start && at < x.start + x.count);
      const { name, label } = hit.object.userData.surface;
      panel.restore({ surface: { kind: "surface", name, label,
                                 face: g?.faceId ?? 0 } });
      return;
    }
    if (!tool.poles) return;
    const rect = renderer.domElement.getBoundingClientRect();
    const index = nearestPole(tool.poles.flat().map((p) => {
      const v = new THREE.Vector3(...p).project(camera);
      return [(v.x + 1) / 2 * rect.width, (1 - v.y) / 2 * rect.height];
    }), [event.clientX - rect.left, event.clientY - rect.top]);
    if (index < 0) return;
    const nv = tool.poles[0].length;
    const i = Math.floor(index / nv) + 1;
    const j = (index % nv) + 1;
    const moves = [...(tool.values.moves ?? [])];
    if (moves.some((m) => m[0] === i && m[1] === j)) return;
    moves.push([i, j, 0, 0, 5]);
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
    // Réédition : la grille se lit sur la surface d'origine.
    const source = spec?.source
      ? { kind: "surface", name: spec.source, face: spec.face ?? 0 } : null;
    tool = { edit: surface, key: null, poles: null, values: {
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
        ...(surface ? [] : [{ label: t("Grille"), rows: [{ type: "number",
          key: "grid", label: t("Pôles par côté"), value: tool.values.grid,
          min: 4, step: 1 }] }]),
        { label: t("Points déplacés"), rows: [{ type: "points", key: "moves",
          value: tool.values.moves, head: 2, titles: ["dX", "dY", "dZ"],
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
          const moves = (values.moves ?? []).filter((m) => m.length === 5);
          if (moves.length) {
            refresh(call("edit_surface_freeform",
              { surface: surface.name, moves }));
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
