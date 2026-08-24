// Chargement des plugins client au démarrage.
// La liste vient de `list_plugins` : nom + point d'entrée. Un nom d'URL
// qui ne correspond pas au nom annoncé n'est pas importé.

const ENTRY_RE = /^\/plugins\/([a-z][a-z0-9_]*)\/plugin\.js$/;

/** Valide l'entrée JS : même nom que le manifeste, chemin jailé. */
export function pluginEntryUrl(nom, entree) {
  if (typeof nom !== "string" || typeof entree !== "string") return "";
  const match = ENTRY_RE.exec(entree);
  if (!match || match[1] !== nom) return "";
  return entree;
}

/**
 * Importe chaque plugin annoncé et appelle `register(api)`.
 * Un module cassé n'empêche pas les suivants. `importer` est injectable
 * pour les tests Node.
 * @param {(op: string, params?: object) => Promise<object>} call
 * @param {object} api
 * @param {(url: string) => Promise<object>} [importer]
 * @returns {Promise<string[]>} noms effectivement enregistrés
 */
export async function loadClientPlugins(call, api, importer = (url) => import(url)) {
  let listed;
  try {
    listed = await call("list_plugins");
  } catch {
    return [];
  }
  const loaded = [];
  for (const item of listed?.plugins ?? []) {
    const url = pluginEntryUrl(item?.nom, item?.entree);
    if (!url) continue;
    try {
      const mod = await importer(url);
      if (typeof mod?.register === "function") {
        mod.register(api);
        loaded.push(item.nom);
      }
    } catch {
      // Un plugin JS cassé n'empêche pas les autres, comme côté moteur.
    }
  }
  return loaded;
}
