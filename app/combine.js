// Combiner — les corps outils que le panneau propose.
//
// Le noyau propose les corps inactifs. Un plugin peut ajouter ses
// propres outils (`api.combineTools`) : il dit lesquels, demande une
// confirmation si l'opération risque d'être longue, et apprend combien
// elle a duré. Le noyau ne sait rien de leur métier.

/**
 * @typedef {{
 *   options: (tree: object|null) => Array<[string, string]>,
 *   confirm?: (tree: object|null, tool: string) => string|null,
 *   finished?: (tree: object|null, tool: string, seconds: number) => void,
 * }} CombineTools
 */

/** @type {CombineTools[]} */
const providers = [];

/** Enregistre les outils d'un plugin. `options` est obligatoire. */
export function addCombineTools(hooks) {
  if (!hooks || typeof hooks.options !== "function") return;
  providers.push(hooks);
}

/** Pour les tests : retire les outils enregistrés. */
export function resetCombineTools() {
  providers.length = 0;
}

/** Corps inactifs, puis outils des plugins : `[nom, libellé]`. */
export function combineToolOptions(tree) {
  const bodies = (tree?.bodies ?? []).filter((b) => !b.active);
  const options = bodies.map((b) => [b.name, b.label]);
  for (const hooks of providers) {
    let extra;
    try {
      extra = hooks.options(tree);
    } catch {
      continue; // un plugin cassé n'empêche pas de combiner deux corps
    }
    for (const item of Array.isArray(extra) ? extra : []) {
      if (Array.isArray(item) && typeof item[0] === "string" && item[0]) {
        options.push([item[0], String(item[1] ?? item[0])]);
      }
    }
  }
  return options;
}

/** Première question posée par un plugin, ou `null`. */
export function combineConfirm(tree, tool) {
  for (const hooks of providers) {
    if (typeof hooks.confirm !== "function") continue;
    let question;
    try {
      question = hooks.confirm(tree, tool);
    } catch {
      continue;
    }
    if (typeof question === "string" && question) return question;
  }
  return null;
}

/**
 * Une combinaison a abouti. `tree` est l'arbre d'avant l'opération :
 * c'est lui qui décrit l'outil tel qu'il a été combiné.
 */
export function combineFinished(tree, tool, seconds) {
  for (const hooks of providers) {
    try {
      hooks.finished?.(tree, tool, seconds);
    } catch {
      // un plugin cassé ne doit pas masquer le résultat
    }
  }
}
