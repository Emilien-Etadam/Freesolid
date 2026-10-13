// Barre de menus. Le modèle est pur : le DOM ne fait que l'afficher et
// déclencher le bouton déjà câblé (ou une action nommée, s'il n'y a pas
// de bouton). Insertion est lu dans ribbon.json, comme le ruban.

import { t } from "./i18n.js";
import { isButtonId } from "./ribbon.js";

/** Ouvert, survol, fermeture. `null` : aucun menu ouvert. */
export function reduceMenu(openId, event) {
  if (event.type === "toggle") return openId === event.id ? null : event.id;
  if (event.type === "hover") return openId ? event.id : null;
  if (event.type === "close") return null;
  return openId;
}

function item(label, extra) {
  return { label, ...extra };
}

/** Groupes du ruban, dans l'ordre, sans les séparateurs. */
export function insertionItems(ribbon) {
  const tabs = (ribbon?.onglets ?? []).filter((tab) =>
    Array.isArray(tab.groupes) && tab.groupes.some((group) =>
      (group.boutons ?? []).some((button) => button && !button.sep
        && isButtonId(button.id))));
  const items = [];
  for (const tab of tabs) {
    if (items.length) items.push({ sep: true });
    if (tabs.length > 1 && tab.libelle) items.push({ heading: String(tab.libelle) });
    for (const group of tab.groupes) {
      const buttons = (group.boutons ?? []).filter((button) =>
        button && !button.sep && isButtonId(button.id));
      if (!buttons.length) continue;
      if (group.libelle) items.push({ heading: String(group.libelle) });
      for (const button of buttons) {
        items.push(item(String(button.libelle || button.id), { click: button.id }));
      }
    }
  }
  return items;
}

/** Les six menus, libellés français (la traduction se fait à l'affichage). */
export function menuBarModel(ribbon) {
  return [
    { id: "file", label: "Fichier", items: [
      item("Nouveau", { action: "create", shortcut: "Ctrl+N" }),
      item("Accueil", { action: "home" }),
      item("Ouvrir", { click: "btn-open" }),
      item("Enregistrer", { click: "btn-save" }),
      item("Exporter", { click: "btn-export" }),
      item("Mise en plan", { click: "btn-drawing" }),
      item("Capture d'écran", { action: "screenshot" }),
      item("Propriétés…", { action: "properties" }),
      item("Enregistrer comme gabarit…", { action: "save-template" }),
    ] },
    { id: "edit", label: "Édition", items: [
      item("Annuler", { click: "btn-undo", shortcut: "Ctrl+Z" }),
      item("Rétablir", { click: "btn-redo", shortcut: "Ctrl+Y" }),
      item("Reconstruire", { click: "btn-rebuild" }),
      { sep: true },
      item("Copier la fonction", { action: "copy", shortcut: "Ctrl+C" }),
      item("Coller sur la sélection", { action: "paste", shortcut: "Ctrl+V" }),
      { sep: true },
      item("Supprimer", { action: "delete" }),
    ] },
    { id: "view", label: "Affichage", items: [
      item("Face", { click: "view-front", shortcut: "Ctrl+1" }),
      item("Arrière", { view: "view-back", shortcut: "Ctrl+2" }),
      item("Gauche", { view: "view-left", shortcut: "Ctrl+3" }),
      item("Droite", { click: "view-right", shortcut: "Ctrl+4" }),
      item("Dessus", { click: "view-top", shortcut: "Ctrl+5" }),
      item("Dessous", { view: "view-bottom", shortcut: "Ctrl+6" }),
      item("Iso", { click: "view-iso", shortcut: "Ctrl+7" }),
      item("Zoom au mieux", { click: "view-fit", shortcut: "F" }),
      item("Zoom sur la sélection", { click: "view-zoom-sel" }),
      item("Vue précédente", { click: "view-prev", shortcut: "Ctrl+Maj+Z" }),
      { sep: true },
      item("Boîte d'orientation", { action: "orient", shortcut: "Espace" }),
      item("Origine", { action: "origin" }),
    ] },
    { id: "insert", label: "Insertion", items: insertionItems(ribbon) },
    { id: "tools", label: "Outils", items: [
      item("Mesurer", { click: "btn-measure" }),
      item("Évaluer", { click: "btn-evaluate" }),
      item("Équations", { click: "btn-equations" }),
      item("Tableau des configurations…", { action: "config-table" }),
      item("Raccourcis clavier…", { action: "shortcuts" }),
      item("Paramètres", { click: "btn-settings" }),
    ] },
    { id: "help", label: "Aide", items: [
      item("À propos", { click: "btn-settings" }),
      item("Autotest du moteur", { click: "btn-selftest" }),
      item("Signaler un problème", { action: "report" }),
    ] },
  ];
}

function viewButton(doc, view) {
  if (!/^[a-z0-9-]+$/.test(view)) return null;
  return doc.querySelector(`#orient-box [data-view="${view}"]`);
}

/** Affiche le modèle et déclenche les boutons existants. */
export function installMenuBar(doc, model, { onAction } = {}) {
  const root = doc.getElementById("menubar");
  if (!root) return;
  root.replaceChildren();
  let openId = null;
  const tops = [];

  function refreshDisabled() {
    if (!openId) return;
    const panel = root.querySelector(
      `.menu-top[data-menu="${openId}"] .menu-panel`);
    const menu = model.find((entry) => entry.id === openId);
    if (!panel || !menu) return;
    const buttons = panel.querySelectorAll("[role=menuitem]");
    let index = 0;
    for (const entry of menu.items) {
      if (entry.sep || entry.heading) continue;
      const button = buttons[index++];
      if (!button) break;
      if (entry.click) {
        const target = doc.getElementById(entry.click);
        button.disabled = !target || target.disabled;
      } else if (entry.view) {
        button.disabled = !viewButton(doc, entry.view);
      }
    }
  }

  function setOpen(id) {
    openId = id;
    for (const top of tops) {
      const on = top.dataset.menu === id;
      top.classList.toggle("open", on);
      top.setAttribute("aria-expanded", on ? "true" : "false");
      const panel = top.querySelector(".menu-panel");
      if (panel) panel.hidden = !on;
    }
    refreshDisabled();
  }

  function apply(next) {
    const id = reduceMenu(openId, next);
    if (id !== openId) setOpen(id);
  }

  for (const menu of model) {
    const top = doc.createElement("button");
    top.type = "button";
    top.className = "menu-top";
    top.dataset.menu = menu.id;
    top.textContent = t(menu.label);
    top.setAttribute("aria-haspopup", "true");
    top.setAttribute("aria-expanded", "false");
    const panel = doc.createElement("div");
    panel.className = "menu-panel";
    panel.hidden = true;
    panel.setAttribute("role", "menu");
    for (const entry of menu.items) {
      if (entry.sep) {
        const sep = doc.createElement("div");
        sep.className = "menu-sep";
        panel.appendChild(sep);
        continue;
      }
      if (entry.heading) {
        const heading = doc.createElement("div");
        heading.className = "menu-heading";
        heading.textContent = t(entry.heading);
        panel.appendChild(heading);
        continue;
      }
      const button = doc.createElement("button");
      button.type = "button";
      button.setAttribute("role", "menuitem");
      const label = doc.createElement("span");
      label.textContent = t(entry.label);
      button.appendChild(label);
      if (entry.shortcut) {
        const shortcut = doc.createElement("span");
        shortcut.className = "menu-shortcut";
        shortcut.textContent = t(entry.shortcut);
        button.appendChild(shortcut);
      }
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        if (button.disabled) return;
        setOpen(null);
        if (entry.click) doc.getElementById(entry.click)?.click();
        else if (entry.view) viewButton(doc, entry.view)?.click();
        else if (entry.action) onAction?.(entry.action);
      });
      panel.appendChild(button);
    }
    top.addEventListener("click", (event) => {
      event.stopPropagation();
      apply({ type: "toggle", id: menu.id });
    });
    top.addEventListener("mouseenter", () => {
      apply({ type: "hover", id: menu.id });
    });
    top.appendChild(panel);
    root.appendChild(top);
    tops.push(top);
  }

  doc.addEventListener("click", () => apply({ type: "close" }));
  doc.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && openId) {
      apply({ type: "close" });
      event.preventDefault();
      event.stopPropagation();
    }
  }, true);
}
