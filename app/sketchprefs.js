// Esquisse : les réglages d'affichage gardés d'une séance à l'autre — la
// vue tournée face au plan à l'ouverture, l'accrochage à la grille, les
// symboles de relation, les cotes, le peigne de courbure. Les boutons de
// la barre d'esquisse et les Paramètres changent le même réglage.

export const SKETCH_PREFS_KEY = "freesolid.sketchPrefs";

const DEFAULTS = {
  normalView: true,
  gridSnap: false,
  showRelations: true,
  showDims: true,
  showComb: false,
};

export function defaultSketchPrefs() {
  return { ...DEFAULTS };
}

/** Un réglage sûr : chaque clé connue, booléenne, sinon sa valeur par
 *  défaut. */
export function normalizeSketchPrefs(raw) {
  const prefs = defaultSketchPrefs();
  for (const key of Object.keys(DEFAULTS)) {
    if (typeof raw?.[key] === "boolean") prefs[key] = raw[key];
  }
  return prefs;
}

export function readSketchPrefs(storage) {
  let raw = null;
  try {
    raw = JSON.parse(storage?.getItem(SKETCH_PREFS_KEY) ?? "null");
  } catch {
    // stockage indisponible ou valeur abîmée : réglage par défaut.
  }
  return normalizeSketchPrefs(raw);
}

export function writeSketchPrefs(storage, prefs) {
  try {
    storage?.setItem(SKETCH_PREFS_KEY, JSON.stringify(normalizeSketchPrefs(prefs)));
    return true;
  } catch {
    return false;
  }
}
