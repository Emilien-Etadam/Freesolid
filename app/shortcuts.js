// Raccourcis clavier personnalisés et infobulles enrichies.
// Le modèle est pur (combinaisons, réservations, stockage) ; l'infobulle
// enrichie est la seule partie DOM.

import { t } from "./i18n.js";

const STORE_KEY = "freesolid.shortcuts";
const MODIFIERS = ["Ctrl", "Alt", "Shift"];
const NAMED = {
  " ": "Space", Spacebar: "Space", Esc: "Escape", Del: "Delete",
};
const WORDS = {
  ctrl: "Ctrl", control: "Ctrl", ctl: "Ctrl", cmd: "Ctrl", alt: "Alt",
  maj: "Shift", shift: "Shift", espace: "Space", space: "Space",
  suppr: "Delete", delete: "Delete", entree: "Enter", "entrée": "Enter",
  enter: "Enter", echap: "Escape", "échap": "Escape", escape: "Escape",
  tab: "Tab", inser: "Insert", insert: "Insert", home: "Home", end: "End",
  fin: "End", debut: "Home", "début": "Home",
};

/** Touches déjà prises par FreeSolid ou par le navigateur. */
export const RESERVED = new Set([
  "F", "Z", "Shift+Z", "Space", "Tab", "Shift+Tab", "Escape", "Enter",
  "Delete", "Backspace", "F2", "F5", "F11", "F12",
  "Ctrl+Z", "Ctrl+Y", "Ctrl+Shift+Z", "Ctrl+N", "Ctrl+F", "Ctrl+A",
  "Ctrl+C", "Ctrl+V", "Ctrl+X", "Ctrl+W", "Ctrl+T", "Ctrl+R", "Ctrl+L",
  "Ctrl+P", "Ctrl+Shift+I", "Ctrl+Shift+R",
  ...[1, 2, 3, 4, 5, 6, 7, 8].map((n) => `Ctrl+${n}`),
]);

function canonical(mods, key) {
  if (!key || MODIFIERS.includes(key)) return null;
  return [...MODIFIERS.filter((m) => mods.has(m)), key].join("+");
}

function keyName(raw) {
  const key = NAMED[raw] ?? raw;
  if (key.length === 1) return key.toUpperCase();
  if (/^F([1-9]|1[0-2])$/.test(key)) return key;
  if (["Space", "Tab", "Escape", "Enter", "Delete", "Backspace", "Insert",
    "Home", "End", "PageUp", "PageDown"].includes(key)) return key;
  if (key.startsWith("Arrow")) return key;
  return null;
}

/** Combinaison d'un appui (« Ctrl+Shift+K »), null pour une touche seule
 *  de modification ou inconnue. */
export function comboOf(event) {
  const mods = new Set();
  if (event.ctrlKey || event.metaKey) mods.add("Ctrl");
  if (event.altKey) mods.add("Alt");
  if (event.shiftKey) mods.add("Shift");
  const key = keyName(String(event.key ?? ""));
  return key ? canonical(mods, key) : null;
}

/** Texte tapé (« ctrl+maj+k », « Alt+E ») → combinaison, null si illisible. */
export function parseCombo(text) {
  const parts = String(text ?? "").split("+").map((p) => p.trim())
    .filter(Boolean);
  if (!parts.length) return null;
  const mods = new Set();
  let key = null;
  for (const [i, part] of parts.entries()) {
    const word = WORDS[part.toLowerCase()];
    if (word && MODIFIERS.includes(word) && i < parts.length - 1) {
      mods.add(word);
      continue;
    }
    if (i !== parts.length - 1) return null;
    key = keyName(word ?? (part.length === 1 ? part : part[0].toUpperCase()
      + part.slice(1)));
  }
  return key ? canonical(mods, key) : null;
}

/** Combinaison à l'affichage (« Maj » en français). */
export function comboLabel(combo) {
  const names = { Shift: t("Maj"), Space: t("Espace"), Escape: t("Échap"),
                  Enter: t("Entrée"), Delete: t("Suppr") };
  return String(combo ?? "").split("+").map((p) => names[p] ?? p).join("+");
}

export function readShortcuts(storage) {
  try {
    const saved = JSON.parse(storage?.getItem(STORE_KEY) ?? "{}");
    if (!saved || typeof saved !== "object" || Array.isArray(saved)) return {};
    return Object.fromEntries(Object.entries(saved)
      .filter(([id, combo]) => typeof id === "string" && typeof combo === "string"
        && parseCombo(combo) === combo && !RESERVED.has(combo)));
  } catch {
    return {};
  }
}

export function writeShortcuts(storage, map) {
  try {
    storage?.setItem(STORE_KEY, JSON.stringify(map));
  } catch { /* stockage refusé : valable pour la session */ }
}

/** Attribue `combo` à la commande `id`. La combinaison quitte la commande
 *  qui l'avait ; une commande n'a qu'un raccourci. Renvoie
 *  { map, error?, replaced? } — `map` inchangée en cas d'erreur. */
export function assignShortcut(map, id, text) {
  const combo = parseCombo(text);
  if (!combo) return { map, error: "Raccourci illisible — exemple : Ctrl+Maj+E" };
  if (RESERVED.has(combo) || combo.startsWith("Arrow")
      || /(^|\+)Arrow/.test(combo)) {
    return { map, error: "Ce raccourci est déjà pris par FreeSolid ou le navigateur" };
  }
  const next = {};
  let replaced = null;
  for (const [other, value] of Object.entries(map ?? {})) {
    if (value === combo && other !== id) {
      replaced = other;
      continue;
    }
    if (other !== id) next[other] = value;
  }
  next[id] = combo;
  return { map: next, replaced };
}

/** Infobulle : nom (avant « — »), détail, touches (celles écrites entre
 *  parenthèses à la fin du nom, sinon le raccourci personnel). */
export function tipParts(title, combo = null) {
  let text = String(title ?? "").trim();
  let keys = combo ? comboLabel(combo) : null;
  const dash = text.indexOf(" — ");
  let name = dash >= 0 ? text.slice(0, dash) : text;
  const detail = dash >= 0 ? text.slice(dash + 3).trim() : "";
  const written = name.match(/\s*\(([^()]+)\)\s*$/);
  if (written) {
    name = name.slice(0, written.index);
    if (!keys) keys = written[1];
  }
  text = name.trim();
  return { name: text, detail, keys };
}

/** Infobulles enrichies sur les barres : nom en gras, détail, touches.
 *  Le `title` natif est mis de côté le temps du survol (la recherche de
 *  commandes le lit). */
export function installRichTips(doc, { selector, shortcutFor, delay = 500 }) {
  const tip = doc.createElement("div");
  tip.id = "rich-tip";
  tip.hidden = true;
  doc.body.appendChild(tip);
  let timer = null;
  let current = null;

  function hide() {
    clearTimeout(timer);
    tip.hidden = true;
    if (current?.dataset.tipTitle != null) {
      current.title = current.dataset.tipTitle;
      delete current.dataset.tipTitle;
    }
    current = null;
  }

  doc.addEventListener("mouseover", (event) => {
    const button = event.target.closest?.(selector);
    if (button === current) return;
    hide();
    if (!button?.title) return;
    current = button;
    button.dataset.tipTitle = button.title;
    button.title = "";
    timer = setTimeout(() => {
      const parts = tipParts(button.dataset.tipTitle, shortcutFor(button.id));
      tip.replaceChildren();
      const head = doc.createElement("strong");
      head.textContent = parts.name;
      tip.appendChild(head);
      if (parts.keys) {
        const keys = doc.createElement("kbd");
        keys.textContent = parts.keys;
        tip.appendChild(keys);
      }
      if (parts.detail) {
        const detail = doc.createElement("p");
        detail.textContent = parts.detail;
        tip.appendChild(detail);
      }
      tip.hidden = false;
      const box = button.getBoundingClientRect();
      const width = tip.offsetWidth;
      const left = Math.min(Math.max(4, box.left), doc.documentElement.clientWidth
        - width - 4);
      tip.style.left = `${left}px`;
      tip.style.top = `${box.bottom + 6}px`;
    }, delay);
  });
  doc.addEventListener("mousedown", hide, true);
  doc.addEventListener("scroll", hide, true);
}
