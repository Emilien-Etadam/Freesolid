// Fonctions — combiner des corps (booléen).

import { combineConfirm, combineToolOptions } from "../combine.js";

/** Combiner : corps outils du noyau, plus ceux des plugins
 *  (`combine.js`). Un plugin peut aussi poser ce panneau sous un bouton
 *  de son onglet (`api.featureButton`). */
const COMBINE_FEATURE = {
  icon: "boolean",
  title: "Combiner",
  guard: (ctx) => {
    const options = combineToolOptions(ctx.lastTree);
    return options.length ? null
      : "Combiner : créez d'abord un second corps";
  },
  groups: (ctx) => {
    const options = combineToolOptions(ctx.lastTree);
    return [{
      label: "Opération",
      rows: [
        { type: "select", key: "type", value: "cut",
          options: [["cut", "Soustraire"], ["fuse", "Ajouter"],
                    ["common", "Intersection"]] },
        { type: "select", key: "tool", value: options[0]?.[0] ?? "",
          label: "Corps outil",
          options },
      ],
    }];
  },
  note: "S'applique au corps actif. Un second corps est absorbé.",
  // Un booléen peut durer des dizaines de secondes : l'aperçu jaune le
  // lancerait à l'ouverture du panneau, avant la confirmation.
  preview: false,
  confirm: (v, ctx) => combineConfirm(ctx.lastTree, v.tool),
  build: (v) => ({ op: "add_boolean",
    params: { tool: v.tool, type: v.type } }),
  refresh: "part",
};

export const COMBINER = [
  {
    button: "btn-boolean",
    ...COMBINE_FEATURE,
  },
];
