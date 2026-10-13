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

  function paramAt(event) {
    const ray = rayAt(event);
    return axisParam(ray.origin.toArray(), ray.direction.toArray(),
      handle.origin.toArray(), handle.dir.toArray());
  }

  function hits(event) {
    if (!handle) return false;
    rayAt(event);
    return raycaster.intersectObject(handle.group, true).length > 0;
  }

  function hide() {
    if (!handle) return;
    handle.group.traverse((obj) => {
      obj.geometry?.dispose();
      obj.material?.dispose();
    });
    scene.remove(handle.group);
    handle = null;
    drag = null;
    canvas.style.cursor = "";
  }

  function place() {
    const { group, origin, dir, offset } = handle;
    group.position.copy(origin).addScaledVector(dir, offset);
    group.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
  }

  function show(spec) {
    hide();
    const size = Math.max(ctx.partCenterRadius().radius * 0.5, 15);
    const color = ctx.sceneTheme.accent ?? 0x3d8bfd;
    const group = new THREE.Group();
    const material = () => new THREE.MeshBasicMaterial({
      color, depthTest: false, transparent: true, opacity: 0.95 });
    const shaft = new THREE.Mesh(
      new THREE.CylinderGeometry(size * 0.05, size * 0.05, size, 10), material());
    shaft.position.y = size / 2;
    const cone = new THREE.Mesh(
      new THREE.ConeGeometry(size * 0.16, size * 0.36, 18), material());
    cone.position.y = size + size * 0.18;
    group.add(shaft, cone);
    group.renderOrder = 40;
    shaft.renderOrder = cone.renderOrder = 40;
    scene.add(group);
    handle = { group, spec, offset: 0,
               origin: new THREE.Vector3(...spec.origin),
               dir: new THREE.Vector3(...spec.dir).normalize() };
    place();
  }

  // Avant la sélection et la navigation : la poignée prend le geste.
  window.addEventListener("pointerdown", (event) => {
    if (event.target !== canvas || event.button !== 0 || !hits(event)) return;
    const t0 = paramAt(event);
    if (t0 === null) return;
    event.stopImmediatePropagation();
    event.preventDefault();
    drag = { t0 };
    controls.enabled = false;
  }, true);

  window.addEventListener("pointermove", (event) => {
    if (!handle) return;
    if (!drag) {
      if (event.target === canvas) canvas.style.cursor = hits(event) ? "grab" : canvas.style.cursor;
      return;
    }
    const t = paramAt(event);
    if (t === null) return;
    handle.offset = t - drag.t0;
    place();
    handle.spec.onDrag?.(handle.offset);
  }, true);

  window.addEventListener("pointerup", (event) => {
    if (!drag || event.button !== 0) return;
    event.stopImmediatePropagation();
    const offset = handle.offset;
    drag = null;
    controls.enabled = true;
    const spec = handle.spec;
    spec.onEnd?.(offset);
  }, true);

  return { show, hide, get active() { return handle !== null; } };
}
