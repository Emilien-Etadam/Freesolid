// Découpe de l'historique autour de la barre de retour.
// Module pur — testable en Node, sans DOM.

// Pas d'annulation (op du moteur) → libellé de la liste d'historique.
const STEP_LABELS = {
  add_rect_sketch: "Esquisse rectangle",
  add_pad: "Extrusion",
  add_pocket: "Enlèvement extrudé",
  add_fillet: "Congé",
  add_chamfer: "Chanfrein",
  add_revolution: "Révolution",
  add_groove: "Enlèvement de révolution",
  add_mirror: "Symétrie",
  add_linear_pattern: "Répétition linéaire",
  add_polar_pattern: "Répétition circulaire",
  add_thickness: "Coque",
  add_draft: "Dépouille",
  add_hole: "Perçage",
  add_datum_plane: "Plan de référence",
  add_datum_axis: "Axe de référence",
  add_datum_point: "Point de référence",
  add_datum_cs: "Repère",
  add_loft: "Lissage",
  add_sweep: "Balayage",
  add_helix: "Hélice",
  add_body: "Corps",
  add_boolean: "Combiner",
  add_text: "Texte",
  set_body_color: "Couleur du corps",
  set_param: "Modifier la fonction",
  set_params: "Modifier la fonction",
  set_profile_contours: "Contours du profil",
  rename: "Renommer",
  set_variable: "Équations",
  delete_variable: "Équations",
  set_tip: "Barre de retour",
  tip_to_end: "Barre de retour",
  delete_feature: "Supprimer",
  reorder_feature: "Réordonner",
  set_comment: "Commentaire",
  paste_feature: "Coller",
  set_folder: "Dossier", rename_folder: "Dossier",
  add_configuration: "Configuration", activate_configuration: "Configuration",
  rename_configuration: "Configuration", delete_configuration: "Configuration",
  sketch_start: "Nouvelle esquisse",
  sketch_finish: "Fermer l'esquisse",
  insert_component: "Insérer un composant",
  move_component: "Déplacer un composant",
  add_joint: "Contrainte d'assemblage",
};

/** Libellé (français, traduit à l'affichage) d'un pas d'annulation. */
export function undoStepLabel(op) {
  if (STEP_LABELS[op]) return STEP_LABELS[op];
  if (op.startsWith("sketch_")) return "Modification d'esquisse";
  if (op.startsWith("surface_") || op.startsWith("curve_")) return "Surface";
  if (op.startsWith("add_")) return "Fonction";
  return "Modification";
}

/** Nombre de lignes d'arbre en erreur (fonctions, leurs esquisses,
 *  surfaces), chacune comptée une fois. */
export function countTreeErrors(tree) {
  const names = new Set();
  const visit = (items) => {
    for (const item of items ?? []) {
      if (item.error) names.add(item.name);
      visit(item.children);
    }
  };
  visit(tree?.features);
  visit(tree?.surfaces);
  return names.size;
}

/** Libellé d'esquisse dans l'arbre : (-) encore libre, (+) en trop. */
export function sketchTreeLabel(label, definition) {
  if (definition === "under") return `(-) ${label}`;
  if (definition === "over") return `(+) ${label}`;
  return label;
}

// Esquisses libres et géométrie de référence (plans, axes, points) :
// elles ne font pas le solide, la barre ne les recule que sur demande.
const REFERENCE_TYPES = new Set([
  "Sketcher::SketchObject", "PartDesign::Plane", "PartDesign::Line",
  "PartDesign::Point", "PartDesign::CoordinateSystem",
]);

function isVolumeRow(row) {
  return !row.surface && !REFERENCE_TYPES.has(row.item.type);
}

/** Lignes top-niveau (fonctions + esquisses libres + surfaces),
 *  ordonnées par `order` (index document). */
export function chronologicalHistory(features, surfaces) {
  const featureList = features ?? [];
  const surfaceList = surfaces ?? [];
  const rows = [];
  for (const [index, item] of featureList.entries()) {
    rows.push({ item, surface: false, index });
  }
  for (const [index, item] of surfaceList.entries()) {
    rows.push({ item, surface: true, index: featureList.length + index });
  }
  rows.sort((a, b) => {
    const oa = typeof a.item.order === "number" ? a.item.order : a.index + 1e6;
    const ob = typeof b.item.order === "number" ? b.item.order : b.index + 1e6;
    if (oa !== ob) return oa - ob;
    return a.index - b.index;
  });
  return rows;
}

/** Sépare l'historique en `before` / `after` la barre de retour.
 *
 *  Une surface, une esquisse libre ou une référence (plan, axe, point)
 *  est *après* ssi `rolled_back` est vrai.
 *  Une fonction volumique est après le tip (tip absent + fonctions
 *  présentes = toutes après). Barre `"none"` si aucune ligne. */
export function splitHistoryAroundBar(features, surfaces, tip) {
  const history = chronologicalHistory(features, surfaces);
  if (history.length === 0) {
    return { bar: "none", before: [], after: [] };
  }
  const hasVolume = history.some(isVolumeRow);
  const before = [];
  const after = [];
  let passedTip = false;
  for (const row of history) {
    if (!isVolumeRow(row)) {
      if (row.item.rolled_back) after.push(row);
      else before.push(row);
    } else if (!tip && hasVolume) {
      after.push(row);
    } else if (!passedTip) {
      before.push(row);
      if (row.item.name === tip) passedTip = true;
    } else {
      after.push(row);
    }
  }
  return {
    bar: before.length === 0 ? "start" : "middle",
    before,
    after,
  };
}
