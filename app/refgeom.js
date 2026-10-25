// Géométrie de référence : axes, points et repères — les panneaux de
// création et leur dessin dans la vue (les plans de référence, eux, se
// montrent au survol de l'arbre).

import { t } from "./i18n.js";
import { num } from "./num.js";

const KINDS = {
  datum_axis: "axis",
  datum_point: "point",
  datum_cs: "cs",
};

/** Axes, points et repères à dessiner : placés, pas derrière la barre de
 *  retour. */
export function referenceItems(tree) {
  const out = [];
  const visit = (items) => {
    for (const item of items ?? []) {
      if (KINDS[item.type_key] && item.placement && !item.rolled_back) {
        out.push({ ...item, shape: KINDS[item.type_key] });
      }
      visit(item.children);
    }
  };
  visit(tree?.features);
  return out;
}

/** Paramètres d'un panneau → { op, params }, ou null s'il manque le choix. */
export function referenceBuild(kind, v) {
  if (kind === "axis") {
    if (v.by !== "edge") return { op: "add_datum_axis", params: { axis: v.by } };
    const edge = v.edge?.edges?.[0];
    return edge == null ? null : { op: "add_datum_axis", params: { edge } };
  }
  const op = kind === "point" ? "add_datum_point" : "add_datum_cs";
  if (v.by === "vertex") {
    return v.vertex?.kind === "vertex"
      ? { op, params: { vertex: [v.vertex.x, v.vertex.y, v.vertex.z] } } : null;
  }
  if (v.by === "center") {
    const edge = v.edge?.edges?.[0];
    return edge == null ? null : { op, params: { edge } };
  }
  const point = [num(v.x), num(v.y), num(v.z)];
  return point.every(Number.isFinite) ? { op, params: { point } } : null;
}

export function installRefGeometry(ctx) {
  const { THREE, scene, sceneTheme } = ctx;
  let group = null;

  function clear() {
    if (!group) return;
    group.traverse((obj) => {
      obj.geometry?.dispose();
      obj.material?.dispose();
    });
    scene.remove(group);
    group = null;
  }

  function line(points, color, dashed = false) {
    const geometry = new THREE.BufferGeometry().setFromPoints(
      points.map((p) => new THREE.Vector3(...p)));
    const material = dashed
      ? new THREE.LineDashedMaterial({ color, dashSize: 3, gapSize: 2 })
      : new THREE.LineBasicMaterial({ color });
    const segment = new THREE.Line(geometry, material);
    if (dashed) segment.computeLineDistances();
    return segment;
  }

  /** Redessine les axes, points et repères de l'arbre. */
  function draw(tree) {
    clear();
    const items = referenceItems(tree);
    // Créés par l'utilisateur : toujours visibles (la case « Plans de
    // référence » ne vise que les trois plans d'origine).
    if (!items.length) return;
    const { radius } = ctx.partCenterRadius();
    const reach = Math.max(radius * 1.2, 40);
    group = new THREE.Group();
    group.name = "reference-geometry";
    for (const item of items) {
      const holder = new THREE.Group();
      holder.matrixAutoUpdate = false;
      holder.matrix.set(...item.placement);
      if (item.shape === "axis") {
        // Un axe court le long de son Z local.
        holder.add(line([[0, 0, -reach], [0, 0, reach]], sceneTheme.accent, true));
      } else if (item.shape === "point") {
        const geometry = new THREE.BufferGeometry().setFromPoints(
          [new THREE.Vector3()]);
        holder.add(new THREE.Points(geometry, new THREE.PointsMaterial(
          { color: sceneTheme.accent, size: 9, sizeAttenuation: false })));
      } else {
        const size = reach / 3;
        holder.add(line([[0, 0, 0], [size, 0, 0]], 0xd9534f),
          line([[0, 0, 0], [0, size, 0]], 0x5cb85c),
          line([[0, 0, 0], [0, 0, size]], 0x4a90d9));
      }
      group.add(holder);
    }
    scene.add(group);
  }

  function open(kind) {
    const edges = ctx.currentSelection(["edges"]);
    const isAxis = kind === "axis";
    const byOptions = isAxis
      ? [["X", t("Axe X de l'origine")], ["Y", t("Axe Y de l'origine")],
         ["Z", t("Axe Z de l'origine")], ["edge", t("Arête du solide")]]
      : [["vertex", t("Sommet cliqué")],
         ...(kind === "point" ? [["center", t("Centre d'une arête circulaire")]] : []),
         ["xyz", t("Coordonnées")]];
    const titles = { axis: "Axe de référence", point: "Point de référence",
                     cs: "Repère" };
    const icons = { axis: "datum_axis", point: "datum_point", cs: "datum_cs" };
    ctx.featureCommand(() => ctx.panel.open({
      icon: icons[kind],
      title: t(titles[kind]),
      groups: [{ label: t("Référence"), rows: [
        { type: "select", key: "by", options: byOptions,
          value: isAxis ? (edges ? "edge" : "Z") : "vertex" },
        { type: "selection", key: "edge", accepts: ["edges"], value: edges,
          hint: t(isAxis ? "Cliquez une arête droite ou circulaire"
            : "Cliquez une arête circulaire"),
          showIf: (v) => v.by === "edge" || v.by === "center" },
        { type: "selection", key: "vertex", accepts: ["vertex"],
          hint: t("Cliquez près d'un coin de la pièce"),
          showIf: (v) => v.by === "vertex" },
        ...["x", "y", "z"].map((axis) => ({
          type: "number", key: axis, label: axis.toUpperCase(), value: 0,
          unit: "mm", showIf: (v) => v.by === "xyz" })),
      ] }],
      onApply: (v) => {
        const built = referenceBuild(kind, v);
        if (!built) {
          ctx.say(t("Choisissez d'abord ce qui porte l'élément"), true);
          return;
        }
        ctx.refresh(ctx.call(built.op, built.params));
      },
    }));
  }

  for (const [id, kind] of [["btn-datum-axis", "axis"],
    ["btn-datum-point", "point"], ["btn-datum-cs", "cs"]]) {
    document.getElementById(id)?.addEventListener("click", () => open(kind));
  }

  return { draw };
}
