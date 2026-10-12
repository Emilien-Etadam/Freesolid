// Arbre de création, volet flottant et renommage.
// Les sélections (`lastTree`, esquisse, plan, surface) restent dans main.js.

import { t } from "./i18n.js";
import { iconSrc } from "./icons.js";
import { num } from "./num.js";
import { arcAngles } from "./geom2d.js";
import { sketchTreeLabel, splitHistoryAroundBar } from "./history.js";
import { renameClickAction } from "./rename.js";
import {
  chamferRows, chamferFieldValue, chamferEditValues, chamferProblem,
  revolutionGroups, revolutionEditValues, revolutionProblem,
  checkedContours, contourRows, vertexChamferDistances, vertexChamferRows,
} from "./features.js";
import { isGraphFeature, isRepeatFeature } from "./graph.js";
import { readScene } from "./theme.js";

const sceneTheme = readScene();

// Rôles de la table icons.js : même rôle que la commande qui crée
// l'élément. Le graphe garde, lui, les fichiers d'avant.
export const TREE_ICONS = {
  "Sketcher::SketchObject": "sketch",
  "PartDesign::Pad": "nodes_extrude",
  "PartDesign::Pocket": "pocket",
  "PartDesign::Fillet": "fillet",
  "PartDesign::Chamfer": "chamfer",
  "PartDesign::Revolution": "revolve",
  "PartDesign::Groove": "groove",
  "PartDesign::Mirrored": "mirror",
  "PartDesign::LinearPattern": "linear_pattern",
  "PartDesign::PolarPattern": "polar_pattern",
  "PartDesign::Thickness": "shell",
  "PartDesign::Draft": "draft",
  "PartDesign::Hole": "hole",
  "PartDesign::Plane": "plane",
  "PartDesign::AdditiveLoft": "loft",
  "PartDesign::SubtractiveLoft": "loft",
  "PartDesign::AdditivePipe": "sweep",
  "PartDesign::SubtractivePipe": "sweep",
  "PartDesign::AdditiveHelix": "nodes_helix",
  "PartDesign::Boolean": "boolean",
  "PartDesign::Body": "body",
  "Part::Extrusion": "nodes_extrude",
  "Part::Revolution": "revolve",
  "Part::Loft": "loft",
  "Part::Feature": "body",
  "Part::Offset": "body",
  "App::Link": "insert",
};

// Icônes des surfaces dans l'arbre, par type d'objet.
const SURFACE_ICONS = {
  "Part::Extrusion": "surface_extrude",
  "Part::Revolution": "surface_revolve",
  "Part::Loft": "surface_loft",
  "Part::Sweep": "surface_sweep",
  "Part::Face": "surface_planar",
  "Part::Offset": "surface_offset",
  "Surface::Filling": "surface_fill",
  "Surface::Extend": "surface_extend",
  "Part::FeaturePython": "surface_trim",
  "Surface::GeomFillSurface": "surface_boundary",
  "Part::RuledSurface": "surface_ruled",
  "Part::Fillet": "surface_fillet",
  "Part::Section": "curve_intersection",
  "Part::ProjectOnSurface": "curve_project",
  "PartDesign::SubShapeBinder": "curve_composite",
  "Part::Helix": "nodes_helix",
  "Part::Offset2D": "surface_radiate",
};

export const PROP_LABELS = {
  Length: ["Profondeur", "mm"],
  LengthFwd: ["Longueur", "mm"],
  Pitch: ["Pas", "mm"],
  Height: ["Hauteur", "mm"],
  Radius: ["Rayon", "mm"],
  Size: ["Distance", "mm"],
  Angle: ["Angle", "°"],
  Thickness: ["Épaisseur", "mm"],
  Thickness2: ["Épaisseur côté 2", "mm"],
  CapThickness: ["Épaisseur des extrémités", "mm"],
  Value: ["Épaisseur", "mm"],
  Occurrences: ["Nombre d'occurrences", ""],
  Diameter: ["Diamètre", "mm"],
  Depth: ["Profondeur", "mm"],
  HoleCutDiameter: ["Ø lamage/fraisage", "mm"],
  HoleCutDepth: ["Profondeur du lamage", "mm"],
};

/** Branche l'arbre. Les fonctions renvoyées sont celles que le reste
 *  de l'application appelle déjà. */
export function installTree(ctx) {
  const {
    THREE, scene, treeEl, panel,
    say, call, refresh, refreshAny,
    disposeSubtree, hexColor, partCenterRadius,
    repaintEdges, repaintGroups, repaintSurfaces, sketchHighlightMaterial,
    updatePlaneVisibility, pickPlane, schedulePreview,
    findFeatureInTree, updateEditMode, toggleOrigin, openEquationsPanel,
    clearAssemblyView, closeGraph, enterGraphFeature, syncGraphFromTree,
  } = ctx;

  // ---------- arbre en surimpression pendant une commande ----------
  // Le panneau prend la place de l'arbre : l'arbre (le même élément, avec
  // ses écouteurs) passe dans un volet en haut à gauche de la vue, pour y
  // cliquer une fonction, une esquisse ou un plan pendant la commande.

  const treeFlyout = document.getElementById("tree-flyout");
  const treeFlyoutBody = document.getElementById("tree-flyout-body");
  const TREE_FLYOUT_KEY = "freesolid.treeFlyoutOpen";

  function updateTreeFlyout() {
    if (!treeFlyout) return;
    const tree = document.getElementById("tree");
    if (panel.active) {
      if (tree.parentElement !== treeFlyoutBody) treeFlyoutBody.appendChild(tree);
      treeFlyout.hidden = false;
    } else {
      const aside = document.querySelector("aside");
      if (tree.parentElement !== aside) {
        aside.insertBefore(tree, document.getElementById("panel"));
      }
      treeFlyout.hidden = true;
    }
  }

  function setTreeFlyoutOpen(open) {
    treeFlyout?.classList.toggle("collapsed", !open);
    try { localStorage.setItem(TREE_FLYOUT_KEY, open ? "1" : "0"); } catch { /* ok */ }
  }

  document.getElementById("tree-flyout-toggle")?.addEventListener("click", () =>
    setTreeFlyoutOpen(treeFlyout.classList.contains("collapsed")));
  setTreeFlyoutOpen((() => {
    try { return localStorage.getItem(TREE_FLYOUT_KEY) !== "0"; } catch { return true; }
  })());


  // ---------- plans de référence (fantôme + sélection d'esquisse) ----------

  let datumGhost = null;

  function refreshDatumGhost(hoverFeature) {
    if (datumGhost) {
      disposeSubtree(datumGhost);
      scene.remove(datumGhost);
      datumGhost = null;
    }
    const feature = hoverFeature ?? ctx.selectedDatumFeature;
    if (!feature?.placement) return;
    const { radius } = partCenterRadius();
    const size = Math.max(radius * 1.4, 60);
    const holder = new THREE.Group();
    holder.matrixAutoUpdate = false;
    holder.matrix.set(...feature.placement);
    const fillMaterial = new THREE.MeshBasicMaterial({
      color: sceneTheme.accent, transparent: true, opacity: 0.14,
      side: THREE.DoubleSide, depthWrite: false });
    fillMaterial.userData.own = true;
    const fill = new THREE.Mesh(
      new THREE.PlaneGeometry(size, size), fillMaterial);
    const borderMaterial = new THREE.LineBasicMaterial(
      { color: sceneTheme.accent, transparent: true, opacity: 0.7 });
    borderMaterial.userData.own = true;
    const border = new THREE.LineSegments(
      new THREE.EdgesGeometry(fill.geometry), borderMaterial);
    holder.add(fill, border);
    scene.add(holder);
    datumGhost = holder;
  }

  function onDatumRow(feature) {
    cancelPendingSurfaceClick();
    clearSketchSelection({ quiet: true });
    clearSurfaceSelection({ quiet: true });
    ctx.selectedDatumFeature =
      ctx.selectedDatumFeature?.name === feature.name
        ? null
        : { name: feature.name, placement: feature.placement };
    if (ctx.selectedDatumFeature) {
      ctx.selectedPlane = null;
      ctx.selectedFaceId = null;
      repaintGroups();
      updatePlaneVisibility();
    }
    refreshDatumGhost(null);
    if (ctx.lastTree) renderTree(ctx.lastTree);
    say(ctx.selectedDatumFeature
      ? t("{f} choisi — cliquez Esquisse pour dessiner dessus",
        { f: feature.label })
      : "Plan de référence désélectionné");
  }

  function treeIcon(file) {
    const img = document.createElement("img");
    img.src = iconSrc(file);
    img.alt = "";
    return img;
  }

  const expandedFeatures = new Set(); // les fonctions dépliées (persiste)
  const folderState = Object.create(null); // dossiers tête, mémoire de session
  const folderPrevCounts = Object.create(null); // compteurs du rendu précédent
  let sketchClickTimer = null;
  let surfaceClickTimer = null;

  /** Clic simple (éventuellement différé pour laisser passer le double-clic). */
  function onSketchRowClick(feature) {
    clearTimeout(sketchClickTimer);
    sketchClickTimer = setTimeout(() => selectSketch(feature), 280);
  }

  function onSketchRowDblClick(feature) {
    clearTimeout(sketchClickTimer);
    sketchClickTimer = null;
    // Entrer en édition sans passer par le toggle de sélection.
    clearSketchSelection({ quiet: true });
    if (ctx.lastTree) renderTree(ctx.lastTree);
    editFeature(feature);
  }

  function clearSketchHighlight() {
    if (!ctx.sketchHighlightGroup) return;
    scene.remove(ctx.sketchHighlightGroup);
    disposeSubtree(ctx.sketchHighlightGroup);
    ctx.sketchHighlightGroup = null;
  }

  function drawSketchHighlight(state) {
    clearSketchHighlight();
    if (!state?.entities?.length) return;
    const group = new THREE.Group();
    group.renderOrder = 25;
    group.matrixAutoUpdate = false;
    group.matrix.set(...state.placement);
    for (const entity of state.entities) {
      let points = null;
      if (entity.type === "line") {
        points = [
          new THREE.Vector3(entity.p1[0], entity.p1[1], 0),
          new THREE.Vector3(entity.p2[0], entity.p2[1], 0)];
      } else if (entity.type === "circle") {
        points = [];
        for (let i = 0; i <= 48; i++) {
          const a = (i / 48) * Math.PI * 2;
          points.push(new THREE.Vector3(
            entity.c[0] + entity.r * Math.cos(a),
            entity.c[1] + entity.r * Math.sin(a), 0));
        }
      } else if (entity.type === "arc") {
        const { a1, a2 } = arcAngles(entity);
        points = [];
        for (let i = 0; i <= 32; i++) {
          const a = a1 + (i / 32) * (a2 - a1);
          points.push(new THREE.Vector3(
            entity.c[0] + entity.r * Math.cos(a),
            entity.c[1] + entity.r * Math.sin(a), 0));
        }
      } else if (entity.type === "poly" && entity.points?.length > 1) {
        points = entity.points.map((p) => new THREE.Vector3(p[0], p[1], 0));
      }
      if (!points) continue;
      const line = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(points),
        sketchHighlightMaterial);
      line.renderOrder = 25;
      group.add(line);
    }
    scene.add(group);
    ctx.sketchHighlightGroup = group;
  }

  function sketchConsumerLabel(tree, sketchName) {
    for (const feature of tree?.features ?? []) {
      for (const child of feature.children ?? []) {
        if (child.name === sketchName) return feature.label;
      }
    }
    return null;
  }

  function clearSketchSelection({ quiet = false } = {}) {
    const had = ctx.selectedSketch !== null || ctx.sketchHighlightGroup
      || ctx.sketchInfoOpen;
    ctx.selectedSketch = null;
    clearSketchHighlight();
    if (ctx.sketchInfoOpen) {
      ctx.sketchInfoOpen = false;
      if (panel.active) panel.close({ silent: true });
    }
    if (!had) return;
    if (!quiet && ctx.lastTree) renderTree(ctx.lastTree);
  }

  function cancelPendingSurfaceClick() {
    clearTimeout(surfaceClickTimer);
    surfaceClickTimer = null;
  }

  function surfaceRecord(ref) {
    const name = ref?.name;
    if (!name) return null;
    return (ctx.lastTree?.surfaces ?? []).find((s) => s.name === name) ?? ref;
  }

  function onSurfaceClick(surface) {
    clearTimeout(surfaceClickTimer);
    const target = { name: surface.name, label: surface.label };
    surfaceClickTimer = setTimeout(() => selectSurface(target), 280);
  }

  function onSurfaceDblClick(ref) {
    cancelPendingSurfaceClick();
    const surface = surfaceRecord(ref);
    if (!surface) return;
    clearSurfaceSelection({ quiet: true });
    if (ctx.lastTree) renderTree(ctx.lastTree);
    editSurface(surface);
  }

  function clearSurfaceSelection({ quiet = false } = {}) {
    const had = ctx.selectedSurface !== null;
    ctx.selectedSurface = null;
    repaintSurfaces();
    if (!had) return;
    if (!quiet && ctx.lastTree) renderTree(ctx.lastTree);
  }

  function selectSurface(surface) {
    const pick = { kind: "surface", name: surface.name, label: surface.label };
    if (panel.notifyPick("surface", pick)) return;
    if (ctx.selectedSurface?.name === surface.name) {
      clearSurfaceSelection();
      say("Surface désélectionnée");
      return;
    }
    ctx.selectedPlane = null;
    ctx.selectedDatumFeature = null;
    refreshDatumGhost(null);
    updatePlaneVisibility();
    ctx.selectedFaceId = null;
    ctx.selectedEdges = new Set();
    clearSketchSelection({ quiet: true });
    ctx.selectedSurface = { name: surface.name, label: surface.label };
    if (ctx.lastTree) renderTree(ctx.lastTree);
    repaintGroups();
    repaintEdges();
    repaintSurfaces();
    say(surface.label);
  }

  async function selectSketch(feature) {
    const pick = { kind: "sketch", name: feature.name, label: feature.label };
    if (panel.notifyPick("sketch", pick)) return; // loft/sweep absorbe
    if (ctx.selectedSketch?.name === feature.name) {
      clearSketchSelection();
      say("Esquisse désélectionnée");
      return;
    }
    // Autre sélection d'arbre : un seul focus à la fois.
    ctx.selectedPlane = null;
    ctx.selectedDatumFeature = null;
    refreshDatumGhost(null);
    updatePlaneVisibility();
    cancelPendingSurfaceClick();
    clearSurfaceSelection({ quiet: true });
    ctx.selectedSketch = { name: feature.name, label: feature.label };
    if (ctx.lastTree) renderTree(ctx.lastTree);
    try {
      const state = await call("sketch_state", { sketch: feature.name });
      if (ctx.selectedSketch?.name !== feature.name) return; // course
      drawSketchHighlight(state);
      openSketchInfoPanel(state, feature);
    } catch (error) {
      say(error.message, true);
      clearSketchSelection();
    }
  }

  function openSketchInfoPanel(state, feature) {
    const usedBy = sketchConsumerLabel(ctx.lastTree, feature.name);
    const nEnt = state.entities?.length ?? 0;
    const nCon = state.constraints?.length ?? 0;
    const dof = state.dof;
    const status = state.fullyConstrained
      ? t("totalement contrainte")
      : dof !== null && dof !== undefined
        ? t("{n} degré(s) de liberté", { n: dof })
        : t("état inconnu");
    ctx.sketchInfoOpen = true;
    panel.open({
      icon: "sketch",
      title: state.label || feature.label,
      noApply: true,
      groups: [{
        label: t("Propriétés"),
        rows: [
          { type: "note",
            text: t("Support : {s}", { s: state.support || "—" }) },
          { type: "note",
            text: t("Entités : {e} — Contraintes : {c}", { e: nEnt, c: nCon }) },
          { type: "note", text: t("État : {s}", { s: status }) },
          { type: "note",
            text: t("Utilisée par : {f}", { f: usedBy ?? t("libre") }) },
        ],
      }],
      actions: [{
        label: t("Modifier"),
        title: t("Modifier l'esquisse"),
        className: "paction",
        onClick: () => {
          ctx.sketchInfoOpen = false;
          const target = {
            type: "Sketcher::SketchObject",
            name: feature.name,
            label: feature.label,
          };
          ctx.selectedSketch = null;
          clearSketchHighlight();
          if (ctx.lastTree) renderTree(ctx.lastTree);
          editFeature(target);
        },
      }],
      onCancel: () => {
        // Fermer / Échap uniquement (open() remplace en silencieux).
        ctx.sketchInfoOpen = false;
        ctx.selectedSketch = null;
        clearSketchHighlight();
        if (ctx.lastTree) renderTree(ctx.lastTree);
      },
    });
  }

  function onPlaneRow(id) {
    if (ctx.planePicking) { pickPlane(id); return; }
    cancelPendingSurfaceClick();
    clearSketchSelection({ quiet: true });
    clearSurfaceSelection({ quiet: true });
    ctx.selectedPlane = ctx.selectedPlane === id ? null : id;
    if (ctx.selectedPlane !== null) {
      ctx.selectedDatumFeature = null;
      refreshDatumGhost(null);
      if (ctx.selectedFaceId !== null) {
        ctx.selectedFaceId = null;
        repaintGroups();
      }
    }
    updatePlaneVisibility();
    if (ctx.lastTree) renderTree(ctx.lastTree);
    say(ctx.selectedPlane
      ? "Plan choisi — cliquez Esquisse pour dessiner dessus"
      : "Plan désélectionné");
  }

  function dropRolledBackSelection(tree) {
    let dropped = false;
    if (ctx.selectedSurface) {
      const surf = (tree.surfaces ?? []).find(
        (item) => item.name === ctx.selectedSurface.name);
      if (!surf || surf.rolled_back) {
        ctx.selectedSurface = null;
        dropped = true;
      }
    }
    if (ctx.selectedSketch) {
      const feat = (tree.features ?? []).find(
        (item) => item.name === ctx.selectedSketch.name);
      if (feat?.type === "Sketcher::SketchObject" && feat.rolled_back) {
        ctx.selectedSketch = null;
        clearSketchHighlight();
        dropped = true;
      }
    }
    if (dropped) {
      ctx.hoveredSurface = null;
      ctx.hoveredSketch = null;
      repaintGroups();
    }
  }

  function rememberFolderCount(key, count) {
    const prev = folderPrevCounts[key];
    if (typeof prev === "number" && count > prev) {
      folderState[key] = true;
    }
    folderPrevCounts[key] = count;
  }

  function folderIsOpen(key, defaultOpen) {
    return Object.prototype.hasOwnProperty.call(folderState, key)
      ? folderState[key]
      : defaultOpen;
  }

  function toggleFolder(key, defaultOpen) {
    folderState[key] = !folderIsOpen(key, defaultOpen);
    if (ctx.lastTree) renderTree(ctx.lastTree);
  }

  function appendFolder(key, label, count, icon, defaultOpen, extra = {}) {
    const open = folderIsOpen(key, defaultOpen);
    const item = document.createElement("li");
    item.className = "folder" + (count === 0 ? " empty" : "");
    item.dataset.folder = key;
    const arrow = document.createElement("span");
    arrow.className = "arrow";
    arrow.textContent = open ? "▾" : "▸";
    arrow.addEventListener("click", (event) => {
      event.stopPropagation();
      toggleFolder(key, defaultOpen);
    });
    item.appendChild(arrow);
    item.appendChild(treeIcon(icon));
    item.appendChild(document.createTextNode(`${label} (${count})`));
    if (extra.title) item.title = extra.title;
    if (extra.clickToggles !== false) {
      item.addEventListener("click", () => toggleFolder(key, defaultOpen));
    }
    if (extra.onDblClick) {
      item.addEventListener("dblclick", (event) => {
        event.stopPropagation();
        extra.onDblClick();
      });
    }
    treeEl.appendChild(item);
    return open;
  }

  function appendBodyRow(bodyInfo) {
    const bodyItem = document.createElement("li");
    const empty = bodyInfo.has_solid !== true;
    bodyItem.className = "body in-folder"
      + (bodyInfo.active ? " active" : "")
      + (empty ? " empty" : "")
      + (bodyInfo.hidden ? " hidden-object" : "");
    bodyItem.appendChild(treeIcon("body"));
    if (hexColor(bodyInfo.color)) {
      const swatch = document.createElement("span");
      swatch.className = "swatch";
      swatch.style.background = bodyInfo.color;
      bodyItem.appendChild(swatch);
    }
    const suffix = empty
      ? " — " + t("vide")
      : (bodyInfo.active ? ""
        : " — " + t("{n} élément(s)", { n: bodyInfo.count }));
    bodyItem.appendChild(document.createTextNode(bodyInfo.label + suffix
      + (bodyInfo.hidden ? " — " + t("masqué") : "")));
    if (bodyInfo.name) {
      bodyItem.dataset.feat = bodyInfo.name;
      if (!bodyInfo.active) bodyItem.title = t("Clic : activer ce corps");
      bodyItem.addEventListener("click", (event) => {
        if (consumeTreeRenameClick(event, bodyItem, bodyInfo)) return;
        if (!bodyInfo.active) {
          refresh(call("set_active_body", { body: bodyInfo.name }));
        }
      });
      bodyItem.addEventListener("contextmenu",
        (event) => ctx.openMenu(event, bodyInfo));
    }
    treeEl.appendChild(bodyItem);
  }

  function surfaceIcon(surface) {
    if (isGraphFeature(surface)) return "graph_feature";
    if (surface.curve) return "spline3d";
    if (surface.surface?.kind === "untrim") return "surface_untrim";
    if (surface.surface?.kind === "deleteface") return "surface_delete_face";
    if (surface.surface?.kind === "split") return "surface_split";
    if (surface.surface?.kind === "flatten") return "surface_flatten";
    if (surface.surface?.kind === "freeform") return "surface_freeform";
    return SURFACE_ICONS[surface.type] ?? "surface_body";
  }

  function appendSurfaceRow(surface, { inFolder = true, rolledBack = false } = {}) {
    const item = document.createElement("li");
    item.className = "surface" + (inFolder ? " in-folder" : "")
      + (ctx.selectedSurface?.name === surface.name ? " sel" : "")
      + (rolledBack ? " rolled-back" : "")
      + (surface.hidden ? " hidden-object" : "");
    if (!inFolder) item.dataset.hist = surface.name;
    item.dataset.feat = surface.name;
    const children = surface.children ?? [];
    const hasChildren = children.length > 0;
    const arrow = document.createElement("span");
    arrow.className = "arrow";
    arrow.textContent = hasChildren
      ? (expandedFeatures.has(surface.name) ? "▾" : "▸") : "";
    if (hasChildren) {
      arrow.addEventListener("click", (event) => {
        event.stopPropagation();
        if (!expandedFeatures.delete(surface.name)) {
          expandedFeatures.add(surface.name);
        }
        renderTree(ctx.lastTree);
      });
    }
    item.appendChild(arrow);
    item.appendChild(treeIcon(surfaceIcon(surface)));
    item.appendChild(document.createTextNode(surface.label));
    if (surface.consumed) {
      // Remplacée par une autre (ajustée, prolongée, épaissie, cousue) :
      // gardée dans l'historique, plus affichée.
      item.classList.add("consumed");
    }
    item.title = t("Surface / courbe — clic : sélectionner pour une " +
      "commande · double-clic : modifier · clic droit : modifier, " +
      "renommer, supprimer");
    item.addEventListener("click", (event) => {
      if (consumeTreeRenameClick(event, item, surface)) return;
      onSurfaceClick(surface);
    });
    item.addEventListener("dblclick", () => onSurfaceDblClick(surface));
    item.addEventListener("contextmenu", (event) => ctx.openMenu(event, surface));
    treeEl.appendChild(item);
    if (hasChildren && expandedFeatures.has(surface.name)) {
      for (const child of children) {
        const row = document.createElement("li");
        row.className = "child" + (inFolder ? " in-folder" : "")
          + (child.error ? " error" : "")
          + (rolledBack ? " rolled-back" : "");
        row.dataset.feat = child.name;
        row.appendChild(treeIcon("sketch"));
        row.appendChild(document.createTextNode(child.label));
        row.title = `${child.kind} — `
          + t("double-clic : modifier l'esquisse · clic droit : modifier");
        row.addEventListener("dblclick", () => onSketchRowDblClick(child));
        row.addEventListener("contextmenu", (event) => ctx.openMenu(event, child));
        row.addEventListener("click", (event) => {
          if (consumeTreeRenameClick(event, row, child)) return;
          onSketchRowClick(child);
        });
        treeEl.appendChild(row);
      }
    }
  }

  function appendRollbackBar(tree) {
    const bar = document.createElement("li");
    bar.className = "rollback";
    bar.textContent = t("▲ barre de retour arrière ▲");
    bar.title = t("Glisser pour déplacer · double-clic : revenir à l'état final");
    bar.addEventListener("dblclick", () => refresh(call("tip_to_end")));
    bindRollbackDrag(bar, tree);
    treeEl.appendChild(bar);
  }

  // Glisser-déposer d'une fonction dans l'arbre : le repère d'insertion de
  // la barre de retour montre où elle ira ; le moteur la déplace avec ses
  // esquisses, et refuse si l'arbre ne se reconstruit plus.
  let suppressTreeClick = false;
  let treeRenameClick = { name: null, at: null };
  let renameState = null;

  function consumeTreeRenameClick(event, row, feature) {
    if (!feature?.name || event.target.closest(".arrow, input")) return false;
    const action = renameClickAction({
      previousAt: treeRenameClick.at,
      sameRow: treeRenameClick.name === feature.name,
      now: Date.now(),
      moved: false,
      dragging: row.classList.contains("dragging") || suppressTreeClick,
    });
    treeRenameClick = { name: feature.name, at: Date.now() };
    if (action === "select") {
      for (const item of treeEl.querySelectorAll("li.sel")) {
        if (item !== row) item.classList.remove("sel");
      }
      row.classList.add("sel");
    }
    if (action === "rename") {
      event.stopPropagation();
      beginInlineRename(row, feature);
      return true;
    }
    return action === "ignore";
  }

  function rowLabelNode(row) {
    const nodes = [...row.childNodes].filter(
      (node) => node.nodeType === Node.TEXT_NODE && node.textContent.trim());
    return nodes.at(-1) ?? null;
  }

  function beginInlineRename(row, feature) {
    if (!row || !feature?.name || !feature.label) return;
    if (renameState?.input?.isConnected) commitInlineRename();
    if (row.querySelector("input.tree-rename")) return;
    const text = rowLabelNode(row);
    if (!text) return;
    const shown = text.textContent;
    const input = document.createElement("input");
    input.type = "text";
    input.className = "tree-rename";
    input.value = feature.label;
    input.setAttribute("aria-label", t("Nouveau nom :"));
    text.replaceWith(input);
    renameState = { input, feature, shown };
    input.addEventListener("keydown", (event) => {
      event.stopPropagation();
      if (event.key === "Enter") {
        event.preventDefault();
        commitInlineRename();
      } else if (event.key === "Escape") {
        event.preventDefault();
        cancelInlineRename();
      }
    });
    input.addEventListener("blur", () => {
      if (renameState?.input === input) commitInlineRename();
    });
    input.focus();
    input.select();
  }

  function finishRenameField(input, shown) {
    if (input.isConnected) input.replaceWith(document.createTextNode(shown));
  }

  function commitInlineRename() {
    if (!renameState) return;
    const state = renameState;
    renameState = null;
    const label = state.input.value.trim();
    if (!label || label === state.feature.label) {
      finishRenameField(state.input, state.shown);
      return;
    }
    finishRenameField(state.input, label);
    refreshAny(call("rename", { feature: state.feature.name, label }));
  }

  function cancelInlineRename() {
    if (!renameState) return;
    const state = renameState;
    renameState = null;
    finishRenameField(state.input, state.shown);
  }

  function treeRowFor(name) {
    if (!name) return null;
    return treeEl.querySelector(`li[data-feat="${CSS.escape(name)}"]`);
  }

  function renameRecord(name) {
    return findFeatureInTree(ctx.lastTree, name)
      ?? (ctx.lastTree?.bodies ?? []).find((body) => body.name === name)
      ?? null;
  }

  function beginRenameSelected() {
    if (treeEl.querySelector("li.dragging")) return;
    const clicked = treeRenameClick.name ? treeRowFor(treeRenameClick.name) : null;
    const row = clicked?.classList.contains("sel")
      ? clicked
      : treeEl.querySelector("li.sel[data-feat]");
    if (!row) return;
    const feature = renameRecord(row.dataset.feat);
    if (!feature?.label) return;
    beginInlineRename(row, feature);
  }
  treeEl.addEventListener("click", (event) => {
    if (!suppressTreeClick) return;
    suppressTreeClick = false;
    event.stopPropagation();
    event.preventDefault();
  }, true);

  function bindFeatureDrag(row, feature) {
    row.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 || panel.active || ctx.sketchMode.active) return;
      if (event.target.closest("input")) return;
      const start = { x: event.clientX, y: event.clientY };
      let dragging = false;
      const onMove = (moveEvent) => {
        if (!dragging && Math.hypot(moveEvent.clientX - start.x,
                                    moveEvent.clientY - start.y) < 6) return;
        dragging = true;
        row.classList.add("dragging");
        const slots = rollbackSlotPositions();
        if (slots.length) showInsertMark(nearestRollbackSlot(moveEvent.clientY, slots));
      };
      const onUp = (upEvent) => {
        document.removeEventListener("pointermove", onMove);
        document.removeEventListener("pointerup", onUp);
        hideInsertMark();
        row.classList.remove("dragging");
        if (!dragging) return;
        // Le clic qui suit le lâcher ne doit pas sélectionner ; s'il ne vient
        // pas (lâcher hors de la ligne), le drapeau retombe aussitôt.
        suppressTreeClick = true;
        setTimeout(() => { suppressTreeClick = false; }, 0);
        const rows = [...treeEl.querySelectorAll("li[data-hist]")];
        const slots = rollbackSlotPositions();
        if (!slots.length) return;
        const slot = nearestRollbackSlot(upEvent.clientY, slots);
        const own = rows.indexOf(row);
        if (slot.index === own || slot.index === own + 1) return;
        const params = slot.index < rows.length
          ? { feature: feature.name, target: rows[slot.index].dataset.hist,
              after: false }
          : { feature: feature.name, target: rows[rows.length - 1].dataset.hist,
              after: true };
        refresh(call("reorder_feature", params));
      };
      document.addEventListener("pointermove", onMove);
      document.addEventListener("pointerup", onUp);
    });
  }

  function applyRollbackSlot(index, history) {
    if (index <= 0) {
      refresh(call("set_tip", {}));
      return;
    }
    if (index >= history.length) {
      refresh(call("tip_to_end"));
      return;
    }
    const target = history[index - 1];
    refresh(call("set_tip", { feature: target.item.name }));
  }

  function rollbackSlotPositions() {
    const rows = [...treeEl.querySelectorAll("li[data-hist]")];
    if (!rows.length) return [];
    const slots = [{ y: rows[0].getBoundingClientRect().top, index: 0 }];
    for (let i = 0; i < rows.length; i++) {
      slots.push({
        y: rows[i].getBoundingClientRect().bottom,
        index: i + 1,
      });
    }
    return slots;
  }

  function nearestRollbackSlot(clientY, slots) {
    let best = slots[0];
    let bestDist = Infinity;
    for (const slot of slots) {
      const dist = Math.abs(clientY - slot.y);
      if (dist < bestDist) {
        bestDist = dist;
        best = slot;
      }
    }
    return best;
  }

  function showInsertMark(slot) {
    let mark = treeEl.querySelector("li.insert-mark");
    if (!mark) {
      mark = document.createElement("li");
      mark.className = "insert-mark";
      treeEl.appendChild(mark);
    }
    const treeRect = treeEl.getBoundingClientRect();
    mark.style.top = `${slot.y - treeRect.top}px`;
  }

  function hideInsertMark() {
    treeEl.querySelector("li.insert-mark")?.remove();
  }

  function bindRollbackDrag(bar, tree) {
    bar.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      const startX = event.clientX;
      const startY = event.clientY;
      const split = splitHistoryAroundBar(
        tree.features ?? [], tree.surfaces ?? [], tree.tip);
      const history = split.before.concat(split.after);
      const currentSlot = split.before.length;
      let dragging = false;
      try {
        bar.setPointerCapture(event.pointerId);
      } catch {
        // Capture indisponible (pointeur déjà relâché) : le drag s'arrête.
      }

      const onMove = (moveEvent) => {
        const dist = Math.hypot(
          moveEvent.clientX - startX, moveEvent.clientY - startY);
        if (!dragging && dist < 5) return;
        dragging = true;
        bar.classList.add("dragging");
        const slots = rollbackSlotPositions();
        if (!slots.length) return;
        showInsertMark(nearestRollbackSlot(moveEvent.clientY, slots));
      };
      const onUp = (upEvent) => {
        bar.removeEventListener("pointermove", onMove);
        bar.removeEventListener("pointerup", onUp);
        bar.removeEventListener("pointercancel", onUp);
        hideInsertMark();
        bar.classList.remove("dragging");
        if (!dragging) return;
        const slots = rollbackSlotPositions();
        if (!slots.length) return;
        const slot = nearestRollbackSlot(upEvent.clientY, slots);
        if (slot.index === currentSlot) return;
        applyRollbackSlot(slot.index, history);
      };
      bar.addEventListener("pointermove", onMove);
      bar.addEventListener("pointerup", onUp);
      bar.addEventListener("pointercancel", onUp);
    });
  }

  function renderTree(tree) {
    ctx.welcomeApi?.hideWelcome();
    clearAssemblyView(); // un arbre de pièce = le mode assemblage s'efface
    dropRolledBackSelection(tree);
    ctx.lastTree = tree;
    updateEditMode();
    ctx.treeHoverPlane = null;
    treeEl.innerHTML = "";

    const bodies = tree.bodies
      ?? [{ name: null, label: tree.body, active: true, count: 0 }];
    const surfaces = tree.surfaces ?? [];
    const variables = tree.variables ?? [];
    const solidCount = bodies.filter((body) => body.has_solid === true).length;
    const bodiesDefaultOpen = bodies.length > 1
      || bodies.some((body) => body.error);
    const surfacesDefaultOpen = surfaces.some((surface) => surface.error
      || (surface.children ?? []).some((child) => child.error));

    rememberFolderCount("bodies", solidCount);
    rememberFolderCount("surfaces", surfaces.length);
    rememberFolderCount("equations", variables.length);

    // Ordre de l'arbre : dossiers en tête, puis plans, puis fonctions.
    const bodiesOpen = appendFolder(
      "bodies", t("Corps volumiques"), solidCount, "body",
      bodiesDefaultOpen,
      { title: t("Corps de la pièce — clic : déplier") });
    if (bodiesOpen) {
      for (const bodyInfo of bodies) appendBodyRow(bodyInfo);
    }

    const surfacesOpen = appendFolder(
      "surfaces", t("Corps surfaciques"), surfaces.length, "surface_body",
      surfacesDefaultOpen,
      { title: t("Surfaces et courbes — clic : déplier") });
    if (surfacesOpen) {
      for (const surface of surfaces) appendSurfaceRow(surface);
    }

    const equationsOpen = appendFolder(
      "equations", t("Équations"), variables.length, "equations", false,
      {
        clickToggles: false,
        title: t("Double-clic : ouvrir les équations"),
        onDblClick: openEquationsPanel,
      });
    if (equationsOpen) {
      for (const variable of variables) {
        const row = document.createElement("li");
        row.className = "in-folder";
        row.appendChild(treeIcon("equations"));
        row.appendChild(document.createTextNode(
          `${variable.name} = ${variable.value}`));
        row.title = t("Double-clic : ouvrir les équations");
        row.addEventListener("dblclick", openEquationsPanel);
        treeEl.appendChild(row);
      }
    }

    renderActiveBodyContents(tree);
    ctx.pluginRuntime?.renderTreeRows(tree, {
      treeIcon, openMenu: ctx.openMenu, append: (row) => treeEl.appendChild(row),
    });
    syncGraphFromTree();
  }

  function renderActiveBodyContents(tree) {
    // Les trois plans de base, toujours là.
    for (const plane of tree.planes ?? []) {
      const item = document.createElement("li");
      item.className = "plane" + (ctx.selectedPlane === plane.id ? " sel" : "");
      item.appendChild(treeIcon("origin_plane"));
      item.appendChild(document.createTextNode(plane.label));
      item.title = t("Clic : choisir ce plan pour la prochaine esquisse");
      item.addEventListener("click", () => onPlaneRow(plane.id));
      item.addEventListener("mouseenter", () => {
        ctx.treeHoverPlane = plane.id;
        updatePlaneVisibility();
      });
      item.addEventListener("mouseleave", () => {
        ctx.treeHoverPlane = null;
        updatePlaneVisibility();
      });
      treeEl.appendChild(item);
    }
    // L'origine ferme le groupe des références, comme d'habitude en CAO.
    const origin = document.createElement("li");
    origin.className = "plane origin" + (ctx.originShown ? " sel" : "");
    origin.appendChild(treeIcon("origin"));
    origin.appendChild(document.createTextNode(t("Origine")));
    origin.title = t("Clic : afficher ou masquer l'origine");
    origin.addEventListener("click", toggleOrigin);
    treeEl.appendChild(origin);

    const features = tree.features ?? [];
    const split = splitHistoryAroundBar(features, tree.surfaces ?? [], tree.tip);
    if (split.bar !== "none") {
      for (const row of split.before) {
        if (row.surface) {
          appendSurfaceRow(row.item, {
            inFolder: false, rolledBack: !!row.item.rolled_back,
          });
        } else {
          appendFeatureHistoryRow(row.item, false);
        }
      }
      appendRollbackBar(tree);
      for (const row of split.after) {
        if (row.surface) {
          appendSurfaceRow(row.item, {
            inFolder: false, rolledBack: true,
          });
        } else {
          appendFeatureHistoryRow(row.item, true);
        }
      }
    }
  }

  function appendFeatureHistoryRow(feature, rolledBack) {
    const row = document.createElement("li");
    row.classList.add("feat");
    row.dataset.feat = feature.name;
    row.dataset.hist = feature.name;
    if (feature.error) row.classList.add("error");
    if (rolledBack) row.classList.add("rolled-back");
    if (feature.suppressed) row.classList.add("suppressed");
    if (ctx.selectedFeatureName === feature.name) row.classList.add("sel");
    const hasChildren = !!feature.children?.length;
    const arrow = document.createElement("span");
    arrow.className = "arrow";
    arrow.textContent = hasChildren
      ? (expandedFeatures.has(feature.name) ? "▾" : "▸") : "";
    if (hasChildren) {
      arrow.addEventListener("click", (event) => {
        event.stopPropagation();
        if (!expandedFeatures.delete(feature.name)) {
          expandedFeatures.add(feature.name);
        }
        renderTree(ctx.lastTree);
      });
    }
    row.appendChild(arrow);
    const icon = isGraphFeature(feature)
      ? "graph_feature"
      : isRepeatFeature(feature)
        ? "linear_pattern"
        : feature.surface_cut ? "surface_cut"
          : feature.vertex_chamfer ? "vertex_chamfer"
          : feature.delete_face ? "surface_delete_face"
            : feature.replace_face ? "replace_face"
            : TREE_ICONS[feature.type];
    if (icon) row.appendChild(treeIcon(icon));
    row.appendChild(document.createTextNode(
      feature.type === "Sketcher::SketchObject"
        ? sketchTreeLabel(feature.label, sketchDefinitionOf(feature))
        : feature.label));
    if (ctx.sketchMode.editing === feature.name) row.classList.add("editing");
    row.title = `${feature.kind} — `
      + t("double-clic : modifier · clic droit : modifier, barre de retour, supprimer · glisser : réordonner");
    if (feature.comment) {
      const note = document.createElement("span");
      note.className = "tree-note";
      note.textContent = " ✎";
      row.appendChild(note);
      row.title = `${feature.comment}\n\n${row.title}`;
    }
    row.addEventListener("dblclick", () => {
      if (feature.type === "Sketcher::SketchObject") {
        onSketchRowDblClick(feature);
      } else {
        editFeature(feature);
      }
    });
    row.addEventListener("contextmenu", (event) => ctx.openMenu(event, feature));
    bindFeatureDrag(row, feature);
    if (feature.type === "PartDesign::Plane") {
      // Un plan de référence se choisit comme un plan d'origine.
      row.classList.add("plane");
      if (ctx.selectedDatumFeature?.name === feature.name) {
        row.classList.add("sel");
      }
      row.addEventListener("click", (event) => {
        if (consumeTreeRenameClick(event, row, feature)) return;
        onDatumRow(feature);
      });
      row.addEventListener("mouseenter", () => refreshDatumGhost(feature));
      row.addEventListener("mouseleave", () => refreshDatumGhost(null));
    }
    if (feature.type === "Sketcher::SketchObject") {
      if (ctx.selectedSketch?.name === feature.name) row.classList.add("sel");
      row.addEventListener("click", (event) => {
        if (consumeTreeRenameClick(event, row, feature)) return;
        onSketchRowClick(feature);
      });
    } else if (feature.type !== "PartDesign::Plane") {
      row.addEventListener("click", (event) => {
        if (consumeTreeRenameClick(event, row, feature)) return;
        ctx.selectedFeatureName = feature.name;
        panel.notifyPick("feature", {
          kind: "feature", name: feature.name, label: feature.label,
        });
      });
    }
    treeEl.appendChild(row);

    // L'esquisse consommée vit sous sa fonction.
    if (hasChildren && expandedFeatures.has(feature.name)) {
      for (const child of feature.children) {
        const childRow = document.createElement("li");
        childRow.className = "child" + (child.error ? " error" : "");
        childRow.dataset.feat = child.name;
        if (rolledBack) childRow.classList.add("rolled-back");
        if (ctx.selectedSketch?.name === child.name) childRow.classList.add("sel");
        childRow.appendChild(treeIcon("sketch"));
        childRow.appendChild(document.createTextNode(
          sketchTreeLabel(child.label, sketchDefinitionOf(child))));
        if (ctx.sketchMode.editing === child.name) childRow.classList.add("editing");
        childRow.title = `${child.kind} — `
          + t("double-clic : modifier l'esquisse · clic droit : modifier");
        if (child.shared?.length) {
          childRow.classList.add("shared");
          childRow.appendChild(document.createTextNode(" ⇄"));
          childRow.title = t("Esquisse partagée — aussi utilisée par : {f}",
            { f: child.shared.join(", ") }) + " · " + childRow.title;
        }
        childRow.addEventListener("dblclick", () => onSketchRowDblClick(child));
        childRow.addEventListener("contextmenu", (event) => ctx.openMenu(event, child));
        childRow.addEventListener("click", (event) => {
          if (consumeTreeRenameClick(event, childRow, child)) return;
          onSketchRowClick(child);
        });
        treeEl.appendChild(childRow);
      }
    }
  }
  // (fin du rendu du corps actif)

  /** En cours d'édition, l'état vient du solveur de l'esquisse ouverte. */
  function sketchDefinitionOf(item) {
    if (ctx.sketchMode.editing === item.name && ctx.sketchMode.definition) {
      return ctx.sketchMode.definition;
    }
    return item.definition;
  }

  // Property names -> designer-facing labels for the edit panel.

  async function editSurface(surface) {
    if (isGraphFeature(surface) || isRepeatFeature(surface)) {
      enterGraphFeature(surface);
      return;
    }
    if (surface.curve) {
      ctx.openCurve3d(surface);
      return;
    }
    if (surface.surface?.kind === "extend") {
      editExtend(surface);
      return;
    }
    if (surface.surface?.kind === "trim") {
      editTrim(surface);
      return;
    }
    if (surface.surface?.kind === "offset") {
      editOffset(surface);
      return;
    }
    if (surface.surface?.kind === "fillet") {
      editSurfaceFillet(surface);
      return;
    }
    if (surface.surface?.kind === "freeform" && surface.surface.moves) {
      ctx.openPoles(surface);
      return;
    }
    if (surface.surface?.kind === "flatten") {
      showFlatten(surface);
      return;
    }
    if (surface.surface?.kind === "freeform") {
      editFreeform(surface);
      return;
    }
    if (surface.static || surface.type === "Part::Feature") {
      say("Surface figée — non éditable");
      return;
    }
    await editFeature({
      name: surface.name,
      label: surface.label,
      type: surface.type,
    });
  }

  // Prolongement : la distance (et le bord d'origine) se rééditent.
  function editExtend(surface) {
    const spec = surface.surface;
    panel.open({
      icon: "surface_extend",
      title: surface.label,
      groups: [{
        label: t("Paramètres"),
        rows: [
          { type: "number", key: "distance", label: t("Distance"),
            value: spec.distance, unit: "mm", min: 0.01 },
          { type: "check", key: "all", label: t("Tous les bords"),
            value: spec.edge == null },
        ],
      }],
      onApply: (v) => {
        const distance = num(v.distance);
        if (!(distance > 0)) {
          say(t("Prolonger : une distance positive"), true);
          return;
        }
        const params = { surface: surface.name, distance };
        if (!v.all && spec.edge != null) params.edge = spec.edge;
        refresh(call("edit_surface_extend", params));
      },
    });
  }

  // Coupe par surface : garder l'autre côté, avec l'aperçu.
  function editSurfaceCut(feature) {
    const spec = feature.surface_cut;
    panel.open({
      icon: "surface_cut",
      title: feature.label,
      groups: [{
        label: t("Options"),
        rows: [
          { type: "check", key: "flip", label: t("Inverser le côté"),
            value: spec.flip },
          ...(spec.thickness ? [{ type: "number", key: "thickness",
            label: t("Épaisseur"), value: spec.thickness, unit: "mm",
            min: 0.01 }] : []),
        ],
      }],
      onApply: (v) => {
        const thickness = spec.thickness ? num(v.thickness) : null;
        if (!!v.flip === spec.flip && thickness === (spec.thickness ?? null)) {
          return;
        }
        if (spec.thickness && !(thickness > 0)) return;
        refresh(call("edit_surface_cut", { feature: feature.name,
          flip: !!v.flip, ...(thickness ? { thickness } : {}) }));
      },
    });
  }

  // Patron à plat : sa déformation mesurée (lecture seule ; le patron
  // suit la surface d'origine).
  function showFlatten(surface) {
    const spec = surface.surface;
    const exact = (spec.area_error ?? 0) < 0.5 && (spec.edge_error ?? 0) < 0.5;
    panel.open({
      icon: "surface_flatten",
      title: surface.label,
      noApply: true,
      groups: [{
        label: t("Déformation du patron"),
        rows: [
          { type: "note", readonly: true, text: t(
            "Aire : {a} % · contour : {e} %",
            { a: fmtPct(spec.area_error), e: fmtPct(spec.edge_error) }) },
          { type: "note", readonly: true, text: exact
            ? t("Face développable : le patron est exact.")
            : t("Face à double courbure : le patron s'étire pour se "
              + "mettre à plat ; ces écarts disent de combien.") },
        ],
      }],
    });
  }

  function fmtPct(value) {
    return (Math.round((value ?? 0) * 100) / 100).toLocaleString(
      document.documentElement.lang || undefined);
  }

  // Forme libre : hauteur et rayon d'influence.
  function editFreeform(surface) {
    const spec = surface.surface;
    panel.open({
      icon: "surface_freeform",
      title: surface.label,
      groups: [
        { label: t("Points à pousser"),
          rows: [{ type: "points", key: "pushes", value: spec.pushes,
                   extra: { label: "Hauteur", value: 5 } }] },
        { label: t("Paramètres"),
          rows: [
            { type: "number", key: "radius", label: t("Rayon d'influence"),
              value: spec.radius, unit: "mm", min: 0.01 },
            { type: "check", key: "keepEdges", label: t("Bords fixes"),
              value: spec.keep_edges },
          ] },
      ],
      onApply: (v) => {
        const radius = num(v.radius);
        const pushes = (v.pushes ?? []).filter((p) => p.length === 4);
        if (!(radius > 0) || !pushes.length) return;
        refresh(call("edit_surface_freeform", { surface: surface.name,
          radius, pushes, keep_edges: !!v.keepEdges }));
      },
    });
  }

  // Congé de surface : son rayon.
  function editSurfaceFillet(surface) {
    panel.open({
      icon: "surface_fillet",
      title: surface.label,
      groups: [{
        label: t("Paramètres"),
        rows: [{ type: "number", key: "radius", label: t("Rayon"),
                 value: surface.surface.radius, unit: "mm", min: 0.01 }],
      }],
      onApply: (v) => {
        const radius = num(v.radius);
        if (!(radius > 0)) return;
        refresh(call("edit_surface_fillet",
          { surface: surface.name, radius }));
      },
    });
  }

  // Surface décalée : sa distance (négative = de l'autre côté).
  function editOffset(surface) {
    panel.open({
      icon: "surface_offset",
      title: surface.label,
      groups: [{
        label: t("Paramètres"),
        rows: [{ type: "number", key: "distance", label: t("Distance"),
                 value: surface.surface.distance, unit: "mm" }],
      }],
      onApply: (v) => {
        const distance = num(v.distance);
        if (distance === null) return;
        refresh(call("set_params", {
          feature: surface.name, values: { Value: distance } }));
      },
    });
  }

  // Ajustement : garder l'autre partie (la partie écartée n'est plus
  // visible, on ne peut pas la cliquer).
  function editTrim(surface) {
    panel.open({
      icon: "surface_trim",
      title: surface.label,
      groups: [{
        label: t("Partie à garder"),
        rows: [{ type: "check", key: "other",
                 label: t("Garder l'autre partie"), value: true }],
      }],
      onApply: (v) => {
        if (!v.other) return;
        refresh(call("edit_surface_trim", { surface: surface.name }));
      },
    });
  }

  function findSketch(tree, name) {
    const stack = [...(tree?.features ?? [])];
    while (stack.length) {
      const item = stack.pop();
      if (!item) continue;
      if (item.name === name) return item;
      if (item.children) stack.push(...item.children);
    }
    return null;
  }

  function editRevolved(feature) {
    const spec = feature.revolution;
    const sketch = findSketch(ctx.lastTree, spec.profile);
    panel.open({
      icon: TREE_ICONS[feature.type] ?? "revolve",
      title: feature.label,
      groups: [...revolutionGroups(sketch, {
        angle: chamferFieldValue(feature.params, "Angle", spec.angle),
        axis: spec.axis,
        reversed: spec.reversed,
        midplane: spec.midplane,
      }), ...contourGroups(feature)],
      onChange: (v) => {
        const values = revolutionEditValues(v, spec, feature.params);
        schedulePreview(values && Object.keys(values).length
          ? { op: "set_params",
              params: { feature: feature.name, values } }
          : null);
      },
      onApply: (v) => {
        const values = revolutionEditValues(v, spec, feature.params);
        if (values === null) {
          say(revolutionProblem(), true);
          return;
        }
        applyEdit(feature, v, values);
      },
    });
  }

  function editChamfer(feature) {
    const spec = feature.chamfer;
    panel.open({
      icon: "chamfer",
      title: feature.label,
      groups: [{
        label: "Paramètres du chanfrein",
        rows: chamferRows({
          kind: spec.type,
          size: chamferFieldValue(feature.params, "Size", spec.size),
          size2: chamferFieldValue(feature.params, "Size2", spec.size2),
          angle: chamferFieldValue(feature.params, "Angle", spec.angle),
          flip: spec.flip,
        }),
      }],
      onChange: (v) => {
        const values = chamferEditValues(v, spec, feature.params);
        schedulePreview(values && Object.keys(values).length
          ? { op: "set_params",
              params: { feature: feature.name, values } }
          : null);
      },
      onApply: (v) => {
        const values = chamferEditValues(v, spec, feature.params);
        if (values === null) {
          say(chamferProblem(v), true);
          return;
        }
        if (!Object.keys(values).length) return;
        refresh(call("set_params", { feature: feature.name, values }));
      },
    });
  }

  /** Groupe « Contours » d'une fonction dont l'esquisse en a plusieurs. */
  function contourGroups(feature) {
    const profile = feature.profile;
    if (!(profile?.count > 1)) return [];
    return [{ label: t("Contours"),
              rows: contourRows(profile.sizes, profile.used) }];
  }

  /** OK d'une réédition : les paramètres, puis les contours s'ils ont
   *  changé — chacun son appel, l'arbre suit. */
  function applyEdit(feature, v, values) {
    const profile = feature.profile;
    let contours = null;
    if (profile?.count > 1) {
      const chosen = checkedContours(v, profile.count)
        ?? [...Array(profile.count).keys()];
      if (!chosen.length) {
        say(t("Contours : cochez au moins un contour"), true);
        return;
      }
      const same = chosen.length === profile.used.length
        && chosen.every((i) => profile.used.includes(i));
      if (!same) contours = chosen.length === profile.count ? [] : chosen;
    }
    const hasValues = Object.keys(values ?? {}).length > 0;
    if (!hasValues && contours === null) return;
    refresh((async () => {
      let tree = null;
      if (hasValues) {
        tree = await call("set_params", { feature: feature.name, values });
      }
      if (contours !== null) {
        tree = await call("set_profile_contours",
          { feature: feature.name, contours });
      }
      return tree;
    })());
  }

  async function editFeature(feature) {
    if (isGraphFeature(feature) || isRepeatFeature(feature)) {
      enterGraphFeature(feature);
      return;
    }
    if (feature.type === "Sketcher::SketchObject") {
      closeGraph();
      ctx.sketchMode.enter(call("sketch_edit", { feature: feature.name }));
      return;
    }
    if (feature.vertex_chamfer) {
      panel.open({
        icon: "vertex_chamfer",
        title: feature.label,
        groups: [{ label: t("Distances"),
          rows: vertexChamferRows(feature.vertex_chamfer) }],
        onApply: (v) => {
          const distances = vertexChamferDistances(v);
          if (!distances) {
            say(t("Distance de chanfrein invalide"), true);
            return;
          }
          refresh(call("edit_vertex_chamfer",
            { feature: feature.name, distances }));
        },
      });
      return;
    }
    if (feature.text) {
      // Gravure rééditable (P032) : panneau dédié -> edit_text.
      const txt = feature.text;
      panel.open({
        icon: TREE_ICONS[feature.type] ?? "body",
        title: feature.label,
        groups: [{
          label: t("Gravure"),
          rows: [
            { type: "text", key: "text", label: t("Texte"), value: txt.text },
            { type: "number", key: "size", label: t("Taille"), unit: "mm",
              value: txt.size },
            { type: "number", key: "depth", label: t("Profondeur"), unit: "mm",
              value: txt.depth },
            { type: "number", key: "x", label: t("X"), unit: "mm", value: txt.x },
            { type: "number", key: "y", label: t("Y"), unit: "mm", value: txt.y },
          ],
        }],
        onApply: (v) => {
          refresh(call("edit_text", {
            feature: feature.name,
            text: String(v.text ?? txt.text),
            size: num(v.size) ?? txt.size,
            depth: num(v.depth) ?? txt.depth,
            x: num(v.x) ?? txt.x,
            y: num(v.y) ?? txt.y,
          }));
        },
      });
      return;
    }
    if (feature.surface_cut) {
      editSurfaceCut(feature);
      return;
    }
    if (feature.type === "PartDesign::Chamfer" && feature.chamfer) {
      editChamfer(feature);
      return;
    }
    if ((feature.type === "PartDesign::Revolution"
         || feature.type === "PartDesign::Groove") && feature.revolution) {
      editRevolved(feature);
      return;
    }
    try {
      const info = await call("get_params", { feature: feature.name });
      if (!info.params.length) {
        say(t("{f} : aucun paramètre numérique éditable", { f: info.label }));
        return;
      }
      // Champs texte : nombre OU expression (« 2*Variables.Largeur ») —
      // le moteur tranche. Σ marque les propriétés déjà pilotées.
      const collectChanged = (v) => {
        const values = {};
        for (const p of info.params) {
          const original = String(p.expr ?? p.value);
          const raw = String(v[p.prop] ?? "").trim();
          if (raw && raw !== original) values[p.prop] = raw;
        }
        return values;
      };
      panel.open({
        icon: TREE_ICONS[feature.type] ?? "body",
        title: info.label,
        groups: [{
          label: t("Paramètres"),
          rows: info.params.map((p) => {
            const [label, unit] = PROP_LABELS[p.prop] ?? [p.prop, "mm"];
            return { type: "text", key: p.prop,
                     label: (p.expr ? "Σ " : "") + label, unit,
                     value: String(p.expr ?? p.value) };
          }),
        }, ...contourGroups(feature)],
        // L'édition profite du même aperçu jaune que la création.
        onChange: (v) => {
          const values = collectChanged(v);
          schedulePreview(Object.keys(values).length
            ? { op: "set_params",
                params: { feature: feature.name, values } }
            : null);
        },
        onApply: (v) => applyEdit(feature, v, collectChanged(v)),
      });
    } catch (error) {
      say(error.message, true);
    }
  }


  return {
    updateTreeFlyout, refreshDatumGhost, onDatumRow, treeIcon,
    onSketchRowClick, onSketchRowDblClick, clearSketchSelection,
    cancelPendingSurfaceClick, onSurfaceClick, onSurfaceDblClick,
    clearSurfaceSelection, selectSketch, onPlaneRow,
    beginInlineRename, treeRowFor, beginRenameSelected,
    renderTree, editSurface, editFeature,
  };
}
