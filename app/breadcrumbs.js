// Fil d'Ariane de la sélection, en haut à gauche de la vue : la pièce, la
// fonction qui a créé la face choisie, son esquisse, la face. Un clic sur
// une étape la choisit dans l'arbre, un double-clic l'édite. Le calcul du
// fil est pur (breadcrumbTrail) ; l'affichage suit les choix de la vue.

import { t } from "./i18n.js";
import { iconSrc } from "./icons.js";
import { TREE_ICONS } from "./tree.js";

/** La fonction `name` dans l'arbre (dossiers compris), ou null. */
export function findFeature(features, name) {
  for (const feature of features ?? []) {
    if (feature.name === name) return feature;
    const inner = findFeature(feature.features ?? feature.items, name);
    if (inner) return inner;
  }
  return null;
}

/** Étapes du fil pour la face `faceId` : [{ kind, label, icon, item }].
 *  `groups` : les groupes du maillage ({ faceId, feature }). Sans face, un
 *  fil vide. */
export function breadcrumbTrail(tree, groups, faceId) {
  if (faceId === null || faceId === undefined || !tree) return [];
  const trail = [{ kind: "part", label: tree.body ?? t("Pièce"), icon: "body" }];
  const group = (groups ?? []).find((g) => g.faceId === faceId);
  const feature = group?.feature ? findFeature(tree.features, group.feature) : null;
  if (feature) {
    trail.push({ kind: "feature", label: feature.label ?? feature.name,
                 icon: TREE_ICONS[feature.type] ?? "body", item: feature });
    const sketch = (feature.children ?? []).find(
      (child) => child.type === "Sketcher::SketchObject");
    if (sketch) {
      trail.push({ kind: "sketch", label: sketch.label ?? sketch.name,
                   icon: "Sketcher_Sketch", item: sketch });
    }
  }
  trail.push({ kind: "face", label: t("Face {n}", { n: faceId }) });
  return trail;
}

export function installBreadcrumbs(ctx) {
  const host = document.getElementById("viewport");
  if (!host) return null;
  const bar = document.createElement("nav");
  bar.id = "breadcrumbs";
  bar.setAttribute("aria-label", t("Fil de la sélection"));
  bar.hidden = true;
  host.appendChild(bar);

  function hidden() {
    return ctx.panel?.active || ctx.sketchMode?.active || ctx.assemblyState;
  }

  function render() {
    const trail = hidden() ? []
      : breadcrumbTrail(ctx.lastTree, ctx.meshGroups, ctx.selectedFaceId);
    bar.replaceChildren();
    bar.hidden = trail.length === 0;
    trail.forEach((step, i) => {
      if (i) {
        const sep = document.createElement("span");
        sep.className = "crumb-sep";
        sep.textContent = "›";
        sep.setAttribute("aria-hidden", "true");
        bar.appendChild(sep);
      }
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "crumb crumb-" + step.kind;
      const src = step.icon ? iconSrc(step.icon) : "";
      if (src) {
        const img = document.createElement("img");
        img.src = src;
        img.alt = "";
        chip.appendChild(img);
      }
      chip.appendChild(document.createTextNode(step.label));
      if (step.kind === "feature") {
        chip.title = t("Clic : choisir dans l'arbre · double-clic : modifier");
        chip.addEventListener("click", () => {
          ctx.selectedFeatureName = step.item.name;
          if (ctx.lastTree) ctx.renderTree(ctx.lastTree);
        });
        chip.addEventListener("dblclick", () => ctx.editFeature?.(step.item));
      } else if (step.kind === "sketch") {
        chip.title = t("Clic : choisir l'esquisse · double-clic : la modifier");
        chip.addEventListener("click", () => ctx.onSketchRowClick?.(step.item));
        chip.addEventListener("dblclick", () => ctx.onSketchRowDblClick?.(step.item));
      } else {
        chip.tabIndex = -1;
      }
      bar.appendChild(chip);
    });
  }

  // La vue signale chaque choix de face ; l'arbre, chaque reconstruction.
  const previous = ctx.onFacePicked;
  ctx.onFacePicked = (face) => {
    previous?.(face);
    render();
  };
  ctx.treeHooks?.push(() => render());
  document.addEventListener("freesolid:sketch-state", render);
  return { render };
}
