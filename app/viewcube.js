// Vues standard et boîte d'orientation. Le cadrage et le placement de
// la boîte sont purs ; le reste relie la caméra et les boutons.

import { coverBounds } from "./navigation.js";

/** Zoom orthographique pour qu'une sphère de ce rayon tienne dans la vue,
 *  avec une marge. `orthoHeight` est la hauteur de référence du frustum. */
export function orthoZoomFor(radius, width, height, orthoHeight) {
  const aspect = (width || 1) / (height || 1);
  const needed = 2 * Math.max(radius, 1) * 1.25;
  return Math.min(orthoHeight * aspect, orthoHeight) / needed;
}

/** Place la boîte sous le pointeur, en la gardant dans la fenêtre.
 *  Coordonnées en pixels, origine en haut à gauche de l'écran pour
 *  `at`, de la zone graphique pour `host`. */
export function placeOrientBox(at, host, box) {
  const left = Math.min(Math.max(at.x - host.left - box.width / 2, 4),
    host.width - box.width - 4);
  const top = Math.min(Math.max(at.y - host.top - box.height / 2, 4),
    host.height - box.height - 4);
  return { left, top };
}

// Vue de face = normale au Plan de face (XZ), etc. — mêmes plans que le vocab.
export const VIEWS = {
  "view-iso":    { direction: [1, -1, 1], up: [0, 0, 1] },
  // Dimétrique : deux axes raccourcis pareil ; trimétrique : trois différents.
  "view-dimetric":  { direction: [1, -1, 0.55], up: [0, 0, 1] },
  "view-trimetric": { direction: [1, -0.62, 0.5], up: [0, 0, 1] },
  "view-front":  { direction: [0, -1, 0], up: [0, 0, 1] },
  "view-back":   { direction: [0, 1, 0],  up: [0, 0, 1] },
  "view-left":   { direction: [-1, 0, 0], up: [0, 0, 1] },
  "view-right":  { direction: [1, 0, 0],  up: [0, 0, 1] },
  "view-top":    { direction: [0, 0, 1],  up: [0, 1, 0] },
  // Vue de dessous : l'avant de la pièce passe en haut de l'écran.
  "view-bottom": { direction: [0, 0, -1], up: [0, -1, 0] },
  "view-fit":    { direction: null,       up: null },
};

export const VIEW_KEYS = {
  1: "view-front", 2: "view-back", 3: "view-left", 4: "view-right",
  5: "view-top", 6: "view-bottom", 7: "view-iso",
};

// Normale des plans d'origine, côté d'où on les regarde (même sens que
// les vues Face / Dessus / Droite).
const PLANE_VIEW_NORMALS = { XY: [0, 0, 1], XZ: [0, -1, 0], YZ: [1, 0, 0] };

/** Branche les vues standard et la boîte d'orientation. */
export function installViewCube(ctx) {
  const {
    THREE, camera, controls, viewSize, ORTHO_HEIGHT, say, setLayout, container,
  } = ctx;

  function partCenterRadius() {
    // La sphère n'existe qu'une fois calculée (un lancer de rayon le fait) :
    // juste après un chargement, le cadrage prenait le rayon par défaut.
    const partMesh = ctx.partMesh;
    if (partMesh && !partMesh.geometry.boundingSphere) {
      partMesh.geometry.computeBoundingSphere();
    }
    if (!partMesh || !partMesh.geometry.boundingSphere)
      return { center: new THREE.Vector3(0, 0, 20), radius: 90 };
    const sphere = partMesh.geometry.boundingSphere;
    return { center: sphere.center.clone(), radius: Math.max(sphere.radius, 1) };
  }

  function fitOrthoZoom(radius) {
    const size = viewSize();
    camera.zoom = orthoZoomFor(radius, size.width, size.height, ORTHO_HEIGHT);
    camera.updateProjectionMatrix();
  }

  // direction = d'où l'on regarde ; null = garder l'angle actuel (zoom au mieux).
  // bounds, s'il est donné, remplace la sphère de la pièce (esquisse).
  function frameView(direction, up, bounds = null) {
    const { center, radius } = bounds ?? partCenterRadius();
    if (up) camera.up.set(...up);
    const dir = direction
      ? new THREE.Vector3(...direction).normalize()
      : camera.position.clone().sub(controls.target).normalize();
    if (dir.lengthSq() < 1e-12) dir.set(1, -1, 1).normalize();
    // Distance : near/far et orbite uniquement — la taille vient du zoom.
    const distance = Math.max(radius * 2.5, 80);
    controls.target.copy(center);
    camera.position.copy(center).addScaledVector(dir, distance);
    camera.lookAt(center);
    fitOrthoZoom(radius);
  }

  function visiblePartSphere() {
    const partMesh = ctx.partMesh;
    const partEdges = ctx.partEdges;
    if (!partMesh || (!partMesh.visible && !partEdges?.visible)) return null;
    if (!partMesh.geometry.boundingSphere) partMesh.geometry.computeBoundingSphere();
    if (!partMesh.geometry.boundingSphere) return null;
    const { center, radius } = partCenterRadius();
    return { center: [center.x, center.y, center.z], radius };
  }

  /** En esquisse : cadrer la géométrie et la pièce visible, sans tourner. */
  function frameSketch() {
    const sphere = visiblePartSphere();
    const covered = coverBounds(
      ctx.sketchMode.framePoints(), sphere ? [sphere] : []);
    frameView(null, null, covered
      ? { center: new THREE.Vector3(...covered.center), radius: covered.radius }
      : null);
  }

  for (const [id, view] of Object.entries(VIEWS)) {
    document.getElementById(id)?.addEventListener("click", () => {
      if (ctx.sketchMode.active) {
        if (id === "view-fit") frameSketch();
        return; // les autres vues quitteraient le plan
      }
      frameView(view.direction, view.up);
    });
  }

  /** « Normal à » : la face ou le plan sélectionné face à l'écran. Un second
   *  appui, alors qu'on regarde déjà dans cet axe, passe de l'autre côté. */
  function viewNormalTo() {
    let normal = null;
    if (ctx.selectedFaceId !== null && ctx.lastFaceHit?.face === ctx.selectedFaceId
        && ctx.lastFaceHit.normal) {
      normal = new THREE.Vector3(...ctx.lastFaceHit.normal);
    } else if (ctx.selectedPlane !== null && PLANE_VIEW_NORMALS[ctx.selectedPlane]) {
      normal = new THREE.Vector3(...PLANE_VIEW_NORMALS[ctx.selectedPlane]);
    }
    if (!normal || normal.lengthSq() < 1e-12) {
      say("Normal à : sélectionnez d'abord une face plane ou un plan.");
      return;
    }
    normal.normalize();
    const looking = camera.position.clone().sub(controls.target).normalize();
    if (looking.dot(normal) > 0.999) normal.negate();
    // Haut de l'écran : Z, sauf si on regarde le long de Z.
    const up = Math.abs(normal.z) > 0.9 ? [0, 1, 0] : [0, 0, 1];
    frameView([normal.x, normal.y, normal.z], up);
  }

  // Les vues standard dépliées en croix autour de la face, plus iso,
  // dimétrique, trimétrique et « Normal à ». Elle s'ouvre sous le curseur ;
  // l'épingle la garde ouverte après un choix.
  const orientBox = document.getElementById("orient-box");
  let orientPinned = false;
  let lastViewportPointer = null;

  container.addEventListener("pointermove", (event) => {
    lastViewportPointer = { x: event.clientX, y: event.clientY };
  });

  function openOrientBox() {
    if (!orientBox) return;
    ctx.hideContextToolbar?.(); // elle passerait par-dessus la boîte
    const host = container.getBoundingClientRect();
    const at = lastViewportPointer ?? {
      x: host.left + host.width / 2, y: host.top + host.height / 2 };
    orientBox.hidden = false;
    const box = orientBox.getBoundingClientRect();
    const place = placeOrientBox(at, host, box);
    orientBox.style.left = `${place.left}px`;
    orientBox.style.top = `${place.top}px`;
  }

  function closeOrientBox() {
    if (orientBox) orientBox.hidden = true;
  }

  function orientBoxOpen() {
    return orientBox?.hidden === false;
  }

  orientBox?.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    const view = button.dataset.view;
    if (button.dataset.action === "pin") {
      orientPinned = !orientPinned;
      button.classList.toggle("on", orientPinned);
      return;
    }
    if (button.dataset.action === "close") {
      closeOrientBox();
      return;
    }
    if (button.dataset.layout) setLayout(button.dataset.layout);
    else if (view === "normal") viewNormalTo();
    else if (VIEWS[view]) frameView(VIEWS[view].direction, VIEWS[view].up);
    if (!orientPinned) closeOrientBox();
  });

  return {
    partCenterRadius, frameView, frameSketch, viewNormalTo,
    openOrientBox, closeOrientBox, orientBoxOpen,
  };
}
