// Menu contextuel de la zone graphique — module pur.
//
// Clic droit sur la géométrie : les actions qui portent sur ce qu'on
// vise (face, arête, esquisse), puis la fonction qui l'a produite, puis
// la vue. En esquisse : les outils de tracé et la sortie d'esquisse.
// Chaque entrée porte une clé d'action ; main.js relie la clé à la
// commande existante. Les libellés sont en français (langue source) et
// passent par t() au rendu.
//
// Entrée : { key, label } | { header } | { separator: true }
// | { bar: [clé…] } (rangée d'icônes en tête du menu : les actions sur ce
// qu'on vise), `danger: true` pour une action destructive.

const SEP = { separator: true };

/** Libellés des actions de la rangée d'icônes (infobulles). */
const ACTION_LABELS = {
  "sketch-on-face": "Esquisse sur cette face",
  "normal-to": "Normal à (Ctrl+8)",
  fillet: "Congé",
  chamfer: "Chanfrein",
  shell: "Coque",
  measure: "Mesurer",
  "edit-feature": "Modifier la fonction",
  "edit-sketch": "Modifier l'esquisse",
  pad: "Extrusion",
  pocket: "Enlèvement extrudé",
  revolve: "Révolution",
};

/** Icône de chaque action (fichier de app/icons/). */
const MENU_ICONS = {
  "sketch-on-face": "fs_sketch.svg",
  "normal-to": "fs_normal_to.svg",
  fillet: "fs_fillet.svg",
  chamfer: "fs_chamfer.svg",
  shell: "fs_shell.svg",
  measure: "fs_measure.svg",
  "edit-feature": "fs_edit.svg",
  "edit-sketch": "fs_sketch.svg",
  pad: "nodes_extrude.svg",
  pocket: "fs_pocket.svg",
  revolve: "fs_revolve.svg",
  "edit-surface": "fs_edit.svg",
  rollback: "fs_rollback.svg",
  "delete-feature": "fs_delete.svg",
  "zoom-fit": "fs_zoom_fit.svg",
  orient: "fs_orient.svg",
  origin: "fs_origin.svg",
  "sk-select": "fs_select.svg",
  "sk-line": "nodes_line.svg",
  "sk-rect": "fs_rect.svg",
  "sk-circle": "nodes_circle.svg",
  "sk-dim": "fs_dimension.svg",
  "sk-trim": "fs_trim.svg",
  "sk-finish": "fs_sketch_ok.svg",
  "sk-cancel": "fs_sketch_cancel.svg",
};

/** Fichier d'icône d'une action du menu, ou "" s'il n'y en a pas. */
export function menuIcon(key) {
  return MENU_ICONS[key] ?? "";
}

function viewSection(ctx) {
  return [
    { header: "Vue" },
    { key: "zoom-fit", label: "Zoom au mieux (F)" },
    { key: "orient", label: "Orientation… (Espace)" },
    { key: "origin", label: ctx.originShown ? "Masquer l'origine" : "Afficher l'origine" },
  ];
}

function featureSection(feature) {
  if (!feature) return [];
  const items = [
    { header: feature.label },
    { key: "edit-feature", label: "Modifier la fonction" },
  ];
  if (feature.sketch) items.push({ key: "edit-sketch", label: "Modifier l'esquisse" });
  items.push(
    { key: "rollback", label: "Amener la barre de retour ici" },
    { key: "delete-feature", label: "Supprimer", danger: true },
  );
  return items;
}

/** Barre d'icônes contextuelle : les actions les plus courantes sur ce
 *  qu'un clic gauche vient de sélectionner (clés du menu ci-dessous). */
export function contextToolbarKeys(hit) {
  if (hit?.kind === "face") {
    return ["sketch-on-face", "normal-to", "fillet", "chamfer", "shell",
      ...(hit.feature ? ["edit-feature"] : [])];
  }
  if (hit?.kind === "edge") return ["fillet", "chamfer", "measure"];
  if (hit?.kind === "sketch") return ["edit-sketch", "pad", "pocket", "revolve"];
  return [];
}

/** Libellé d'infobulle d'une clé, repris du menu contextuel. */
export function viewMenuLabel(key, ctx = {}) {
  if (ACTION_LABELS[key]) return ACTION_LABELS[key];
  for (const item of viewMenuItems(ctx)) {
    if (item.key === key) return item.label;
  }
  return key;
}

/** Place le menu sous le pointeur. S'il est plus haut que la place
 *  en dessous, il s'ouvre au-dessus. S'il ne tient nulle part,
 *  `maxHeight` le borne sous le ruban (`topLimit`) : le menu défile
 *  au lieu de le recouvrir. Pixels, origine en haut à gauche. */
export function placeViewMenu({
  x, y, width, height,
  viewportWidth, viewportHeight,
  topLimit = 0,
  margin = 4,
}) {
  const bottom = viewportHeight - margin;
  const ceiling = topLimit + margin;
  const spaceBelow = bottom - y;
  const spaceAbove = y - ceiling;
  let top;
  let maxHeight;
  if (height <= spaceBelow) {
    top = y;
    maxHeight = spaceBelow;
  } else if (height <= spaceAbove) {
    top = y - height;
    maxHeight = spaceAbove;
  } else if (spaceAbove > spaceBelow) {
    maxHeight = Math.max(0, spaceAbove);
    top = y - maxHeight;
  } else {
    maxHeight = Math.max(0, spaceBelow);
    top = y;
  }
  if (top < ceiling) top = ceiling;
  if (top + maxHeight > bottom) maxHeight = Math.max(0, bottom - top);
  const minLeft = margin;
  const maxLeft = Math.max(minLeft, viewportWidth - width - margin);
  const left = Math.min(Math.max(x, minLeft), maxLeft);
  return { left, top, maxHeight };
}

export function viewMenuItems(ctx = {}) {
  if (ctx.mode === "sketch") {
    return [
      { header: "Esquisse" },
      { key: "sk-select", label: "Sélectionner" },
      { key: "sk-line", label: "Ligne (L)" },
      { key: "sk-rect", label: "Rectangle (R)" },
      { key: "sk-circle", label: "Cercle (C)" },
      { key: "sk-dim", label: "Cotation (D)" },
      { key: "sk-trim", label: "Ajuster (T)" },
      SEP,
      { key: "sk-finish", label: "Fermer l'esquisse" },
      { key: "sk-cancel", label: "Quitter sans garder", danger: true },
      SEP,
      { key: "zoom-fit", label: "Zoom au mieux (F)" },
    ];
  }
  // Ce qu'on vise : une rangée d'icônes (les actions qui portent dessus),
  // puis la fonction qui l'a produite, puis la vue. Annuler, rétablir et
  // reconstruire restent dans l'accès rapide et au clavier.
  const hit = ctx.hit ?? null;
  let items = [];
  if (hit?.kind === "face") {
    items = [
      { bar: ["sketch-on-face", "normal-to", "fillet", "chamfer", "shell", "measure"] },
      ...featureSection(hit.feature),
    ];
  } else if (hit?.kind === "edge") {
    items = [{ bar: ["fillet", "chamfer", "measure"] }];
  } else if (hit?.kind === "sketch") {
    items = [
      { header: hit.label ?? "Esquisse" },
      { bar: ["edit-sketch", "pad", "pocket", "revolve"] },
    ];
  } else if (hit?.kind === "surface") {
    items = [
      { header: hit.label ?? "Surface" },
      { key: "edit-surface", label: "Modifier" },
    ];
  }
  if (items.length) items.push(SEP);
  return [...items, ...viewSection(ctx)];
}
