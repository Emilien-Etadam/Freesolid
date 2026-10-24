// Esquisse : la sélection d'entités (sans l'origine) et le panneau
// d'une entité — propriétés, poignées de spline, relations qui la touchent.

import { t } from "../i18n.js";
import {
  entityKindTitle, entityPropertyLines, isDrivingConstraint,
} from "../geom2d.js";
import { ORIGIN_GEO } from "./commun.js";

export function installEntites(sk) {
  const {
    call, say, panel, mode, splineEdit, applyState, safe, editListedDim,
  } = sk;

  const ENTITY_ICONS = {
    Ligne: "nodes_line",
    Cercle: "nodes_circle",
    Arc: "nodes_arc",
    Spline: "nodes_bspline",
    Ellipse: "ellipse",
    Polyligne: "nodes_line",
    Entité: "sketch",
  };

  /** La sélection sans l'origine : ce qu'on peut symétriser, répéter… */
  function entityPicks() {
    return mode.selection.filter((pick) => pick.geo !== ORIGIN_GEO);
  }

  function uniqueSelectionGeos() {
    const seen = [];
    for (const pick of mode.selection) {
      if (!seen.includes(pick.geo)) seen.push(pick.geo);
    }
    return seen;
  }

  function abandonEntityPanel() {
    sk.entityPanelOpen = false;
    sk.entityPanelGeo = null;
    sk.entityPanelGen += 1;
  }

  function closeEntityPanel() {
    sk.entityPanelGen += 1;
    if (!sk.entityPanelOpen) return;
    sk.entityPanelOpen = false;
    sk.entityPanelGeo = null;
    if (panel.active) panel.close({ silent: true });
  }

  function constraintItemLabel(constraint) {
    return constraint.label
      + (constraint.name ? ` « ${constraint.name} »` : "")
      + (constraint.value !== undefined
         ? " = " + (constraint.type === "Angle"
             ? (constraint.value * 180 / Math.PI).toFixed(1) + "°"
             : constraint.value.toFixed(2))
         : "");
  }

  function syncEntityPanel({ refresh = false } = {}) {
    if (!mode.active || mode.drag) return;
    const geos = uniqueSelectionGeos();
    // Barre d'état : la longueur de ce qui est sélectionné.
    document.dispatchEvent(new CustomEvent("freesolid:sketch-selection", {
      detail: geos.map((id) => mode.state?.entities.find((e) => e.id === id))
        .filter(Boolean) }));
    if (geos.length !== 1) {
      closeEntityPanel();
      return;
    }
    const geo = geos[0];
    if (sk.entityPanelOpen && sk.entityPanelGeo === geo && !refresh) return;
    openEntityPanel(geo);
  }

  async function openEntityPanel(geo) {
    const gen = ++sk.entityPanelGen;
    const entity = mode.state?.entities.find((e) => e.id === geo);
    if (!entity || !mode.state) {
      closeEntityPanel();
      return;
    }
    let listed = { constraints: [] };
    try {
      listed = await call("sketch_constraints",
        { sketch: mode.state.sketch, geo });
    } catch (error) {
      say(error.message, true);
    }
    if (gen !== sk.entityPanelGen || !mode.active) return;
    if (uniqueSelectionGeos()[0] !== geo) return;

    const title = entityKindTitle(entity);
    const propRows = entityPropertyLines(entity).map((text) => ({
      type: "note",
      text,
      readonly: true,
      onClick: () => say(
        "Cette valeur est informative — coter l'entité (D) pour la piloter."),
    }));
    propRows.push({
      type: "note",
      text: t("Construction : {v}",
        { v: entity.construction ? t("oui") : t("non") }),
      readonly: true,
    });
    const constraints = listed.constraints ?? [];
    const hasDriving = constraints.some(isDrivingConstraint);
    sk.entityPanelOpen = true;
    sk.entityPanelGeo = geo;
    const splineGroup = splineEdit.panelGroup();
    panel.open({
      icon: ENTITY_ICONS[title] ?? ENTITY_ICONS.Entité,
      title,
      noApply: true,
      autoFocus: false,
      onChange: splineGroup ? (values) => splineEdit.panelChange(values) : undefined,
      groups: [
        { label: t("Propriétés"), rows: propRows },
        ...(splineGroup ? [splineGroup] : []),
        {
          label: t("Relations"),
          rows: [{
            type: "list",
            empty: t("— aucune relation sur cette entité —"),
            items: constraints.map((c) => {
              const driving = isDrivingConstraint(c);
              return {
                label: constraintItemLabel(c),
                editable: driving,
                onEdit: driving ? () => editListedDim(c, geo) : undefined,
                onDelete: async () => {
                  try {
                    applyState(await call("sketch_delete_constraint", {
                      sketch: mode.state.sketch, constraint: c.id,
                    }), { keepSelection: true });
                  } catch (error) {
                    say(error.message, true);
                  }
                },
              };
            }),
          }],
        },
      ],
      note: hasDriving
        ? "Cliquez une cote dans Relations pour la modifier."
        : "Pour piloter une valeur : Cotation (D).",
      actions: [
        {
          label: t("Construction"),
          title: entity.construction
            ? "Géométrie de construction — cliquer pour basculer en réelle"
            : "Géométrie réelle — cliquer pour basculer en construction",
          className: "paction",
          onClick: () => {
            safe(call("sketch_toggle_construction",
              { sketch: mode.state.sketch, geo }),
            { keepSelection: true });
          },
        },
        {
          label: t("Supprimer"),
          title: t("Supprimer l'entité (Suppr)"),
          className: "paction",
          onClick: () => {
            safe(call("sketch_delete_geo",
              { sketch: mode.state.sketch, geo }));
          },
        },
      ],
      onCancel: () => {
        abandonEntityPanel();
        if (mode.selection.length) {
          mode.selection = [];
          sk.redraw();
        }
      },
    });
  }

  return {
    entityPicks, uniqueSelectionGeos, abandonEntityPanel, closeEntityPanel,
    syncEntityPanel, openEntityPanel,
  };
}
