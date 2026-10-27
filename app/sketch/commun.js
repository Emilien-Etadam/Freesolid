// Esquisse : ce que partagent sketch.js et les modules de app/sketch/.

import { readScene } from "../theme.js";

export const sceneTheme = readScene();

/** Le point racine du moteur : l'origine de l'esquisse (point 1). */
export { ORIGIN_GEO } from "../sketchsnap.js";
