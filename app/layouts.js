// Dispositions multi-fenêtres de la zone graphique : une, deux (l'une
// au-dessus de l'autre ou côte à côte) ou quatre fenêtres. Module pur :
// main.js place les canvas et garde une caméra par fenêtre.
//
// Chaque fenêtre est une fraction de la zone graphique (x, y, w, h) et
// une vue de départ : « current » reprend la vue en cours, les autres
// sont des vues standard (clés de VIEWS dans main.js). À quatre, la
// disposition est celle des projections orthogonales du dessin
// industriel (projection américaine) : dessus au-dessus de la face,
// droite à sa droite, la vue en cours dans le coin restant.

export const LAYOUTS = {
  single: [{ x: 0, y: 0, w: 1, h: 1, view: "current" }],
  "two-h": [
    { x: 0, y: 0, w: 1, h: 0.5, view: "current" },
    { x: 0, y: 0.5, w: 1, h: 0.5, view: "view-front" },
  ],
  "two-v": [
    { x: 0, y: 0, w: 0.5, h: 1, view: "view-front" },
    { x: 0.5, y: 0, w: 0.5, h: 1, view: "current" },
  ],
  four: [
    { x: 0, y: 0, w: 0.5, h: 0.5, view: "view-top" },
    { x: 0.5, y: 0, w: 0.5, h: 0.5, view: "current" },
    { x: 0, y: 0.5, w: 0.5, h: 0.5, view: "view-front" },
    { x: 0.5, y: 0.5, w: 0.5, h: 0.5, view: "view-right" },
  ],
};

/** Fenêtres d'une disposition (copies) ; un nom inconnu donne une seule. */
export function layoutPanes(name) {
  return (LAYOUTS[name] ?? LAYOUTS.single).map((pane) => ({ ...pane }));
}

/** Fenêtre qui reprend la vue en cours. */
export function currentPaneIndex(panes) {
  return Math.max(0, panes.findIndex((pane) => pane.view === "current"));
}

/** Rectangle en pixels d'une fenêtre dans une zone ``width`` × ``height``.
 *  Un trait de ``gap`` pixels sépare deux fenêtres voisines. */
export function paneRect(pane, width, height, gap = 2) {
  const half = gap / 2;
  const x0 = Math.round(pane.x * width) + (pane.x > 0 ? half : 0);
  const y0 = Math.round(pane.y * height) + (pane.y > 0 ? half : 0);
  const x1 = Math.round((pane.x + pane.w) * width)
    - (pane.x + pane.w < 1 ? half : 0);
  const y1 = Math.round((pane.y + pane.h) * height)
    - (pane.y + pane.h < 1 ? half : 0);
  return { left: x0, top: y0,
           width: Math.max(x1 - x0, 1), height: Math.max(y1 - y0, 1) };
}
