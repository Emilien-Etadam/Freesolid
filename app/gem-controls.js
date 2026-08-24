// Commandes de diamètre d'une pierre : touches et boutons du ruban
// Bijouterie appellent le même pas. Module pur, sans FreeCAD ni DOM.

/** Pas clavier / boutons Ø − Ø + : 0,1 mm. */
export const GEM_STEP_MM = 0.1;

export const GEM_DIAMETRE_MINUS_TITLE = "Diamètre − 0,1 mm (↓)";
export const GEM_DIAMETRE_PLUS_TITLE = "Diamètre + 0,1 mm (↑)";
export const GEM_DIAMETRE_DISABLED_TITLE =
  "Sélectionnez une pierre pour régler le diamètre";

export function formatMmFr(value, digits = 2) {
  if (!Number.isFinite(value)) return "—";
  return value.toFixed(digits).replace(".", ",");
}

/** Delta de diamètre pour un keydown, ou 0 si la touche n'agit pas.
 *  `+` / `−` de la rangée du haut ne font rien : seuls ↑ / ↓ et
 *  le pavé numérique. */
export function gemDiametreDeltaFromKey(event) {
  if (!event || event.ctrlKey || event.metaKey || event.altKey) return 0;
  if (event.key === "ArrowUp" || event.code === "NumpadAdd") {
    return GEM_STEP_MM;
  }
  if (event.key === "ArrowDown" || event.code === "NumpadSubtract") {
    return -GEM_STEP_MM;
  }
  return 0;
}

/** Même delta que les flèches, pour `Ø −` / `Ø +`. */
export function gemDiametreDeltaFromButton(which) {
  if (which === "plus") return GEM_STEP_MM;
  if (which === "minus") return -GEM_STEP_MM;
  return 0;
}

/** État du groupe Réglage : boutons grisés sans pierre, libellé `Ø —`. */
export function gemRibbonState(hasSelection, diametre) {
  const selected = !!hasSelection;
  return {
    disabled: !selected,
    label: selected && Number.isFinite(diametre)
      ? `Ø ${formatMmFr(diametre)} mm`
      : "Ø —",
    minusTitle: selected
      ? GEM_DIAMETRE_MINUS_TITLE
      : GEM_DIAMETRE_DISABLED_TITLE,
    plusTitle: selected
      ? GEM_DIAMETRE_PLUS_TITLE
      : GEM_DIAMETRE_DISABLED_TITLE,
  };
}
