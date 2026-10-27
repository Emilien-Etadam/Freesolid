// Esquisse : la sélection d'entités (sans l'origine) et ses panneaux —
// celui d'une entité (propriétés, poignées de spline, relations qui la
// touchent) et celui d'une sélection de plusieurs éléments ou d'un point
// (ce qui est choisi, les relations à ajouter, celles qui y sont).

import { t } from "../i18n.js";
import {
  entityKindTitle, entityPropertyLines, isDrivingConstraint, pickLabel,
  samePick,
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

  /** L'entité entière choisie seule (son panneau), ou null : plusieurs
   *  éléments, ou un point, ont le panneau de la sélection. */
  function soleEntity() {
    const [pick, ...rest] = mode.selection;
    return pick && !rest.length && pick.point == null
      && pick.geo !== ORIGIN_GEO ? pick.geo : null;
  }

  /** Ce que le panneau de la sélection montre : il se rouvre quand la
   *  sélection change. */
  function selectionKey() {
    return "sélection:" + mode.selection
      .map((pick) => `${pick.geo}.${pick.point ?? ""}`).join(",");
  }

  function syncEntityPanel({ refresh = false } = {}) {
    if (!mode.active || mode.drag) return;
    // Barre d'état : la longueur des entités choisies entières (un point
    // n'a pas de longueur).
    const whole = mode.selection.filter((pick) => pick.point == null)
      .map((pick) => pick.geo);
    document.dispatchEvent(new CustomEvent("freesolid:sketch-selection", {
      detail: whole.map((id) => mode.state?.entities.find((e) => e.id === id))
        .filter(Boolean) }));
    if (!mode.selection.length) {
      closeEntityPanel();
      return;
    }
    const geo = soleEntity();
    const key = geo ?? selectionKey();
    if (sk.entityPanelOpen && sk.entityPanelGeo === key && !refresh) return;
    if (geo != null) openEntityPanel(geo);
    else openSelectionPanel(key);
  }

  /** « Ajouter une relation » : un groupe de panneau, ou rien si la
   *  sélection n'en permet aucune. */
  function relationGroup() {
    const items = sk.relationButtons?.() ?? [];
    return items.length
      ? [{ label: t("Ajouter une relation"), rows: [{ type: "buttons", items }] }]
      : [];
  }

  function deleteConstraintItem(c) {
    return async () => {
      try {
        applyState(await call("sketch_delete_constraint", {
          sketch: mode.state.sketch, constraint: c.id,
        }), { keepSelection: true });
      } catch (error) {
        say(error.message, true);
      }
    };
  }

  /** Le panneau de plusieurs éléments choisis (Ctrl+clic), ou d'un
   *  point : chacun, qu'un ✕ retire de la sélection ; les relations que
   *  la sélection permet ; celles qui ne touchent qu'elle. */
  async function openSelectionPanel(key) {
    const gen = ++sk.entityPanelGen;
    let listed = { constraints: [] };
    try {
      listed = await call("sketch_constraints", { sketch: mode.state.sketch });
    } catch (error) {
      say(error.message, true);
    }
    if (gen !== sk.entityPanelGen || !mode.active) return;
    if (selectionKey() !== key) return;
    const entities = mode.state?.entities ?? [];
    const geos = new Set(mode.selection.map((pick) => pick.geo));
    const existing = (listed.constraints ?? []).filter((c) => c.geos.length
      && c.geos.every((g) => geos.has(g)));
    sk.entityPanelOpen = true;
    sk.entityPanelGeo = key;
    panel.open({
      icon: "select",
      title: t("Sélection ({n} entité(s))", { n: mode.selection.length }),
      noApply: true,
      autoFocus: false,
      groups: [
        {
          label: t("Éléments choisis"),
          rows: [{
            type: "list",
            items: mode.selection.map((pick) => ({
              label: pickLabel(pick, entities),
              onDelete: () => {
                mode.selection = mode.selection.filter(
                  (s) => !samePick(s, pick));
                sk.redraw();
                syncEntityPanel();
              },
            })),
          }],
        },
        ...relationGroup(),
        {
          label: t("Relations existantes"),
          rows: [{
            type: "list",
            empty: t("— aucune relation entre ces éléments —"),
            items: existing.map((c) => ({
              label: constraintItemLabel(c),
              onDelete: deleteConstraintItem(c),
            })),
          }],
        },
      ],
      note: t("Ctrl+clic : ajouter ou retirer un élément ; clic dans le vide : tout désélectionner."),
      onCancel: () => {
        abandonEntityPanel();
        if (mode.selection.length) {
          mode.selection = [];
          sk.redraw();
        }
      },
    });
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
    if (soleEntity() !== geo) return;

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
        ...relationGroup(),
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
                onDelete: deleteConstraintItem(c),
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
