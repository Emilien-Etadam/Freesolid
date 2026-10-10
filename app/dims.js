// Cotes — libellé, ancrage 2D, champ d'édition. Sans Three.js : le
// sprite 3D reste dans sketch.js ; le panneau est le même en esquisse
// et hors esquisse.

import { simpleDecimal } from "./num.js";
import { t } from "./i18n.js";

/** Libellé d'une cote : « largeur = 60.00 », préfixe Σ si expression,
 *  Ø pour un diamètre, R pour un rayon. */
export function dimLabel(dim) {
  const number = dim.type === "Angle"
    ? (dim.value * 180 / Math.PI).toFixed(1) + "°"
    : Number(dim.value).toFixed(2);
  const symbol = dim.type === "Diameter" ? "Ø"
    : dim.type === "Radius" ? "R" : "";
  return (dim.expr ? "Σ " : "")
    + (dim.name ? dim.name + " = " : "") + symbol + number;
}

/** Bulle du congé en cours : « R = 3.00 », ou l'expression telle quelle. */
export function filletRadiusLabel(raw) {
  const text = String(raw ?? "").trim();
  if (!text) return null;
  const numeric = simpleDecimal(text);
  return numeric == null ? `R = ${text}` : `R = ${numeric.toFixed(2)}`;
}

// ---------- tracé d'une cote d'esquisse ----------
// Coordonnées locales de l'esquisse. `size` est l'unité de tracé (écart
// entre la pièce et la ligne de cote), choisie par l'appelant à l'échelle
// de l'écran. Résultat : { label, segments, arrows } — une flèche est
// { x, y, dx, dy } : pointe en (x, y), dirigée selon (dx, dy) unitaire.

const ORIGIN = { id: -1, type: "point", p1: [0, 0] };

function pointOf(entity, pos) {
  if (!entity) return null;
  if (pos === 1 && entity.p1) return { x: entity.p1[0], y: entity.p1[1] };
  if (pos === 2 && entity.p2) return { x: entity.p2[0], y: entity.p2[1] };
  if (pos === 3 && entity.c) return { x: entity.c[0], y: entity.c[1] };
  return null;
}

function unit(dx, dy) {
  const n = Math.hypot(dx, dy);
  return n > 1e-12 ? { x: dx / n, y: dy / n } : null;
}

function centroid(entities) {
  let sx = 0, sy = 0, n = 0;
  for (const e of entities ?? []) {
    for (const p of [e.p1, e.p2, e.c]) {
      if (p) { sx += p[0]; sy += p[1]; n += 1; }
    }
  }
  return n ? { x: sx / n, y: sy / n } : { x: 0, y: 0 };
}

/** Cote alignée entre A et B : à l'endroit où elle a été posée
 *  (`offset`, signé, sur la normale A→B), sinon décalée vers l'extérieur
 *  de l'esquisse. */
function alignedDim(a, b, entities, size, offset = null) {
  const d = unit(b.x - a.x, b.y - a.y);
  if (!d) return null;
  let n = { x: -d.y, y: d.x };
  let off = size * 2;
  if (offset != null) {
    if (offset < 0) n = { x: -n.x, y: -n.y };
    off = Math.abs(offset);
  } else {
    const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    const c = centroid(entities);
    if ((mid.x - c.x) * n.x + (mid.y - c.y) * n.y < 0) n = { x: -n.x, y: -n.y };
  }
  const ext = size * 0.6;
  const a2 = { x: a.x + n.x * off, y: a.y + n.y * off };
  const b2 = { x: b.x + n.x * off, y: b.y + n.y * off };
  return {
    label: { x: (a2.x + b2.x) / 2 + n.x * size, y: (a2.y + b2.y) / 2 + n.y * size },
    segments: [
      [a.x, a.y, a.x + n.x * (off + ext), a.y + n.y * (off + ext)],
      [b.x, b.y, b.x + n.x * (off + ext), b.y + n.y * (off + ext)],
      [a2.x, a2.y, b2.x, b2.y],
    ],
    arrows: [
      { x: a2.x, y: a2.y, dx: -d.x, dy: -d.y },
      { x: b2.x, y: b2.y, dx: d.x, dy: d.y },
    ],
  };
}

/** Cote horizontale ("DistanceX") ou verticale ("DistanceY") entre A et
 *  B : ligne de cote parallèle à l'axe, là où elle a été posée (`offset`
 *  depuis A), sinon au-dessus / à droite. */
function axisDim(a, b, kind, size, offset = null) {
  const off = size * 2;
  const ext = size * 0.6;
  if (kind === "DistanceX") {
    const y = offset != null ? a.y + offset : Math.max(a.y, b.y) + off;
    const dir = Math.sign(b.x - a.x) || 1;
    const side = y >= Math.max(a.y, b.y) ? 1 : -1;
    return {
      label: { x: (a.x + b.x) / 2, y: y + size * side },
      segments: [[a.x, a.y, a.x, y + ext * side], [b.x, b.y, b.x, y + ext * side],
                 [a.x, y, b.x, y]],
      arrows: [{ x: a.x, y, dx: -dir, dy: 0 }, { x: b.x, y, dx: dir, dy: 0 }],
    };
  }
  const x = offset != null ? a.x + offset : Math.max(a.x, b.x) + off;
  const dir = Math.sign(b.y - a.y) || 1;
  const side = x >= Math.max(a.x, b.x) ? 1 : -1;
  return {
    label: { x: x + size * side, y: (a.y + b.y) / 2 },
    segments: [[a.x, a.y, x + ext * side, a.y], [b.x, b.y, x + ext * side, b.y],
               [x, a.y, x, b.y]],
    arrows: [{ x, y: a.y, dx: 0, dy: -dir }, { x, y: b.y, dx: 0, dy: dir }],
  };
}

/**
 * Cote entre deux points, selon l'endroit où le curseur la pose : à côté
 * des deux points → verticale, au-dessus ou au-dessous → horizontale,
 * entre eux ou en biais → alignée. Coordonnées locales de l'esquisse.
 */
export function pointPairDimKind(a, b, cursor) {
  const tolerance = 1e-9;
  const besideX = cursor.x < Math.min(a.x, b.x) - tolerance
    || cursor.x > Math.max(a.x, b.x) + tolerance;
  const besideY = cursor.y < Math.min(a.y, b.y) - tolerance
    || cursor.y > Math.max(a.y, b.y) + tolerance;
  if (besideY && !besideX) return "DistanceX";
  if (besideX && !besideY) return "DistanceY";
  return "Distance";
}

/** Aperçu de cette cote : la polyligne A → attache → attache → B, la
 *  ligne de cote passant par le curseur. */
export function pointPairDimPath(a, b, kind, cursor) {
  if (kind === "DistanceX") {
    return [a, { x: a.x, y: cursor.y }, { x: b.x, y: cursor.y }, b];
  }
  if (kind === "DistanceY") {
    return [a, { x: cursor.x, y: a.y }, { x: cursor.x, y: b.y }, b];
  }
  const d = unit(b.x - a.x, b.y - a.y);
  if (!d) return [a, b];
  const n = { x: -d.y, y: d.x };
  const off = (cursor.x - a.x) * n.x + (cursor.y - a.y) * n.y;
  return [a, { x: a.x + n.x * off, y: a.y + n.y * off },
          { x: b.x + n.x * off, y: b.y + n.y * off }, b];
}

/** Cote directe de A à B (point → ligne, lignes parallèles). */
function directDim(a, b, size) {
  const d = unit(b.x - a.x, b.y - a.y);
  if (!d) return null;
  const n = { x: -d.y, y: d.x };
  return {
    label: { x: (a.x + b.x) / 2 + n.x * size, y: (a.y + b.y) / 2 + n.y * size },
    segments: [[a.x, a.y, b.x, b.y]],
    arrows: [
      { x: a.x, y: a.y, dx: -d.x, dy: -d.y },
      { x: b.x, y: b.y, dx: d.x, dy: d.y },
    ],
  };
}

function projectOnLine(p, line) {
  const ax = line.p1[0], ay = line.p1[1];
  const vx = line.p2[0] - ax, vy = line.p2[1] - ay;
  const len2 = vx * vx + vy * vy;
  if (len2 < 1e-18) return { x: ax, y: ay };
  const u = ((p.x - ax) * vx + (p.y - ay) * vy) / len2;
  return { x: ax + u * vx, y: ay + u * vy };
}

/** Direction de lecture d'un rayon ou d'un diamètre : 45°, ou le milieu
 *  d'un arc. */
function radialDirection(entity) {
  if (entity.type === "arc" && entity.p1 && entity.p2 && entity.c) {
    const a1 = Math.atan2(entity.p1[1] - entity.c[1], entity.p1[0] - entity.c[0]);
    let a2 = Math.atan2(entity.p2[1] - entity.c[1], entity.p2[0] - entity.c[0]);
    if (a2 <= a1) a2 += Math.PI * 2;
    const a = (a1 + a2) / 2;
    return { x: Math.cos(a), y: Math.sin(a) };
  }
  return { x: Math.SQRT1_2, y: Math.SQRT1_2 };
}

function lineDirFrom(line, origin) {
  const m = { x: (line.p1[0] + line.p2[0]) / 2, y: (line.p1[1] + line.p2[1]) / 2 };
  return unit(m.x - origin.x, m.y - origin.y)
    ?? unit(line.p2[0] - line.p1[0], line.p2[1] - line.p1[1]);
}

function angleDim(l1, l2, size) {
  const x1 = l1.p1[0], y1 = l1.p1[1];
  const v1x = l1.p2[0] - x1, v1y = l1.p2[1] - y1;
  const x2 = l2.p1[0], y2 = l2.p1[1];
  const v2x = l2.p2[0] - x2, v2y = l2.p2[1] - y2;
  const den = v1x * v2y - v1y * v2x;
  if (Math.abs(den) < 1e-12) return null;
  const s = ((x2 - x1) * v2y - (y2 - y1) * v2x) / den;
  const o = { x: x1 + s * v1x, y: y1 + s * v1y };
  const d1 = lineDirFrom(l1, o);
  const d2 = lineDirFrom(l2, o);
  if (!d1 || !d2) return null;
  let a1 = Math.atan2(d1.y, d1.x);
  let a2 = Math.atan2(d2.y, d2.x);
  let sweep = a2 - a1;
  while (sweep > Math.PI) sweep -= Math.PI * 2;
  while (sweep < -Math.PI) sweep += Math.PI * 2;
  const r = size * 4;
  const segments = [];
  const steps = 16;
  for (let i = 0; i < steps; i++) {
    const t0 = a1 + sweep * (i / steps);
    const t1 = a1 + sweep * ((i + 1) / steps);
    segments.push([o.x + r * Math.cos(t0), o.y + r * Math.sin(t0),
                   o.x + r * Math.cos(t1), o.y + r * Math.sin(t1)]);
  }
  const mid = a1 + sweep / 2;
  const sign = Math.sign(sweep) || 1;
  a2 = a1 + sweep;
  return {
    label: { x: o.x + (r + size) * Math.cos(mid), y: o.y + (r + size) * Math.sin(mid) },
    segments,
    arrows: [
      { x: o.x + r * Math.cos(a1), y: o.y + r * Math.sin(a1),
        dx: Math.sin(a1) * sign, dy: -Math.cos(a1) * sign },
      { x: o.x + r * Math.cos(a2), y: o.y + r * Math.sin(a2),
        dx: -Math.sin(a2) * sign, dy: Math.cos(a2) * sign },
    ],
  };
}

/**
 * Tracé complet d'une cote d'esquisse. `constraint` vient de
 * sketch_state.constraints (geos, pos) ; sans lui, ou pour un cas non
 * prévu, seul le libellé est placé (ancrage historique).
 */
export function dimGeometry(dim, constraint, entities, size = 2) {
  // -1 : l'origine de l'esquisse, un point (cote depuis l'origine).
  const byId = (id) => (id === -1 ? ORIGIN
    : (entities ?? []).find((e) => e.id === id) ?? null);
  const fallback = () => {
    const anchor = sketchDimAnchor(dim, entities);
    return anchor ? { label: anchor, segments: [], arrows: [] } : null;
  };
  const [g1, g2] = constraint?.geos ?? [dim.geo, null];
  const [p1, p2] = constraint?.pos ?? [0, 0];
  const e1 = byId(g1);
  const e2 = g2 != null && g2 >= -1 ? byId(g2) : null;
  let out = null;
  if (dim.type === "Distance" && e1) {
    if (!e2 && e1.type === "line" && !p1) {
      out = alignedDim(pointOf(e1, 1), pointOf(e1, 2), entities, size,
        dim.offset);
    } else if (e2 && p1 && p2) {
      const a = pointOf(e1, p1), b = pointOf(e2, p2);
      if (a && b) out = alignedDim(a, b, entities, size, dim.offset);
    } else if (e2 && p1 && e2.type === "line") {
      const a = pointOf(e1, p1);
      if (a) out = directDim(a, projectOnLine(a, e2), size);
    }
  } else if ((dim.type === "DistanceX" || dim.type === "DistanceY")
             && e1 && e2 && p1 && p2) {
    const a = pointOf(e1, p1), b = pointOf(e2, p2);
    if (a && b) out = axisDim(a, b, dim.type, size, dim.offset);
  } else if ((dim.type === "Radius" || dim.type === "Diameter")
             && e1?.c && e1.r != null) {
    const dir = radialDirection(e1);
    const c = { x: e1.c[0], y: e1.c[1] };
    const rim = { x: c.x + dir.x * e1.r, y: c.y + dir.y * e1.r };
    const label = { x: c.x + dir.x * (e1.r + size * 2),
                    y: c.y + dir.y * (e1.r + size * 2) };
    if (dim.type === "Radius") {
      out = {
        label,
        segments: [[c.x, c.y, rim.x, rim.y], [rim.x, rim.y, label.x, label.y]],
        arrows: [{ x: rim.x, y: rim.y, dx: dir.x, dy: dir.y }],
      };
    } else {
      const opp = { x: c.x - dir.x * e1.r, y: c.y - dir.y * e1.r };
      out = {
        label,
        segments: [[opp.x, opp.y, rim.x, rim.y], [rim.x, rim.y, label.x, label.y]],
        arrows: [
          { x: rim.x, y: rim.y, dx: dir.x, dy: dir.y },
          { x: opp.x, y: opp.y, dx: -dir.x, dy: -dir.y },
        ],
      };
    }
  } else if (dim.type === "Angle" && e1?.type === "line"
             && e2?.type === "line") {
    out = angleDim(e1, e2, size);
  }
  return out ?? fallback();
}

/** Les deux traits d'une pointe de flèche, en segments. */
export function arrowSegments(arrow, length) {
  const segs = [];
  for (const sign of [1, -1]) {
    const a = Math.PI * (1 - sign * 0.14);
    const cos = Math.cos(a), sin = Math.sin(a);
    const bx = arrow.dx * cos - arrow.dy * sin;
    const by = arrow.dx * sin + arrow.dy * cos;
    segs.push([arrow.x, arrow.y, arrow.x + bx * length, arrow.y + by * length]);
  }
  return segs;
}

/** Position 2D d'une cote d'esquisse, dans le plan de l'esquisse. */
export function sketchDimAnchor(dim, entities) {
  const entity = (entities ?? []).find((item) => item.id === dim.geo);
  if (!entity) return null;
  if (entity.type === "line" && entity.p1 && entity.p2) {
    return {
      x: (entity.p1[0] + entity.p2[0]) / 2,
      y: (entity.p1[1] + entity.p2[1]) / 2 + 4,
    };
  }
  const center = entity.c || [0, 0];
  const radius = entity.r ?? 0;
  return { x: center[0] + radius * 0.7, y: center[1] + radius * 0.7 };
}

/**
 * Champ d'édition de cote — le même en esquisse et hors esquisse.
 * `onApply(values, { shown, isSketchAngle })` envoie sketch_set_dim
 * ou set_params selon l'appelant.
 */
export function openDimEditor({ panel, dim, onApply, onCancel }) {
  const isSketchAngle = dim.kind === "sketch" && dim.type === "Angle";
  const shown = dim.expr
    || (isSketchAngle
      ? (dim.value * 180 / Math.PI).toFixed(2)
      : String(+Number(dim.value).toFixed(4)));
  const unit = isSketchAngle || dim.unit === "°" ? "°" : (dim.unit || "mm");
  panel.open({
    icon: "Constraint_Dimension",
    title: t("Cote") + (dim.name ? ` — ${dim.name}` : ""),
    groups: [{
      label: t("Cote"),
      rows: [
        { type: "text", key: "name", label: t("Nom"), value: dim.name || "",
          placeholder: t("largeur"),
          showIf: () => dim.kind === "sketch" },
        { type: "text", key: "value", label: t("Valeur ou expression"),
          value: shown, unit },
      ],
    }],
    note: t("Expression : « Variables.Largeur / 2 » ou " +
          "« .Constraints.largeur * 2 » (les noms de cotes de cette " +
          "esquisse s'utilisent avec .Constraints.nom)"),
    onApply: (values) => onApply(values, { shown, isSketchAngle }),
    onCancel,
  });
}

export function dimEditPayload(values, dim, { shown, isSketchAngle }) {
  const payload = {};
  if (dim.kind === "sketch") {
    const name = (values.name ?? "").trim();
    if (name !== (dim.name ?? "")) payload.name = name;
  }
  const raw = String(values.value ?? "").trim();
  if (raw && raw !== shown) {
    const parsed = simpleDecimal(raw);
    if (parsed != null) {
      payload.value = isSketchAngle ? parsed * Math.PI / 180 : parsed;
    } else {
      payload.expr = raw;
    }
  }
  return payload;
}
