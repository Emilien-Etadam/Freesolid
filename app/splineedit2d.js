// Édition d'une spline d'esquisse dans la vue, comme la spline 3D : quand
// une seule spline est sélectionnée, ses points de passage apparaissent.
// Tirer un point le déplace ; cliquer un point montre sa poignée de
// tangente, dont on tire les bouts (Alt : un seul côté) ; Ctrl+clic sur la
// courbe ajoute un point (la forme ne bouge pas) ; Suppr retire le point
// choisi. Le panneau de l'entité porte le peigne de courbure, le polygone
// de contrôle (pôles à tirer), Simplifier, Lisser et les longueurs de la
// poignée. Calcul : splinemath.js ; le moteur redessine la spline à sa
// place (sketch_set_spline), ses relations tiennent.

import { t } from "./i18n.js";
import {
  sample, curvatureComb, maxCurvature, allHandleTips, preferPoint, dragTip, pinTangent,
  insertPoint, removePoint, simplify, relax, nearestOnCurve, cleanTangents,
  solve,
} from "./splinemath.js";

const PICK_PX = 9;

/** Spline éditable : une entité d'esquisse qui porte sa définition. */
export function editableSpline(entity) {
  return entity?.kind === "spline" && entity.spline?.points?.length >= 2 ? entity : null;
}

/** Définition en 3D (z = 0) pour splinemath. */
export function lift(spec) {
  return {
    points: spec.points.map(([x, y]) => [x, y, 0]),
    closed: !!spec.closed,
    tangents: (spec.tangents ?? []).map((tg) => (tg
      ? { dir: [tg.dir[0], tg.dir[1], 0], in: tg.in, out: tg.out } : null)),
  };
}

/** Définition à plat pour le moteur. */
export function flatten(spec) {
  return {
    points: spec.points.map((p) => [p[0], p[1]]),
    closed: !!spec.closed,
    tangents: cleanTangents(spec.tangents, spec.points.length).map((tg) => (tg
      ? { dir: [tg.dir[0], tg.dir[1]], in: tg.in, out: tg.out } : null)),
  };
}

export function createSplineEditor2d(deps) {
  const { THREE, theme, toScreen, toLocal, call, say, controls, getState,
    selectedSpline, applyState, redraw, setCursor } = deps;
  // Options d'affichage, gardées d'une spline à l'autre.
  const view = { comb: false, combScale: 100, polygon: false, tolerance: 0.1 };
  let geo = null;      // spline suivie
  let chosen = null;   // index du point choisi
  let edit = null;     // définition en cours (pendant un glisser)
  let drag = null;     // { kind, index, side?, moved, screen }
  let poles = null;    // pôles (2D) de la définition courante
  let polesKey = null;
  let poleBusy = false;
  let poleNext = null;

  const mat = {
    dot: new THREE.PointsMaterial({ color: theme.accent, size: 7, sizeAttenuation: false,
      depthTest: false, transparent: true }),
    chosen: new THREE.PointsMaterial({ color: theme.selection, size: 11,
      sizeAttenuation: false, depthTest: false, transparent: true }),
    handle: new THREE.LineBasicMaterial({ color: theme.selection, depthTest: false,
      transparent: true }),
    handleSoft: new THREE.LineBasicMaterial({ color: theme.accent, depthTest: false,
      transparent: true, opacity: 0.7 }),
    tipSoft: new THREE.PointsMaterial({ color: theme.accent, size: 7, sizeAttenuation: false,
      depthTest: false, transparent: true }),
    comb: new THREE.LineBasicMaterial({ color: theme.dim, depthTest: false,
      transparent: true, opacity: 0.7 }),
    polygon: new THREE.LineDashedMaterial({ color: theme.ink2, dashSize: 1.5, gapSize: 1,
      depthTest: false, transparent: true }),
    pole: new THREE.PointsMaterial({ color: theme.ink2, size: 7, sizeAttenuation: false,
      depthTest: false, transparent: true }),
  };

  /** La spline suivie (et la remise à zéro quand la sélection change). */
  function current() {
    const entity = editableSpline(selectedSpline());
    if (!entity) {
      geo = null;
      chosen = null;
      return null;
    }
    if (entity.id !== geo) {
      geo = entity.id;
      chosen = null;
      poles = null;
      polesKey = null;
    }
    return entity;
  }

  function spec() {
    const entity = current();
    if (!entity) return null;
    return edit ?? lift(entity.spline);
  }

  const keyOf = (s) => JSON.stringify([s.points, cleanTangents(s.tangents, s.points.length), s.closed]);

  async function refreshPoles(s) {
    const key = keyOf(s);
    if (!view.polygon || polesKey === key) return;
    try {
      const result = await call("curve_poles", { points: s.points, closed: s.closed,
        tangents: cleanTangents(s.tangents, s.points.length) });
      poles = result.poles;
      polesKey = key;
      redraw();
    } catch { /* pas de polygone */ }
  }

  function line(pts, material, dashed = false) {
    const geom = new THREE.BufferGeometry().setFromPoints(
      pts.map((p) => new THREE.Vector3(p[0], p[1], 0.02)));
    const obj = new THREE.Line(geom, material);
    if (dashed) obj.computeLineDistances();
    obj.renderOrder = 23;
    return obj;
  }

  function dots(pts, material) {
    const obj = new THREE.Points(new THREE.BufferGeometry().setFromPoints(
      pts.map((p) => new THREE.Vector3(p[0], p[1], 0.03))), material);
    obj.renderOrder = 24;
    return obj;
  }

  /** Surcouches dans le groupe de l'esquisse (coordonnées locales). */
  function draw(group) {
    const s = spec();
    if (!s) return;
    const n = s.points.length;
    group.add(dots(s.points, mat.dot));
    // Poignées de tous les points ; celle du point choisi ressort.
    try {
      allHandleTips(s.points, s.closed, s.tangents).forEach((tips, i) => {
        const isChosen = i === chosen;
        group.add(line([tips.in, s.points[i], tips.out].filter(Boolean),
          isChosen ? mat.handle : mat.handleSoft));
        group.add(dots([tips.in, tips.out].filter(Boolean), isChosen ? mat.chosen : mat.tipSoft));
      });
    } catch { /* pas de poignée */ }
    if (chosen != null && chosen < n) group.add(dots([s.points[chosen]], mat.chosen));
    if (view.comb) {
      try {
        const opts = { closed: s.closed, tangents: s.tangents };
        const peak = maxCurvature(s.points, opts) || 1;
        let size = 1;
        for (const p of s.points) {
          for (const q of s.points) size = Math.max(size, Math.hypot(p[0] - q[0], p[1] - q[1]));
        }
        const scale = (size * 0.25 * (Number(view.combScale) || 100) / 100) / peak;
        const teeth = curvatureComb(s.points, { ...opts, scale });
        for (const [p, q] of teeth) group.add(line([p, q], mat.comb));
        if (teeth.length >= 2) group.add(line(teeth.map(([, q]) => q), mat.comb));
      } catch { /* pas de peigne */ }
    }
    if (view.polygon) {
      if (poles && polesKey === keyOf(s)) {
        group.add(line(poles, mat.polygon, true));
        group.add(dots(poles, mat.pole));
      } else {
        refreshPoles(s);
      }
    }
  }

  const pixels = (p, event) => {
    const sp = toScreen(p[0], p[1]);
    return Math.hypot(sp.x - event.clientX, sp.y - event.clientY);
  };

  function hitAt(event) {
    const s = spec();
    if (!s) return null;
    const nearest = (candidates) => {
      let best = null;
      for (const [p, hit] of candidates) {
        if (!p) continue;
        const d = pixels(p, event);
        if (d < PICK_PX && (!best || d < best.d)) best = { d, hit };
      }
      return best;
    };
    let tips = [];
    try {
      tips = allHandleTips(s.points, s.closed, s.tangents).flatMap((tip, i) => [
        [tip.in, { kind: "tip", index: i, side: "in" }],
        [tip.out, { kind: "tip", index: i, side: "out" }]]);
    } catch { /* pas de poignée */ }
    const found = preferPoint(nearest(s.points.map((p, i) => [p, { kind: "point", index: i }])),
      nearest(tips));
    if (found) return found.hit;
    const best = { d: PICK_PX, hit: null };
    const consider = (p, hit) => {
      const d = pixels(p, event);
      if (d < best.d) { best.d = d; best.hit = hit; }
    };
    if (view.polygon && poles && polesKey === keyOf(s)) {
      poles.forEach((p, i) => consider(p, { kind: "pole", index: i }));
    }
    return best.hit;
  }

  function onCurve(event) {
    const s = spec();
    if (!s) return null;
    let path;
    try { path = sample(s.points, { closed: s.closed, tangents: s.tangents, perSpan: 48 }); } catch { return null; }
    let best = null;
    for (const p of path) {
      const d = pixels(p, event);
      if (d < PICK_PX && (!best || d < best.d)) best = { d, p };
    }
    return best?.p ?? null;
  }

  /** Aperçu : la polyligne de l'entité suit la définition en cours. */
  function preview(s) {
    edit = s;
    const entity = current();
    if (entity) {
      try {
        entity.points = sample(s.points, { closed: s.closed, tangents: s.tangents })
          .map((p) => [p[0], p[1]]);
      } catch { /* garde l'ancien tracé */ }
    }
    redraw();
  }

  async function commit(s, message) {
    const state = getState();
    const entity = current();
    if (!state || !entity) return;
    try {
      const next = await call("sketch_set_spline", { sketch: state.sketch, geo: entity.id,
        ...flatten(s) });
      edit = null;
      applyState(next, { keepSelection: true });
      if (message) say(message);
    } catch (error) {
      edit = null;
      say(error.message, true);
      redraw();
    }
  }

  const round = (v) => Math.round(v * 1e6) / 1e6;

  function pointerDown(event) {
    if (event.button !== 0 || !current()) return false;
    if (event.ctrlKey || event.metaKey) {
      const on = onCurve(event);
      if (!on) return false;
      const s = spec();
      const near = nearestOnCurve(s.points, s.closed, s.tangents, on);
      const result = insertPoint(s.points, s.closed, s.tangents, near.span, near.s);
      chosen = result.index;
      commit({ ...s, points: result.points, tangents: result.tangents },
        t("Point P{n} ajouté.", { n: result.index + 1 }));
      return true;
    }
    const hit = hitAt(event);
    if (!hit) return false;
    drag = { ...hit, moved: false, screen: { x: event.clientX, y: event.clientY } };
    if (hit.kind !== "pole") chosen = hit.index;
    controls.enabled = false;
    setCursor("grabbing");
    redraw();
    return true;
  }

  function pointerMove(event) {
    if (!drag) {
      if (current() && hitAt(event)) {
        setCursor("grab");
        return true;
      }
      return false;
    }
    if (!drag.moved && Math.hypot(event.clientX - drag.screen.x,
      event.clientY - drag.screen.y) < 4) return true;
    drag.moved = true;
    const local = toLocal(event);
    if (!local) return true;
    const target = [round(local.x), round(local.y), 0];
    const s = spec();
    if (drag.kind === "point") {
      const points = s.points.map((p) => [...p]);
      points[drag.index] = target;
      preview({ ...s, points });
    } else if (drag.kind === "tip") {
      preview({ ...s, tangents: dragTip(s.points, s.closed, s.tangents, drag.index,
        drag.side, target, { alone: event.altKey }) });
    } else {
      movePole(drag.index, target);
    }
    return true;
  }

  async function movePole(index, target) {
    if (poleBusy) { poleNext = { index, target }; return; }
    poleBusy = true;
    const s = spec();
    try {
      const result = await call("curve_move_pole", { points: s.points, closed: s.closed,
        tangents: cleanTangents(s.tangents, s.points.length), index, point: target });
      poles = result.poles;
      const next = { ...s, points: result.points, tangents: result.tangents };
      polesKey = keyOf(next);
      preview(next);
    } catch (error) {
      say(error.message ?? String(error), true);
    } finally {
      poleBusy = false;
      const next = poleNext;
      poleNext = null;
      // La dernière position compte ; bouton relâché, on enregistre.
      if (next) movePole(next.index, next.target);
      else if (!drag && edit) commit(edit);
    }
  }

  function pointerUp(event) {
    if (!drag || event.button !== 0) return false;
    const done = drag;
    drag = null;
    controls.enabled = true;
    setCursor("");
    if (done.moved && done.kind !== "pole" && edit) {
      commit(edit);
    } else if (done.moved && done.kind === "pole") {
      if (!poleBusy && edit) commit(edit);
    } else if (!done.moved && done.kind === "point") {
      say(t("Point P{n} : tirez-le, ou tirez les bouts de sa poignée (Alt : un seul côté).",
        { n: done.index + 1 }));
      redraw();
      onChosen?.();
    }
    return true;
  }

  /** Suppr : retire le point choisi (vrai si la touche est prise). */
  function deleteKey() {
    const s = spec();
    if (!s || chosen == null) return false;
    if (s.points.length <= 2) {
      say(t("Une courbe garde au moins deux points."), true);
      return true;
    }
    const removed = chosen;
    const result = removePoint(s.points, s.tangents, removed);
    chosen = null;
    commit({ ...s, ...result }, t("Point P{n} retiré.", { n: removed + 1 }));
    return true;
  }

  let onChosen = null;

  /** Lignes du panneau de l'entité (groupe « Spline »). */
  function panelGroup() {
    const s = spec();
    if (!s) return null;
    const n = s.points.length;
    const rows = [];
    if (chosen != null && chosen < n) {
      let slopes = null;
      try { slopes = solve(s.points, s.closed, s.tangents); } catch { /* rien */ }
      const pct = (v) => Math.round(Math.hypot(...v) * 1000) / 10;
      rows.push(
        { type: "note", readonly: true, text: t("Point P{n}", { n: chosen + 1 }) },
        { type: "check", key: "handleDriven", label: t("Tangente pilotée"),
          value: !!cleanTangents(s.tangents, n)[chosen] },
        { type: "number", key: "handleIn", label: t("Longueur avant"), unit: "%", min: 1,
          step: 5, lazy: true, value: slopes ? pct(slopes.mIn[chosen]) : 100 },
        { type: "number", key: "handleOut", label: t("Longueur après"), unit: "%", min: 1,
          step: 5, lazy: true, value: slopes ? pct(slopes.mOut[chosen]) : 100 },
        { type: "buttons", items: [
          { label: t("Libérer la poignée"), onClick: () => releaseHandles(chosen) },
          { label: t("Retirer le point"), onClick: () => deleteKey() },
        ] },
      );
    } else {
      rows.push({ type: "note", readonly: true,
        text: t("Cliquez un point de la spline pour sa poignée ; Ctrl+clic sur la courbe ajoute un point.") });
    }
    rows.push(
      { type: "check", key: "comb", label: t("Peigne de courbure"), value: view.comb },
      { type: "number", key: "combScale", label: t("Échelle du peigne"), unit: "%", min: 1,
        step: 10, value: view.combScale, showIf: (v) => v.comb },
      { type: "check", key: "polygon", label: t("Polygone de contrôle"), value: view.polygon },
      { type: "number", key: "tolerance", label: t("Tolérance"), unit: "mm", min: 0.0001,
        step: 0.05, value: view.tolerance },
      { type: "buttons", items: [
        { label: t("Simplifier"),
          title: "Retire les points superflus sans écarter la courbe de plus que la tolérance",
          onClick: () => simplifySpline() },
        { label: t("Lisser"), title: "Rapproche chaque point intérieur de ses voisins",
          onClick: () => relaxSpline() },
        { label: t("Libérer toutes les poignées"), onClick: () => releaseHandles(null) },
      ] },
    );
    return { label: t("Spline"), rows };
  }

  /** Une valeur du panneau a changé ; vrai si la spline change (le
   *  moteur répond, le panneau sera reconstruit). */
  function panelChange(values) {
    view.comb = !!values.comb;
    view.polygon = !!values.polygon;
    view.combScale = values.combScale ?? view.combScale;
    view.tolerance = values.tolerance ?? view.tolerance;
    const s = spec();
    if (s && chosen != null && chosen < s.points.length && "handleDriven" in values) {
      let slopes = null;
      try { slopes = solve(s.points, s.closed, s.tangents); } catch { /* rien */ }
      const pct = (v) => Math.round(Math.hypot(...v) * 1000) / 10;
      const was = {
        handleDriven: !!cleanTangents(s.tangents, s.points.length)[chosen],
        handleIn: slopes ? pct(slopes.mIn[chosen]) : 100,
        handleOut: slopes ? pct(slopes.mOut[chosen]) : 100,
      };
      const tangents = cleanTangents(s.tangents, s.points.length);
      const typed = ["handleIn", "handleOut"].some((k) => String(values[k]) !== String(was[k]))
        && Number(values.handleIn) > 0 && Number(values.handleOut) > 0;
      const toggled = !!values.handleDriven !== was.handleDriven;
      if (typed || (toggled && values.handleDriven)) {
        const pinned = tangents[chosen] ?? pinTangent(s.points, s.closed, tangents, chosen)[chosen];
        tangents[chosen] = { dir: pinned.dir, in: Number(values.handleIn) / 100,
                             out: Number(values.handleOut) / 100 };
        commit({ ...s, tangents });
        return true;
      }
      if (toggled && !values.handleDriven) {
        tangents[chosen] = null;
        commit({ ...s, tangents });
        return true;
      }
    }
    redraw();
    return false;
  }

  function releaseHandles(index) {
    const s = spec();
    if (!s) return;
    const tangents = cleanTangents(s.tangents, s.points.length);
    if (index != null) tangents[index] = null;
    else tangents.fill(null);
    commit({ ...s, tangents }, index != null
      ? t("Poignée du point P{n} libérée.", { n: index + 1 })
      : t("Toutes les poignées sont libérées."));
  }

  function simplifySpline() {
    const s = spec();
    if (!s) return;
    const tol = Math.max(Number(String(view.tolerance).replace(",", ".")) || 0.1, 1e-4);
    const result = simplify(s.points, s.closed, s.tangents, tol);
    const removed = s.points.length - result.points.length;
    if (!removed) {
      say(t("Simplifier : aucun point ne part sans dépasser {tol} mm.", { tol }));
      return;
    }
    chosen = null;
    commit({ ...s, ...result },
      t("Simplifier : {n} point(s) en moins (écart ≤ {tol} mm).", { n: removed, tol }));
  }

  function relaxSpline() {
    const s = spec();
    if (!s) return;
    commit({ ...s, points: relax(s.points, s.closed, 0.5) },
      t("Courbe lissée (cliquez encore pour lisser davantage)."));
  }

  return {
    draw, pointerDown, pointerMove, pointerUp, deleteKey, panelGroup, panelChange,
    get dragging() { return drag !== null; },
    get chosen() { return current() ? chosen : null; },
    /** Rappel quand un point est choisi (le panneau se met à jour). */
    set onChosen(fn) { onChosen = fn; },
  };
}
