// Barre d'état : coordonnées sous le curseur, mesure de la sélection et
// mode d'édition. Module pur — main.js et sketch.js lui passent les
// valeurs, il rend les textes (traduits).

import { t } from "./i18n.js";
import { arcAngles } from "./geom2d.js";

function mm(value) {
  return (Math.abs(value) < 5e-3 ? 0 : value).toFixed(2);
}

/** Coordonnées sous le curseur : {x, y} (esquisse) ou {x, y, z}. */
export function coordsText(point) {
  if (!point) return "";
  if (point.z === undefined || point.z === null) {
    return t("X {x}  Y {y} mm", { x: mm(point.x), y: mm(point.y) });
  }
  return t("X {x}  Y {y}  Z {z} mm",
    { x: mm(point.x), y: mm(point.y), z: mm(point.z) });
}

/** Longueur d'une entité d'esquisse (droite, arc, cercle), sinon NaN. */
export function sketchEntityLength(entity) {
  if (entity?.type === "line" && entity.p1 && entity.p2) {
    return Math.hypot(entity.p2[0] - entity.p1[0], entity.p2[1] - entity.p1[1]);
  }
  if (entity?.type === "circle" && entity.r != null) return 2 * Math.PI * entity.r;
  if (entity?.type === "arc" && entity.r != null && entity.c
      && entity.p1 && entity.p2) {
    const { a1, a2 } = arcAngles(entity);
    return entity.r * Math.abs(a2 - a1);
  }
  return NaN;
}

/** Mesure de la sélection : la longueur, ou la somme de plusieurs. */
export function measureText(lengths) {
  const valid = (lengths ?? []).filter(Number.isFinite);
  if (!valid.length) return "";
  const total = valid.reduce((sum, value) => sum + value, 0);
  if (valid.length === 1) return t("Longueur : {v} mm", { v: mm(total) });
  return t("Longueur totale : {v} mm ({n} entités)",
    { v: mm(total), n: valid.length });
}

/** Ce qu'on édite : une esquisse, un assemblage ou une pièce. */
export function editModeText({ sketch, assembly, part } = {}) {
  if (sketch) return t("Édition : esquisse « {name} »", { name: sketch });
  if (assembly) return t("Édition : assemblage");
  if (part) return t("Édition : pièce « {name} »", { name: part });
  return "";
}
