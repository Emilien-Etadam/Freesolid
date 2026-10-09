// Style d'affichage et visibilité de la barre de vue.
// Module pur : main.js applique le résultat sur la scène.

export const DISPLAY_KEY = "freesolid.display";

export const DISPLAY_STYLES = ["shaded-edges", "shaded", "wireframe", "hidden"];

const DEFAULTS = {
  style: "shaded-edges",
  planes: false,
  origin: false,
  sketches: true,
  edges: true,
};

export function defaultDisplay() {
  return { ...DEFAULTS };
}

/** Lit le réglage, ou les défauts si le stockage est vide ou illisible. */
export function readDisplay(storage) {
  const state = defaultDisplay();
  try {
    const raw = storage?.getItem(DISPLAY_KEY);
    if (!raw) return state;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return state;
    if (DISPLAY_STYLES.includes(parsed.style)) state.style = parsed.style;
    for (const key of ["planes", "origin", "sketches", "edges"]) {
      if (typeof parsed[key] === "boolean") state[key] = parsed[key];
    }
  } catch {
    return defaultDisplay();
  }
  return state;
}

export function writeDisplay(storage, state) {
  try {
    storage?.setItem(DISPLAY_KEY, JSON.stringify({
      style: state.style,
      planes: !!state.planes,
      origin: !!state.origin,
      sketches: !!state.sketches,
      edges: !!state.edges,
    }));
  } catch {
    // stockage indisponible : le réglage tient pour la session.
  }
}

/**
 * Ce que la scène doit montrer.
 * `mask` : le solide prend la couleur du fond pour cacher les arêtes derrière.
 * `edges` : l'aperçu des arêtes réelles. `ghostEdges` : les mêmes, estompées,
 * dessinées sans test de profondeur (lignes cachées).
 */
export function displayEffects(state) {
  const style = DISPLAY_STYLES.includes(state?.style) ? state.style : "shaded-edges";
  const edgesOn = state?.edges !== false;
  const wireframe = style === "wireframe";
  const hidden = style === "hidden";
  return {
    style,
    wireframe,
    mask: hidden,
    faces: style !== "wireframe",
    edges: wireframe || hidden ? edgesOn : (style === "shaded-edges" && edgesOn),
    ghostEdges: hidden && edgesOn,
    sketches: state?.sketches !== false,
    planes: !!state?.planes,
    origin: !!state?.origin,
  };
}
