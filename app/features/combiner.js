// Fonctions — combiner des corps (booléen), supprimer des corps.

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

// ---------- supprimer des corps ----------
// Une case par corps du dossier : chaque solide d'un corps qui en garde
// plusieurs, chaque surface. La fonction ôte les corps cochés de la pièce
// à son rang, ou ne garde qu'eux ; ils reviennent quand on recule la
// barre au-dessus d'elle ou qu'on la supprime. La réédition rouvre le
// même panneau, sur les corps qui existent à son rang (app/tree.js).

/** Clé de la case d'un corps (`{ name, solid? }`). */
export function removalKey(target) {
  return Number.isInteger(target.solid)
    ? `rm:${target.name}:${target.solid}` : `rm:${target.name}`;
}

/** Ce que le dossier montre et qu'une suppression peut viser. */
export function removalCandidates(tree) {
  const rows = [];
  for (const body of tree?.bodies ?? []) {
    if (body.has_solid !== true) continue;
    if (body.solids?.length) {
      body.solids.forEach((solid, index) => rows.push(
        { name: body.name, solid: index, label: solid.label }));
    } else {
      rows.push({ name: body.name, label: body.label });
    }
  }
  for (const surface of tree?.surfaces ?? []) {
    if (surface.removed || surface.consumed || surface.rolled_back) continue;
    rows.push({ name: surface.name, label: surface.label, surface: true });
  }
  return rows;
}

/** Cases cochées → cibles du moteur, dans l'ordre des candidats. */
export function removalTargets(v, candidates) {
  return candidates.filter((c) => v[removalKey(c)])
    .map(({ name, solid }) =>
      (Number.isInteger(solid) ? { name, solid } : { name }));
}

/** Paramètres d'une suppression (`targets`, `keep`), ou null tant que
 *  rien n'est coché. */
export function removeBodiesParams(v, candidates) {
  const targets = removalTargets(v, candidates);
  return targets.length ? { targets, keep: v.mode === "keep" } : null;
}

export function removeBodiesBuild(v, ctx) {
  const params = removeBodiesParams(v, removalCandidates(ctx?.lastTree));
  return params ? { op: "add_remove_bodies", params } : null;
}

/** Le mode, puis une case par candidat — cochée d'emblée quand il porte
 *  `checked` (réédition). Création et réédition ont le même panneau. */
export function removeBodiesGroups(candidates, keep = false) {
  const check = (c) => ({ type: "check", key: removalKey(c),
                          label: c.label, value: !!c.checked });
  const solids = candidates.filter((c) => !c.surface);
  const surfaces = candidates.filter((c) => c.surface);
  return [
    { label: "Opération",
      rows: [{ type: "select", key: "mode", value: keep ? "keep" : "remove",
               options: [["remove", "Supprimer les corps cochés"],
                         ["keep", "Garder seulement les corps cochés"]] }] },
    solids.length && { label: "Corps volumiques", rows: solids.map(check) },
    surfaces.length
      && { label: "Corps surfaciques", rows: surfaces.map(check) },
  ].filter(Boolean);
}

export const REMOVE_BODIES_NOTE = "Les corps ôtés reviennent quand on "
  + "recule la barre au-dessus de la fonction, ou qu'on la supprime.";

const REMOVE_BODIES_FEATURE = {
  icon: "remove_bodies",
  title: "Supprimer des corps",
  guard: (ctx) => (removalCandidates(ctx.lastTree).length ? null
    : "Supprimer des corps : la pièce n'a pas encore de corps"),
  groups: (ctx) => removeBodiesGroups(removalCandidates(ctx.lastTree)),
  note: REMOVE_BODIES_NOTE,
  preview: false,
  build: removeBodiesBuild,
  invalid: "Cochez au moins un corps",
  refresh: "part",
};

export const COMBINER = [
  {
    button: "btn-boolean",
    op: "add_boolean",
    ...COMBINE_FEATURE,
  },
  {
    button: "btn-remove-bodies",
    op: "add_remove_bodies",
    ...REMOVE_BODIES_FEATURE,
  },
];
