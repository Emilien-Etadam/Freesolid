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
