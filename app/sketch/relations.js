// Esquisse : les relations manuelles (boutons de la barre, selon la
// sélection, et menu rapide près du curseur) et le panneau Relations, qui
// les liste et les supprime.

import { t } from "../i18n.js";
import { applicableRelations, relationOrder } from "../geom2d.js";
import { iconSrc } from "../icons.js";
import { nearCursor } from "../screen.js";

/** Le nom de chaque relation, dans le panneau de la sélection ; son
 *  icône est ``rel_<relation>``. */
const RELATION_LABELS = {
  horizontal: "Horizontale", vertical: "Verticale", fixed: "Fixe",
  coincident: "Coïncidente", parallel: "Parallèle",
  perpendicular: "Perpendiculaire", tangent: "Tangente", equal: "Égale",
  concentric: "Concentrique", collinear: "Colinéaire", midpoint: "Milieu",
  symmetric: "Symétrique", onobject: "Sur l'entité", coradial: "Corradiale",
  intersection: "Croisement",
};

export function installRelations(sk) {
  const {
    call, say, mode, safe, uniqueSelectionGeos, openEntityPanel, renderer,
  } = sk;

  //: relation -> nombre d'entités attendues. symmetric : 2 points + l'axe.
  const CONSTRAINT_NEEDS = {
    horizontal: 1, vertical: 1, fixed: 1,
    parallel: 2, perpendicular: 2, equal: 2, tangent: 2,
    coincident: 2, concentric: 2, collinear: 2, midpoint: 2,
    onobject: 2, coradial: 2,
    symmetric: 3, intersection: 3,
  };

  /** Pose la relation ``kind`` sur la sélection, prise dans l'ordre des
   *  relations (les points d'abord). ``keepSelection`` : la sélection
   *  reste, pour en poser une autre (le panneau de la sélection). */
  function applyConstraint(kind, { keepSelection = false } = {}) {
    if (!mode.state) return;
    let needed = CONSTRAINT_NEEDS[kind];
    const ordered = relationOrder(mode.selection);
    // Horizontale / verticale : une ligne, ou deux points alignés.
    const lastTwo = ordered.slice(-2);
    if ((kind === "horizontal" || kind === "vertical") && lastTwo.length === 2
        && lastTwo.every((pick) => pick.point != null)) {
      needed = 2;
    }
    if (ordered.length < needed) {
      say(t("Relation : sélectionnez d'abord {n} entité(s) avec l'outil Sélectionner",
        { n: needed }), true);
      return;
    }
    const selection = ordered.slice(-needed);
    const params = { sketch: mode.state.sketch, kind,
                     geo1: selection[0].geo };
    if (selection[0].point != null) params.point1 = selection[0].point;
    if (selection[1]) {
      params.geo2 = selection[1].geo;
      if (selection[1].point != null) params.point2 = selection[1].point;
    }
    if (needed >= 3 && selection[2]) params.geo3 = selection[2].geo;
    safe(call("sketch_constrain", params), { keepSelection });
  }

  /** Les boutons « Ajouter une relation » d'un panneau : les relations
   *  que la sélection permet. */
  function relationButtons() {
    return applicableRelations(mode.selection, mode.state?.entities)
      .map((kind) => ({
        label: RELATION_LABELS[kind],
        icon: "rel_" + kind,
        onClick: () => applyConstraint(kind, { keepSelection: true }),
      }));
  }
  Object.assign(sk, { relationButtons });

  for (const kind of Object.keys(CONSTRAINT_NEEDS)) {
    document.getElementById("sk-c-" + kind)
      .addEventListener("click", () => applyConstraint(kind));
  }

  // ---------- menu rapide, près du curseur ----------

  // Plusieurs éléments choisis au Ctrl+clic (ou au cadre) : les relations
  // qu'ils permettent s'offrent près du curseur. Le menu s'efface quand la
  // souris s'éloigne, au clic suivant, avec Échap ou quand la sélection
  // n'en permet plus.
  let quickEl = null;
  let quickAnchor = null;

  function hideQuickRelations() {
    if (quickEl) quickEl.hidden = true;
    quickAnchor = null;
  }

  function quickMenu() {
    if (quickEl) return quickEl;
    const host = renderer.domElement.parentElement;
    quickEl = document.createElement("div");
    quickEl.id = "sk-quick-relations";
    quickEl.setAttribute("role", "menu");
    quickEl.setAttribute("aria-label", t("Relations possibles"));
    quickEl.hidden = true;
    host.appendChild(quickEl);
    host.addEventListener("pointermove", (event) => {
      if (quickAnchor && Math.hypot(event.clientX - quickAnchor.x,
                                    event.clientY - quickAnchor.y) > 160) {
        hideQuickRelations();
      }
    });
    host.addEventListener("pointerdown", (event) => {
      if (!quickEl.contains(event.target)) hideQuickRelations();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") hideQuickRelations();
    });
    return quickEl;
  }

  /** Ouvre le menu rapide au curseur de ``event`` — s'il y a plusieurs
   *  éléments choisis et une relation à leur proposer. */
  function showQuickRelations(event) {
    const kinds = mode.active && mode.selection.length >= 2
      ? applicableRelations(mode.selection, mode.state?.entities) : [];
    if (!kinds.length) { hideQuickRelations(); return; }
    const menu = quickMenu();
    menu.replaceChildren(...kinds.map((kind) => {
      const button = document.createElement("button");
      button.type = "button";
      button.setAttribute("role", "menuitem");
      button.dataset.relation = kind;
      button.title = t(RELATION_LABELS[kind]);
      const icon = document.createElement("img");
      icon.src = iconSrc("rel_" + kind);
      icon.alt = button.title;
      button.appendChild(icon);
      button.addEventListener("click", (clickEvent) => {
        clickEvent.stopPropagation();
        hideQuickRelations();
        applyConstraint(kind, { keepSelection: true });
      });
      return button;
    }));
    menu.hidden = false;
    const spot = nearCursor(event.clientX, event.clientY,
      menu.parentElement.getBoundingClientRect(),
      { width: menu.offsetWidth, height: menu.offsetHeight });
    menu.style.left = `${spot.left}px`;
    menu.style.top = `${spot.top}px`;
    quickAnchor = { x: event.clientX, y: event.clientY };
  }
  Object.assign(sk, { showQuickRelations, hideQuickRelations });

  /** Avec une sélection, seules les relations qu'elle permet restent
   *  actives (et sont mises en avant) ; sans sélection, toutes. */
  function updateRelationButtons() {
    const selection = mode.active ? mode.selection : [];
    const possible = selection.length
      ? applicableRelations(selection, mode.state?.entities) : null;
    for (const kind of Object.keys(CONSTRAINT_NEEDS)) {
      const button = document.getElementById("sk-c-" + kind);
      if (!button) continue;
      button.disabled = !!possible && !possible.includes(kind);
      button.classList.toggle("suggest", !!possible?.includes(kind));
    }
    if (selection.length < 2 || mode.tool !== "select") hideQuickRelations();
  }

  // ---------- panneau Relations (voir et supprimer) ----------

  async function openRelationsPanel() {
    if (!mode.state) return;
    if (uniqueSelectionGeos().length !== 1) {
      say("Relations : sélectionnez d'abord UNE entité " +
          "(outil Sélectionner)", true);
      return;
    }
    // Un point choisi : le panneau est celui de son entité, choisie
    // entière.
    const geo = uniqueSelectionGeos()[0];
    mode.selection = [{ geo }];
    sk.redraw();
    await openEntityPanel(geo);
  }

  document.getElementById("sk-relations")
    .addEventListener("click", openRelationsPanel);

  return { updateRelationButtons };
}
