// Fonctions — combiner des corps (booléen), supprimer des corps.

import { combineConfirm, combineToolOptions } from "../combine.js";
import { bodyZoneRow } from "./commun.js";

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
// Une zone, comme dans les modeleurs courants : les corps choisis dans la
// vue ou sur une ligne du dossier — un solide d'un corps qui en garde
// plusieurs, une surface (sa ligne). La fonction ôte ces corps de la
// pièce à son rang, ou ne garde qu'eux ; ils reviennent quand on recule
// la barre au-dessus d'elle ou qu'on la supprime. La réédition rouvre le
// même panneau, la zone remplie de ses corps ; seuls les corps qui
// existent à son rang y entrent (app/tree.js).

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

/** Le candidat que vise un choix de la zone (ou une ligne du dossier),
 *  ou null : un corps à plusieurs solides se vise solide par solide. */
export function removalMatch(pick, candidates) {
  return candidates.find((c) => c.name === pick?.name
    && (c.solid ?? null) === (pick.solid ?? null)) ?? null;
}

/** Ce que la zone montre d'un candidat. */
export function removalItem(candidate) {
  const { name, label, solid, surface } = candidate;
  return surface ? { kind: "surface", name, label }
    : { kind: "body", name, label,
        ...(Number.isInteger(solid) ? { solid } : {}) };
}

/** La zone → cibles du moteur, dans l'ordre des clics. */
export function removalTargets(v, candidates) {
  return (v.targets?.items ?? [])
    .map((item) => removalMatch(item, candidates)).filter(Boolean)
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

/** Le mode, puis la zone — remplie d'emblée des candidats qui portent
 *  `checked` (réédition). Création et réédition ont le même panneau. */
export function removeBodiesGroups(candidates, keep = false) {
  return [
    { label: "Opération",
      rows: [{ type: "select", key: "mode", value: keep ? "keep" : "remove",
               options: [["remove", "Supprimer les corps choisis"],
                         ["keep", "Garder seulement les corps choisis"]] }] },
    { label: "Corps",
      rows: [bodyZoneRow("targets", {
        accepts: ["body", "surface"], solids: true,
        allows: (pick) => removalMatch(pick, candidates) !== null,
        value: { kind: "body", items: candidates.filter((c) => c.checked)
          .map(removalItem) } })] },
  ];
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
  invalid: "Choisissez au moins un corps",
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
