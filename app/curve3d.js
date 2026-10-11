// Spline 3D : l'esquisse 3D de FreeSolid. Chaque clic pose un point — sur
// la pièce, une surface ou une courbe (les sommets et centres tout
// proches aimantent), ou dans le vide sur le plan de clic, qui passe par
// le dernier point posé. Tab change de plan. Les coordonnées se
// corrigent dans la liste du panneau ; la courbe se réédite depuis l'arbre.

import { t } from "./i18n.js";
import { snapFacePoint } from "./pointsnap.js";

export const CLICK_PLANES = ["XY", "XZ", "YZ"];

const NORMALS = { XY: [0, 0, 1], XZ: [0, 1, 0], YZ: [1, 0, 0] };

/** Plan de clic : normale du plan choisi, passant par `anchor`. */
export function clickPlane(key, anchor = [0, 0, 0]) {
  return { normal: NORMALS[key] ?? NORMALS.XY, point: anchor };
}

/** Intersection d'un rayon et d'un plan, ou null (rayon parallèle, ou
 *  plan derrière la caméra). */
export function rayPlane(origin, direction, plane) {
  const [nx, ny, nz] = plane.normal;
  const denom = direction[0] * nx + direction[1] * ny + direction[2] * nz;
  if (Math.abs(denom) < 1e-9) return null;
  const tt = ((plane.point[0] - origin[0]) * nx
    + (plane.point[1] - origin[1]) * ny
    + (plane.point[2] - origin[2]) * nz) / denom;
  if (tt < 0) return null;
  return [origin[0] + tt * direction[0], origin[1] + tt * direction[1],
          origin[2] + tt * direction[2]];
}

/** Le point ramené sur l'axe X, Y ou Z qui passe par `last` — celui où
 *  le segment avance le plus (Maj : segment parallèle à un axe). */
export function alongAxis(last, point) {
  const delta = point.map((v, i) => v - last[i]);
  const axis = delta.reduce((best, v, i, all) =>
    (Math.abs(v) > Math.abs(all[best]) ? i : best), 0);
  return { point: last.map((v, i) => (i === axis ? point[i] : v)),
           axis: "XYZ"[axis] };
}

/** Applique les règles des segments (axe imposé, longueur cotée) en
 *  chaîne : le segment i garde sa direction, ramenée sur son axe, prend
 *  sa longueur, et la suite de la courbe suit en bloc. Même calcul que le
 *  moteur (solve_curve_rules). */
export function solveRules(points, rules, fixed = []) {
  const pts = (points ?? []).map((p) => p.slice(0, 3).map(Number));
  const locked = new Set(fixed);
  (rules ?? []).forEach((rule, i) => {
    if (!rule || i + 1 >= pts.length || locked.has(i + 1)) return;
    const [a, b] = [pts[i], pts[i + 1]];
    let d = b.map((v, k) => v - a[k]);
    const k = "XYZ".indexOf(rule.axis ?? "");
    if (rule.axis && k >= 0) {
      d = d.map((v, n) => (n === k ? v : 0));
      if (Math.abs(d[k]) < 1e-9) d[k] = 1;
    } else if (rule.angle != null && i >= 1) {
      d = turnToAngle(a.map((v, n) => v - pts[i - 1][n]), d, rule.angle);
    }
    if (rule.length != null && rule.length > 0) {
      const size = Math.hypot(...d);
      if (size > 1e-9) d = d.map((v) => (v * rule.length) / size);
    }
    const shift = a.map((v, n) => v + d[n] - b[n]);
    for (let j = i + 1; j < pts.length; j++) {
      if (locked.has(j)) break; // un point lié arrête la propagation
      pts[j] = pts[j].map((v, n) => v + shift[n]);
    }
  });
  return relaxRules(pts, rules ?? [], locked);
}

/** Passe globale par relaxation (comme le moteur) : chaque règle déplace
 *  les extrémités libres de son segment jusqu'à ce que toutes tiennent.
 *  Sans point lié, le premier sert d'ancre. Rend le meilleur résultat —
 *  le moteur refuse à l'OK des règles incompatibles. */
export function relaxRules(pts, rules, locked = new Set(), rounds = 4000) {
  const active = (r) => r && ["axis", "length", "angle"]
    .some((k) => r[k] != null && r[k] !== "");
  if (pts.length < 2 || !rules.some(active)) return pts;
  const fixed = locked.size ? locked : new Set([0]);
  const free = (i) => (fixed.has(i) ? 0 : 1);
  const diff = (i) => pts[i + 1].map((v, k) => v - pts[i][k]);
  const move = (i, j, delta) => {
    const total = free(i) + free(j);
    if (!total) return;
    pts[i] = pts[i].map((v, k) => v - (delta[k] * free(i)) / total);
    pts[j] = pts[j].map((v, k) => v + (delta[k] * free(j)) / total);
  };
  const want = (i, rule) => {
    const d = diff(i);
    const k = "XYZ".indexOf(rule.axis ?? "");
    if (rule.axis && k >= 0) return d.map((v, n) => (n === k ? v : 0));
    if (rule.angle != null && rule.angle !== "" && i >= 1) {
      return turnToAngle(pts[i].map((v, n) => v - pts[i - 1][n]), d,
        Number(rule.angle));
    }
    return d;
  };
  const residual = () => rules.reduce((worst, rule, i) => {
    if (!rule || i + 1 >= pts.length) return worst;
    const d = diff(i);
    const w = want(i, rule);
    let r = Math.hypot(...w.map((v, k) => v - d[k]));
    if (rule.length != null && rule.length !== "") {
      r = Math.max(r, Math.abs(Math.hypot(...d) - Number(rule.length)));
    }
    return Math.max(worst, r);
  }, 0);
  for (let round = 0; round < rounds && residual() > 1e-7; round++) {
    rules.forEach((rule, i) => {
      if (!rule || i + 1 >= pts.length) return;
      const d = diff(i);
      const w = want(i, rule);
      move(i, i + 1, w.map((v, k) => v - d[k]));
      if (rule.length != null && rule.length !== "") {
        const e = diff(i);
        const size = Math.hypot(...e);
        if (size > 1e-12) {
          const grow = (Number(rule.length) - size) / size;
          move(i, i + 1, e.map((v) => v * grow));
        }
      }
    });
  }
  return pts;
}

/** `d` tourné dans le plan (prev, d) pour faire `degrees` avec `prev`,
 *  longueur gardée — même calcul que le moteur. */
export function turnToAngle(prev, d, degrees) {
  const norm = (v) => Math.hypot(...v);
  const size = norm(d);
  const base = norm(prev);
  if (size < 1e-9 || base < 1e-9) return d;
  const e1 = prev.map((c) => c / base);
  const dot = (u, v) => u.reduce((s, c, k) => s + c * v[k], 0);
  let side = d.map((c, k) => c - dot(d, e1) * e1[k]);
  if (norm(side) < 1e-9) {
    const helper = Math.abs(e1[2]) < 0.9 ? [0, 0, 1] : [1, 0, 0];
    side = helper.map((c, k) => c - dot(helper, e1) * e1[k]);
  }
  const e2 = side.map((c) => c / norm(side));
  const theta = (degrees * Math.PI) / 180;
  return e1.map((c, k) =>
    size * (Math.cos(theta) * c + Math.sin(theta) * e2[k]));
}

/** Indices des points liés (pour le solveur). */
function linkedIndices(links) {
  return (links ?? []).flatMap((l, i) => (l ? [i] : []));
}

function samePoints(a, b) {
  return a.length === b.length && a.every((p, i) =>
    p.every((v, k) => Math.abs(v - b[i][k]) < 1e-9));
}

/** Plan suivant (Tab). */
export function nextPlane(key) {
  const i = CLICK_PLANES.indexOf(key);
  return CLICK_PLANES[(i + 1) % CLICK_PLANES.length];
}

/** Ce qui manque pour créer la courbe, ou null. */
export function curveProblem(points, closed) {
  if ((points?.length ?? 0) < 2) return "Spline 3D : au moins deux points";
  if (closed && points.length < 3) {
    return "Spline 3D : une courbe fermée demande trois points";
  }
  for (let i = 1; i < points.length; i++) {
    const [a, b] = [points[i - 1], points[i]];
    if (Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]) < 1e-6) {
      return "Spline 3D : deux points consécutifs sont confondus";
    }
  }
  return null;
}

const PLANE_LABELS = {
  XY: "Plan de dessus", XZ: "Plan de face", YZ: "Plan de droite",
};

export function installCurve3d(ctx) {
  const { THREE, camera, renderer, scene, panel, call, refresh, say } = ctx;
  const raycaster = new THREE.Raycaster();
  const preview = new THREE.Group();
  preview.renderOrder = 20;
  let tool = null; // { curve, values }
  let press = null;
  let rubber = null; // point sous le curseur (aperçu du segment suivant)
  // Tracé exact rendu par le moteur (curve3d_preview) ; en attendant sa
  // réponse, une approximation locale.
  let exact = { key: null, points: null };
  let exactTimer = null;

  const lineMaterial = new THREE.LineBasicMaterial({
    color: ctx.sceneTheme.curve, depthTest: false });
  const rubberMaterial = new THREE.LineDashedMaterial({
    color: ctx.sceneTheme.curve, dashSize: 2, gapSize: 1.5, depthTest: false });
  const dotMaterial = new THREE.PointsMaterial({
    color: ctx.sceneTheme.accent, size: 7, sizeAttenuation: false,
    depthTest: false });

  function points() { return tool?.values.points ?? []; }

  function clearPreview() {
    for (const child of [...preview.children]) {
      child.geometry?.dispose();
      preview.remove(child);
    }
  }

  function drawPreview() {
    clearPreview();
    const list = points().map((p) => new THREE.Vector3(...p));
    if (!list.length) return;
    const { spline, closed } = tool.values;
    let path = list;
    if (exact.key === previewKey() && exact.points) {
      path = exact.points.map((p) => new THREE.Vector3(...p));
    } else if (spline && list.length >= 3) {
      const curve = new THREE.CatmullRomCurve3(list, !!closed, "centripetal");
      path = curve.getPoints(Math.max(32, list.length * 24));
    } else if (closed && list.length >= 3) {
      path = [...list, list[0]];
    }
    if (path.length >= 2) {
      preview.add(new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(path), lineMaterial));
    }
    preview.add(new THREE.Points(
      new THREE.BufferGeometry().setFromPoints(list), dotMaterial));
    if (rubber) {
      const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(
        [list[list.length - 1], new THREE.Vector3(...rubber)]), rubberMaterial);
      line.computeLineDistances();
      preview.add(line);
    }
  }

  function previewKey() {
    const v = tool?.values ?? {};
    return JSON.stringify([v.points, !!v.spline, !!v.closed]);
  }

  function requestExact() {
    clearTimeout(exactTimer);
    if (curveProblem(points(), tool.values.closed)) return;
    const key = previewKey();
    if (exact.key === key) return;
    const { spline, closed } = tool.values;
    exactTimer = setTimeout(async () => {
      try {
        const result = await call("curve3d_preview",
          { points: points(), spline: !!spline, closed: !!closed });
        if (!tool || previewKey() !== key) return;
        exact = { key, points: result.points };
        drawPreview();
      } catch {
        // L'approximation reste affichée ; l'erreur viendra à l'OK.
      }
    }, 60);
  }

  function setRay(event) {
    const rect = renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      -((event.clientY - rect.top) / rect.height) * 2 + 1);
    raycaster.setFromCamera(ndc, camera);
  }

  function project(point) {
    const v = new THREE.Vector3(point.x, point.y, point.z).project(camera);
    const rect = renderer.domElement.getBoundingClientRect();
    return { x: rect.left + (v.x + 1) / 2 * rect.width,
             y: rect.top + (1 - v.y) / 2 * rect.height };
  }

  /** Point visé : sur la géométrie (aimanté), sinon sur le plan de clic. */
  function aimedPoint(event) {
    setRay(event);
    const { radius } = ctx.partMesh ? ctx.partCenterRadius() : { radius: 50 };
    raycaster.params.Line.threshold = Math.max(radius * 0.01, 0.3);
    const targets = [ctx.partMesh, ctx.partEdges, ...ctx.surfaceMeshes,
      ...ctx.boundaryLines].filter(Boolean);
    const hit = raycaster.intersectObjects(targets, false)[0];
    const snaps = [...(ctx.edgeSnaps ?? []), ...(ctx.boundarySnaps ?? []),
      ...points().map(([x, y, z]) => ({ x, y, z, kind: "vertex" }))];
    if (hit) {
      const snapped = snapFacePoint(
        { x: hit.point.x, y: hit.point.y, z: hit.point.z }, null, snaps,
        project);
      return { point: [snapped.x, snapped.y, snapped.z],
               snapped: snapped.snapped, onGeometry: true };
    }
    const list = points();
    const plane = clickPlane(tool.values.plane,
      list.length ? list[list.length - 1] : [0, 0, 0]);
    const { origin, direction } = raycaster.ray;
    const point = rayPlane([origin.x, origin.y, origin.z],
      [direction.x, direction.y, direction.z], plane);
    if (!point) return null;
    // Un sommet tout proche à l'écran gagne aussi dans le vide.
    const snapped = snapFacePoint({ x: point[0], y: point[1], z: point[2] },
      null, snaps, project);
    return { point: [snapped.x, snapped.y, snapped.z],
             snapped: snapped.snapped, onGeometry: false };
  }

  function onDown(event) {
    if (!tool || event.button !== 0) return;
    press = { x: event.clientX, y: event.clientY };
  }

  function onUp(event) {
    if (!tool || !press || event.button !== 0) return;
    const travel = Math.hypot(event.clientX - press.x, event.clientY - press.y);
    press = null;
    if (travel > 5) return; // orbite, pas un clic
    const aimed = aimedPoint(event);
    if (!aimed) {
      say(t("Spline 3D : le plan de clic est vu par la tranche — Tab pour en changer"), true);
      return;
    }
    const list = points();
    let axis = null;
    if (event.shiftKey && list.length) {
      // Maj : le segment suit l'axe X, Y ou Z où il avance le plus.
      const locked = alongAxis(list[list.length - 1], aimed.point);
      aimed.point = locked.point;
      axis = locked.axis;
    }
    const round = (v) => Math.round(v * 1000) / 1000;
    const [x, y, z] = aimed.point.map(round);
    panel.notifyPick("point3d", { kind: "point3d", x, y, z });
    if (aimed.onGeometry && aimed.snapped && !axis) {
      // Clic aimanté sur un sommet ou un centre : le point s'y lie et
      // suivra la pièce (le moteur retrouve l'élément).
      const links = [...(tool.values.links ?? [])];
      while (links.length < list.length) links.push(null);
      links[list.length] = true;
      panel.restore({ links });
    }
    if (axis) {
      // Maj : l'axe devient une règle du segment, gardée à la réédition.
      const rules = [...(tool.values.rules ?? [])];
      while (rules.length < list.length) rules.push({ axis: "", length: null });
      rules[list.length - 1] = { ...rules[list.length - 1], axis };
      panel.restore({ rules });
    }
    if (axis) {
      say(t("Point le long de l'axe {a}.", { a: axis }));
      return;
    }
    say(aimed.snapped === "center" ? t("Point au centre du cercle.")
      : aimed.snapped === "vertex" ? t("Point sur le sommet.")
        : aimed.onGeometry ? t("Point sur la géométrie.")
          : t("Point sur le {p}.", { p: t(PLANE_LABELS[tool.values.plane]) }));
  }

  function onMove(event) {
    if (!tool || !points().length) return;
    rubber = aimedPoint(event)?.point ?? null;
    if (rubber && event.shiftKey) {
      const list = points();
      rubber = alongAxis(list[list.length - 1], rubber).point;
    }
    drawPreview();
  }

  function onKey(event) {
    if (!tool || event.key !== "Tab") return;
    // Dans le panneau (champs, boutons), Tab garde son rôle de navigation.
    if (event.target?.closest?.("aside, input, select, textarea, button")) {
      return;
    }
    event.preventDefault();
    const plane = nextPlane(tool.values.plane);
    panel.restore({ plane });
    say(t("Plan de clic : {p}", { p: t(PLANE_LABELS[plane]) }));
  }

  function stop() {
    if (!tool) return;
    tool = null;
    rubber = null;
    clearTimeout(exactTimer);
    exact = { key: null, points: null };
    clearPreview();
    preview.removeFromParent();
    renderer.domElement.removeEventListener("pointerdown", onDown);
    renderer.domElement.removeEventListener("pointerup", onUp);
    renderer.domElement.removeEventListener("pointermove", onMove);
    document.removeEventListener("keydown", onKey, true);
  }

  /** Ouvre l'outil ; `curve` (entrée d'arbre avec `curve`) le réédite. */
  function open(curve = null) {
    stop();
    const spec = curve?.curve;
    tool = { curve, values: {
      points: spec?.points ?? [], plane: "XY", rules: spec?.rules ?? [],
      links: spec?.links ?? [],
      spline: spec?.spline ?? true, closed: spec?.closed ?? false } };
    scene.add(preview);
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);
    renderer.domElement.addEventListener("pointermove", onMove);
    document.addEventListener("keydown", onKey, true);
    panel.open({
      icon: "spline3d",
      title: curve ? curve.label : t("Spline 3D"),
      autoFocus: false,
      groups: [
        { label: t("Points"),
          rows: [
            { type: "points", key: "points", linksKey: "links",
              value: tool.values.points },
            // La note porte aussi la valeur « links » (liste parallèle aux
            // points) : le panneau la garde et la rend à l'OK.
            { type: "note", readonly: true, key: "links",
              value: tool.values.links,
              text: t("⛓ : point lié à un sommet ou un centre de la pièce") },
          ] },
        { label: t("Segments"),
          rows: [{ type: "segments", key: "rules", pointsKey: "points",
                   value: tool.values.rules }] },
        { label: t("Options"),
          rows: [
            { type: "select", key: "plane", label: t("Plan de clic"),
              value: "XY",
              options: CLICK_PLANES.map((k) => [k, PLANE_LABELS[k]]) },
            { type: "check", key: "spline", label: t("Courbe lisse (spline)"),
              value: tool.values.spline },
            { type: "check", key: "closed", label: t("Fermée"),
              value: tool.values.closed },
          ] },
      ],
      note: t("Cliquez sur la pièce, une surface ou une courbe — sommets et "
        + "centres aimantent — ou dans le vide : le point se pose sur le "
        + "plan de clic, qui passe par le dernier point. Tab change de plan, "
        + "Maj garde le segment parallèle à un axe. Décochez « Courbe lisse » "
        + "pour des segments droits."),
      hint: (v) => {
        const problem = curveProblem(v.points, v.closed);
        return problem ? { text: problem, tone: "guide" } : null;
      },
      onChange: (v) => {
        if (!tool) return;
        // Les règles recalent les points : la liste montre le résultat.
        const solved = solveRules(v.points ?? [], v.rules,
          linkedIndices(v.links));
        if (!samePoints(solved, v.points ?? [])) {
          panel.restore({ points: solved });
          return;
        }
        tool.values = v;
        drawPreview();
        requestExact();
      },
      onClose: () => stop(),
      onApply: (v) => {
        const problem = curveProblem(v.points, v.closed);
        if (problem) {
          // Le panneau est déjà fermé : on le rouvre tel quel.
          open(curve);
          panel.restore(v);
          say(t(problem), true);
          return;
        }
        const params = { points: solveRules(v.points, v.rules,
                                            linkedIndices(v.links)),
                         rules: v.rules ?? [], links: v.links ?? [],
                         spline: !!v.spline, closed: !!v.closed };
        refresh(curve
          ? call("edit_curve3d", { curve: curve.name, ...params })
          : call("add_curve3d", params));
      },
    });
  }

  return {
    open,
    get active() { return tool !== null; },
  };
}
