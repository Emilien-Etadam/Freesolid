// Menu contextuel de la zone graphique — module pur.
//
// Clic droit sur la géométrie : les actions qui portent sur ce qu'on
// vise (face, arête, esquisse), puis la fonction qui l'a produite, puis
// la vue. En esquisse : les outils de tracé et la sortie d'esquisse.
// Chaque entrée porte une clé d'action ; main.js relie la clé à la
// commande existante. Les libellés sont en français (langue source) et
// passent par t() au rendu.
//
// Entrée : { key, label } | { header } | { separator: true },
// `danger: true` pour une action destructive.

const SEP = { separator: true };

function viewSection(ctx) {
  return [
    { header: "Vue" },
    { key: "zoom-fit", label: "Zoom au mieux (F)" },
    { key: "orient", label: "Orientation… (Espace)" },
    { key: "origin", label: ctx.originShown ? "Masquer l'origine" : "Afficher l'origine" },
  ];
}

function editSection() {
  return [
    SEP,
    { key: "undo", label: "Annuler (Ctrl+Z)" },
    { key: "redo", label: "Rétablir (Ctrl+Y)" },
    { key: "rebuild", label: "Reconstruire" },
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
  for (const item of viewMenuItems(ctx)) {
    if (item.key === key) return item.label;
  }
  return key;
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
  const hit = ctx.hit ?? null;
  let items = [];
  if (hit?.kind === "face") {
    items = [
      { header: "Face" },
      { key: "sketch-on-face", label: "Esquisse sur cette face" },
      { key: "normal-to", label: "Normal à (Ctrl+8)" },
      { key: "fillet", label: "Congé" },
      { key: "chamfer", label: "Chanfrein" },
      { key: "shell", label: "Coque" },
      { key: "measure", label: "Mesurer" },
      ...featureSection(hit.feature),
    ];
  } else if (hit?.kind === "edge") {
    items = [
      { header: "Arête" },
      { key: "fillet", label: "Congé" },
      { key: "chamfer", label: "Chanfrein" },
      { key: "measure", label: "Mesurer" },
    ];
  } else if (hit?.kind === "sketch") {
    items = [
      { header: hit.label ?? "Esquisse" },
      { key: "edit-sketch", label: "Modifier l'esquisse" },
      { key: "pad", label: "Extrusion" },
      { key: "pocket", label: "Enlèvement extrudé" },
      { key: "revolve", label: "Révolution" },
    ];
  } else if (hit?.kind === "surface") {
    items = [
      { header: hit.label ?? "Surface" },
      { key: "edit-surface", label: "Modifier" },
    ];
  }
  if (items.length) items.push(SEP);
  return [...items, ...viewSection(ctx), ...editSection()];
}
