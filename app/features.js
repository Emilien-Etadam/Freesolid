// Registry déclaratif des panneaux de fonctions mécaniques.
// Le branchement (clic → featureCommand → panel.open) vit dans main.js.
//
// Chaque entrée décrit un panneau « ouvrir → éditer → aperçu → OK ».
// build(v, ctx) rend { op, params } ou null (aperçu éteint, OK bloqué).
//
// Les entrées et leurs aides vivent par famille dans features/ : ce
// fichier les rassemble dans le même ordre et ré-exporte les aides
// publiques (des plugins importent dressup et hasSelection d'ici).

import { VOLUMES } from "./features/volumes.js";
import { HABILLAGE } from "./features/habillage.js";
import { REPETITIONS } from "./features/repetitions.js";
import { COMBINER } from "./features/combiner.js";
import { SURFACES } from "./features/surfaces.js";
import { NOEUDS } from "./features/noeuds.js";

export {
  availableSketches,
  dressup,
  hasSelection,
  NO_SKETCH_AVAILABLE,
  resolveProfileSketch,
} from "./features/commun.js";
export {
  checkedContours,
  contourLabel,
  contourRows,
  extrudeBuild,
  extrudeGroups,
  extrudeInvalid,
  holePositions,
  revolutionAxisOptions,
  revolutionCreationParams,
  revolutionEditValues,
  revolutionGroups,
  revolutionProblem,
} from "./features/volumes.js";
export {
  chamferCreationParams,
  chamferEditValues,
  chamferFieldValue,
  chamferProblem,
  chamferRows,
  shellBuild,
  vertexChamferDistances,
  vertexChamferRows,
} from "./features/habillage.js";
export {
  linearSecondDirection,
  patternDirectionParams,
  patternDirectionRows,
  patternFeaturesGroup,
  patternFeaturesParams,
} from "./features/repetitions.js";
export {
  boundaryParam,
  deleteFacesBuild,
  deleteFacesParams,
  extendParams,
  freeformParams,
  midParams,
  surfaceCutParams,
  surfaceFilletParams,
  trimParams,
} from "./features/surfaces.js";

export const FEATURES = [
  ...VOLUMES,
  ...HABILLAGE,
  ...REPETITIONS,
  ...COMBINER,
  ...SURFACES,
  ...NOEUDS,
];
