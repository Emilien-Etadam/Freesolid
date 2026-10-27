// Menus contextuels : arbre de création et zone graphique.
// Les entrées de la zone graphique viennent de viewmenu.js ; ici on les
// relie aux commandes déjà en place. L'état partagé est lu sur ctx à
// l'appel, pour suivre les réassignations de main.js.

import { t } from "./i18n.js";
import { iconSrc } from "./icons.js";
import { cssHex } from "./theme.js";
import { isGraphFeature, isRepeatFeature } from "./graph.js";
import { isBodyFeatureKey, isSurfaceKey } from "./typekeys.js";
import { SNAP_KINDS } from "./sketchsnap.js";
import {
  contextToolbarKeys, menuIcon, placeViewMenu, viewMenuItems, viewMenuLabel,
} from "./viewmenu.js";

export function isBodyMenuTarget(feature) {
  return feature != null && typeof feature.active === "boolean";
}

/** Fonction de corps (hors plan de référence et corps) : elle se
 *  désactive sans être supprimée. */
export function isSuppressibleTarget(feature) {
  const key = feature?.type_key ?? "";
  return isBodyFeatureKey(key) && key !== "datum_plane"
    && key !== "body" && !isBodyMenuTarget(feature);
}

/** Corps, ou surface du premier niveau : ce qu'on masque et affiche. */
export function isHideableTarget(feature) {
  if (!feature?.name || typeof feature.grounded === "boolean") return false;
  return isBodyMenuTarget(feature) || isSurfaceKey(feature.type_key);
}

export function isFrozenSurface(feature) {
  if (isGraphFeature(feature) || isRepeatFeature(feature)) return false;
  return !!(feature?.static || feature?.type_key === "shape");
}

export function canModifyMenuTarget(feature) {
  if (!feature || isBodyMenuTarget(feature)) return false;
  const key = feature.type_key;
  if (!key || key === "datum_plane") return false;
  if (isFrozenSurface(feature)) return false;
  if (key === "sketch") return true;
  return isBodyFeatureKey(key) || isSurfaceKey(key);
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
  // Entrées propres au menu de la barre de retour et à celui du titre.
  const BAR_ITEMS = ["ctx-forward", "ctx-bar-back", "ctx-end", "ctx-bar-delete"];
  const OWN_ITEMS = new Set(["ctx-bar-back", "ctx-bar-delete", "ctx-flat"]);

  function showMenuAt(event) {
    menuEl.style.display = "block";
    menuEl.style.left = Math.min(event.clientX, window.innerWidth - 200) + "px";
    menuEl.style.top = event.clientY + "px";
  }

  /** Menu réduit à `ids` ; `off` : entrées grisées. */
  function openOnly(event, ids, off = []) {
    event.preventDefault();
    menuFeature = null;
    for (const item of menuEl.children) {
      item.hidden = !ids.includes(item.id);
      item.classList.toggle("disabled", off.includes(item.id));
    }
    showMenuAt(event);
  }

  /** Clic droit sur la barre de retour. */
  function openBarMenu(event) {
    const can = ctx.barCommands();
    openOnly(event, BAR_ITEMS, [
      !can.forward && "ctx-forward", !can.previous && "ctx-bar-back",
      !can.end && "ctx-end", !can.below && "ctx-bar-delete",
    ]);
  }

  /** Clic droit sur le titre « Arbre de création ». */
  function openTreeTitleMenu(event) {
    openOnly(event, ["ctx-flat"]);
    document.getElementById("ctx-flat").classList.toggle("checked", ctx.isFlatTree());
  }

  function modifyMenuTarget(feature) {
    if (feature.type_key === "sketch") {
      onSketchRowDblClick(feature);
    } else if (isSurfaceKey(feature.type_key)) {
      editSurface(feature);
    } else {
      editFeature(feature);
    }
  }

  function openMenu(event, feature) {
    event.preventDefault();
    menuFeature = feature;
    for (const item of menuEl.children) {
      item.hidden = OWN_ITEMS.has(item.id);
      item.classList.remove("disabled");
    }
    const onBody = isBodyMenuTarget(feature);
    // Un composant d'assemblage : fixer / libérer, pas de barre de retour.
    const onComponent = !!ctx.assemblyState && typeof feature.grounded === "boolean";
    document.getElementById("ctx-modify").hidden = !canModifyMenuTarget(feature);
    document.getElementById("ctx-color").hidden = !onBody;
    document.getElementById("ctx-material").hidden = !onBody;
    document.getElementById("ctx-color-reset").hidden = !onBody;
    document.getElementById("ctx-comment").hidden = onBody || onComponent;
    document.getElementById("ctx-copy").hidden = !ctx.canCopyFeature(feature);
    const isFeature = !onBody && !onComponent && !!feature.type_key
      && !isSurfaceKey(feature.type_key);
    document.getElementById("ctx-folder").hidden = !isFeature;
    document.getElementById("ctx-unfolder").hidden = !isFeature || !feature.folder;
    document.getElementById("ctx-relations").hidden = !isFeature;
    document.getElementById("ctx-sketch-plane").hidden =
      feature.type_key !== "sketch" || !!ctx.assemblyState
      || ctx.sketchMode.active;
    const suppress = document.getElementById("ctx-suppress");
    suppress.hidden = !isSuppressibleTarget(feature) || !!ctx.assemblyState;
    suppress.textContent = t(feature.suppressed ? "Réactiver" : "Désactiver");
    const hide = document.getElementById("ctx-hide");
    hide.hidden = !isHideableTarget(feature);
    hide.textContent = t(feature.hidden ? "Afficher" : "Masquer");
    const ground = document.getElementById("ctx-ground");
    ground.hidden = !onComponent;
    ground.textContent = t(feature.grounded ? "Libérer" : "Fixer");
    document.getElementById("ctx-rollback").hidden = !!ctx.assemblyState;
    // Fonction reculée : la barre peut avancer d'un pas vers elle.
    document.getElementById("ctx-forward").hidden = !!ctx.assemblyState
      || !ctx.isAfterBar(feature.name);
    document.getElementById("ctx-end").hidden = !!ctx.assemblyState;
    showMenuAt(event);
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

  document.getElementById("ctx-folder").addEventListener("click", () => {
    if (!menuFeature) return;
    const name = ctx.promptText("Nom du dossier :", menuFeature.folder || "Dossier");
    if (name === null || !name.trim()) return;
    refresh(call("set_folder", { features: [menuFeature.name], folder: name.trim() }));
  });

  document.getElementById("ctx-unfolder").addEventListener("click", () => {
    if (menuFeature) {
      refresh(call("set_folder", { features: [menuFeature.name], folder: "" }));
    }
  });

  // Parents et enfants : un clic sur une ligne ouvre la fonction.
  document.getElementById("ctx-relations").addEventListener("click", async () => {
    if (!menuFeature) return;
    const feature = menuFeature;
    const rel = await call("feature_relations", { feature: feature.name })
      .catch((error) => { ctx.say(String(error.message ?? error), true); return null; });
    if (!rel) return;
    const rows = (list) => list.map((item) => ({
      label: item.label === item.kind ? item.label : `${item.label} — ${item.kind}`,
      onEdit: () => {
        const target = findFeatureInTree(ctx.lastTree, item.name);
        if (target) modifyMenuTarget(target);
      },
    }));
    panel.open({
      icon: "relations",
      title: t("Parents et enfants — {f}", { f: feature.label }),
      groups: [
        { label: t("Parents (elle s'appuie sur…)"), rows: [{ type: "list",
          empty: t("Aucun"), items: rows(rel.parents) }] },
        { label: t("Enfants (s'appuient sur elle)"), rows: [{ type: "list",
          empty: t("Aucun"), items: rows(rel.children) }] },
      ],
      noApply: true,
    });
  });

  document.getElementById("ctx-copy").addEventListener("click", () => {
    if (menuFeature) ctx.copyFeature(menuFeature);
  });

  document.getElementById("ctx-comment").addEventListener("click", () => {
    if (!menuFeature) return;
    const feature = menuFeature;
    panel.open({
      icon: "comment",
      title: t("Commentaire — {f}", { f: feature.label }),
      groups: [{ label: t("Note"), rows: [
        { type: "text", key: "text", label: t("Commentaire"),
          value: feature.comment ?? "",
          placeholder: t("Pourquoi cette cote, ce qu'il reste à faire…") },
      ] }],
      note: t("Visible en survolant la fonction dans l'arbre ; vide : retiré."),
      onApply: (v) => refreshAny(call("set_comment",
        { feature: feature.name, text: String(v.text ?? "") })),
    });
  });

  // Changer de plan : un plan d'origine, un plan de référence ou une
  // face cliquée dans la vue.
  document.getElementById("ctx-sketch-plane").addEventListener("click", () => {
    if (!menuFeature || menuFeature.type_key !== "sketch") return;
    const sketch = menuFeature;
    const tree = ctx.lastTree ?? {};
    const datums = (tree.features ?? [])
      .filter((f) => f.type_key === "datum_plane");
    panel.open({
      icon: "Sketcher_Sketch",
      title: t("Plan de l'esquisse — {s}", { s: sketch.label }),
      groups: [{ label: t("Nouveau plan"), rows: [
        { type: "select", key: "support", value: "XY", options: [
          ...(tree.planes ?? []).map((p) => [p.id, p.label]),
          ...datums.map((d) => [`datum:${d.name}`, d.label]),
          ["face", t("Face du solide")],
        ] },
        { type: "selection", key: "face", accepts: ["face"],
          label: t("Face d'accueil"), hint: t("Cliquez la face d'accueil"),
          showIf: (v) => v.support === "face" },
      ] }],
      note: t("Les entités gardent leurs coordonnées dans l'esquisse ; "
        + "les fonctions qui l'utilisent suivent le nouveau plan."),
      onApply: (v) => {
        const params = { sketch: sketch.name };
        if (v.support === "face") {
          if (v.face?.face == null) {
            ctx.say(t("Cliquez la face d'accueil"), true);
            return;
          }
          params.face = v.face.face;
        } else if (String(v.support).startsWith("datum:")) {
          params.datum = String(v.support).slice(6);
        } else {
          params.plane = v.support;
        }
        refresh(call("sketch_set_plane", params));
      },
    });
  });

  document.getElementById("ctx-suppress").addEventListener("click", () => {
    if (!menuFeature || !isSuppressibleTarget(menuFeature)) return;
    refresh(call("set_suppressed",
      { features: [menuFeature.name], suppressed: !menuFeature.suppressed }));
  });

  document.getElementById("ctx-hide").addEventListener("click", () => {
    if (!menuFeature || !isHideableTarget(menuFeature)) return;
    refreshAny(call("set_hidden",
      { objects: [menuFeature.name], hidden: !menuFeature.hidden }));
  });

  // Matière d'un corps : la bibliothèque, ou une masse volumique propre.
  document.getElementById("ctx-material").addEventListener("click", async () => {
    if (!menuFeature) return;
    const body = menuFeature;
    const library = await call("material_library").catch(() => null);
    if (!library) return;
    const current = body.material;
    panel.open({
      icon: "material",
      title: t("Matière — {b}", { b: body.label }),
      groups: [{ label: t("Matière"), rows: [
        { type: "select", key: "material", value: current?.id ?? "",
          options: [
            ["", t("(aucune)")],
            ...library.materials.map((m) => [m.id,
              `${m.name} — ${m.density} g/cm³`]),
            ["custom", t("Personnalisée…")],
          ] },
        { type: "number", key: "density", label: t("Masse volumique"),
          unit: "g/cm³", min: 0.001,
          value: current?.id === "custom" ? current.density : 1,
          showIf: (v) => v.material === "custom" },
      ] }],
      note: t("La masse (Évaluer) suit la matière ; sa teinte devient la "
        + "couleur du corps, sauf couleur choisie."),
      onApply: (v) => refresh(call("set_body_material", {
        body: body.name, material: String(v.material ?? ""),
        ...(v.material === "custom" ? { density: Number(v.density) } : {}),
      })),
    });
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

  // Les déplacements de la barre passent par l'arbre, qui garde la
  // position quittée pour « Revenir à la position précédente ».
  const barItem = (id, run) => {
    const item = document.getElementById(id);
    item.addEventListener("click", () => {
      if (!item.classList.contains("disabled")) run();
    });
  };
  barItem("ctx-rollback", () => {
    if (menuFeature) ctx.moveBar({ op: "set_tip", feature: menuFeature.name });
  });
  barItem("ctx-forward", () => ctx.stepBar(1));
  barItem("ctx-bar-back", () => ctx.barToPrevious());
  barItem("ctx-end", () => ctx.moveBar({ op: "tip_to_end" }));
  barItem("ctx-bar-delete", () => {
    if (confirm("Supprimer tout ce qui est sous la barre de retour ? "
      + "Une esquisse sortie au-dessus de la barre reste.")) {
      refreshAny(call("delete_rolled_back"));
    }
  });
  barItem("ctx-flat", () => ctx.setFlatTree(!ctx.isFlatTree()));
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
    if (ctx.sketchMode.active) {
      return { mode: "sketch", drawing: ctx.sketchMode.drawing,
               quickSnap: ctx.sketchMode.quickSnap };
    }
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
        .find((child) => child.type_key === "sketch");
      hit = {
        kind: "face",
        face: group.faceId,
        colored: !!group.color,
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

  // Boucle : un second appel sur la même arête prend l'autre face.
  let loopCycle = { edge: null, face: 0 };
  async function selectChain(edge, mode) {
    const again = mode === "loop" && loopCycle.edge === edge;
    loopCycle = { edge: mode === "loop" ? edge : null,
                  face: again ? loopCycle.face + 1 : 0 };
    const result = await call("edge_chain",
      { edge, mode, face: loopCycle.face }).catch((error) => {
      ctx.say(String(error.message ?? error), true);
      return null;
    });
    if (!result) return;
    ctx.selectEdgeIds(result.edges);
    ctx.say(t("{n} arête(s) sélectionnée(s)", { n: result.edges.length }));
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
          type_key: "sketch" }
      : hit.feature.sketchItem),
    rollback: (hit) => ctx.moveBar({ op: "set_tip", feature: hit.feature.name }),
    "select-tangent": (hit) => selectChain(hit.edge, "tangent"),
    "face-color": (hit) => {
      const picker = document.getElementById("body-color-picker");
      const group = ctx.meshGroups.find((g) => g.faceId === hit.face);
      picker.value = hexColor(group?.color) || cssHex(sceneTheme.part);
      picker.addEventListener("change", () => {
        refresh(call("set_face_color", { faces: [hit.face], color: picker.value }));
      }, { once: true });
      picker.click();
    },
    "face-color-reset": (hit) =>
      refresh(call("set_face_color", { faces: [hit.face], color: null })),
    "select-loop": (hit) => selectChain(hit.edge, "loop"),
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
    ...Object.fromEntries(SNAP_KINDS.map((k) =>
      ["snap-" + k.key, () => ctx.sketchMode.pickQuickSnap(k.key)])),
    "snap-none": () => ctx.sketchMode.pickQuickSnap(null),
    "snap-settings": () => ctx.openSettings?.("snaps"),
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
      icon.src = iconSrc(menuIcon(key));
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
          icon.src = iconSrc(menuIcon(key));
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
        if (menuIcon(item.key)) icon.src = iconSrc(menuIcon(item.key));
        else icon.className = "blank";
        row.append(icon, t(item.label));
        if (item.danger) row.classList.add("danger");
        if (item.checked) row.classList.add("checked");
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
  return {
    openMenu, openBarMenu, openTreeTitleMenu, showContextToolbar,
    hideContextToolbar,
  };
}
