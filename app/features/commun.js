// Fonctions — aides partagées entre familles : esquisse de profil,
// sélection, panneaux d'habillage, cotes rééditables.

import { t } from "../i18n.js";
import { plainNumber } from "../num.js";

/** Message moteur quand aucune esquisse libre n'est disponible (d'un
 *  seul tenant : c'est aussi la clé de traduction). */
export const NO_SKETCH_AVAILABLE =
  "aucune esquisse disponible — les esquisses existantes sont déjà utilisées par des fonctions, dessinez-en une nouvelle";

/** Esquisses libres (non consommées) dans l'ordre du corps — comme
 *  `_latest_sketch` côté moteur. */
export function availableSketches(tree) {
  return (tree?.features ?? []).filter(
    (f) => f.type_key === "sketch" && !f.rolled_back);
}

function latestAvailableSketch(tree) {
  const sketches = availableSketches(tree);
  return sketches.length ? sketches[sketches.length - 1] : null;
}

/** Profil affiché / utilisé : sélection d'arbre sinon dernière libre. */
export function resolveProfileSketch(ctx) {
  if (ctx.selectedSketch?.name) return ctx.selectedSketch;
  return latestAvailableSketch(ctx.lastTree);
}

export function hasSelection(sel) {
  return !!sel && (sel.kind === "edges"
    ? sel.edges.length > 0 : sel.face != null);
}

/** Consigne : rien n'est encore choisi. Ce n'est pas une erreur. */
function clickFirst(title) {
  return {
    text: t("{f} : cliquez d'abord dans la zone graphique", { f: t(title) }),
    tone: "guide",
  };
}

export function dressup({ button, op, icon, title, selectionLabel, group, rows,
                   build, accepts = ["face"], hint, note, noteFn, invalid }) {
  return {
    button, op, icon, title,
    dressup: true,
    note,
    noteFn,
    groups: (ctx) => [
      { label: selectionLabel,
        rows: [{ type: "selection", key: "sel", accepts, hint,
                 value: ctx.selection(accepts) }] },
      { label: group, rows },
    ],
    build: (v, ctx) => hasSelection(v.sel) ? build(v, ctx) : null,
    invalid: (v, ctx) => {
      if (!hasSelection(v.sel)) return clickFirst(title);
      if (typeof invalid === "function") return invalid(v, ctx);
      return invalid ?? "Valeur invalide";
    },
    refresh: "part",
  };
}

export function measureRow(key, label, value, unit, showIf) {
  const parsed = plainNumber(value);
  const row = parsed == null
    ? { type: "text", key, label, unit, value: String(value ?? "") }
    : { type: "number", key, label, unit, value: parsed, min: 0.01 };
  if (showIf) row.showIf = showIf;
  return row;
}

export function storedMeasure(params, key, fallback) {
  const found = (params ?? []).find((item) => item.key === key);
  if (found?.expr) return { expr: String(found.expr) };
  if (found && found.value != null) return { numeric: Number(found.value) };
  const parsed = plainNumber(fallback);
  return parsed == null
    ? { expr: String(fallback ?? "") }
    : { numeric: parsed };
}

export function readMeasure(raw, stored, bounds) {
  const text = typeof raw === "string" ? raw.trim() : raw;
  if (stored.expr && String(text ?? "").trim() === stored.expr) return stored.expr;
  const parsed = plainNumber(text);
  if (parsed == null) {
    const expr = String(text ?? "").trim();
    return expr ? expr : null;
  }
  if (!(parsed > bounds.min) || !(parsed < bounds.max)) return null;
  return parsed;
}

export function sameMeasure(value, stored) {
  if (typeof value === "string") return stored.expr === value;
  return stored.numeric != null && Math.abs(value - stored.numeric) < 1e-9;
}
