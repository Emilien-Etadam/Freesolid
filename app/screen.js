// Projection écran, sans Three.js. `rect` est le rectangle du canevas
// (left, top, width, height), comme un DOMRect.

/** NDC (-1..1, Y vers le haut) → pixel de la page. */
export function ndcToScreen(ndcX, ndcY, rect) {
  return {
    x: (ndcX * 0.5 + 0.5) * rect.width + rect.left,
    y: (-ndcY * 0.5 + 0.5) * rect.height + rect.top,
  };
}

/** Pixel de la page → NDC (-1..1, Y vers le haut). */
export function eventToNdc(clientX, clientY, rect) {
  return {
    x: ((clientX - rect.left) / rect.width) * 2 - 1,
    y: -((clientY - rect.top) / rect.height) * 2 + 1,
  };
}

/** Où poser une petite barre près du curseur, en pixels dans ``rect``
 *  (son conteneur) : au-dessus à droite, sans en déborder — à gauche du
 *  curseur au bord droit, dessous au bord du haut. */
export function nearCursor(clientX, clientY, rect, size, gap = 14) {
  const x = clientX - rect.left, y = clientY - rect.top;
  let left = x + gap;
  if (left + size.width > rect.width - 4) left = x - gap - size.width;
  let top = y - gap - size.height;
  if (top < 4) top = y + gap;
  return {
    left: Math.max(4, Math.min(left, rect.width - size.width - 4)),
    top: Math.max(4, Math.min(top, rect.height - size.height - 4)),
  };
}
