// Esquisse : le panneau d'un outil (rayon du congé, côtés du polygone,
// chanfrein…) — la valeur se règle, l'outil reste actif.

import { t } from "../i18n.js";
import { num } from "../num.js";

export function installPanneauOutil(sk) {
  const { panel, mode, abandonEntityPanel, setTool } = sk;

  // Panneau d'outil : la valeur de l'outil (rayon du congé, nombre de
  // côtés) se règle à gauche, l'outil reste actif pour plusieurs clics.
  let toolPanelOpen = null;

  function openToolPanel(tool) {
    abandonEntityPanel();
    toolPanelOpen = tool;
    if (tool === "skchamfer") {
      panel.open({
        icon: "sk_chamfer",
        title: t("Chanfrein d'esquisse"),
        groups: [{
          label: t("Paramètres"),
          rows: [
            { type: "number", key: "distance", label: t("Distance"),
              value: mode.chamfer.distance, unit: "mm", min: 0.01 },
            { type: "number", key: "distance2",
              label: t("Seconde distance (vide = égale)"),
              value: mode.chamfer.distance2 ?? "", unit: "mm", min: 0.01 },
          ],
        }],
        note: t("Cliquez deux lignes près du coin à chanfreiner."),
        onChange: (v) => {
          const d = num(v.distance);
          if (d > 0) mode.chamfer.distance = d;
          const d2 = num(v.distance2);
          mode.chamfer.distance2 = d2 > 0 ? d2 : null;
        },
        onApply: () => { toolPanelOpen = null; setTool("select"); },
        onCancel: () => { toolPanelOpen = null; setTool("select"); },
      });
      return;
    }
    const fillet = tool === "skfillet";
    panel.open({
      icon: fillet ? "sketch_fillet" : "polygon",
      title: fillet ? t("Congé d'esquisse") : t("Polygone"),
      groups: [{
        label: t("Paramètres"),
        rows: [fillet
          ? { type: "number", key: "value", label: t("Rayon"),
              value: mode.filletRadius, unit: "mm", min: 0.01 }
          : { type: "number", key: "value", label: t("Nombre de côtés"),
              value: mode.polygonSides, min: 3, step: 1 },
          ...(fillet ? [] : [{ type: "check", key: "inscribed",
            label: t("Par le cercle inscrit (clic au milieu d'un côté)"),
            value: !!mode.polygonInscribed }])],
      }],
      note: fillet ? t("Cliquez deux lignes près du coin à arrondir.")
        : t("Cliquez le centre, puis un sommet (ou le milieu d'un côté)."),
      onChange: (v) => {
        if (fillet) {
          const radius = num(v.value);
          if (radius > 0) mode.filletRadius = radius;
        } else {
          mode.polygonInscribed = !!v.inscribed;
          const sides = parseInt(v.value, 10);
          if (sides >= 3) {
            mode.polygonSides = sides;
            if (mode.pendingPoly) mode.pendingPoly.sides = sides;
          }
        }
      },
      onApply: () => { toolPanelOpen = null; setTool("select"); },
      onCancel: () => { toolPanelOpen = null; setTool("select"); },
    });
  }

  function closeToolPanel() {
    if (!toolPanelOpen) return;
    toolPanelOpen = null;
    if (panel.active) panel.close({ silent: true });
  }

  return { openToolPanel, closeToolPanel };
}
