// Survol, sélection, cadre et cotes posées sur la pièce.
// Les sélections et le survol restent dans main.js : ce module les lit
// au moment du geste.

import { t } from "./i18n.js";
import { eventToNdc, ndcToScreen } from "./screen.js";
import { snapFacePoint } from "./pointsnap.js";
import { coordsText, measureText } from "./statusbar.js";
import { boxMode, isDrag, normalizeRect, pickInBox } from "./navigation.js";
import {
  dimEditPayload, dimLabel, openDimEditor, sketchDimAnchor,
} from "./dims.js";
import { PROP_LABELS } from "./tree.js";

export function findFeatureInTree(tree, name) {
  if (!name || !tree) return null;
  for (const feature of tree.features ?? []) {
    if (feature.name === name) return feature;
    for (const child of feature.children ?? []) {
      if (child.name === name) return child;
    }
  }
  for (const surface of tree.surfaces ?? []) {
    if (surface.name === name) return surface;
  }
  return null;
}

export function installPicking(ctx) {
  const {
    THREE, scene, camera, renderer, controls,
    say, call, panel, pickEl, measureEl, coordsEl, refresh,
    boxOverlay, featureDimsGroup, createDimSprite,
    surfaceHoverMaterial, surfaceSelectedMaterial,
    focusPanelField, pickFilletRadiusBubble, selectComponent,
    viewSize, ORTHO_HEIGHT, updatePlaneVisibility, repaintEdges, pickPlane,
  } = ctx;

  let featureDimContext = null;

  function linePickThreshold() {
    return ORTHO_HEIGHT / (camera.zoom * Math.max(viewSize().height, 1)) * 8;
  }

  function pickHoveredSketch() {
    if (!ctx.sketchLineMeshes.length) return null;
    raycaster.params.Line.threshold = linePickThreshold();
    const hit = raycaster.intersectObjects(ctx.sketchLineMeshes, false)[0];
    return hit?.object.userData.sketch ?? null;
  }

  /** Arête de surface ou courbe 3D sous le pointeur. */
  function pickBoundaryHit() {
    if (!ctx.boundaryLines.length) return null;
    raycaster.params.Line.threshold = linePickThreshold();
    const hit = raycaster.intersectObjects(ctx.boundaryLines, false)[0];
    if (!hit) return null;
    const { name, label, curve, groups } = hit.object.userData.boundary;
    const group = groups.find((g) => hit.index >= g.start
      && hit.index < g.start + g.count);
    if (!group) return null;
    return { distance: hit.distance, point: hit.point,
             boundary: { name, label, curve, edge: group.edgeId } };
  }

  function pickHoveredSurfaceHit() {
    if (!ctx.surfaceMeshes.length) return null;
    return raycaster.intersectObjects(ctx.surfaceMeshes, false)[0] ?? null;
  }

  function repaintSurfaces() {
    for (const mesh of ctx.surfaceMeshes) {
      const name = mesh.userData.surface?.name;
      if (ctx.selectedSurface?.name === name) {
        mesh.material = surfaceSelectedMaterial;
      } else if (ctx.hoveredSurface?.name === name) {
        mesh.material = surfaceHoverMaterial;
      } else {
        mesh.material = mesh.userData.baseMaterial;
      }
    }
  }

  // Face hover: triangle index -> group -> engine faceId. By construction.
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  function worldToScreen(point) {
    const ndc = new THREE.Vector3(point.x, point.y, point.z).project(camera);
    return ndcToScreen(ndc.x, ndc.y, renderer.domElement.getBoundingClientRect());
  }

  function setPointerFromEvent(event) {
    const rect = renderer.domElement.getBoundingClientRect();
    const ndc = eventToNdc(event.clientX, event.clientY, rect);
    pointer.x = ndc.x;
    pointer.y = ndc.y;
  }

  function pointerCtx() {
    raycaster.setFromCamera(pointer, camera);
    return {
      raycaster, pointer, partMesh: ctx.partMesh, scene, camera, controls,
      meshGroups: ctx.meshGroups,
      get faceHit() {
        return ctx.partMesh ? raycaster.intersectObject(ctx.partMesh)[0] : undefined;
      },
    };
  }

  function pluginSeesPointer() {
    return !ctx.assemblyState && !ctx.planePicking && !ctx.measuring;
  }

  renderer.domElement.addEventListener("pointermove", (event) => {
    if (ctx.sketchMode.active) return;
    if (boxStart && isDrag(boxStart, { x: event.clientX, y: event.clientY })) {
      boxOverlay.show(boxStart, { x: event.clientX, y: event.clientY });
    }
    setPointerFromEvent(event);
    if (pluginSeesPointer()
        && ctx.pluginRuntime?.dispatchPointer("move", event, pointerCtx())) {
      return;
    }
    updateHover(event);
  });

  // Dernière position où le survol a été calculé : un appui ailleurs (le
  // pointeur arrivé sans mouvement, après un menu ou une fenêtre) le
  // recalcule d'abord, sinon le clic viserait l'ancien survol.
  let hoverAt = null;

  /** Face, arête, esquisse, surface ou plan sous le pointeur. */
  function updateHover(event) {
    hoverAt = { x: event.clientX, y: event.clientY };
    setPointerFromEvent(event);
    if (ctx.planePicking) {
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObjects(Object.values(ctx.planeMeshes))[0];
      const id = hit?.object.userData.plane ?? null;
      if (id !== ctx.hoverPlane) {
        ctx.hoverPlane = id;
        updatePlaneVisibility();
      }
      renderer.domElement.style.cursor = id ? "pointer" : "";
      return;
    }
    if (!ctx.partMesh && !ctx.sketchLineMeshes.length && !ctx.surfaceMeshes.length
        && !ctx.boundaryLines.length) {
      coordsEl.textContent = "";
      return;
    }
    raycaster.setFromCamera(pointer, camera);

    // L'esquisse libre gagne sur la face (et l'arête) derrière elle :
    // le geste vise le profil, pas le solide. Priorité en pixels, inchangée.
    const sketchHit = pickHoveredSketch();

    let edgeGroupIndex = -1;
    let groupIndex = -1;
    let surfaceHit = null;
    let boundaryHit = null;
    if (!sketchHit) {
      const faceHit = ctx.partMesh
        ? raycaster.intersectObject(ctx.partMesh)[0] : undefined;
      let edgeHit;
      if (ctx.partMesh && ctx.partEdges) {
        const { radius } = ctx.partCenterRadius();
        raycaster.params.Line.threshold = linePickThreshold();
        edgeHit = raycaster.intersectObject(ctx.partEdges)[0];
        if (edgeHit && (!faceHit
            || edgeHit.distance <= faceHit.distance + radius * 0.02)) {
          edgeGroupIndex = ctx.edgeGroups.findIndex(
            (g) => edgeHit.index >= g.start
                && edgeHit.index < g.start + g.count);
        }
      }
      if (edgeGroupIndex < 0 && faceHit) {
        const indexPosition = faceHit.faceIndex * 3;
        groupIndex = ctx.meshGroups.findIndex(
          (g) => indexPosition >= g.start && indexPosition < g.start + g.count);
      }
      // Un panneau qui attend une face du solide voit à travers les
      // surfaces (remplacer une face recouverte par sa surface).
      const throughSurfaces = panel.needs("face") && (faceHit || edgeHit);
      const surfHit = throughSurfaces ? null : pickHoveredSurfaceHit();
      let pointHit = edgeGroupIndex >= 0 ? edgeHit : faceHit;
      if (surfHit) {
        const solidHit = edgeGroupIndex >= 0 ? edgeHit : faceHit;
        if (!solidHit || surfHit.distance < solidHit.distance) {
          surfaceHit = surfHit.object.userData.surface;
          groupIndex = -1;
          edgeGroupIndex = -1;
          pointHit = surfHit;
        }
      }
      // Un bord (arête de surface, courbe 3D) gagne sur ce qu'il borde,
      // à la même tolérance qu'une arête du solide.
      const bound = throughSurfaces ? null : pickBoundaryHit();
      if (bound) {
        const { radius } = ctx.partMesh ? ctx.partCenterRadius()
          : { radius: 50 };
        if (!pointHit || bound.distance <= pointHit.distance + radius * 0.02) {
          boundaryHit = bound.boundary;
          surfaceHit = null;
          groupIndex = -1;
          edgeGroupIndex = -1;
          pointHit = bound;
        }
      }
      // Barre d'état : coordonnées du point visé sur la pièce.
      coordsEl.textContent = coordsText(pointHit?.point ?? null);
    }
    const surfaceName = surfaceHit?.name ?? null;
    const boundaryKey = boundaryHit
      ? `${boundaryHit.name}:${boundaryHit.edge}` : null;
    const hoveredKey = ctx.hoveredBoundary
      ? `${ctx.hoveredBoundary.name}:${ctx.hoveredBoundary.edge}` : null;
    if (groupIndex !== ctx.hoveredGroup || edgeGroupIndex !== ctx.hoveredEdgeGroup
        || sketchHit?.name !== ctx.hoveredSketch?.name
        || surfaceName !== ctx.hoveredSurface?.name
        || boundaryKey !== hoveredKey) {
      ctx.hoveredGroup = groupIndex;
      ctx.hoveredEdgeGroup = edgeGroupIndex;
      ctx.hoveredSketch = sketchHit;
      ctx.hoveredSurface = surfaceHit;
      ctx.hoveredBoundary = boundaryHit;
      renderer.domElement.style.cursor =
        groupIndex >= 0 || edgeGroupIndex >= 0 || sketchHit || surfaceHit
          || boundaryHit ? "pointer" : "";
      repaintGroups();
      repaintEdges();
      repaintSurfaces();
      ctx.repaintBoundaries();
    }
  }

  function repaintGroups() {
    if (ctx.partMesh) {
      ctx.partMesh.geometry.groups.forEach((g, i) => {
        const isSelected = ctx.meshGroups[i].faceId === ctx.selectedFaceId;
        g.materialIndex = isSelected ? 2 : (i === ctx.hoveredGroup ? 1 : 0);
      });
    }
    const parts = [];
    if (ctx.hoveredSketch) {
      parts.push(ctx.hoveredSketch.label);
    } else if (ctx.hoveredBoundary) {
      const b = ctx.hoveredBoundary;
      parts.push(b.curve ? b.label
        : `${b.label} · ${t("Arête {n}", { n: b.edge })}`);
    } else if (ctx.hoveredSurface) {
      parts.push(ctx.hoveredSurface.label);
    } else if (ctx.hoveredEdgeGroup >= 0) {
      parts.push(t("Arête {n}", { n: ctx.edgeGroups[ctx.hoveredEdgeGroup].edgeId }));
    } else if (ctx.hoveredGroup >= 0) {
      parts.push(t("Face {n}", { n: ctx.meshGroups[ctx.hoveredGroup].faceId }));
    }
    if (ctx.selectedEdges.size) {
      parts.push(t("sél. {n} arête(s) — Ctrl+clic : ajouter",
        { n: ctx.selectedEdges.size }));
    } else if (ctx.selectedFaceId !== null) {
      parts.push(t("sél. Face {n}", { n: ctx.selectedFaceId }));
    } else if (ctx.selectedSurface) {
      parts.push(t("sél. {s}", { s: ctx.selectedSurface.label }));
    }
    pickEl.textContent = parts.join(" · ");
    measureEl.textContent = measureText([...ctx.selectedEdges].map((id) =>
      ctx.edgeGroups.find((g) => g.edgeId === id)?.length));
  }

  // Click selects the hovered face (sticky); click in the void deselects.
  // Guarded against orbit drags: a press that travels is navigation, not a pick.
  let pressPosition = null;
  let boxStart = null; // appui gauche dans le vide : peut devenir un cadre

  /** Arêtes du corps actif retenues par le cadre (fenêtre ou capture). */
  function selectEdgesInBox(start, end, additive) {
    if (!ctx.partEdges) return;
    const rect = normalizeRect(start, end);
    const host = renderer.domElement.getBoundingClientRect();
    const pos = ctx.partEdges.geometry.getAttribute("position");
    const index = ctx.partEdges.geometry.getIndex();
    const v = new THREE.Vector3();
    const items = ctx.edgeGroups.map((g) => {
      const points = [];
      for (let k = g.start; k < g.start + g.count; k++) {
        v.fromBufferAttribute(pos, index.getX(k)).project(camera);
        points.push(ndcToScreen(v.x, v.y, host));
      }
      return { id: g.edgeId, points };
    });
    const ids = pickInBox(items, rect, boxMode(start, end));
    ctx.selectedEdges = additive ? new Set([...ctx.selectedEdges, ...ids]) : new Set(ids);
    ctx.selectedFaceId = null;
    ctx.cancelPendingSurfaceClick();
    ctx.clearSketchSelection({ quiet: true });
    ctx.clearSurfaceSelection({ quiet: true });
    repaintGroups();
    repaintEdges();
    if (ctx.lastTree) ctx.renderTree(ctx.lastTree);
    panel.notifyPick("edges", { kind: "edges", edges: [...ctx.selectedEdges] });
  }

  renderer.domElement.addEventListener("pointerdown", (event) => {
    // L'esquisse et la spline 3D gèrent leurs propres clics.
    if (ctx.sketchMode.active || ctx.curveTool?.active) return;
    pressPosition = { x: event.clientX, y: event.clientY };
    if (!ctx.assemblyState
        && (hoverAt?.x !== event.clientX || hoverAt?.y !== event.clientY)) {
      updateHover(event);
    }
    const nothingHovered = ctx.hoveredGroup < 0 && ctx.hoveredEdgeGroup < 0
      && !ctx.hoveredSketch && !ctx.hoveredSurface && !ctx.hoveredBoundary;
    boxStart = event.button === 0 && nothingHovered && !ctx.assemblyState
      && !ctx.planePicking && !ctx.measuring && ctx.partEdges
      ? { x: event.clientX, y: event.clientY } : null;
    if (!pluginSeesPointer()) return;
    setPointerFromEvent(event);
    ctx.pluginRuntime?.dispatchPointer("down", event, pointerCtx());
  });
  renderer.domElement.addEventListener("pointerup", (event) => {
    if (ctx.sketchMode.active || ctx.curveTool?.active) return;
    if (pluginSeesPointer()) {
      setPointerFromEvent(event);
      if (ctx.pluginRuntime?.dispatchPointer("up", event, pointerCtx())) {
        pressPosition = null;
        return;
      }
    }
    const box = boxStart;
    boxStart = null;
    boxOverlay.hide();
    if (box && isDrag(box, { x: event.clientX, y: event.clientY })) {
      pressPosition = null;
      selectEdgesInBox(box, { x: event.clientX, y: event.clientY },
        event.ctrlKey || event.metaKey);
      return;
    }
    if (!pressPosition) return;
    const travel = Math.hypot(event.clientX - pressPosition.x,
                              event.clientY - pressPosition.y);
    pressPosition = null;
    if (travel > 5) return;
    if (ctx.assemblyState) {
      raycaster.setFromCamera(pointer, camera);
      const hit = ctx.asmGroup
        ? raycaster.intersectObjects(ctx.asmGroup.children, false)[0] : null;
      // Panneau Contrainte ouvert : le clic vise une FACE du composant.
      if (hit && panel.active) {
        const groups = hit.object.userData.groups ?? [];
        const indexPosition = hit.faceIndex * 3;
        const g = groups.find((grp) => indexPosition >= grp.start
          && indexPosition < grp.start + grp.count);
        if (g && panel.notifyPick("asmface", {
              kind: "asmface",
              component: hit.object.userData.component,
              componentLabel: hit.object.userData.componentLabel,
              face: g.faceId })) {
          selectComponent(hit.object.userData.component);
          return;
        }
      }
      selectComponent(hit ? hit.object.userData.component : null);
      return;
    }
    if (ctx.planePicking) {
      if (ctx.hoverPlane) pickPlane(ctx.hoverPlane);
      return;
    }

    if (ctx.onMeasurePointerUp()) return;

    const clearPlaneChoice = () => {
      if (ctx.selectedPlane !== null || ctx.selectedDatumFeature !== null) {
        ctx.selectedPlane = null;
        ctx.selectedDatumFeature = null;
        ctx.refreshDatumGhost(null);
        updatePlaneVisibility();
        if (ctx.lastTree) ctx.renderTree(ctx.lastTree);
      }
    };

    if (ctx.hoveredSketch) {
      ctx.selectedFaceId = null;
      ctx.selectedEdges = new Set();
      clearPlaneChoice();
      ctx.cancelPendingSurfaceClick();
      ctx.clearSurfaceSelection({ quiet: true });
      repaintGroups();
      repaintEdges();
      ctx.selectSketch(ctx.hoveredSketch);
      if (event.button === 0) ctx.showContextToolbar(event);
      return;
    }

    if (ctx.hoveredBoundary) {
      const b = ctx.hoveredBoundary;
      ctx.selectedFaceId = null;
      ctx.selectedEdges = new Set();
      clearPlaneChoice();
      ctx.clearSketchSelection({ quiet: true });
      repaintGroups();
      repaintEdges();
      // Un panneau qui attend des bords les prend ; sinon le clic choisit
      // l'objet entier (la courbe, la surface), comme dans l'arbre. Si la
      // première case vide attend une surface, l'arête la désigne.
      const wanted = panel.firstNeeded(["boundary", "surface"]);
      if (wanted === "surface") {
        ctx.onSurfaceClick({ name: b.name, label: b.label });
        return;
      }
      if (panel.notifyPick("boundary", { kind: "boundary", ...b })) return;
      ctx.onSurfaceClick({ name: b.name, label: b.label });
      return;
    }

    if (ctx.hoveredSurface) {
      ctx.selectedFaceId = null;
      ctx.selectedEdges = new Set();
      clearPlaneChoice();
      ctx.clearSketchSelection({ quiet: true });
      repaintGroups();
      repaintEdges();
      // Une face précise de la surface (supprimer, projeter, désajuster).
      if (panel.accepts("surfface")) {
        raycaster.setFromCamera(pointer, camera);
        const hit = pickHoveredSurfaceHit();
        const groups = hit?.object.userData.groups ?? [];
        const at = hit ? hit.faceIndex * 3 : -1;
        const group = groups.find((g) => at >= g.start && at < g.start + g.count);
        if (hit && panel.notifyPick("surfface", {
          kind: "surfface", ...ctx.hoveredSurface,
          face: group?.faceId ?? 0 })) return;
      }
      // Forme libre : une fois la surface choisie, chaque clic ajoute un
      // point à pousser.
      if (panel.accepts("point3d") && !panel.needs("surface")) {
        raycaster.setFromCamera(pointer, camera);
        const hit = pickHoveredSurfaceHit();
        const round = (v) => Math.round(v * 1000) / 1000;
        if (hit && panel.notifyPick("point3d", { kind: "point3d",
          x: round(hit.point.x), y: round(hit.point.y),
          z: round(hit.point.z) })) return;
      }
      // Ajuster : une fois l'outil choisi, le clic désigne la partie
      // gardée — la surface ET l'endroit cliqué.
      if (panel.accepts("surfpoint") && !panel.needs("surface")) {
        raycaster.setFromCamera(pointer, camera);
        const hit = pickHoveredSurfaceHit();
        const groups = hit?.object.userData.groups ?? [];
        const at = hit ? hit.faceIndex * 3 : -1;
        const group = groups.find((g) => at >= g.start && at < g.start + g.count);
        if (hit && panel.notifyPick("surfpoint", {
          kind: "surfpoint", ...ctx.hoveredSurface, face: group?.faceId ?? 0,
          x: hit.point.x, y: hit.point.y, z: hit.point.z })) return;
      }
      ctx.onSurfaceClick(ctx.hoveredSurface);
      return;
    }

    if (ctx.hoveredEdgeGroup >= 0) {
      const id = ctx.edgeGroups[ctx.hoveredEdgeGroup].edgeId;
      // Remplissage : une arête du solide devient un bord du contour.
      if (panel.accepts("boundary") && !panel.accepts("edges")
          && panel.notifyPick("boundary", {
            kind: "boundary", body: true, name: "body",
            label: t("Solide"), edge: id })) {
        return;
      }
      if (event.ctrlKey || event.metaKey) {
        if (!ctx.selectedEdges.delete(id)) ctx.selectedEdges.add(id);
      } else {
        ctx.selectedEdges = new Set([id]);
      }
      ctx.selectedFaceId = null;
      clearPlaneChoice();
      ctx.cancelPendingSurfaceClick();
      ctx.clearSketchSelection({ quiet: true });
      ctx.clearSurfaceSelection({ quiet: true });
      if (ctx.lastTree) ctx.renderTree(ctx.lastTree);
      repaintGroups();
      repaintEdges();
      panel.notifyPick("edges",
        { kind: "edges", edges: [...ctx.selectedEdges] });
      if (event.button === 0) ctx.showContextToolbar(event);
      return;
    }

    ctx.selectedFaceId = ctx.hoveredGroup >= 0 ? ctx.meshGroups[ctx.hoveredGroup].faceId : null;
    ctx.selectedEdges = new Set(); // une face (ou le vide) remplace les arêtes
    ctx.cancelPendingSurfaceClick();
    ctx.clearSketchSelection({ quiet: true });
    ctx.clearSurfaceSelection({ quiet: true });
    repaintEdges();
    repaintGroups();
    if (ctx.selectedFaceId !== null) {
      clearPlaneChoice();
      raycaster.setFromCamera(pointer, camera);
      const faceHit = ctx.partMesh
        ? raycaster.intersectObject(ctx.partMesh)[0] : null;
      if (faceHit) {
        // La normale sert à « Normal à » (Ctrl+8).
        const normal = faceHit.face
          ? faceHit.face.normal.clone()
            .transformDirection(faceHit.object.matrixWorld)
          : null;
        ctx.lastFaceHit = {
          face: ctx.selectedFaceId,
          x: faceHit.point.x, y: faceHit.point.y, z: faceHit.point.z,
          normal: normal ? [normal.x, normal.y, normal.z] : null,
        };
      }
      // A command panel with a selection box absorbs the pick : d'abord
      // une zone de positions (le point cliqué), sinon une zone de faces.
      // La position s'aimante au centre d'un cercle ou à un sommet tout
      // proche : un perçage au centre d'un moyeu tombe juste.
      const hit = ctx.lastFaceHit
        && snapFacePoint(ctx.lastFaceHit, ctx.lastFaceHit.normal,
          ctx.edgeSnaps, worldToScreen);
      const tookPoint = hit && panel.notifyPick("point", {
        kind: "point", face: ctx.selectedFaceId, x: hit.x, y: hit.y, z: hit.z });
      if (tookPoint && hit.snapped) {
        say(hit.snapped === "center"
          ? t("Position au centre du cercle.") : t("Position sur le sommet."));
      }
      if (!tookPoint) {
        panel.notifyPick("face", { kind: "face", face: ctx.selectedFaceId });
      }
      if (event.button === 0) ctx.showContextToolbar(event);
    } else {
      ctx.lastFaceHit = null;
      clearPlaneChoice();
      clearFeatureDims();
      ctx.pluginRuntime?.runPointerIdle(pointerCtx());
    }
    if (ctx.lastTree) ctx.renderTree(ctx.lastTree);
  });

  function disposeFeatureDimSprites() {
    for (const sprite of ctx.featureDimSprites) {
      sprite.material?.map?.dispose();
      sprite.material?.dispose();
    }
    featureDimsGroup.clear();
    ctx.featureDimSprites = [];
  }

  function clearFeatureDims() {
    disposeFeatureDimSprites();
    featureDimContext = null;
    if (ctx.selectedFeatureName) {
      ctx.selectedFeatureName = null;
      if (ctx.lastTree) ctx.renderTree(ctx.lastTree);
    }
  }

  function sketchWorldPoint(placement, x, y) {
    const matrix = new THREE.Matrix4().set(...placement);
    return new THREE.Vector3(x, y, 0).applyMatrix4(matrix);
  }

  function featureParamWorldPos(param, feature, hit, sketchState) {
    if (sketchState?.placement
        && (param.prop === "Length" || param.prop === "LengthFwd")) {
      const matrix = new THREE.Matrix4().set(...sketchState.placement);
      const origin = new THREE.Vector3().setFromMatrixPosition(matrix);
      const normal = new THREE.Vector3(0, 0, 1).transformDirection(matrix);
      return origin.add(normal.normalize().multiplyScalar(param.value / 2));
    }
    if (hit) return hit.clone().add(new THREE.Vector3(0, 0, 3));
    return new THREE.Vector3(0, 0, 8);
  }

  async function showFeatureDims(featureName, hit) {
    if (!featureName) {
      const match = ctx.lastFaceMatch;
      const detail = match && match.faces
        ? " " + t("({m}/{n} face(s) appariée(s) à une fonction)",
          { m: match.matched, n: match.faces })
        : "";
      say(t("cette face n'a pas de fonction associée") + detail, true);
      clearFeatureDims();
      return;
    }
    const feature = findFeatureInTree(ctx.lastTree, featureName);
    if (!feature) {
      say("cette face n'appartient à aucune fonction éditable");
      clearFeatureDims();
      return;
    }
    ctx.selectedFeatureName = feature.name;
    featureDimContext = {
      feature: feature.name,
      hit: hit ? hit.clone() : null,
    };
    disposeFeatureDimSprites();
    const sketches = (feature.children ?? []).filter(
      (child) => child.type === "Sketcher::SketchObject");
    if (feature.type === "Sketcher::SketchObject") sketches.push(feature);
    const params = feature.params?.length
      ? feature.params
      : ((await call("get_params", { feature: feature.name })).params ?? []);
    let firstSketchState = null;
    for (const sketch of sketches) {
      let state;
      try {
        state = await call("sketch_state", { sketch: sketch.name });
      } catch (error) {
        say(error.message, true);
        continue;
      }
      if (!firstSketchState) firstSketchState = state;
      for (const dim of state.dims ?? []) {
        const anchor = sketchDimAnchor(dim, state.entities);
        if (!anchor) continue;
        const world = sketchWorldPoint(state.placement, anchor.x, anchor.y);
        const sprite = createDimSprite(dimLabel(dim), world.x, world.y, world.z);
        sprite.userData.dim = { ...dim, kind: "sketch", sketch: sketch.name };
        sprite.renderOrder = 24;
        featureDimsGroup.add(sprite);
        ctx.featureDimSprites.push(sprite);
      }
    }
    for (const param of params) {
      const [label, unit] = PROP_LABELS[param.prop] ?? [param.prop, "mm"];
      const dim = {
        kind: "param",
        name: label,
        value: param.value,
        expr: param.expr || "",
        unit,
        feature: feature.name,
        prop: param.prop,
        type: param.prop === "Angle" ? "Angle" : "Distance",
      };
      const world = featureParamWorldPos(
        param, feature, hit, firstSketchState);
      const sprite = createDimSprite(dimLabel({
        ...dim,
        type: dim.unit === "°" ? "Angle" : dim.type,
        value: dim.unit === "°" ? dim.value * Math.PI / 180 : dim.value,
      }), world.x, world.y, world.z);
      sprite.userData.dim = dim;
      sprite.renderOrder = 24;
      featureDimsGroup.add(sprite);
      ctx.featureDimSprites.push(sprite);
    }
    if (!ctx.featureDimSprites.length) {
      say(t("{f} : aucune cote à afficher", { f: feature.label }));
      return;
    }
    if (ctx.lastTree) ctx.renderTree(ctx.lastTree);
    say(t("{f} : {n} cote(s) — double-clic une cote pour la changer",
      { f: feature.label, n: ctx.featureDimSprites.length }));
  }

  function pickFeatureDim(event) {
    if (!ctx.featureDimSprites.length) return false;
    const rect = renderer.domElement.getBoundingClientRect();
    for (const sprite of ctx.featureDimSprites) {
      const projected = sprite.position.clone().project(camera);
      const screen = ndcToScreen(projected.x, projected.y, rect);
      const sx = screen.x;
      const sy = screen.y;
      if (Math.hypot(sx - event.clientX, sy - event.clientY) < 22) {
        editFeatureDim(sprite.userData.dim);
        return true;
      }
    }
    return false;
  }

  function editFeatureDim(dim) {
    if (!dim) return;
    openDimEditor({
      panel,
      dim,
      onApply: (values, meta) => {
        const extra = dimEditPayload(values, dim, meta);
        if (dim.kind === "sketch") {
          if (extra.name === undefined && extra.value === undefined
              && extra.expr === undefined) return;
          refreshFeatureDimEdit(call("sketch_set_dim", {
            sketch: dim.sketch, dim: dim.id, ...extra,
          }).then(() => call("get_tree")));
          return;
        }
        if (extra.value === undefined && extra.expr === undefined) return;
        const raw = extra.expr ?? extra.value;
        refreshFeatureDimEdit(call("set_params", {
          feature: dim.feature,
          values: { [dim.prop]: raw },
        }));
      },
    });
  }

  function refreshFeatureDimEdit(treePromise) {
    const dims = featureDimContext;
    refresh(treePromise).then(() => {
      if (dims) return showFeatureDims(dims.feature, dims.hit);
    });
  }

  renderer.domElement.addEventListener("dblclick", (event) => {
    if (ctx.sketchMode.active || ctx.assemblyState || ctx.planePicking || ctx.measuring) return;
    if (ctx.hoveredSurface) {
      ctx.onSurfaceDblClick(ctx.hoveredSurface);
      return;
    }
    if (pickFilletRadiusBubble(event)) {
      focusPanelField("radius");
      return;
    }
    if (pickFeatureDim(event)) return;
    if (ctx.hoveredGroup < 0) {
      clearFeatureDims();
      return;
    }
    const group = ctx.meshGroups[ctx.hoveredGroup];
    const hit = ctx.lastFaceHit && ctx.lastFaceHit.face === group.faceId
      ? new THREE.Vector3(ctx.lastFaceHit.x, ctx.lastFaceHit.y, ctx.lastFaceHit.z)
      : null;
    showFeatureDims(group.feature, hit);
  });
  return {
    raycaster, pointer, setPointerFromEvent,
    repaintGroups, repaintSurfaces, findFeatureInTree, clearFeatureDims,
  };
}
