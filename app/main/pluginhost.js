// Hôte des plugins clients : onglets et fonctions du ruban, boutons qui
// ouvrent une fonction du noyau, calques de la vue ; crée pluginRuntime.

import { FEATURES } from "../features.js";
import { addCombineTools } from "../combine.js";
import { createPluginApi } from "../plugins.js";
import { buildRibbonElement, buildTabButton, isPluginId } from "../ribbon.js";

export function installPluginHost(ctx) {
  const {
    scene, RIBBONS, call, say, renderer, camera, controls, refresh, showTab,
    bindFeature,
  } = ctx;

  function addPluginRibbon(spec) {
    if (!isPluginId(spec.id) || RIBBONS[spec.id]) return;
    const tab = buildTabButton(document, spec.id, spec.libelle);
    const push = document.querySelector("#topbar .push");
    if (push) push.parentElement.insertBefore(tab, push);
    tab.addEventListener("click", () => showTab(spec.id));

    const ribbon = buildRibbonElement(document, spec.id, spec.groupes);
    const sketchbar = document.getElementById("sketchbar");
    sketchbar.parentElement.insertBefore(ribbon, sketchbar);
    RIBBONS[spec.id] = ribbon.id;
  }

  function addPluginFeature(entry) {
    FEATURES.push(entry);
    bindFeature(entry);
  }

  /** Un bouton de plugin ouvre une fonction du noyau, sans la dupliquer. */
  function addPluginFeatureButton(id, coreButton) {
    const entry = FEATURES.find((feat) => feat.button === coreButton);
    if (!entry) return;
    entry.buttons = [...(entry.buttons ?? [entry.button]), id];
    bindFeature(entry);
  }

  function addPluginHud(node) {
    if (!(node instanceof Node)) return;
    const viewbar = document.getElementById("viewbar");
    if (viewbar) viewbar.after(node);
    else document.getElementById("viewport")?.appendChild(node);
  }

  ctx.pluginRuntime = createPluginApi({
    call, refresh, say,
    tree: () => ctx.lastTree,
    scene, camera, controls, renderer,
    addRibbon: addPluginRibbon,
    addFeature: addPluginFeature,
    addFeatureButton: addPluginFeatureButton,
    addCombineTools,
    addHud: addPluginHud,
  });
}
