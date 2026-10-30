// Poignées d'édition directe : une flèche qu'on tire le long d'un axe
// (profondeur d'une extrusion, plan de coupe…). Le calcul du déplacement
// est pur ; la poignée elle-même vit dans la scène.

/** Paramètre t du point de l'axe (o + t·d) le plus proche du rayon
 *  (r + s·u) ; null si rayon et axe sont parallèles. */
export function axisParam(rayOrigin, rayDir, axisOrigin, axisDir) {
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const w = [rayOrigin[0] - axisOrigin[0], rayOrigin[1] - axisOrigin[1],
             rayOrigin[2] - axisOrigin[2]];
  const a = dot(rayDir, rayDir);
  const b = dot(rayDir, axisDir);
  const c = dot(axisDir, axisDir);
  const d = dot(rayDir, w);
  const e = dot(axisDir, w);
  const den = a * c - b * b;
  if (Math.abs(den) < 1e-9 * a * c) return null;
  return (a * e - b * d) / den;
}

/** Longueur d'une flèche, à l'échelle de la pièce (`radius` : rayon de
 *  son encombrement) : un quart du rayon, 7,5 mm au moins. */
export function handleSize(radius) {
  return Math.max(radius * 0.25, 7.5);
}

/** Une poignée à la fois dans la vue. `show({ origin, dir, onDrag, onEnd })`
 *  la pose ; `hide()` la retire. Pendant le glisser, la vue ne tourne pas
 *  et le clic ne sélectionne rien. */
export function installHandles(ctx) {
  const { THREE, scene, camera, renderer, controls, raycaster } = ctx;
  const canvas = renderer.domElement;
  let handle = null; // { group, cone, origin, dir, spec }
  let drag = null;   // { t0 }

  function rayAt(event) {
    const rect = canvas.getBoundingClientRect();
    const ndc = new THREE.Vector2(
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      -((event.clientY - rect.top) / rect.height) * 2 + 1);
    raycaster.setFromCamera(ndc, camera);
    return raycaster.ray;
  }

  function paramAt(event, axis) {
    const ray = rayAt(event);
    return axisParam(ray.origin.toArray(), ray.direction.toArray(),
      handle.origin.toArray(), handle.axes[axis].dir.toArray());
  }

  /** Index de la flèche sous le pointeur, ou -1. */
  function hitAxis(event) {
    if (!handle) return -1;
    rayAt(event);
    const hit = raycaster.intersectObject(handle.root, true)[0];
    return hit ? hit.object.userData.axis ?? -1 : -1;
  }

  function hide() {
    if (!handle) return;
    handle.root.traverse((obj) => {
      obj.geometry?.dispose();
      obj.material?.dispose();
    });
    scene.remove(handle.root);
    handle = null;
    drag = null;
    controls.enabled = true;
    canvas.style.cursor = "";
  }

  function place() {
    const { root, origin, axes, offset, active } = handle;
    root.position.copy(origin);
    if (active >= 0) root.position.addScaledVector(axes[active].dir, offset);
  }

  function arrow(dir, color, size, axis) {
    const group = new THREE.Group();
    const material = () => new THREE.MeshBasicMaterial({
      color, depthTest: false, transparent: true, opacity: 0.95 });
    const shaft = new THREE.Mesh(
      new THREE.CylinderGeometry(size * 0.05, size * 0.05, size, 10), material());
    shaft.position.y = size / 2;
    const cone = new THREE.Mesh(
      new THREE.ConeGeometry(size * 0.16, size * 0.36, 18), material());
    cone.position.y = size + size * 0.18;
    for (const part of [shaft, cone]) {
      part.renderOrder = 40;
      part.userData.axis = axis;
    }
    group.add(shaft, cone);
    group.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
    return group;
  }

  /** Pose une poignée : une flèche (`dir`, `onDrag(d)`, `onEnd(d)`) ou
   *  plusieurs (`axes: [{ dir, color }]`, `onDrag(d, i)`, `onEnd(d, i)`).
   *  `owner` dit à qui elle est (« panel » : au panneau ouvert). */
  function show(spec) {
    hide();
    const size = spec.size ?? handleSize(ctx.partCenterRadius().radius);
    const accent = ctx.sceneTheme.accent ?? 0x3d8bfd;
    const axes = (spec.axes ?? [{ dir: spec.dir, color: accent }]).map((a) => ({
      dir: new THREE.Vector3(...a.dir).normalize(), color: a.color ?? accent }));
    const root = new THREE.Group();
    axes.forEach((a, i) => root.add(arrow(a.dir, a.color, size, i)));
    scene.add(root);
    handle = { root, spec, axes, offset: 0, active: -1,
               origin: new THREE.Vector3(...spec.origin) };
    place();
  }

  // Avant la sélection et la navigation : la poignée prend le geste.
  window.addEventListener("pointerdown", (event) => {
    if (event.target !== canvas || event.button !== 0) return;
    const axis = hitAxis(event);
    if (axis < 0) return;
    const t0 = paramAt(event, axis);
    if (t0 === null) return;
    event.stopImmediatePropagation();
    event.preventDefault();
    drag = { t0, axis };
    handle.active = axis;
    handle.offset = 0;
    controls.enabled = false;
  }, true);

  window.addEventListener("pointermove", (event) => {
    if (!handle) return;
    if (!drag) {
      if (event.target === canvas && hitAxis(event) >= 0) canvas.style.cursor = "grab";
      return;
    }
    const t = paramAt(event, drag.axis);
    if (t === null) return;
    handle.offset = t - drag.t0;
    place();
    handle.spec.onDrag?.(handle.offset, drag.axis);
  }, true);

  window.addEventListener("pointerup", (event) => {
    if (!drag || event.button !== 0) return;
    event.stopImmediatePropagation();
    const { axis } = drag;
    const offset = handle.offset;
    drag = null;
    controls.enabled = true;
    handle.spec.onEnd?.(offset, axis);
  }, true);

  return {
    show, hide,
    get active() { return handle !== null; },
    get owner() { return handle?.spec.owner ?? null; },
  };
}
