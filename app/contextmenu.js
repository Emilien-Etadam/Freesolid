// Menus contextuels : arbre de création et zone graphique.
// Les entrées de la zone graphique viennent de viewmenu.js ; ici on les
// relie aux commandes déjà en place. L'état partagé est lu sur ctx à
// l'appel, pour suivre les réassignations de main.js.

import { t } from "./i18n.js";
import { cssHex } from "./theme.js";
import { isGraphFeature, isRepeatFeature } from "./graph.js";
import {
  contextToolbarKeys, menuIcon, placeViewMenu, viewMenuItems, viewMenuLabel,
} from "./viewmenu.js";

export function isBodyMenuTarget(feature) {
  return feature != null && typeof feature.active === "boolean";
}

export function isFrozenSurface(feature) {
  if (isGraphFeature(feature) || isRepeatFeature(feature)) return false;
  return !!(feature?.static || feature?.type === "Part::Feature");
}

export function canModifyMenuTarget(feature) {
  if (!feature || isBodyMenuTarget(feature)) return false;
  const type = feature.type;
  if (!type || type === "PartDesign::Plane") return false;
  if (isFrozenSurface(feature)) return false;
  if (type === "Sketcher::SketchObject") return true;
  return type.startsWith("PartDesign::")
    || type.startsWith("Part::")
    || type.startsWith("Surface::");
}

/** Branche les deux menus. Renvoie les ouvertures appelées par l'arbre,
 *  la sélection et les fenêtres. */
export function installContextMenu(ctx) {
  const {
    call, refresh, refreshAny, refreshAssembly,
    hexColor, sceneTheme, confirm,
    onSketchRowDblClick, editSurface, editFeature,
    treeRowFor, beginInlineRename,
    findFeatureInTree,
    frameView, openOrientBox, toggleOrigin, viewNormalTo,
    selectSketch, onSurfaceDblClick,
    panel, container, renderer,
  } = ctx;
  // ---------- tree context menu ----------

  const menuEl = document.getElementById("ctxmenu");
  let menuFeature = null;

  function modifyMenuTarget(feature) {
    if (feature.type === "Sketcher::SketchObject") {
      onSketchRowDblClick(feature);
    } else if (feature.type.startsWith("Part::")
               || feature.type.startsWith("Surface::")) {
      editSurface(feature);
    } else {
      editFeature(feature);
    }
  }

  function openMenu(event, feature) {
    event.preventDefault();
    menuFeature = feature;
    const onBody = isBodyMenuTarget(feature);
    // Un composant d'assemblage : fixer / libérer, pas de barre de retour.
    const onComponent = !!ctx.assemblyState && typeof feature.grounded === "boolean";
    document.getElementById("ctx-modify").hidden = !canModifyMenuTarget(feature);
    document.getElementById("ctx-color").hidden = !onBody;
    document.getElementById("ctx-color-reset").hidden = !onBody;
    const ground = document.getElementById("ctx-ground");
    ground.hidden = !onComponent;
    ground.textContent = t(feature.grounded ? "Libérer" : "Fixer");
    document.getElementById("ctx-rollback").hidden = !!ctx.assemblyState;
    document.getElementById("ctx-end").hidden = !!ctx.assemblyState;
    menuEl.style.display = "block";
    menuEl.style.left = Math.min(event.clientX, window.innerWidth - 200) + "px";
    menuEl.style.top = event.clientY + "px";
  }
  document.addEventListener("click", () => { menuEl.style.display = "none"; });

  document.getElementById("ctx-modify").addEventListener("click", () => {
    if (!menuFeature || !canModifyMenuTarget(menuFeature)) return;
    modifyMenuTarget(menuFeature);
  });

  document.getElementById("ctx-rename").addEventListener("click", () => {
    if (!menuFeature) return;
    const row = treeRowFor(menuFeature.name);
    if (!row) return;
    beginInlineRename(row, menuFeature);
  });

  document.getElementById("ctx-color").addEventListener("click", () => {
    if (!menuFeature) return;
    const bodyName = menuFeature.name;
    const picker = document.getElementById("body-color-picker");
    picker.value = hexColor(menuFeature.color) || cssHex(sceneTheme.part);
    picker.addEventListener("change", () => {
      refresh(call("set_body_color", { body: bodyName, color: picker.value }));
    }, { once: true });
    picker.click();
  });

  document.getElementById("ctx-color-reset").addEventListener("click", () => {
    if (!menuFeature) return;
    refresh(call("set_body_color", { body: menuFeature.name, color: null }));
  });

  document.getElementById("ctx-ground").addEventListener("click", () => {
    if (!menuFeature || typeof menuFeature.grounded !== "boolean") return;
    refreshAssembly(call("set_component_grounded", {
      component: menuFeature.name, grounded: !menuFeature.grounded,
    }));
  });

  document.getElementById("ctx-rollback").addEventListener("click", () => {
    if (menuFeature) refresh(call("set_tip", { feature: menuFeature.name }));
  });
  document.getElementById("ctx-end").addEventListener("click", () =>
    refresh(call("tip_to_end")));
  document.getElementById("ctx-delete").addEventListener("click", () => {
    if (!menuFeature) return;
    if (confirm(t("Supprimer « {f} » ?", { f: menuFeature.label })))
      refreshAny(call("delete_feature", { feature: menuFeature.name }));
  });

  // ---------- menu contextuel de la zone graphique ----------
  // Clic droit : ce qui est visé (face, arête, esquisse, surface) décide
  // des entrées (viewmenu.js) ; le clic droit a déjà sélectionné l'élément.

  const viewMenuEl = document.createElement("div");
  viewMenuEl.id = "view-menu";
  document.body.appendChild(viewMenuEl);
  let viewMenuHit = null;

  function viewMenuContext() {
    if (ctx.sketchMode.active) return { mode: "sketch" };
    let hit = null;
    if (ctx.hoveredEdgeGroup >= 0) {
      hit = { kind: "edge", edge: ctx.edgeGroups[ctx.hoveredEdgeGroup].edgeId };
    } else if (ctx.hoveredSketch) {
      hit = { kind: "sketch", sketch: ctx.hoveredSketch, label: ctx.hoveredSketch.label };
    } else if (ctx.hoveredSurface) {
      hit = { kind: "surface", surface: ctx.hoveredSurface, label: ctx.hoveredSurface.label };
    } else if (ctx.hoveredGroup >= 0) {
      const group = ctx.meshGroups[ctx.hoveredGroup];
      const feature = findFeatureInTree(ctx.lastTree, group.feature);
      const sketch = (feature?.children ?? [])
        .find((child) => child.type === "Sketcher::SketchObject");
      hit = {
        kind: "face",
        face: group.faceId,
        feature: feature ? {
          name: feature.name, label: feature.label, sketch: sketch?.name,
          item: feature, sketchItem: sketch,
        } : null,
      };
    }
    return { hit, originShown: ctx.originShown };
  }

  function clickButton(id) {
    document.getElementById(id)?.click();
  }

  function sketchTool(tool) {
    document.querySelector(`#sketchbar [data-tool="${tool}"]`)?.click();
  }

  async function withSketchSelected(hit, buttonId) {
    if (ctx.selectedSketch?.name !== hit.sketch.name) await selectSketch(hit.sketch);
    clickButton(buttonId);
  }

  const VIEW_MENU_ACTIONS = {
    "zoom-fit": () => frameView(null, null),
    orient: () => openOrientBox(),
    origin: () => toggleOrigin(),
    undo: () => refreshAny(call("undo")),
    redo: () => refreshAny(call("redo")),
    rebuild: () => clickButton("btn-rebuild"),
    "sketch-on-face": () => clickButton("btn-sketch"),
    "normal-to": () => viewNormalTo(),
    fillet: () => clickButton("btn-fillet"),
    chamfer: () => clickButton("btn-chamfer"),
    shell: () => clickButton("btn-shell"),
    measure: () => clickButton("btn-measure"),
    "edit-feature": (hit) => editFeature(hit.feature.item),
    "edit-sketch": (hit) => onSketchRowDblClick(hit.kind === "sketch"
      ? { name: hit.sketch.name, label: hit.sketch.label,
          type: "Sketcher::SketchObject" }
      : hit.feature.sketchItem),
    rollback: (hit) => refresh(call("set_tip", { feature: hit.feature.name })),
    "delete-feature": (hit) => {
      if (confirm(t("Supprimer « {f} » ?", { f: hit.feature.label }))) {
        refreshAny(call("delete_feature", { feature: hit.feature.name }));
      }
    },
    pad: (hit) => withSketchSelected(hit, "btn-pad"),
    pocket: (hit) => withSketchSelected(hit, "btn-pocket"),
    revolve: (hit) => withSketchSelected(hit, "btn-revolution"),
    "edit-surface": (hit) => onSurfaceDblClick(hit.surface),
    "sk-select": () => sketchTool("select"),
    "sk-line": () => sketchTool("line"),
    "sk-rect": () => sketchTool("rect"),
    "sk-circle": () => sketchTool("circle"),
    "sk-dim": () => sketchTool("dim"),
    "sk-trim": () => sketchTool("trim"),
    "sk-finish": () => ctx.sketchMode.finish(),
    "sk-cancel": () => ctx.sketchMode.cancel(),
  };

  function hideViewMenu() {
    viewMenuEl.style.display = "none";
  }

  // Barre d'icônes contextuelle : après un clic gauche sur une face, une
  // arête ou une esquisse, les actions courantes s'offrent près du curseur ;
  // elle s'efface quand la souris s'éloigne.
  const ctxBarEl = document.createElement("div");
  ctxBarEl.id = "ctx-toolbar";
  ctxBarEl.hidden = true;
  container.appendChild(ctxBarEl);
  let ctxBarAnchor = null;
  let ctxBarHit = null;

  function hideContextToolbar() {
    ctxBarEl.hidden = true;
    ctxBarAnchor = null;
  }

  function showContextToolbar(event) {
    if (panel.active || ctx.measuring || ctx.assemblyState) return;
    const menu = viewMenuContext();
    const keys = contextToolbarKeys(menu.hit);
    if (!keys.length) { hideContextToolbar(); return; }
    ctxBarHit = menu.hit;
    ctxBarEl.innerHTML = "";
    for (const key of keys) {
      const button = document.createElement("button");
      const icon = document.createElement("img");
      icon.src = "icons/" + menuIcon(key);
      icon.alt = "";
      button.appendChild(icon);
      button.title = t(viewMenuLabel(key, menu));
      button.addEventListener("click", (clickEvent) => {
        clickEvent.stopPropagation();
        hideContextToolbar();
        VIEW_MENU_ACTIONS[key]?.(ctxBarHit);
      });
      ctxBarEl.appendChild(button);
    }
    const host = container.getBoundingClientRect();
    ctxBarEl.hidden = false;
    ctxBarEl.style.left = `${Math.min(event.clientX - host.left + 14,
      host.width - ctxBarEl.offsetWidth - 4)}px`;
    ctxBarEl.style.top = `${Math.max(event.clientY - host.top - 46, 4)}px`;
    ctxBarAnchor = { x: event.clientX, y: event.clientY };
  }

  renderer.domElement.addEventListener("pointermove", (event) => {
    if (ctxBarAnchor && Math.hypot(event.clientX - ctxBarAnchor.x,
                                   event.clientY - ctxBarAnchor.y) > 160) {
      hideContextToolbar();
    }
  });
  renderer.domElement.addEventListener("pointerdown", hideContextToolbar);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hideContextToolbar();
  });

  renderer.domElement.addEventListener("contextmenu", (event) => {
    event.preventDefault();
    if (ctx.assemblyState || ctx.planePicking || ctx.measuring) return;
    menuEl.style.display = "none";
    const menu = viewMenuContext();
    viewMenuHit = menu.hit;
    viewMenuEl.innerHTML = "";
    for (const item of viewMenuItems(menu)) {
      const row = document.createElement("div");
      if (item.separator) {
        row.className = "sep";
      } else if (item.header) {
        row.className = "head";
        row.textContent = t(item.header);
      } else if (item.bar) {
        // Rangée d'icônes : les actions sur ce qu'on vise.
        row.className = "bar";
        for (const key of item.bar) {
          const button = document.createElement("button");
          button.type = "button";
          const label = t(viewMenuLabel(key, menu));
          button.title = label;
          button.setAttribute("aria-label", label);
          const icon = document.createElement("img");
          icon.src = "icons/" + menuIcon(key);
          icon.alt = "";
          button.appendChild(icon);
          button.addEventListener("click", () => {
            hideViewMenu();
            VIEW_MENU_ACTIONS[key]?.(viewMenuHit);
          });
          row.appendChild(button);
        }
      } else {
        const icon = document.createElement("img");
        icon.alt = "";
        if (menuIcon(item.key)) icon.src = "icons/" + menuIcon(item.key);
        else icon.className = "blank";
        row.append(icon, t(item.label));
        if (item.danger) row.classList.add("danger");
        row.addEventListener("click", () => {
          hideViewMenu();
          VIEW_MENU_ACTIONS[item.key]?.(viewMenuHit);
        });
      }
      viewMenuEl.appendChild(row);
    }
    viewMenuEl.style.maxHeight = "none";
    viewMenuEl.style.display = "block";
    const header = document.querySelector("header");
    const place = placeViewMenu({
      x: event.clientX,
      y: event.clientY,
      width: viewMenuEl.offsetWidth,
      height: viewMenuEl.offsetHeight,
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
      topLimit: header ? header.getBoundingClientRect().bottom : 0,
    });
    viewMenuEl.style.left = `${place.left}px`;
    viewMenuEl.style.top = `${place.top}px`;
    viewMenuEl.style.maxHeight = `${place.maxHeight}px`;
  });
  document.addEventListener("click", hideViewMenu);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hideViewMenu();
  });
  return { openMenu, showContextToolbar, hideContextToolbar };
}
