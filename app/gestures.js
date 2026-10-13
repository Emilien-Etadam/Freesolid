// Gestes de la souris : glisser au bouton droit dans la vue fait
// apparaître une couronne de commandes ; relâcher dans une direction lance
// celle-ci. Un clic droit sans glisser garde le menu contextuel. Pas en
// assemblage (le bouton droit y tourne les composants).

import { t } from "./i18n.js";

/** Commandes de la couronne, dans le sens trigonométrique depuis la
 *  droite : droite, haut, gauche, bas. `click` : bouton à déclencher. */
export const PART_GESTURES = [
  { label: "Esquisse", click: "btn-sketch" },
  { label: "Vue de dessus", click: "view-top" },
  { label: "Zoom au mieux", click: "view-fit" },
  { label: "Vue isométrique", click: "view-iso" },
];

export const SKETCH_GESTURES = [
  { label: "Ligne", tool: "line" },
  { label: "Rectangle", tool: "rect" },
  { label: "Cercle", tool: "circle" },
  { label: "Cotation", tool: "dim" },
];

/** Secteur visé par un déplacement (écran : y vers le bas) parmi `count`,
 *  0 = droite puis sens trigonométrique ; -1 trop près du centre. */
export function gestureSlot(dx, dy, count = 4, deadZone = 24) {
  if (Math.hypot(dx, dy) < deadZone) return -1;
  const step = (2 * Math.PI) / count;
  const angle = Math.atan2(-dy, dx);
  return ((Math.round(angle / step) % count) + count) % count;
}

export function installGestures(ctx) {
  const { renderer } = ctx;
  const canvas = renderer.domElement;
  const ring = document.createElement("div");
  ring.id = "gesture-ring";
  ring.hidden = true;
  document.body.appendChild(ring);
  let gesture = null;
  let swallowMenu = false;

  function actions() {
    return ctx.sketchMode?.active ? SKETCH_GESTURES : PART_GESTURES;
  }

  function show(x, y) {
    ring.replaceChildren();
    const list = actions();
    list.forEach((action, i) => {
      const item = document.createElement("span");
      item.textContent = t(action.label);
      const angle = (i * 2 * Math.PI) / list.length;
      item.style.left = `${Math.cos(angle) * 70}px`;
      item.style.top = `${-Math.sin(angle) * 52}px`;
      ring.appendChild(item);
    });
    ring.style.left = `${x}px`;
    ring.style.top = `${y}px`;
    ring.hidden = false;
  }

  function highlight(slot) {
    [...ring.children].forEach((item, i) => item.classList.toggle("on", i === slot));
  }

  canvas.addEventListener("pointerdown", (event) => {
    if (event.button !== 2 || ctx.assemblyState) return;
    gesture = { x: event.clientX, y: event.clientY, shown: false, slot: -1 };
  });

  canvas.addEventListener("pointermove", (event) => {
    if (!gesture) return;
    const dx = event.clientX - gesture.x;
    const dy = event.clientY - gesture.y;
    if (!gesture.shown && Math.hypot(dx, dy) > 10) {
      gesture.shown = true;
      show(gesture.x, gesture.y);
    }
    if (gesture.shown) {
      gesture.slot = gestureSlot(dx, dy, actions().length);
      highlight(gesture.slot);
    }
  });

  window.addEventListener("pointerup", (event) => {
    if (!gesture || event.button !== 2) return;
    const done = gesture;
    gesture = null;
    ring.hidden = true;
    if (!done.shown) return;
    // Un geste n'ouvre pas en plus le menu contextuel.
    swallowMenu = true;
    setTimeout(() => { swallowMenu = false; }, 400);
    const action = actions()[done.slot];
    if (!action) return;
    if (action.tool) {
      document.querySelector(`#sketchbar [data-tool="${action.tool}"]`)?.click();
    } else {
      document.getElementById(action.click)?.click();
    }
  });

  window.addEventListener("contextmenu", (event) => {
    if (!swallowMenu) return;
    event.preventDefault();
    event.stopImmediatePropagation();
  }, true);
}
