// Outils de débogage : `window.__freesolidDebug`, lu par le smoke
// (points écran de la pièce, de l'esquisse, de la surface ; compteurs).

import * as THREE from "three";
import { ndcToScreen } from "../screen.js";

export function installDebug(ctx) {
  const { call, renderer, camera, rotationPivot, volumesGroup, refresh } = ctx;

  function volumeVisibleCount() {
    if (!volumesGroup.visible) return 0;
    let n = 0;
    volumesGroup.traverse((obj) => {
      if (obj !== volumesGroup && (obj.isMesh || obj.isLineSegments)
          && obj.visible) {
        n += 1;
      }
    });
    return n;
  }

  function sketchScreenPoint() {
    const lines = ctx.sketchLineMeshes[0];
    if (!lines) return null;
    const pos = lines.geometry.getAttribute("position");
    if (!pos || pos.count < 2) return null;
    const a = new THREE.Vector3().fromBufferAttribute(pos, 0);
    const b = new THREE.Vector3().fromBufferAttribute(pos, 1);
    const mid = a.add(b).multiplyScalar(0.5);
    mid.project(camera);
    const rect = renderer.domElement.getBoundingClientRect();
    const screen = ndcToScreen(mid.x, mid.y, rect);
    return {
      name: lines.userData.sketch?.name ?? null,
      label: lines.userData.sketch?.label ?? null,
      x: screen.x,
      y: screen.y,
    };
  }

  function surfaceScreenPoint() {
    const mesh = ctx.surfaceMeshes[0];
    if (!mesh) return null;
    // Le triangle le plus éloigné de la pièce : le centre de la surface peut
    // tomber sur une arête du solide, que le clic choisirait alors.
    const pos = mesh.geometry.getAttribute("position");
    const index = mesh.geometry.getIndex();
    if (!pos) return null;
    const solid = ctx.partMesh
      ? new THREE.Box3().setFromObject(ctx.partMesh) : null;
    const vertex = (i) => new THREE.Vector3().fromBufferAttribute(
      pos, index ? index.getX(i) : i);
    const count = index ? index.count : pos.count;
    let center = null;
    let farthest = -1;
    for (let i = 0; i + 2 < count; i += 3) {
      const c = vertex(i).add(vertex(i + 1)).add(vertex(i + 2))
        .multiplyScalar(1 / 3);
      const ndc = c.clone().project(camera);
      if (Math.abs(ndc.x) > 0.95 || Math.abs(ndc.y) > 0.95) continue;
      const d = solid ? solid.distanceToPoint(c) : 0;
      if (d > farthest) { farthest = d; center = c; }
    }
    if (!center) return null;
    const projected = center.clone().project(camera);
    const rect = renderer.domElement.getBoundingClientRect();
    const screen = ndcToScreen(projected.x, projected.y, rect);
    return {
      name: mesh.userData.surface?.name ?? null,
      label: mesh.userData.surface?.label ?? null,
      x: screen.x,
      y: screen.y,
    };
  }

  /** Centre du premier volume visible, en coordonnées écran — pour que le
   *  smoke clique la pièce là où elle est, pas là où il l'espère. */
  function volumeScreenPoint() {
    let mesh = null;
    volumesGroup.traverse((obj) => {
      if (!mesh && obj.isMesh && obj.visible) mesh = obj;
    });
    if (!mesh) return null;
    mesh.geometry.computeBoundingSphere();
    const center = mesh.geometry.boundingSphere?.center;
    if (!center) return null;
    const projected = mesh.localToWorld(center.clone()).project(camera);
    const rect = renderer.domElement.getBoundingClientRect();
    return ndcToScreen(projected.x, projected.y, rect);
  }

  window.__freesolidDebug = {
    get volumeVisibleCount() { return volumeVisibleCount(); },
    get volumeScreenPoint() { return volumeScreenPoint(); },
    get isOrthographic() { return camera.isOrthographicCamera === true; },
    get sketchLineCount() { return ctx.sketchLineMeshes.length; },
    get sketchScreenPoint() { return sketchScreenPoint(); },
    get surfaceMeshCount() { return ctx.surfaceMeshes.length; },
    get surfaceScreenPoint() { return surfaceScreenPoint(); },
    get featureDimCount() { return ctx.featureDimSprites.length; },
    /** Centre de rotation projeté à l'écran, ou null. */
    get rotationPivotScreen() {
      const pivot = rotationPivot();
      if (!pivot) return null;
      camera.updateMatrixWorld();
      const p = pivot.clone().project(camera);
      const rect = renderer.domElement.getBoundingClientRect();
      return ndcToScreen(p.x, p.y, rect);
    },
    get selectedFeatureName() { return ctx.selectedFeatureName; },
    /** Spline 3D ouverte : points et tracé à l'écran. */
    get curve3dScreen() { return ctx.curveTool?.screen() ?? null; },
    /** Esquisse 3D ouverte : outil, définition, points et cotes à l'écran. */
    get sketch3dScreen() { return ctx.sketch3dTool?.screen() ?? null; },
    refresh: () => refresh(call("get_tree")),
    get graphFeatureActive() { return ctx.graphFn.active; },
    get graphFeatureKind() { return ctx.graphFn.kind; },
    get graphFeatureErrorNode() { return ctx.graphFn.errorNode; },
    get graphFeatureOutput() { return ctx.graphFn.draft?.output ?? null; },
    get graphFeatureNodeIds() {
      return (ctx.graphFn.draft?.nodes ?? []).map((node) => String(node.id));
    },
  };
}
