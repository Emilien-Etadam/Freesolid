// Ce qu'une ligne de l'arbre rouvre au double-clic : le nom de son
// éditeur, ou null quand rien ne s'y réédite. Le double-clic (tree.js)
// et « Modifier » (menus de l'arbre et de la vue) lisent ces deux
// fonctions : le menu ne propose plus ce que le double-clic refuse, ni
// ne cache ce qu'il ouvre.
//
// `has_params` vient du moteur : vrai quand get_params a au moins une
// cote. Absent (ligne d'un plugin, ligne reconstruite à la main), on
// tente get_params, comme avant.

import { isGraphFeature, isRepeatFeature } from "./graph.js";

const params = (item) => (item.has_params === false ? null : "params");

/** Fonction de corps, esquisse, suppression ou réseau de corps. */
export function featureEditor(item) {
  if (!item?.type_key || typeof item.active === "boolean") return null;
  // La répétition qui porte la ligne, si elle a de quoi se rééditer.
  if (item.edits) return item.edits_has_params === false ? null : "edits";
  if (isGraphFeature(item) || isRepeatFeature(item)) return "graph";
  if (item.type_key === "sketch") return "sketch";
  if (item.vertex_chamfer) return "vertex_chamfer";
  if (item.text) return "text";
  if (item.surface_cut) return "surface_cut";
  if (item.type_key === "chamfer" && item.chamfer) return "chamfer";
  if ((item.type_key === "revolution" || item.type_key === "groove")
      && item.revolution) return "revolution";
  if ((item.type_key === "pad" || item.type_key === "pocket")
      && item.extrude) return "extrude";
  if (item.type_key === "thickness" && item.shell) return "shell";
  if (item.type_key === "hole" && item.hole) return "hole";
  if (item.type_key === "remove_bodies") return "remove_bodies";
  return params(item);
}

/** Surface ou courbe hors corps. Une surface figée ne se réédite pas. */
export function surfaceEditor(item) {
  if (!item) return null;
  if (isGraphFeature(item) || isRepeatFeature(item)) return "graph";
  if (item.curve) return "curve3d";
  if (item.sketch3d) return "sketch3d";
  const kind = item.surface?.kind;
  if (kind === "extend") return "extend";
  if (kind === "trim") return "trim";
  if (kind === "offset") return "offset";
  if (kind === "fillet") return "surface_fillet";
  if (kind === "freeform") return item.surface.moves ? "poles" : "freeform";
  if (kind === "flatten") return "flatten";
  if (isFrozen(item)) return null;
  // Radiée : distance et sens, comme à la création.
  if (item.type_key === "surface_radiate") return params(item) && "radiate";
  return params(item);
}

/** Forme figée : calculée une fois, sans cotes. */
export function isFrozen(item) {
  return !!(item?.static || item?.type_key === "shape");
}

/** La ligne `name` est-elle une surface de l'arbre ? */
export function isSurfaceRow(tree, name) {
  return (tree?.surfaces ?? []).some((surface) => surface.name === name);
}
