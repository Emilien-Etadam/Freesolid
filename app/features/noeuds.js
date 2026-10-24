// Fonctions — nœuds : fonction graphe, réseau variable.

import { minimalGraphCurve, minimalGraphFeature, minimalRepeatGraph } from "../graph.js";

export const NOEUDS = [
  {
    button: "btn-graph-feature",
    op: "add_graph_feature",
    icon: "graph_feature",
    title: "Fonction graphe",
    preview: false,
    groups: () => [{
      label: "Opération",
      rows: [
        { type: "select", key: "mode", value: "fuse",
          options: [
            ["fuse", "Solide — Ajouter"],
            ["cut", "Solide — Soustraire"],
            ["curve", "Courbe ou surface"],
          ] },
      ],
    }],
    note: "La géométrie produite est figée : changer une variable globale "
      + "ne recalcule pas la fonction — il faut la rouvrir et appliquer. "
      + "Le résultat est une forme combinée par un booléen, pas une "
      + "chaîne de fonctions.",
    build: (v) => {
      if (v.mode === "curve") {
        return {
          op: "add_graph_feature",
          params: { graph: minimalGraphCurve() },
        };
      }
      return {
        op: "add_graph_feature",
        params: { graph: minimalGraphFeature(), mode: v.mode },
      };
    },
    refresh: "part",
    openGraphEditor: true,
  },
  {
    button: "btn-repeat-variable",
    op: "add_repeat_feature",
    icon: "variable_pattern",
    title: "Réseau variable",
    preview: false,
    groups: (ctx) => [
      { label: "Fonctions",
        rows: [{ type: "selection", key: "features", accepts: ["feature"],
                 multiple: true, value: ctx?.selection?.(["feature"]) ?? null,
                 hint: "Cliquez les fonctions dans l'arbre, dans "
                       + "l'ordre du groupe" }] },
      { label: "Opération",
        rows: [
          { type: "select", key: "mode", value: "fuse",
            options: [["fuse", "Ajouter"], ["cut", "Soustraire"]] },
        ] },
    ],
    note: "Rejoue un groupe de fonctions avec des cotes différentes. "
      + "Si la topologie d'une instance ne correspond plus, la "
      + "répétition s'arrête plutôt que de produire.",
    build: (v) => {
      const items = v.features?.items ?? [];
      if (!items.length) return null;
      return {
        op: "add_repeat_feature",
        params: {
          features: items.map((item) => item.name),
          graph: minimalRepeatGraph(),
          mode: v.mode,
        },
      };
    },
    invalid: "Réseau variable : cliquez au moins une fonction dans l'arbre",
    refresh: "part",
    openGraphEditor: true,
  },
];
