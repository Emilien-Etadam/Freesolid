// Clic lent sur une ligne déjà choisie : au-delà d'un double-clic, le
// second clic renomme — s'il suit le premier de peu. Plus tard, c'est une
// simple sélection : un clic sur une ligne choisie depuis longtemps
// n'ouvre pas le champ (Suppr y viderait le nom au lieu de supprimer la
// fonction). Un glisser-déposer ne doit jamais ouvrir le champ.

export const RENAME_GAP_MS = 500;
export const RENAME_MAX_GAP_MS = 1500;

export function renameClickAction({
  previousAt, sameRow, now, moved = false, dragging = false,
}) {
  if (dragging || moved) return "ignore";
  const previous = Number(previousAt);
  if (!sameRow || !Number.isFinite(previous)) return "select";
  const gap = Number(now) - previous;
  if (gap < RENAME_GAP_MS) return "ignore";
  if (gap <= RENAME_MAX_GAP_MS) return "rename";
  return "select";
}
