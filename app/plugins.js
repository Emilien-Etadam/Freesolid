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

/**
 * API client exposée à `register(api)`. L'hôte fournit le DOM et le
 * moteur ; ici on ne fait que collecter et dispatcher, dans l'ordre
 * d'enregistrement.
 *
 * @param {{
 *   call: Function,
 *   refresh: Function,
 *   say: Function,
 *   tree: () => object|null,
 *   scene?: object,
 *   camera?: object,
 *   controls?: object,
 *   addRibbon?: Function,
 *   addFeature?: Function,
 *   addHud?: Function,
 * }} host
 */
export function createPluginApi(host) {
  const keys = [];
  const treeRows = [];
  const viewports = [];
  const pointers = [];
  let viewportObjects = [];

  const api = {
    get call() { return host.call; },
    get refresh() { return host.refresh; },
    get say() { return host.say; },
    get tree() { return host.tree(); },
    get scene() { return host.scene; },
    get camera() { return host.camera; },
    get controls() { return host.controls; },
    get renderer() { return host.renderer; },

    ribbon(spec) {
      if (!spec || typeof spec !== "object") return;
      host.addRibbon?.(spec);
    },
    feature(entry) {
      if (!entry || typeof entry !== "object") return;
      host.addFeature?.(entry);
    },
    hud(node) {
      if (node) host.addHud?.(node);
    },
    key(handler) {
      if (typeof handler === "function") keys.push(handler);
    },
    treeRow(predicat, rendu) {
      if (typeof predicat !== "function" || typeof rendu !== "function") return;
      treeRows.push({ predicat, rendu });
    },
    viewport(hooks) {
      if (!hooks || typeof hooks !== "object") return;
      viewports.push(hooks);
    },
    pointer(hooks) {
      if (!hooks || typeof hooks !== "object") return;
      pointers.push(hooks);
    },
  };

  return {
    api,
    dispatchKey(event) {
      for (const handler of keys) {
        if (handler(event) === true) return true;
      }
      return false;
    },
    renderTreeRows(tree, helpers) {
      for (const { predicat, rendu } of treeRows) {
        let items;
        try {
          items = predicat(tree);
        } catch {
          continue;
        }
        const list = Array.isArray(items) ? items : [];
        for (const item of list) {
          let row;
          try {
            row = rendu(item, helpers);
          } catch {
            continue;
          }
          if (row) helpers.append(row);
        }
      }
    },
    clearViewport(detach) {
      for (const hooks of viewports) {
        try { hooks.onClear?.(); } catch { /* un plugin cassé n'empêche pas */ }
      }
      if (typeof detach === "function") {
        for (const obj of viewportObjects) detach(obj);
      }
      viewportObjects = [];
    },
    applyViewport(mesh, ctx, detach) {
      this.clearViewport(detach);
      for (const hooks of viewports) {
        let objects;
        try {
          objects = hooks.onMesh?.(mesh, ctx);
        } catch {
          continue;
        }
        const list = Array.isArray(objects) ? objects : (objects ? [objects] : []);
        for (const obj of list) {
          if (!obj) continue;
          ctx.volumesGroup.add(obj);
          viewportObjects.push(obj);
        }
      }
    },
    get viewportObjects() { return viewportObjects; },
    dispatchPointer(phase, event, ctx) {
      if (phase !== "down" && phase !== "move" && phase !== "up") return false;
      for (const hooks of pointers) {
        const fn = hooks[phase];
        if (typeof fn === "function" && fn(event, ctx) === true) return true;
      }
      return false;
    },
    runPointerIdle(ctx) {
      for (const hooks of pointers) {
        try { hooks.idle?.(ctx); } catch { /* un plugin cassé n'empêche pas */ }
      }
    },
  };
}
