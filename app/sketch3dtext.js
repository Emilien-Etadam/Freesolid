// Esquisse 3D : libellés (entités, cotes) et choix de la cote selon les
// clics de l'outil Cotation — sans Three.js, testé sous Node.

import { t } from "./i18n.js";

/** Texte d'une cote : « 30 » (mm) ou « 90° ». */
export function dimText(dim) {
  const value = Number(dim.value);
  const shown = Number.isFinite(value) ? Number(value.toFixed(3)) : "?";
  return dim.type === "angle" ? `${shown}°` : `${shown}`;
}

/** Libellé d'une entité dans le panneau. */
export function entityText(spec, i) {
  const e = spec.entities[i];
  const n = i + 1;
  if (e.type === "line") {
    const rel = spec.relations.find((r) => r.entity === i);
    const base = t("Ligne {n} (P{a}–P{b})", { n, a: e.a + 1, b: e.b + 1 });
    return rel ? `${base} · ${t("le long de {a}", { a: rel.axis })}` : base;
  }
  if (e.type === "spline") return t("Spline {n} ({k} points)", { n, k: e.pts.length });
  return t("Point {n} (P{p})", { n, p: e.p + 1 });
}

/** Libellé d'une cote dans le panneau. */
export function dimLabel(spec, dim) {
  if (dim.type === "length") return t("Longueur L{n} = {v}", { n: dim.entity + 1, v: dimText(dim) });
  if (dim.type === "distance") {
    return t("Distance P{a}–P{b} = {v}", { a: dim.p1 + 1, b: dim.p2 + 1, v: dimText(dim) });
  }
  return t("Angle L{a}–L{b} = {v}", { a: dim.e1 + 1, b: dim.e2 + 1, v: dimText(dim) });
}

/** La cote que donnent les choix faits avec l'outil Cotation : `picks`
 *  [{ kind: "entity"|"point", index }], `last` le clic de fin (même
 *  forme, ou null pour un clic dans le vide). Rend { dim } (sans valeur),
 *  { wait } (il faut un autre choix) ou { reset }. */
export function dimFromPicks(spec, picks, last) {
  const isLine = (p) => p?.kind === "entity" && spec.entities[p.index]?.type === "line";
  const first = picks[0];
  if (!first) {
    if (isLine(last) || last?.kind === "point") return { wait: last };
    return { reset: true };
  }
  if (isLine(first)) {
    if (!last || (last.kind === "entity" && last.index === first.index)) {
      return { dim: { type: "length", entity: first.index } };
    }
    if (isLine(last)) return { dim: { type: "angle", e1: first.index, e2: last.index } };
    return { reset: true };
  }
  if (first.kind === "point" && last?.kind === "point" && last.index !== first.index) {
    return { dim: { type: "distance", p1: first.index, p2: last.index } };
  }
  return { reset: true };
}

/** Index d'une cote qui mesure déjà la même chose que `dim`, ou -1. */
export function findDim(spec, dim) {
  const same = (a, b) => a.length === b.length && a.every((x) => b.includes(x));
  return spec.dims.findIndex((d) => d.type === dim.type && (
    d.type === "length" ? d.entity === dim.entity
      : d.type === "distance" ? same([d.p1, d.p2], [dim.p1, dim.p2])
        : same([d.e1, d.e2], [dim.e1, dim.e2])));
}
