// Écran d'accueil et dialogue Nouveau. Les récents et l'astuce du jour
// sont purs : le DOM ne fait que les afficher.

import { t } from "./i18n.js";

export const RECENT_KEY = "freesolid.recent";
export const MAX_RECENT = 8;

export const TIPS = [
  "S ouvre les raccourcis sous le curseur.",
  "Ctrl+1 à Ctrl+7 changent de vue. F cadre la pièce.",
  "La molette zoome, le bouton du milieu tourne la vue.",
  "Échap ferme le menu, le dialogue ou l'outil en cours.",
  "Ctrl+N crée une pièce ou un assemblage.",
];

export function readRecent(storage) {
  try {
    const parsed = JSON.parse(storage?.getItem(RECENT_KEY) || "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item) => typeof item === "string" && item).slice(0, MAX_RECENT);
  } catch {
    return [];
  }
}

/** Le chemin ouvert ou enregistré passe en tête. Les doublons sortent. */
export function rememberRecent(storage, path) {
  const clean = String(path || "").trim();
  if (!clean) return readRecent(storage);
  const next = [clean, ...readRecent(storage).filter((item) => item !== clean)]
    .slice(0, MAX_RECENT);
  try {
    storage?.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    // stockage indisponible : la liste reste en mémoire le temps du retour.
  }
  return next;
}

/** Une astuce par jour, stable pour une même date. */
export function tipForDay(date, tips = TIPS) {
  const list = tips.length ? tips : TIPS;
  const start = Date.UTC(date.getFullYear(), 0, 0);
  const day = Math.floor((date.getTime() - start) / 86400000);
  const index = ((day % list.length) + list.length) % list.length;
  return list[index];
}

export function fileTitle(path) {
  const text = String(path || "");
  const cut = Math.max(text.lastIndexOf("/"), text.lastIndexOf("\\"));
  return cut >= 0 ? text.slice(cut + 1) : text;
}

/** Accueil et dialogue Nouveau. `hasDocument` décide si Échap peut fermer. */
export function installWelcome(doc, {
  storage, onPart, onAssembly, onOpen, onRecent, hasDocument,
} = {}) {
  const welcome = doc.getElementById("welcome");
  const chooser = doc.getElementById("new-dialog");
  const recent = doc.getElementById("welcome-recent");
  const tip = doc.getElementById("welcome-tip");

  function renderRecent() {
    if (!recent) return;
    recent.replaceChildren();
    const items = readRecent(storage);
    if (!items.length) {
      const empty = doc.createElement("p");
      empty.className = "welcome-empty";
      empty.textContent = t("Aucun fichier récent");
      recent.appendChild(empty);
      return;
    }
    for (const path of items) {
      const button = doc.createElement("button");
      button.type = "button";
      button.textContent = fileTitle(path);
      button.title = path;
      button.addEventListener("click", () => onRecent?.(path));
      recent.appendChild(button);
    }
  }

  function showWelcome() {
    if (!welcome) return;
    if (tip) tip.textContent = t(tipForDay(new Date()));
    renderRecent();
    welcome.hidden = false;
  }

  function hideWelcome() {
    if (welcome) welcome.hidden = true;
  }

  function showNew() {
    if (chooser) chooser.hidden = false;
  }

  function hideNew() {
    if (chooser) chooser.hidden = true;
  }

  welcome?.querySelector("[data-welcome='part']")
    ?.addEventListener("click", () => onPart?.());
  welcome?.querySelector("[data-welcome='assembly']")
    ?.addEventListener("click", () => onAssembly?.());
  welcome?.querySelector("[data-welcome='open']")
    ?.addEventListener("click", () => onOpen?.());
  chooser?.querySelector("[data-new='part']")
    ?.addEventListener("click", () => { hideNew(); onPart?.(); });
  chooser?.querySelector("[data-new='assembly']")
    ?.addEventListener("click", () => { hideNew(); onAssembly?.(); });
  chooser?.querySelector("[data-new='cancel']")
    ?.addEventListener("click", hideNew);

  doc.getElementById("btn-home")?.addEventListener("click", showWelcome);

  doc.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && chooser && !chooser.hidden) {
      hideNew();
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }
    if (event.key === "Escape" && welcome && !welcome.hidden && hasDocument?.()) {
      hideWelcome();
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }
    if ((event.ctrlKey || event.metaKey) && (event.key === "n" || event.key === "N")) {
      if (/^(INPUT|SELECT|TEXTAREA)$/.test(event.target?.tagName)) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      showNew();
    }
  }, true);

  return { showWelcome, hideWelcome, showNew, hideNew, renderRecent };
}
