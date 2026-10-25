// Genres d'objets du moteur (`type_key`), regroupés par famille.
//
// Le moteur envoie pour chaque objet un genre neutre (« pad », « sketch »,
// « surface_extrude »…) tiré de sa table (engine/vocab.py, TYPE_KEYS).
// L'interface ne lit jamais le type propre au modeleur ; quand elle doit
// savoir à quelle famille un objet appartient, elle le lit ici.
// tests/test_type_keys.py vérifie que ces listes suivent la table.

/** Fonctions de corps : volumes, références, lieurs, corps. « feature » est
 *  le genre d'une fonction de corps que la table ne nomme pas. */
export const BODY_FEATURE_KEYS = new Set([
  "pad", "pocket", "revolution", "groove", "loft", "loft_cut", "sweep",
  "sweep_cut", "helix", "helix_cut", "hole", "fillet", "chamfer", "draft",
  "thickness", "mirror", "linear_pattern", "polar_pattern", "boolean",
  "datum_plane", "datum_axis", "datum_point", "datum_cs", "binder", "body",
  "feature",
]);

/** Surfaces et courbes hors corps, formes figées comprises. « surface » est
 *  le genre d'une surface que la table ne nomme pas. */
export const SURFACE_KEYS = new Set([
  "shape", "surface_extrude", "surface_revolve", "surface_loft",
  "surface_sweep", "surface_offset", "surface_planar", "surface_ruled",
  "surface_fillet", "surface_radiate", "surface_trim", "curve_intersection",
  "curve_project", "curve_helix", "surface_fill", "surface_extend",
  "surface_boundary", "surface",
]);

/** Fonction de corps (ou corps). */
export function isBodyFeatureKey(key) {
  return BODY_FEATURE_KEYS.has(key);
}

/** Surface ou courbe hors corps. */
export function isSurfaceKey(key) {
  return SURFACE_KEYS.has(key);
}
