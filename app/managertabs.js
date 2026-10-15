// Le gestionnaire à onglets, en tête du volet gauche : l'arbre de
// création, le panneau de la commande en cours (Propriétés), les
// configurations, l'affichage (style, corps visibles). L'onglet Propriétés
// s'allume tout seul quand une commande ouvre son panneau ; l'onglet Arbre
// montre alors l'arbre à la place du panneau, qui reste ouvert.

import { t } from "./i18n.js";

const ICONS = {
  tree: '<path d="M3 3h5M5 3v12M5 8h5M5 13h5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><rect x="10.5" y="6.5" width="5" height="3" rx="1" fill="none" stroke="currentColor" stroke-width="1.4"/><rect x="10.5" y="11.5" width="5" height="3" rx="1" fill="none" stroke="currentColor" stroke-width="1.4"/>',
  props: '<rect x="3" y="2.5" width="12" height="13" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M6 6.5h6M6 9.5h6M6 12.5h4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
  configs: '<rect x="2.5" y="5" width="8" height="8" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.4"/><rect x="7.5" y="2.5" width="8" height="8" rx="1.5" fill="var(--panel)" stroke="currentColor" stroke-width="1.4"/>',
  display: '<path d="M1.5 9s2.8-5 7.5-5 7.5 5 7.5 5-2.8 5-7.5 5-7.5-5-7.5-5z" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="9" cy="9" r="2.2" fill="none" stroke="currentColor" stroke-width="1.4"/>',
};

export const TABS = [
  ["tree", "Arbre de création"],
  ["props", "Propriétés"],
  ["configs", "Configurations"],
  ["display", "Affichage"],
];

/** L'onglet à montrer : un panneau qui s'ouvre prend la main, une
 *  fermeture rend l'arbre ; sinon le choix tient. */
export function nextTab(current, { panelOpen, panelWasOpen }) {
  if (panelOpen && !panelWasOpen) return "props";
  if (!panelOpen && current === "props") return "tree";
  return current;
}

const STYLES = [
  ["shaded-edges", "Ombré + arêtes"],
  ["shaded", "Ombré seul"],
  ["wireframe", "Filaire"],
  ["hidden", "Lignes cachées estompées"],
];

export function installManagerTabs(ctx) {
  const aside = document.querySelector("aside");
  if (!aside) return null;
  const strip = document.createElement("div");
  strip.id = "manager-tabs";
  strip.setAttribute("role", "tablist");
  strip.setAttribute("aria-label", t("Gestionnaire"));
  const buttons = {};
  for (const [key, label] of TABS) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.setAttribute("role", "tab");
    btn.dataset.mgr = key;
    btn.title = t(label);
    btn.setAttribute("aria-label", t(label));
    btn.innerHTML = `<svg viewBox="0 0 18 18" width="18" height="18" aria-hidden="true">${ICONS[key]}</svg>`;
    btn.addEventListener("click", () => select(key));
    strip.appendChild(btn);
    buttons[key] = btn;
  }
  aside.prepend(strip);
  const configsEl = document.createElement("div");
  configsEl.id = "mgr-configs";
  configsEl.className = "mgr-pane";
  const displayEl = document.createElement("div");
  displayEl.id = "mgr-display";
  displayEl.className = "mgr-pane";
  aside.append(configsEl, displayEl);

  let current = "tree";
  let panelWasOpen = false;

  function placeTree() {
    // Arbre demandé pendant une commande : il revient dans le volet, le
    // panneau reste ouvert derrière ; sinon l'arbre volant le reprend.
    const tree = document.getElementById("tree");
    const panelEl = document.getElementById("panel");
    if (ctx.panel?.active && current === "tree") {
      if (tree && tree.parentElement !== aside) aside.insertBefore(tree, panelEl);
      const flyout = document.getElementById("tree-flyout");
      if (flyout) flyout.hidden = true;
    } else {
      ctx.updateTreeFlyout?.();
    }
  }

  function apply() {
    aside.dataset.mgr = current;
    for (const [key, btn] of Object.entries(buttons)) {
      const on = key === current;
      btn.classList.toggle("on", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    }
    buttons.props.disabled = !ctx.panel?.active;
    placeTree();
    if (current === "configs") renderConfigs();
    if (current === "display") renderDisplay();
  }

  function select(key) {
    if (key === "props" && !ctx.panel?.active) return;
    current = key;
    apply();
  }

  function sync() {
    const panelOpen = !!ctx.panel?.active;
    current = nextTab(current, { panelOpen, panelWasOpen });
    panelWasOpen = panelOpen;
    apply();
  }

  function heading(text) {
    const h = document.createElement("h2");
    h.textContent = t(text);
    return h;
  }

  function actionButton(label, onClick, title) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "mgr-action";
    b.textContent = t(label);
    if (title) b.title = t(title);
    b.addEventListener("click", onClick);
    return b;
  }

  function renderConfigs() {
    const tree = ctx.lastTree;
    const configs = tree?.configurations ?? { active: null, names: [] };
    configsEl.replaceChildren(heading("Configurations"));
    const list = document.createElement("ul");
    list.className = "mgr-list";
    if (!configs.names?.length) {
      const empty = document.createElement("li");
      empty.className = "mgr-empty";
      empty.textContent = t("Une seule variante pour l'instant : ajoutez une configuration pour en créer d'autres.");
      list.appendChild(empty);
    }
    for (const name of configs.names ?? []) {
      const item = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = name === configs.active ? "mgr-item on" : "mgr-item";
      btn.textContent = name;
      btn.title = name === configs.active ? t("Configuration active")
        : t("Activer cette configuration");
      btn.addEventListener("click", () => {
        if (name !== configs.active) {
          ctx.refresh(ctx.call("activate_configuration", { name }));
        }
      });
      item.appendChild(btn);
      list.appendChild(item);
    }
    const actions = document.createElement("div");
    actions.className = "mgr-actions";
    actions.append(
      actionButton("Ajouter…", async () => {
        const name = await ctx.promptText?.(t("Nom de la configuration"), "");
        if (name) ctx.refresh(ctx.call("add_configuration", { name }));
      }, "Nouvelle configuration, relevée sur l'état actuel"),
      actionButton("Tableau…", () => ctx.openConfigTable?.(),
        "Les cotes de chaque configuration, côte à côte"),
    );
    configsEl.append(list, actions);
  }

  function renderDisplay() {
    const tree = ctx.lastTree;
    displayEl.replaceChildren(heading("Style d'affichage"));
    const styles = document.createElement("div");
    styles.className = "mgr-actions";
    for (const [style, label] of STYLES) {
      styles.appendChild(actionButton(label, () => {
        document.querySelector(`#style-menu [data-style="${style}"]`)?.click();
      }));
    }
    displayEl.append(styles, heading("Corps"));
    const list = document.createElement("ul");
    list.className = "mgr-list";
    const rows = [
      ...(tree?.bodies ?? []).filter((b) => b.has_solid !== false)
        .map((b) => ({ name: b.name, label: b.label, hidden: b.hidden, color: b.color })),
      ...(tree?.surfaces ?? []).map((s) => ({ name: s.name, label: s.label,
                                              hidden: s.hidden, surface: true })),
    ];
    if (!rows.length) {
      const empty = document.createElement("li");
      empty.className = "mgr-empty";
      empty.textContent = t("— aucun corps —");
      list.appendChild(empty);
    }
    for (const row of rows) {
      const item = document.createElement("li");
      item.className = row.hidden ? "mgr-row hidden-object" : "mgr-row";
      const eye = document.createElement("button");
      eye.type = "button";
      eye.className = "mgr-eye";
      eye.textContent = row.hidden ? "◌" : "●";
      const label = row.hidden ? t("Afficher {n}", { n: row.label })
        : t("Masquer {n}", { n: row.label });
      eye.title = label;
      eye.setAttribute("aria-label", label);
      eye.addEventListener("click", () => {
        ctx.refresh(ctx.call("set_hidden", { objects: [row.name], hidden: !row.hidden }));
      });
      const swatch = document.createElement("span");
      swatch.className = "mgr-swatch";
      if (row.color) swatch.style.background = row.color;
      if (row.surface) swatch.classList.add("surface");
      const text = document.createElement("span");
      text.textContent = row.label;
      item.append(eye, swatch, text);
      list.appendChild(item);
    }
    displayEl.appendChild(list);
  }

  ctx.treeHooks?.push(() => {
    if (current === "configs") renderConfigs();
    if (current === "display") renderDisplay();
  });
  apply();
  return { sync, select, get current() { return current; } };
}
