// Boîte de raccourcis sous le curseur (touche S). Le modèle est pur :
// hors esquisse, une poignée de fonctions ; en esquisse, les outils de
// tracé et la cotation. La recherche parcourt tout le ruban et ces outils.

import { t } from "./i18n.js";
import { isButtonId } from "./ribbon.js";

/** Hors esquisse, dans l'ordre d'apparition. */
export const PART_SHORTCUTS = [
  "btn-sketch", "btn-pad", "btn-pocket", "btn-fillet", "btn-chamfer",
  "btn-linpattern", "btn-polpattern", "btn-repeat-variable",
];

/** Outils de tracé et cotation, pas les relations. */
export const SKETCH_TOOLS = [
  "select", "line", "rect", "rectc", "circle", "spline", "ellipse",
  "arc", "arc3", "slot", "polygon", "dim",
];

/** Libellé court d'un titre « Nom (raccourci) — détail ». */
export function commandLabel(title, fallback = "") {
  const text = String(title || "").split(/[—(]/)[0].trim();
  return text || fallback;
}

/** Commandes du ruban, libellé français source. */
export function ribbonCommands(ribbon) {
  const commands = [];
  for (const tab of ribbon?.onglets ?? []) {
    for (const group of tab.groupes ?? []) {
      for (const button of group.boutons ?? []) {
        if (!button || button.sep || !button.libelle) continue;
        if (!isButtonId(button.id)) continue;
        commands.push({
          kind: "button", id: button.id, label: String(button.libelle),
        });
      }
    }
  }
  return commands;
}

function dedupe(commands) {
  const seen = new Set();
  const out = [];
  for (const command of commands) {
    const key = command.kind + ":" + (command.id || command.tool);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(command);
  }
  return out;
}

/**
 * Ce que la boîte montre. `translate` est `t` : la recherche porte sur
 * le libellé affiché, donc « fillet » en anglais.
 */
export function shortcutOffers({
  sketch, query, commands, sketchTools, translate = (text) => text,
}) {
  const q = String(query || "").trim().toLowerCase();
  if (q) {
    return dedupe([...sketchTools, ...commands]).filter((command) =>
      String(translate(command.label)).toLowerCase().includes(q));
  }
  if (sketch) return sketchTools;
  const byId = new Map(commands.map((command) => [command.id, command]));
  return PART_SHORTCUTS.map((id) => byId.get(id)).filter(Boolean);
}

/** Coin supérieur gauche, juste sous le pointeur, sans sortir de l'écran. */
export function placeNearPointer(point, size, bounds) {
  const margin = 8;
  const width = Math.max(0, bounds.width);
  const height = Math.max(0, bounds.height);
  const x = Number.isFinite(point?.x) ? point.x : width / 2;
  const y = (Number.isFinite(point?.y) ? point.y : height / 2) + 14;
  const left = Math.min(Math.max(x, margin),
    Math.max(margin, width - size.width - margin));
  const top = Math.min(Math.max(y, margin),
    Math.max(margin, height - size.height - margin));
  return { left, top };
}

function readSketchTools(doc) {
  const allowed = new Set(SKETCH_TOOLS);
  const tools = [];
  for (const button of doc.querySelectorAll("#sketchbar button[data-tool]")) {
    const tool = button.dataset.tool;
    if (!allowed.has(tool)) continue;
    tools.push({
      kind: "tool",
      tool,
      label: button.dataset.label
        || commandLabel(button.getAttribute("title"), tool),
    });
  }
  return tools;
}

/** Affiche la boîte, l'ouvre avec S, la ferme avec Échap ou un clic à côté. */
export function installShortcutBar(doc, { ribbon, sketchActive, pointer }) {
  const box = doc.getElementById("shortcut-box");
  const list = doc.getElementById("shortcut-list");
  const search = doc.getElementById("shortcut-search");
  if (!box || !list || !search) return;
  const commands = ribbonCommands(ribbon);
  let at = null;

  function render() {
    const offers = shortcutOffers({
      sketch: Boolean(sketchActive?.()),
      query: search.value,
      commands,
      sketchTools: readSketchTools(doc),
      translate: t,
    });
    list.replaceChildren();
    if (!offers.length) {
      const empty = doc.createElement("p");
      empty.className = "shortcut-empty";
      empty.textContent = t("Aucune commande");
      list.appendChild(empty);
      return;
    }
    for (const offer of offers) {
      const button = doc.createElement("button");
      button.type = "button";
      const source = offer.kind === "tool"
        ? doc.querySelector(`#sketchbar button[data-tool="${offer.tool}"]`)
        : doc.getElementById(offer.id);
      const icon = source?.querySelector("img");
      if (icon) {
        const img = doc.createElement("img");
        img.src = icon.src;
        img.alt = "";
        button.appendChild(img);
      }
      const label = doc.createElement("span");
      label.textContent = t(offer.label);
      button.appendChild(label);
      button.disabled = Boolean(source?.disabled);
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        close();
        source?.click();
      });
      list.appendChild(button);
    }
  }

  function place() {
    const point = at || pointer?.();
    const size = box.getBoundingClientRect();
    const pos = placeNearPointer(point, size, {
      width: doc.defaultView?.innerWidth ?? 0,
      height: doc.defaultView?.innerHeight ?? 0,
    });
    box.style.left = `${pos.left}px`;
    box.style.top = `${pos.top}px`;
  }

  function open() {
    search.value = "";
    box.hidden = false;
    render();
    place();
    search.focus();
  }

  function close() {
    box.hidden = true;
    search.value = "";
  }

  function toggle() {
    if (box.hidden) open();
    else close();
  }

  search.addEventListener("input", render);
  search.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      close();
    }
  });
  doc.addEventListener("pointermove", (event) => {
    at = { x: event.clientX, y: event.clientY };
  });
  doc.addEventListener("click", (event) => {
    if (!box.hidden && !box.contains(event.target)) close();
  });
  doc.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !box.hidden) {
      close();
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }
    if (event.key !== "s" && event.key !== "S") return;
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(event.target?.tagName)) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    toggle();
  }, true);

  return { open, close, toggle };
}
