// Caméra, fenêtres, rendu et plans de base.
// Le maillage de la pièce et les sélections restent dans main.js.

import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { cssHex } from "./theme.js";
import { displayEffects, writeDisplay } from "./display.js";
import { currentPaneIndex, layoutPanes, paneRect } from "./layouts.js";
import { perspectiveFrustum } from "./projection.js";
import { createSceneLook } from "./scenelook.js";
import { t } from "./i18n.js";
import { eventToNdc } from "./screen.js";
import { VIEWS } from "./viewcube.js";
import {
  boxMode, middleAction, normalizeRect, pushView, readReverseWheel,
  writeReverseWheel, zoomSpeedFor,
} from "./navigation.js";

export function installViewport(ctx) {
  const { THREE, sceneTheme, say, call, disposeSubtree, syncVisibilityMenu } = ctx;

  // ---------- viewport ----------

  const container = document.getElementById("viewport");
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  // En tête du conteneur : les calques posés par-dessus (boîtes, barres)
  // restent au-dessus des canvas des fenêtres multiples.
  container.prepend(renderer.domElement);

  const scene = new THREE.Scene();
  const look = createSceneLook(THREE, scene, sceneTheme);

  // Hauteur du frustum (unités monde) à zoom = 1. Le zoom OrbitControls
  // et « Zoom au mieux » ajustent camera.zoom, pas la distance.
  const ORTHO_HEIGHT = 200;

  /** Caméra de vue : pilotée comme une vue orthographique (zoom,
   *  panoramique, cadrage), elle projette en perspective quand
   *  ``perspective`` est vrai (projection.js). ``focus`` : le centre de la
   *  vue, d'où se mesure le recul de l'œil. */
  class ViewCamera extends THREE.OrthographicCamera {
    constructor(...args) {
      super(...args);
      this.perspective = false;
      this.focus = null;
    }

    updateProjectionMatrix() {
      super.updateProjectionMatrix();
      if (!this.perspective || !this.focus) return;
      const f = perspectiveFrustum({
        width: (this.right - this.left) / this.zoom,
        height: (this.top - this.bottom) / this.zoom,
        rigDistance: this.position.distanceTo(this.focus),
      });
      this.projectionMatrix
        .makePerspective(f.left, f.right, f.top, f.bottom, f.near, f.far)
        .multiply(new THREE.Matrix4().makeTranslation(0, 0, -f.back));
      this.projectionMatrixInverse.copy(this.projectionMatrix).invert();
    }
  }

  // Le lancer de rayons de three.js choisit rayons parallèles ou divergents
  // selon le type de caméra ; la caméra de vue est « orthographique » pour
  // les contrôles, donc on lui donne ici le rayon de sa vraie projection.
  {
    const baseSetFromCamera = THREE.Raycaster.prototype.setFromCamera;
    THREE.Raycaster.prototype.setFromCamera = function setFromCamera(coords, cam) {
      if (!cam?.perspective) return baseSetFromCamera.call(this, coords, cam);
      this.camera = cam;
      this.ray.origin.set(coords.x, coords.y, -1).unproject(cam);
      this.ray.direction.set(coords.x, coords.y, 1).unproject(cam)
        .sub(this.ray.origin).normalize();
    };
  }

  const camera = new ViewCamera(
    -ORTHO_HEIGHT / 2, ORTHO_HEIGHT / 2,
    ORTHO_HEIGHT / 2, -ORTHO_HEIGHT / 2,
    0.1, 10000);
  camera.position.set(160, -160, 120);
  camera.up.set(0, 0, 1); // CAD is Z-up

  // Dispositions multi-fenêtres (layouts.js). Le canvas principal, sa caméra
  // et ses contrôles occupent toujours la fenêtre active : sélection, cotes
  // et esquisse n'en savent rien. Les autres fenêtres sont dessinées par des
  // canvas secondaires, chacune avec l'état de caméra qu'elle avait. Cliquer
  // une fenêtre secondaire l'active : les états s'échangent, rien ne saute.
  let panes = layoutPanes("single");
  let activePane = 0;
  const extraViews = [];   // { renderer, pane } — pane : index, ou -1
  const paneCamera = new ViewCamera(-1, 1, 1, -1, 0.1, 10000);

  /** Taille en pixels de la fenêtre active. */
  function viewSize() {
    const width = container.clientWidth, height = container.clientHeight;
    if (panes.length < 2) return { width, height };
    return paneRect(panes[activePane], width, height);
  }

  const controls = new OrbitControls(camera, renderer.domElement);
  camera.focus = controls.target;
  // Pas d'inertie : la vue s'arrête dès qu'on lâche la souris.
  controls.enableDamping = false;

  // Navigation (navigation.js) : le milieu tourne, Ctrl + milieu déplace,
  // Maj + milieu zoome, la molette zoome vers le curseur ; le bouton gauche
  // sélectionne (clic ou cadre), le droit reste au menu contextuel.
  const localStore = (() => { try { return window.localStorage; } catch { return null; } })();
  controls.mouseButtons = { LEFT: null, MIDDLE: THREE.MOUSE.ROTATE, RIGHT: null };
  controls.zoomToCursor = true;
  controls.zoomSpeed = zoomSpeedFor(readReverseWheel(localStore));

  // OrbitControls inverse lui-même ROTATE/PAN quand Ctrl ou Maj est tenu :
  // on lui donne le bouton qui, avec ces touches, produit le bon geste.
  function orbitButtonFor(action, event) {
    const mod = event.ctrlKey || event.metaKey || event.shiftKey;
    if (action === "dolly") return THREE.MOUSE.DOLLY;
    if (action === "pan") return mod ? THREE.MOUSE.ROTATE : THREE.MOUSE.PAN;
    return mod ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE;
  }
  // Capture : passe avant le pointerdown d'OrbitControls, qui lit
  // mouseButtons à l'appui.
  renderer.domElement.addEventListener("pointerdown", (event) => {
    if (event.button !== 1) return;
    controls.mouseButtons.MIDDLE = orbitButtonFor(
      middleAction(event, { rotateLocked: !controls.enableRotate }), event);
  }, { capture: true });
  // Pas de défilement automatique du navigateur au clic milieu.
  renderer.domElement.addEventListener("mousedown", (event) => {
    if (event.button === 1) event.preventDefault();
  });

  // Centre de rotation : un clic milieu (sans glisser) sur la pièce pose le
  // centre, un clic milieu dans le vide le retire. Avec un centre posé, le
  // glisser milieu tourne la vue autour de lui (il reste fixe à l'écran) ;
  // OrbitControls, qui ne sait tourner qu'autour du centre de la vue, est
  // mis de côté le temps du glisser.
  let rotationPivot = null;
  let pivotDrag = null;
  const pivotMarker = new THREE.Points(
    new THREE.BufferGeometry().setFromPoints([new THREE.Vector3()]),
    new THREE.PointsMaterial({ color: sceneTheme.selection, size: 10,
      sizeAttenuation: false, depthTest: false }));
  pivotMarker.visible = false;
  pivotMarker.renderOrder = 30;
  scene.add(pivotMarker);

  function pickPivot(event) {
    const rect = renderer.domElement.getBoundingClientRect();
    const ndc = eventToNdc(event.clientX, event.clientY, rect);
    const at = new THREE.Vector2(ndc.x, ndc.y);
    ctx.raycaster.setFromCamera(at, camera);
    const targets = [ctx.partMesh, ...ctx.othersMeshes, ...ctx.surfaceMeshes,
      ...(ctx.asmGroup ? ctx.asmGroup.children : [])].filter(Boolean);
    return ctx.raycaster.intersectObjects(targets, false)[0]?.point ?? null;
  }

  function setRotationPivot(point) {
    rotationPivot = point ? point.clone() : null;
    pivotMarker.visible = !!rotationPivot;
    if (rotationPivot) pivotMarker.position.copy(rotationPivot);
    say(rotationPivot
      ? "Centre de rotation posé — clic milieu dans le vide pour le retirer."
      : "Centre de rotation : centre de la vue.");
  }

  /** Tourne caméra et cible autour du centre : lacet autour de l'axe haut de
   *  la caméra (Z, ou Y après une vue de dessus), tangage autour de
   *  l'horizontale de l'écran. Même axe haut que lookAt : pas de saut. */
  function orbitAroundPivot(dx, dy) {
    const height = renderer.domElement.clientHeight || 1;
    const yaw = -2 * Math.PI * dx / height;
    const pitch = -2 * Math.PI * dy / height;
    const view = new THREE.Vector3().subVectors(controls.target, camera.position)
      .normalize();
    const right = new THREE.Vector3().crossVectors(view, camera.up).normalize();
    const up = camera.up.clone().normalize();
    const q = new THREE.Quaternion().setFromAxisAngle(up, yaw);
    const qPitch = new THREE.Quaternion().setFromAxisAngle(right, pitch);
    const tilted = view.clone().applyQuaternion(qPitch);
    if (Math.abs(tilted.dot(up)) < 0.995) q.multiply(qPitch); // pas de bascule au pôle
    for (const point of [camera.position, controls.target]) {
      point.sub(rotationPivot).applyQuaternion(q).add(rotationPivot);
    }
    camera.lookAt(controls.target);
  }

  renderer.domElement.addEventListener("pointerdown", (event) => {
    if (event.button !== 1) return;
    pivotDrag = { x: event.clientX, y: event.clientY, last: null,
      custom: !!rotationPivot && controls.enableRotate
        && !event.ctrlKey && !event.metaKey && !event.shiftKey };
    if (pivotDrag.custom) {
      rememberView();
      controls.enabled = false;
      pivotDrag.last = { x: event.clientX, y: event.clientY };
    }
  }, { capture: true });

  renderer.domElement.addEventListener("pointermove", (event) => {
    if (!pivotDrag?.custom || !pivotDrag.last) return;
    orbitAroundPivot(event.clientX - pivotDrag.last.x,
                     event.clientY - pivotDrag.last.y);
    pivotDrag.last = { x: event.clientX, y: event.clientY };
  });

  window.addEventListener("pointerup", (event) => {
    if (!pivotDrag || event.button !== 1) return;
    const drag = pivotDrag;
    pivotDrag = null;
    if (drag.custom) controls.enabled = true;
    if (Math.hypot(event.clientX - drag.x, event.clientY - drag.y) > 4) return;
    if (ctx.sketchMode?.active) return;
    setRotationPivot(pickPivot(event));
  });

  function setReverseWheel(reversed) {
    writeReverseWheel(localStore, reversed);
    controls.zoomSpeed = zoomSpeedFor(reversed);
  }

  // Cadre de sélection : un rectangle HTML posé sur la vue. Trait plein en
  // fenêtre (gauche → droite), tirets en capture (droite → gauche).
  const boxEl = document.createElement("div");
  boxEl.id = "box-select";
  boxEl.hidden = true;
  const boxOverlay = {
    show(start, end) {
      const host = container.getBoundingClientRect();
      const r = normalizeRect(start, end);
      boxEl.hidden = false;
      boxEl.className = boxMode(start, end);
      boxEl.style.left = `${r.left - host.left}px`;
      boxEl.style.top = `${r.top - host.top}px`;
      boxEl.style.width = `${r.right - r.left}px`;
      boxEl.style.height = `${r.bottom - r.top}px`;
    },
    hide() { boxEl.hidden = true; },
  };
  container.appendChild(boxEl);
  // ---------- plans de base (Face / Dessus / Droite) ----------
  // Toujours là : visibles dans l'arbre, cliquables
  // dans la zone graphique quand la commande Esquisse attend un plan.

  const PLANE_ROTATIONS = {
    XY: [0, 0, 0],
    XZ: [Math.PI / 2, 0, 0],
    YZ: [0, Math.PI / 2, 0],
  };
  const planesGroup = new THREE.Group();
  planesGroup.visible = false;
  scene.add(planesGroup);
  // Mêmes noms que vocab.ORIGIN_PLANES — affichés sur les plans eux-mêmes.
  const PLANE_LABELS = {
    XY: t("Plan de dessus"), XZ: t("Plan de face"), YZ: t("Plan de droite"),
  };

  function makePlaneLabel(text) {
    const canvas = document.createElement("canvas");
    canvas.width = 256;
    canvas.height = 44;
    const ctx = canvas.getContext("2d");
    ctx.font = "600 24px system-ui";
    ctx.fillStyle = cssHex(sceneTheme.dim);
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(text, 128, 22);
    const material = new THREE.SpriteMaterial({
      map: new THREE.CanvasTexture(canvas),
      transparent: true, depthTest: false });
    material.userData.own = true;
    const sprite = new THREE.Sprite(material);
    sprite.renderOrder = 10;
    return sprite;
  }

  let lastPlanesSize = null;

  function rebuildPlanes() {
    const { center, radius } = ctx.partCenterRadius();
    look.fitGrid(center, radius);
    const size = Math.max(radius * 1.7, 80);
    if (lastPlanesSize === size && Object.keys(ctx.planeMeshes).length) {
      updatePlaneVisibility();
      return;
    }
    disposeSubtree(planesGroup);
    planesGroup.clear();
    ctx.planeMeshes = {};
    lastPlanesSize = size;
    for (const [id, rotation] of Object.entries(PLANE_ROTATIONS)) {
      const holder = new THREE.Group();
      holder.rotation.set(...rotation);
      const fillMaterial = new THREE.MeshBasicMaterial({
        color: sceneTheme.accent, transparent: true, opacity: 0.1,
        side: THREE.DoubleSide, depthWrite: false });
      fillMaterial.userData.own = true;
      const fill = new THREE.Mesh(
        new THREE.PlaneGeometry(size, size), fillMaterial);
      fill.userData.plane = id;
      const borderMaterial = new THREE.LineBasicMaterial(
        { color: sceneTheme.accent, transparent: true, opacity: 0.6 });
      borderMaterial.userData.own = true;
      const border = new THREE.LineSegments(
        new THREE.EdgesGeometry(fill.geometry), borderMaterial);
      const label = makePlaneLabel(PLANE_LABELS[id]);
      // Décalée vers un coin : au centre du bord, les étiquettes du plan de
      // dessus et du plan de droite tombaient au même endroit.
      label.position.set(-size * 0.3, size * 0.46, 0);
      label.scale.set(size * 0.42, size * 0.42 * (44 / 256), 1);
      holder.add(fill, border, label);
      planesGroup.add(holder);
      ctx.planeMeshes[id] = fill;
    }
    updatePlaneVisibility();
    if (ctx.originShown) rebuildOrigin();
  }

  // Origine de la pièce : trois axes courts depuis (0, 0, 0), affichés à la
  // demande (ligne « Origine » de l'arbre), à la taille de la pièce.
  const originGroup = new THREE.Group();
  originGroup.visible = false;
  originGroup.renderOrder = 12;
  scene.add(originGroup);

  function rebuildOrigin() {
    disposeSubtree(originGroup);
    originGroup.clear();
    const { radius } = ctx.partCenterRadius();
    const length = Math.max(radius * 0.35, 12);
    const axes = [[1, 0, 0, sceneTheme.axisX], [0, 1, 0, sceneTheme.axisY], [0, 0, 1, sceneTheme.axisZ]];
    for (const [x, y, z, color] of axes) {
      const arrow = new THREE.ArrowHelper(
        new THREE.Vector3(x, y, z), new THREE.Vector3(0, 0, 0),
        length, color, length * 0.2, length * 0.1);
      arrow.traverse((obj) => {
        if (obj.material) {
          // Passe transparente : dessinée après la pièce, qui l'est aussi.
          obj.material.transparent = true;
          obj.material.depthTest = false;
          obj.material.userData.own = true;
        }
        obj.renderOrder = 12;
      });
      originGroup.add(arrow);
    }
    originGroup.visible = ctx.originShown;
  }

  function toggleOrigin() {
    setOriginShown(!ctx.originShown);
    say(ctx.originShown ? "Origine affichée." : "Origine masquée.");
  }

  function setOriginShown(shown) {
    ctx.originShown = !!shown;
    ctx.displayState = { ...ctx.displayState, origin: ctx.originShown };
    writeDisplay(localStore, ctx.displayState);
    rebuildOrigin();
    if (ctx.lastTree) ctx.renderTree(ctx.lastTree);
    syncVisibilityMenu();
  }

  function updatePlaneVisibility() {
    const showAll = displayEffects(ctx.displayState).planes;
    const single = ctx.planePicking ? null : (ctx.treeHoverPlane ?? ctx.selectedPlane);
    planesGroup.visible = ctx.planePicking || showAll || single !== null;
    for (const [id, mesh] of Object.entries(ctx.planeMeshes)) {
      mesh.parent.visible = ctx.planePicking || showAll || id === single;
      mesh.material.opacity =
        (ctx.planePicking && id === ctx.hoverPlane) || id === ctx.selectedPlane
          ? 0.28 : 0.1;
    }
  }
  function startPlanePick() {
    ctx.planePicking = true;
    ctx.hoverPlane = null;
    rebuildPlanes();
    say("Esquisse : cliquez un plan — dans la zone graphique ou dans " +
        "l'arbre (Échap pour annuler)");
  }

  function cancelPlanePick() {
    ctx.planePicking = false;
    ctx.hoverPlane = null;
    updatePlaneVisibility();
    say("Esquisse annulée.");
  }

  function pickPlane(id) {
    ctx.planePicking = false;
    ctx.hoverPlane = null;
    ctx.selectedPlane = null;
    updatePlaneVisibility();
    if (ctx.lastTree) ctx.renderTree(ctx.lastTree);
    ctx.sketchMode.enter(call("sketch_start", { plane: id }));
  }
  /** Frustum orthographique pour un rapport largeur / hauteur. */
  function setOrthoFrustum(cam, width, height) {
    const aspect = height > 0 ? width / height : 1;
    cam.left = -ORTHO_HEIGHT * aspect / 2;
    cam.right = ORTHO_HEIGHT * aspect / 2;
    cam.top = ORTHO_HEIGHT / 2;
    cam.bottom = -ORTHO_HEIGHT / 2;
    cam.updateProjectionMatrix();
  }

  /** Canvas dans une fenêtre (rectangle en pixels), ou plein cadre. */
  function placeCanvas(canvas, rect) {
    canvas.classList.toggle("fs-pane", !!rect);
    for (const key of ["left", "top", "width", "height"]) {
      canvas.style[key] = rect ? `${rect[key]}px` : "";
    }
  }

  function resize() {
    const { width: w, height: h } = viewSize();
    const multi = panes.length > 1;
    // updateStyle=false : le CSS (100 %) fait suivre le canvas à sa cellule,
    // setSize ne règle que le tampon de rendu.
    renderer.setSize(w, h, false);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    placeCanvas(renderer.domElement, multi
      ? paneRect(panes[activePane], container.clientWidth, container.clientHeight)
      : null);
    renderer.domElement.classList.toggle("active", multi);
    setOrthoFrustum(camera, w, h);
    const others = panes.map((_, i) => i).filter((i) => i !== activePane);
    while (extraViews.length < others.length) extraViews.push(createExtraView());
    extraViews.forEach((view, k) => {
      view.pane = others[k] ?? -1;
      view.renderer.domElement.hidden = view.pane < 0;
      if (view.pane < 0) return;
      const rect = paneRect(panes[view.pane], container.clientWidth,
                            container.clientHeight);
      view.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      view.renderer.setSize(rect.width, rect.height, false);
      placeCanvas(view.renderer.domElement, rect);
    });
  }
  new ResizeObserver(resize).observe(container);

  /** Canvas secondaire : il dessine une fenêtre inactive ; un appui dessus
   *  l'active. */
  function createExtraView() {
    const view = { renderer: new THREE.WebGLRenderer({ antialias: true }),
                   pane: -1 };
    renderer.domElement.after(view.renderer.domElement);
    view.renderer.domElement.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      activatePane(view.pane);
    });
    // La molette aussi : les crans suivants zooment la fenêtre activée.
    view.renderer.domElement.addEventListener("wheel",
      () => activatePane(view.pane), { passive: true });
    return view;
  }

  // Vue précédente : la caméra d'avant chaque geste ou cadrage.
  let viewHistory = [];
  function rememberView() {
    viewHistory = pushView(viewHistory, cameraState(), performance.now());
  }
  controls.addEventListener("start", rememberView);

  /** Revient à la vue d'avant le dernier geste ; faux s'il n'y en a pas. */
  function previousView() {
    const last = viewHistory.pop();
    if (!last) return false;
    applyCameraState(last.state);
    return true;
  }

  /** Image PNG de la vue (data URL). */
  function captureImage() {
    renderer.render(scene, camera);
    return renderer.domElement.toDataURL("image/png");
  }

  function cameraState() {
    return { position: camera.position.clone(), up: camera.up.clone(),
             zoom: camera.zoom, target: controls.target.clone() };
  }

  function applyCameraState(state) {
    camera.up.copy(state.up);
    camera.position.copy(state.position);
    camera.zoom = state.zoom;
    controls.target.copy(state.target);
    camera.lookAt(state.target);
    camera.updateProjectionMatrix();
  }

  function activatePane(index) {
    if (index < 0 || index === activePane || index >= panes.length) return;
    if (ctx.sketchMode.active) {
      say("En esquisse, la fenêtre active reste celle de l'esquisse.");
      return;
    }
    ctx.hideContextToolbar();
    panes[activePane].state = cameraState();
    activePane = index;
    applyCameraState(panes[index].state);
    resize();
  }

  /** Une, deux ou quatre fenêtres. La vue en cours garde sa fenêtre ; les
   *  autres partent d'une vue standard cadrée sur la pièce. */
  function setLayout(name) {
    if (ctx.sketchMode.active) {
      say("Terminez l'esquisse avant de changer de disposition.");
      return;
    }
    const current = cameraState();
    panes = layoutPanes(name);
    for (const [index, pane] of panes.entries()) {
      if (pane.view === "current" || !VIEWS[pane.view]) {
        pane.state = current;
        continue;
      }
      activePane = index;   // le cadrage se règle sur cette fenêtre
      ctx.frameView(VIEWS[pane.view].direction, VIEWS[pane.view].up);
      pane.state = cameraState();
    }
    activePane = currentPaneIndex(panes);
    applyCameraState(current);
    resize();
  }

  function renderExtraViews() {
    for (const view of extraViews) {
      const state = panes[view.pane]?.state;
      if (view.pane < 0 || !state) continue;
      const { width, height } = paneRect(panes[view.pane],
        container.clientWidth, container.clientHeight);
      paneCamera.perspective = camera.perspective;
      paneCamera.focus = state.target;
      paneCamera.up.copy(state.up);
      paneCamera.position.copy(state.position);
      paneCamera.zoom = state.zoom;
      paneCamera.lookAt(state.target);
      setOrthoFrustum(paneCamera, width, height);
      paneCamera.updateProjectionMatrix();
      look.follow(paneCamera);
      view.renderer.render(scene, paneCamera);
    }
  }

  renderer.setAnimationLoop(() => {
    controls.update();
    ctx.tickExplode();
    // En perspective, le recul de l'œil suit la distance au centre de la vue
    // (cadrage, panoramique) : la projection se recalcule à chaque image.
    if (camera.perspective) camera.updateProjectionMatrix();
    look.follow(camera);
    renderer.render(scene, camera);
    renderExtraViews();
  });

  return {
    container, renderer, scene, camera, controls,
    ORTHO_HEIGHT, viewSize, boxOverlay, localStore, originGroup,
    setReverseWheel, setLayout, rebuildPlanes, rebuildOrigin,
    toggleOrigin, setOriginShown, updatePlaneVisibility,
    startPlanePick, cancelPlanePick, pickPlane,
    rememberView, previousView, captureImage,
    /** Centre de rotation posé au clic milieu, ou null. */
    rotationPivot: () => rotationPivot,
  };
}
