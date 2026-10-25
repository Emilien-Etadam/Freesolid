// Découpe de l'historique autour de la barre de retour.
// Module pur — testable en Node, sans DOM.

// Pas d'annulation (op du moteur) → libellé de la liste d'historique.
export const STEP_LABELS = {
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
  delete_rolled_back: "Supprimer sous la barre",
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
  // Ces ops tombaient sur le repli générique : même texte, désormais
  // explicite (tests/js/coherence.test.mjs). Un libellé précis viendra.
  add_curve3d: "Fonction", add_delete_face: "Fonction",
  add_graph_feature: "Fonction", add_repeat_feature: "Fonction",
  add_replace_face: "Fonction", add_sketch3d: "Fonction",
  add_surface_cut: "Fonction", add_vertex_chamfer: "Fonction",
  array_component: "Modification", edit_curve3d: "Modification",
  edit_graph_feature: "Modification", edit_repeat_feature: "Modification",
  edit_sketch3d: "Modification", edit_surface_cut: "Modification",
  edit_surface_extend: "Modification", edit_surface_fillet: "Modification",
  edit_surface_freeform: "Modification", edit_surface_trim: "Modification",
  edit_text: "Modification", edit_vertex_chamfer: "Modification",
  make_drawing: "Modification", set_body_material: "Modification",
  set_component_grounded: "Modification",
  set_configuration_values: "Modification", set_face_color: "Modification",
  set_suppressed: "Modification", solve_assembly: "Modification",
};

/** Familles d'ops nommées par préfixe : une ligne commune suffit. */
export const STEP_PREFIXES = [
  ["sketch_", "Modification d'esquisse"],
  ["surface_", "Surface"],
  ["curve_", "Surface"],
];

/** Libellé (français, traduit à l'affichage) d'un pas d'annulation. */
export function undoStepLabel(op) {
  if (Object.hasOwn(STEP_LABELS, op)) return STEP_LABELS[op];
  const family = STEP_PREFIXES.find(([prefix]) => op.startsWith(prefix));
  if (family) return family[1];
  // Repli des ops hors catalogue (plugins) ; une op du noyau n'y tombe
  // pas (tests/js/coherence.test.mjs).
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

/** Rang d'une ligne : son `order` (index document), sinon après tout. */
function rowRank(row) {
  return typeof row.item.order === "number" ? row.item.order : row.index + 1e6;
}

function byRank(a, b) {
  const ra = rowRank(a);
  const rb = rowRank(b);
  if (ra !== rb) return ra - rb;
  return a.index - b.index;
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
  rows.sort(byRank);
  return rows;
}

/** Esquisses sorties par la barre (`unabsorbed`) des fonctions reculées :
 *  des lignes au-dessus d'elle, chacune à son rang. La ligne de la
 *  fonction devient une copie, sans elles. */
function liftChildren(sides) {
  const lifted = [];
  const seen = new Set();
  for (const [i, row] of sides.after.entries()) {
    if (row.surface) continue;
    const children = row.item.children ?? [];
    const lift = children.filter((child) => child.unabsorbed);
    if (!lift.length) continue;
    sides.after[i] = { ...row, item: {
      ...row.item, children: children.filter((child) => !lift.includes(child)),
    } };
    for (const child of lift) {
      if (seen.has(child.name)) continue; // partagée : une seule ligne
      seen.add(child.name);
      lifted.push({
        item: child, surface: false, index: row.index, parent: row.item.name,
      });
    }
  }
  if (!lifted.length) return;
  sides.before.push(...lifted);
  sides.before.sort(byRank);
}

/** Sépare l'historique en `before` / `after` la barre de retour.
 *
 *  Une surface, une esquisse libre ou une référence (plan, axe, point)
 *  est *après* ssi `rolled_back` est vrai.
 *  Une fonction volumique est après le tip (tip absent + fonctions
 *  présentes = toutes après). Barre `"none"` si aucune ligne.
 *
 *  Une esquisse que la barre a sortie de sa fonction (`unabsorbed`) passe
 *  au-dessus, à son rang ; la fonction reste dessous, sans elle. */
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
  liftChildren({ before, after });
  return {
    bar: before.length === 0 ? "start" : "middle",
    before,
    after,
  };
}
