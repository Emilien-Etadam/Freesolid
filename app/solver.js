// FreeSolid — M3 : le solveur planegcs (WASM) dans le client.
//
// Le même solveur que FreeCAD, compilé en WebAssembly (paquet
// @salusoft89/planegcs, LGPL, vendu dans app/vendor/). L'état d'esquisse
// envoyé par le serveur est traduit en primitives + contraintes
// planegcs ; pendant un drag, la résolution est locale (60 fps, zéro
// réseau) via deux contraintes temporaires coordinate_x/y sur le point
// tiré. Le serveur reste la vérité : au lâcher, un sketch_move final
// réconcilie.
//
// Tout état non traduisible (géométrie ou contrainte inconnue) rend le
// modèle « non supporté » : l'appelant retombe sur le drag serveur.

import { arcAngles } from "./geom2d.js";

export function createLocalSolver(loadModule) {
  let wrapper = null;
  let status = "idle"; // idle | loading | ready | failed
  let model = null;    // { primitives, entities } ou null

  async function ensureInit() {
    if (status !== "idle") return status === "ready";
    status = "loading";
    try {
      const mod = loadModule
        ? await loadModule()
        : await import("./vendor/planegcs/index.js");
      wrapper = await mod.make_gcs_wrapper(
        loadModule ? undefined : "vendor/planegcs/planegcs_dist/planegcs.wasm");
      status = "ready";
      return true;
    } catch (error) {
      console.warn("solveur local indisponible :", error);
      status = "failed";
      return false;
    }
  }

  // ---------- traduction état serveur -> primitives planegcs ----------

  const pid = (geo, pos) => `g${geo}p${pos}`;

  function pointRef(geo, pos) {
    if (geo === null || geo === undefined) return null;
    if (geo === -1 && pos === 1) return "origin"; // le point origine
    if (geo < 0) return null;                     // axes : pas un point
    return pid(geo, pos);
  }

  function lineRef(geo) {
    if (geo === -1) return "gx";
    if (geo === -2) return "gy";
    if (geo === null || geo === undefined || geo < 0) return null;
    return `g${geo}`;
  }

  function baseFrame() {
    return [
      { id: "origin", type: "point", x: 0, y: 0, fixed: true },
      { id: "axp1", type: "point", x: 0, y: 0, fixed: true },
      { id: "axp2", type: "point", x: 1, y: 0, fixed: true },
      { id: "gx", type: "line", p1_id: "axp1", p2_id: "axp2" },
      { id: "ayp1", type: "point", x: 0, y: 0, fixed: true },
      { id: "ayp2", type: "point", x: 0, y: 1, fixed: true },
      { id: "gy", type: "line", p1_id: "ayp1", p2_id: "ayp2" },
    ];
  }

  function geometryPrimitives(state, blocked) {
    const primitives = [];
    const kinds = {};
    for (const entity of state.entities) {
      const g = entity.id;
      const fixed = blocked.has(g);
      if (entity.type === "line") {
        kinds[g] = "line";
        primitives.push(
          { id: pid(g, 1), type: "point",
            x: entity.p1[0], y: entity.p1[1], fixed },
          { id: pid(g, 2), type: "point",
            x: entity.p2[0], y: entity.p2[1], fixed },
          { id: `g${g}`, type: "line",
            p1_id: pid(g, 1), p2_id: pid(g, 2) });
      } else if (entity.type === "circle") {
        kinds[g] = "circle";
        primitives.push(
          { id: pid(g, 3), type: "point",
            x: entity.c[0], y: entity.c[1], fixed },
          { id: `g${g}`, type: "circle",
            c_id: pid(g, 3), radius: entity.r });
      } else if (entity.type === "arc") {
        kinds[g] = "arc";
        const { a1, a2 } = arcAngles(entity);
        primitives.push(
          { id: pid(g, 3), type: "point",
            x: entity.c[0], y: entity.c[1], fixed },
          { id: pid(g, 1), type: "point",
            x: entity.p1[0], y: entity.p1[1], fixed },
          { id: pid(g, 2), type: "point",
            x: entity.p2[0], y: entity.p2[1], fixed },
          { id: `g${g}`, type: "arc", c_id: pid(g, 3),
            start_id: pid(g, 1), end_id: pid(g, 2),
            radius: entity.r, start_angle: a1, end_angle: a2 },
          { id: `g${g}rules`, type: "arc_rules", a_id: `g${g}` });
      } else {
        return null; // spline/ellipse : pas encore côté solveur local
      }
    }
    return { primitives, kinds };
  }

  // Une contrainte FreeCAD -> zéro, une ou plusieurs planegcs.
  // Tableau vide : valide (Block, déjà posé via `fixed` sur les points).
  // `null` ou `undefined` : non supporté — load() refuse toute l'esquisse
  // et l'appelant retombe sur le drag serveur. Ne pas ignorer `null` :
  // une contrainte connue mais irrésolue (ex. coïncidence vers un point
  // d'axe) laisserait le modèle local sous-contraint.
  function translate(c, kinds, index) {
    const [g1, g2, g3] = c.geos;
    const [p1, p2, p3] = c.pos;
    const P1 = pointRef(g1, p1), P2 = pointRef(g2, p2);
    const L1 = lineRef(g1), L2 = lineRef(g2), L3 = lineRef(g3);
    const id = (s) => `c${index}${s}`;
    switch (c.type) {
      case "Coincident":
        if (!P1 || !P2) return null;
        return [{ id: id(""), type: "p2p_coincident",
                  p1_id: P1, p2_id: P2 }];
      case "Horizontal":
        if (g2 !== null && P1 && P2) {
          return [{ id: id(""), type: "horizontal_pp",
                    p1_id: P1, p2_id: P2 }];
        }
        return L1 ? [{ id: id(""), type: "horizontal_l", l_id: L1 }] : null;
      case "Vertical":
        if (g2 !== null && P1 && P2) {
          return [{ id: id(""), type: "vertical_pp",
                    p1_id: P1, p2_id: P2 }];
        }
        return L1 ? [{ id: id(""), type: "vertical_l", l_id: L1 }] : null;
      case "Parallel":
        return L1 && L2
          ? [{ id: id(""), type: "parallel", l1_id: L1, l2_id: L2 }]
          : null;
      case "Perpendicular":
        return L1 && L2
          ? [{ id: id(""), type: "perpendicular_ll",
               l1_id: L1, l2_id: L2 }]
          : null;
      case "Tangent": {
        const k1 = kinds[g1], k2 = kinds[g2];
        if (k1 === "line" && k2 === "line") {
          // colinéaire : les deux extrémités de l2 sur la droite de l1
          return [
            { id: id("a"), type: "point_on_line_pl",
              p_id: pid(g2, 1), l_id: L1 },
            { id: id("b"), type: "point_on_line_pl",
              p_id: pid(g2, 2), l_id: L1 },
          ];
        }
        if (k1 === "line" && k2 === "circle") {
          return [{ id: id(""), type: "tangent_lc",
                    l_id: L1, c_id: `g${g2}` }];
        }
        if (k1 === "circle" && k2 === "line") {
          return [{ id: id(""), type: "tangent_lc",
                    l_id: L2, c_id: `g${g1}` }];
        }
        if (k1 === "line" && k2 === "arc") {
          return [{ id: id(""), type: "tangent_la",
                    l_id: L1, a_id: `g${g2}` }];
        }
        if (k1 === "arc" && k2 === "line") {
          return [{ id: id(""), type: "tangent_la",
                    l_id: L2, a_id: `g${g1}` }];
        }
        if (k1 === "circle" && k2 === "circle") {
          return [{ id: id(""), type: "tangent_cc",
                    c1_id: `g${g1}`, c2_id: `g${g2}` }];
        }
        return undefined; // combinaison non couverte
      }
      case "Equal": {
        const k1 = kinds[g1], k2 = kinds[g2];
        if (k1 === "line" && k2 === "line") {
          return [{ id: id(""), type: "equal_length",
                    l1_id: L1, l2_id: L2 }];
        }
        if (k1 === "circle" && k2 === "circle") {
          return [{ id: id(""), type: "equal_radius_cc",
                    c1_id: `g${g1}`, c2_id: `g${g2}` }];
        }
        if (k1 === "arc" && k2 === "arc") {
          return [{ id: id(""), type: "equal_radius_aa",
                    a1_id: `g${g1}`, a2_id: `g${g2}` }];
        }
        if (k1 === "circle" && k2 === "arc") {
          return [{ id: id(""), type: "equal_radius_ca",
                    c1_id: `g${g1}`, a2_id: `g${g2}` }];
        }
        if (k1 === "arc" && k2 === "circle") {
          return [{ id: id(""), type: "equal_radius_ca",
                    c1_id: `g${g2}`, a2_id: `g${g1}` }];
        }
        return undefined;
      }
      case "Distance":
        if (P1 && P2) {
          return [{ id: id(""), type: "p2p_distance",
                    p1_id: P1, p2_id: P2, distance: c.value }];
        }
        if (P1 && L2) {
          return [{ id: id(""), type: "p2l_distance",
                    p_id: P1, l_id: L2, distance: c.value }];
        }
        if (g1 !== null && g2 === null && kinds[g1] === "line") {
          return [{ id: id(""), type: "p2p_distance",
                    p1_id: pid(g1, 1), p2_id: pid(g1, 2),
                    distance: c.value }];
        }
        return undefined;
      case "DistanceX":
      case "DistanceY": {
        const prop = c.type === "DistanceX" ? "x" : "y";
        if (P1 && P2) {
          return [{ id: id(""), type: "difference",
                    param1: { o_id: P1, prop },
                    param2: { o_id: P2, prop },
                    difference: c.value }];
        }
        if (P1 && g2 === null) {
          const which = prop === "x" ? "coordinate_x" : "coordinate_y";
          return [{ id: id(""), type: which, p_id: P1,
                    [prop]: c.value }];
        }
        return undefined;
      }
      case "Radius":
        if (kinds[g1] === "circle") {
          return [{ id: id(""), type: "circle_radius",
                    c_id: `g${g1}`, radius: c.value }];
        }
        if (kinds[g1] === "arc") {
          return [{ id: id(""), type: "arc_radius",
                    a_id: `g${g1}`, radius: c.value }];
        }
        return undefined;
      case "Diameter":
        if (kinds[g1] === "circle") {
          return [{ id: id(""), type: "circle_diameter",
                    c_id: `g${g1}`, diameter: c.value }];
        }
        return undefined;
      case "Angle":
        if (L1 && L2 && g2 !== null) {
          return [{ id: id(""), type: "l2l_angle_ll",
                    l1_id: L1, l2_id: L2, angle: c.value }];
        }
        return undefined;
      case "Symmetric":
        if (P1 && P2 && L3) {
          return [{ id: id(""), type: "p2p_symmetric_ppl",
                    p1_id: P1, p2_id: P2, l_id: L3 }];
        }
        return undefined;
      case "PointOnObject":
        if (P1 && kinds[g2] === "line") {
          return [{ id: id(""), type: "point_on_line_pl",
                    p_id: P1, l_id: L2 }];
        }
        if (P1 && kinds[g2] === "circle") {
          return [{ id: id(""), type: "point_on_circle",
                    p_id: P1, c_id: `g${g2}` }];
        }
        if (P1 && kinds[g2] === "arc") {
          return [{ id: id(""), type: "point_on_arc",
                    p_id: P1, a_id: `g${g2}` }];
        }
        return undefined;
      case "Block":
        return []; // géré via fixed sur les points
      default:
        return undefined; // type inconnu -> fallback serveur
    }
  }

  function load(state) {
    model = null;
    if (status !== "ready" || !state?.constraints) return false;
    const blocked = new Set(
      state.constraints
        .filter((c) => c.type === "Block")
        .map((c) => c.geos[0]));
    const geometry = geometryPrimitives(state, blocked);
    if (!geometry) return false;
    const { kinds } = geometry;
    const primitives = baseFrame().concat(geometry.primitives);
    for (const [index, c] of state.constraints.entries()) {
      if (c.driving === false) continue; // cote de référence
      const translated = translate(c, kinds, index);
      if (translated == null) return false; // null ou undefined : fallback
      primitives.push(...translated);
    }
    model = { primitives, entities: state.entities };
    return true;
  }

  function drag(geo, pos, x, y) {
    if (!model || status !== "ready") return null;
    const target = pid(geo, pos);
    const primitives = model.primitives.concat([
      { id: "dragx", type: "coordinate_x", p_id: target, x,
        temporary: true, driving: true },
      { id: "dragy", type: "coordinate_y", p_id: target, y,
        temporary: true, driving: true },
    ]);
    try {
      wrapper.clear_data();
      wrapper.push_primitives_and_params(primitives);
      const solved = wrapper.solve();
      if (solved > 1) return null; // 0 succès, 1 convergé
      wrapper.apply_solution();
    } catch (error) {
      console.warn("solve local :", error);
      model = null; // état corrompu : retour au serveur
      return null;
    }
    const read = (id) => wrapper.sketch_index.get_primitive(id);
    const updates = [];
    for (const entity of model.entities) {
      const g = entity.id;
      if (entity.type === "line") {
        const a = read(pid(g, 1)), b = read(pid(g, 2));
        entity.p1 = [a.x, a.y];
        entity.p2 = [b.x, b.y];
      } else if (entity.type === "circle") {
        const c = read(pid(g, 3)), prim = read(`g${g}`);
        entity.c = [c.x, c.y];
        if (prim?.radius !== undefined) entity.r = prim.radius;
      } else if (entity.type === "arc") {
        const c = read(pid(g, 3));
        const a = read(pid(g, 1)), b = read(pid(g, 2));
        entity.c = [c.x, c.y];
        entity.p1 = [a.x, a.y];
        entity.p2 = [b.x, b.y];
        const prim = read(`g${g}`);
        if (prim?.radius !== undefined) entity.r = prim.radius;
      }
      updates.push(entity);
    }
    return updates;
  }

  return {
    ensureInit,
    load,
    drag,
    get ready() { return status === "ready"; },
  };
}
