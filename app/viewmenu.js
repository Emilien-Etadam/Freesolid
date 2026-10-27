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
// qu'on vise), `danger: true` pour une action destructive, `checked: true`
// pour un choix en cours.

import { SNAP_KINDS } from "./sketchsnap.js";

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
  "face-color": "Couleur de la face…",
};

/** Rôle d'icône de chaque action (table de icons.js). */
const MENU_ICONS = {
  "sketch-on-face": "sketch",
  "normal-to": "normal_to",
  fillet: "fillet",
  chamfer: "chamfer",
  shell: "shell",
  measure: "measure",
  "edit-feature": "edit",
  "edit-sketch": "sketch",
  pad: "nodes_extrude",
  pocket: "pocket",
  revolve: "revolve",
  "edit-surface": "edit",
  rollback: "rollback",
  "select-tangent": "sel_tangent",
  "face-color": "face_color",
  "face-color-reset": "face_color",
  "select-loop": "sel_loop",
  "delete-feature": "delete",
  "zoom-fit": "zoom_fit",
  orient: "orient",
  origin: "origin",
  "sk-select": "select",
  "sk-line": "nodes_line",
  "sk-rect": "rect",
  "sk-circle": "nodes_circle",
  "sk-dim": "dimension",
  "sk-trim": "trim",
  "sk-finish": "sketch_ok",
  "sk-cancel": "sketch_cancel",
  ...Object.fromEntries(SNAP_KINDS.map((k) => ["snap-" + k.key, k.icon])),
  "snap-none": "sketch_cancel",
  "snap-settings": "sk_snap",
};

/** Rôle d'icône d'une action du menu, ou "" s'il n'y en a pas. */
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

/** Pendant un tracé : l'accrochage rapide, une sorte pour l'entité en
 *  cours (`ctx.quickSnap` : celle choisie), et le réglage. */
function quickSnapSection(ctx) {
  if (!ctx.drawing) return [];
  const quick = ctx.quickSnap ?? null;
  return [
    { header: "Accrochage rapide" },
    ...SNAP_KINDS.map((k) => ({ key: "snap-" + k.key, label: k.label,
      ...(quick?.kind === k.key ? { checked: true } : {}) })),
    ...(quick ? [{ key: "snap-none", label: "Retirer l'accrochage rapide" }] : []),
    { key: "snap-settings", label: "Réglages des accrochages…" },
    SEP,
  ];
}

export function viewMenuItems(ctx = {}) {
  if (ctx.mode === "sketch") {
    return [
      ...quickSnapSection(ctx),
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
      { bar: ["sketch-on-face", "normal-to", "fillet", "chamfer", "shell",
        "measure", "face-color"] },
      ...(hit.colored ? [{ key: "face-color-reset", label: "Couleur de face par défaut" }] : []),
      ...featureSection(hit.feature),
    ];
  } else if (hit?.kind === "edge") {
    items = [
      { bar: ["fillet", "chamfer", "measure"] },
      { key: "select-tangent", label: "Sélectionner la chaîne tangente" },
      { key: "select-loop", label: "Sélectionner la boucle (encore : l'autre face)" },
    ];
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
