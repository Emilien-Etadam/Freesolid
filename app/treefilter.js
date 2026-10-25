// Filtre de l'arbre de création. Module pur — testable en Node, sans DOM.

/** Texte comparable : minuscules, sans accents. */
export function foldText(text) {
  return String(text ?? "").normalize("NFD").replace(/\p{M}/gu, "")
    .toLowerCase();
}

/** Lignes visibles sous le filtre `query`, dans l'ordre de `lines`.
 *
 *  `lines` : `{ label, parent, keep }` dans l'ordre de l'arbre ; `parent`
 *  est l'indice de la ligne parente (-1 au premier niveau, toujours avant
 *  l'enfant) ; `keep` garde la ligne quoi qu'il arrive (la barre de
 *  retour). Une ligne paraît si son libellé contient le texte cherché,
 *  sans tenir compte de la casse ni des accents, ou si un de ses enfants
 *  paraît. Filtre vide : tout paraît. */
export function filterTreeLines(lines, query) {
  const needle = foldText(query).trim();
  const visible = lines.map((line) => !needle || !!line.keep
    || foldText(line.label).includes(needle));
  if (!needle) return visible;
  lines.forEach((line, i) => {
    if (!visible[i] || line.keep) return;
    // Le parent précède l'enfant : ses ancêtres sont déjà traités s'il
    // était visible lui-même.
    for (let p = line.parent; p >= 0 && !visible[p]; p = lines[p].parent) {
      visible[p] = true;
    }
  });
  return visible;
}
