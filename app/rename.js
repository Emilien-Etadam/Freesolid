// Clic lent sur une ligne déjà choisie : au-delà d'un double-clic, le
// second clic renomme. Un glisser-déposer ne doit jamais ouvrir le champ.

export const RENAME_GAP_MS = 500;

export function renameClickAction({
  previousAt, sameRow, now, moved = false, dragging = false,
}) {
  if (dragging || moved) return "ignore";
  const previous = Number(previousAt);
  if (!sameRow || !Number.isFinite(previous)) return "select";
  if (Number(now) - previous < RENAME_GAP_MS) return "ignore";
  return "rename";
}
