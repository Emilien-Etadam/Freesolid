// Démarrage : gabarits, accueil, ping du moteur, plugins clients, puis
// resynchronisation avec la pièce ou l'assemblage déjà ouvert.

import { FEATURES } from "../features.js";
import { loadClientPlugins } from "../plugins.js";
import { installWelcome } from "../welcome.js";
import { t } from "../i18n.js";

export function installBoot(ctx) {
  const {
    call, say, localStore, refresh, updateViewport, renderTree,
    clearFeatureDims, openDocument, showTab, bindFeature, showAssemblyMeshes,
    renderAssemblyTree, mayDiscard,
  } = ctx;

  // Nouvelle pièce depuis un gabarit (accueil, volet de ressources).
  ctx.openTemplate = async (name) => {
    if (!(await mayDiscard())) return;
    clearFeatureDims();
    refresh(call("new_from_template", { name }));
  };

  ctx.welcomeApi = installWelcome(document, {
    storage: localStore,
    hasDocument: () => Boolean(ctx.lastTree || ctx.assemblyState),
    onPart: () => document.getElementById("btn-new").click(),
    onAssembly: () => document.getElementById("btn-newasm").click(),
    onOpen: () => document.getElementById("btn-open").click(),
    onRecent: (path) => openDocument(path),
    listTemplates: () => call("list_templates").then((r) => r.templates),
    onTemplate: (name) => ctx.openTemplate(name),
  });

  call("ping")
    .then(async (info) => {
      await loadClientPlugins(call, ctx.pluginRuntime.api);
      for (const entry of FEATURES) bindFeature(entry);
      say(t("Moteur prêt — FreeCAD {v}", { v: info.freecad }));
      // Resynchronise avec le moteur : après un rechargement de la page,
      // la pièce en cours réapparaît au lieu d'être écrasée au premier
      // clic sur Esquisse.
      try {
        const gen = ++ctx.viewGen;
        const tree = await call("get_tree");
        if (gen !== ctx.viewGen) return;
        renderTree(tree);
        await updateViewport(gen);
      } catch {
        try {
          // Peut-être un assemblage en cours dans le moteur.
          const gen = ++ctx.viewGen;
          ctx.assemblyState = await call("assembly_tree");
          if (gen !== ctx.viewGen) return;
          renderAssemblyTree(ctx.assemblyState);
          const meshes = await call("tessellate_assembly");
          if (gen !== ctx.viewGen) return;
          showAssemblyMeshes(meshes);
          showTab("assembly");
        } catch {
          // pas encore de document — l'accueil propose d'en créer un
          ctx.welcomeApi?.showWelcome();
        }
      }
    })
    .catch(() => say("Moteur injoignable — lancez engine/server.py avec freecadcmd", true));
}
