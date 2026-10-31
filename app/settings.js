// Panneau Paramètres, rangé comme les options des modeleurs courants : des
// onglets (Options du système : gardées par le navigateur, pour tous les
// documents), l'arbre des pages à gauche, la page choisie à droite, une
// recherche qui filtre l'arbre et marque les options trouvées. Les
// changements attendent OK ; Annuler (ou Échap) les oublie ; Réinitialiser
// remet les valeurs par défaut de la page ou de tout l'onglet, à valider.
//
// Tout ce qui est décision est une fonction pure et testée (pages, champs,
// recherche, brouillon, lignes d'information, langue, pont Tauri) ; le DOM
// n'est touché que dans createSettingsDialog.

import { t } from "./i18n.js";
import { DISPLAY_STYLES } from "./display.js";
import { ANGLE_STEP, SNAP_KINDS } from "./sketchsnap.js";

export const REPO_URL = "https://github.com/Emilien-Etadam/Freesolid";
const RELEASES_URL = REPO_URL + "/releases";
export const ISSUES_URL = REPO_URL + "/issues";
const LICENSE_URL = REPO_URL + "/blob/main/LICENSE";

export const LANG_KEY = "freesolid.lang";
const LANGS = [["fr", "Français"], ["en", "English"]];

/** « fr-FR », « en_US », « de »… → langue livrée, français par défaut. */
export function detectLang(navigatorLang) {
  const code = String(navigatorLang || "").toLowerCase().slice(0, 2);
  return LANGS.some(([id]) => id === code) ? code : "fr";
}

export function readLang(storage, navigatorLang) {
  try {
    const stored = storage?.getItem(LANG_KEY);
    if (LANGS.some(([id]) => id === stored)) return stored;
  } catch {
    // stockage indisponible : la langue du navigateur fait foi.
  }
  return detectLang(navigatorLang);
}

export function writeLang(storage, lang) {
  if (!LANGS.some(([id]) => id === lang)) return false;
  try {
    storage?.setItem(LANG_KEY, lang);
    return true;
  } catch {
    return false;
  }
}

export const THEME_KEY = "freesolid.theme";
/** Thèmes proposés : id, libellé (traduit à l'affichage). */
const THEMES = [["dark", "Sombre"], ["light", "Clair"], ["system", "Selon le système"]];

/** Le thème choisi ; clair (« Atelier ») par défaut. */
export function readTheme(storage) {
  try {
    const stored = storage?.getItem(THEME_KEY);
    if (THEMES.some(([id]) => id === stored)) return stored;
  } catch {
    // stockage indisponible : thème par défaut.
  }
  return "light";
}

export function writeTheme(storage, theme) {
  if (!THEMES.some(([id]) => id === theme)) return false;
  try {
    storage?.setItem(THEME_KEY, theme);
    return true;
  } catch {
    return false;
  }
}

/** « system » suit le réglage du système ; sinon le choix tel quel. Le
 *  même calcul tourne en tête d'index.html, avant que la scène ne lise
 *  ses couleurs. */
export function resolveTheme(theme, prefersLight) {
  if (theme === "system") return prefersLight ? "light" : "dark";
  return theme === "light" ? "light" : "dark";
}

/**
 * Pont vers l'application de bureau, ou null dans un navigateur.
 * `win.__TAURI__` n'existe que dans la fenêtre Tauri (API globale).
 */
export function desktopBridge(win) {
  const T = win?.__TAURI__;
  if (!T?.core?.invoke) return null;
  return {
    appVersion: () => T.app?.getVersion ? T.app.getVersion() : Promise.resolve(null),
    checkUpdate: () => T.updater?.check
      ? T.updater.check()
      : Promise.reject(new Error("updater indisponible")),
    relaunch: () => T.process?.relaunch
      ? T.process.relaunch()
      : Promise.reject(new Error("relance indisponible")),
    openUrl: (url) => T.opener?.openUrl
      ? T.opener.openUrl(url)
      : Promise.reject(new Error("ouverture indisponible")),
    engineLogPath: () => T.core.invoke("engine_log_path"),
  };
}

/**
 * Lignes « libellé → valeur » du panneau, à partir du `ping` du moteur.
 * `ping` peut être null (moteur injoignable) : les lignes le disent.
 */
export function infoRows(ping, { appVersion = null, engineUrl = "", logPath = "" } = {}) {
  const rows = [];
  const version = appVersion || ping?.freesolid || t("inconnue");
  rows.push(["FreeSolid", version]);
  if (!ping) {
    rows.push([t("Moteur"), t("injoignable")]);
  } else {
    const ref = ping.freecad_reference;
    const freecad = ping.freecad || t("inconnue");
    rows.push(["FreeCAD", ref && ref !== freecad
      ? `${freecad} (${t("référence {ref}", { ref })})`
      : freecad]);
    if (ping.freecadcmd) rows.push(["freecadcmd", ping.freecadcmd]);
  }
  if (engineUrl) rows.push([t("Adresse du moteur"), engineUrl]);
  if (logPath) rows.push([t("Journal du moteur"), logPath]);
  return rows;
}

/** Texte d'état de la recherche de mise à jour. */
export function updateStatus(kind, detail = "") {
  switch (kind) {
    case "checking": return t("Recherche en cours…");
    case "none": return t("FreeSolid est à jour.");
    case "available": return t("Version {v} disponible.", { v: detail });
    case "downloading": return detail ? t("Téléchargement… {p}", { p: detail }) : t("Téléchargement…");
    case "installed": return t("Mise à jour installée, relance…");
    case "error": return t("Mise à jour impossible : {e}", { e: detail });
    case "browser": return t("Les mises à jour automatiques existent dans "
      + "l'application de bureau. Dans le navigateur : git pull.");
    default: return "";
  }
}

function esc(text) {
  return String(text).replace(/[&<>"]/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;" }[c]));
}

// ---------- pages et champs ----------

/** Les onglets du panneau : id, libellé. Les options du système valent
 *  pour toute session ; les propriétés du document sont gardées dans le
 *  fichier ouvert. */
export const SETTINGS_TABS = [
  ["system", "Options du système"],
  ["document", "Propriétés du document"],
];

/** Les pages, dans l'ordre de l'arbre ; `parent` en fait une sous-page. */
export const SETTINGS_PAGES = [
  { id: "general", tab: "system", label: "Général" },
  { id: "colors", tab: "system", label: "Couleurs" },
  { id: "sketch", tab: "system", label: "Esquisse" },
  { id: "snaps", tab: "system", label: "Relations et accrochages", parent: "sketch" },
  { id: "display", tab: "system", label: "Affichage" },
  { id: "selection", tab: "system", label: "Sélection" },
  { id: "tree", tab: "system", label: "Arbre de création" },
  { id: "view", tab: "system", label: "Vue" },
  { id: "about", tab: "system", label: "À propos" },
  { id: "units", tab: "document", label: "Unités" },
  { id: "grid", tab: "document", label: "Grille" },
  { id: "quality", tab: "document", label: "Qualité d'image" },
];

/** Les choix de la qualité d'image : du plus rapide au plus fin. */
const QUALITY_LABELS = [
  ["coarse", "Grossière"], ["normal", "Normale"], ["fine", "Fine"],
  ["finest", "Très fine"],
];

const STYLE_LABELS = {
  "shaded-edges": "Ombré + arêtes", shaded: "Ombré seul",
  wireframe: "Filaire", hidden: "Lignes cachées estompées",
};

/** Un champ pris dans un réglage en objet (`stores[name]` : read/apply). */
function inObject(name, key) {
  return {
    store: name,
    get: (stores) => stores[name]?.read()?.[key],
    set: (stores, value) => stores[name]?.apply({ ...stores[name].read(), [key]: value }),
  };
}

/** Un réglage simple (`stores[name]` : read/apply). */
function whole(name) {
  return {
    store: name,
    get: (stores) => stores[name]?.read(),
    set: (stores, value) => stores[name]?.apply(value),
  };
}

/**
 * Les champs des pages, dans leur ordre d'affichage. Un champ : `id`,
 * `page`, `group` (le cadre qui le contient), `kind` (check, radio,
 * select, number), `label`, `default`, `store` (le réglage qu'il lit),
 * `get`/`set` sur les réglages, et
 * selon sa sorte `options` ([valeur, libellé]), `name` (d'un groupe de
 * boutons radio), `min`/`max`, `note`,
 * `reload` (la page se recharge à la validation), `enabledBy` (l'id du
 * champ qui l'active, ou les ids de ceux qui doivent l'être tous).
 * `navigatorLang` donne la langue par défaut.
 */
export function settingsFields(navigatorLang = "") {
  const snapKinds = SNAP_KINDS.map((k) => ({
    id: "snaps.kind." + k.key, page: "snaps", group: "Accrocher à", kind: "check",
    label: k.label, default: true, enabledBy: "snaps.enabled", store: "sketchSnaps",
    get: (stores) => !stores.sketchSnaps.read().off.includes(k.key),
    set: (stores, on) => {
      const snaps = stores.sketchSnaps.read();
      const off = snaps.off.filter((key) => key !== k.key);
      stores.sketchSnaps.apply({ ...snaps, off: on ? off : [...off, k.key] });
    },
  }));
  const check = (id, page, group, label, fallback, access) => (
    { id, page, group, kind: "check", label, default: fallback, ...access });
  const docNumber = (id, page, group, label, key, fallback, range) => ({
    id, page, group, kind: "number", label, default: fallback, ...range,
    ...inObject("docOptions", key) });
  return [
    { id: "lang", page: "general", group: "Interface", kind: "select",
      label: "Langue", options: LANGS, translate: false,
      default: detectLang(navigatorLang), reload: true, ...whole("lang") },
    { id: "ribbonLabels", name: "ribbon-labels", page: "general", group: "Interface",
      kind: "radio", label: "Libellés du ruban", default: "icons-and-text",
      options: [["icons-and-text", "Icônes et texte"], ["icons-only", "Icônes seules"]],
      ...whole("ribbonLabels") },
    { id: "theme", page: "colors", group: "Thème", kind: "select",
      label: "Thème", options: THEMES, default: "light", reload: true,
      ...whole("theme") },
    check("sketch.normalView", "sketch", "À l'ouverture",
      "Tourner la vue face au plan de l'esquisse", true,
      inObject("sketchPrefs", "normalView")),
    check("sketch.showRelations", "sketch", "Affichage",
      "Afficher les symboles de relation", true,
      inObject("sketchPrefs", "showRelations")),
    check("sketch.showDims", "sketch", "Affichage", "Afficher les cotes", true,
      inObject("sketchPrefs", "showDims")),
    check("sketch.showComb", "sketch", "Affichage",
      "Afficher le peigne de courbure des splines", false,
      inObject("sketchPrefs", "showComb")),
    check("snaps.enabled", "snaps", "Accrochages", "Accrocher pendant le tracé",
      true, inObject("sketchSnaps", "enabled")),
    ...snapKinds,
    { id: "snaps.angleStep", page: "snaps", group: "Accrocher à", kind: "number",
      label: "Valeur du pas", min: 1, max: 90, default: ANGLE_STEP,
      note: "degrés, depuis l'axe X ou la ligne précédente",
      enabledBy: ["snaps.enabled", "snaps.kind.angle"],
      ...inObject("sketchSnaps", "angleStep") },
    check("sketch.gridSnap", "snaps", "Grille", "Accrocher à la grille", false,
      inObject("sketchPrefs", "gridSnap")),
    { id: "display.style", page: "display", group: "Style", kind: "select",
      label: "Style d'affichage", default: "shaded-edges",
      options: DISPLAY_STYLES.map((style) => [style, STYLE_LABELS[style]]),
      ...inObject("display", "style") },
    check("display.perspective", "display", "Style", "Perspective", false,
      inObject("display", "perspective")),
    check("display.planes", "display", "Montrer", "Plans de référence", false,
      inObject("display", "planes")),
    check("display.origin", "display", "Montrer", "Origine", false,
      inObject("display", "origin")),
    check("display.sketches", "display", "Montrer", "Esquisses", true,
      inObject("display", "sketches")),
    check("display.edges", "display", "Montrer", "Aperçu des arêtes", true,
      inObject("display", "edges")),
    ...[["faces", "Faces"], ["edges", "Arêtes"], ["sketches", "Esquisses"],
      ["surfaces", "Surfaces et courbes"]].map(([key, label]) => ({
      ...check("select." + key, "selection", "Sélectionnables", label, true,
        inObject("selectFilter", key)),
      get: (stores) => stores.selectFilter.read()?.[key] !== false,
    })),
    check("tree.flat", "tree", "Arbre", "Arbre à plat", false, whole("flatTree")),
    check("view.reverseWheel", "view", "Molette", "Inverser le sens du zoom", false,
      whole("reverseWheel")),
    check("view.zoomToCursor", "view", "Molette", "Zoomer vers le curseur", true,
      whole("zoomToCursor")),
    docNumber("doc.lengthDecimals", "units", "Décimales", "Longueurs",
      "length_decimals", 2, { min: 0, max: 6, note: "dans les cotes et les lectures" }),
    docNumber("doc.angleDecimals", "units", "Décimales", "Angles",
      "angle_decimals", 1, { min: 0, max: 4 }),
    check("doc.gridFixed", "grid", "Esquisse", "Pas de grille fixe", false,
      inObject("docOptions", "grid_fixed")),
    docNumber("doc.gridStep", "grid", "Esquisse", "Pas de la grille", "grid_step",
      10, { min: 0.01, max: 1000, decimals: 2, enabledBy: "doc.gridFixed",
        note: "mm, pour l'accrochage à la grille et les longueurs avec Maj ; sinon le pas suit le zoom" }),
    { id: "doc.quality", page: "quality", group: "Facettes", kind: "select",
      label: "Qualité d'image", default: "normal", options: QUALITY_LABELS,
      note: "plus fine : plus lente à afficher",
      ...inObject("docOptions", "quality") },
  ];
}

/** Le texte où l'on cherche : minuscules, sans accents. */
export function searchText(text) {
  return String(text ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

/**
 * Ce que la recherche trouve : `fields`, les ids des champs dont le
 * libellé, le cadre ou un choix contient tous les mots de `query` ;
 * `pages`, les pages qui en ont un (ou dont le nom répond), avec leur
 * parent. `label` traduit un texte (t). Une recherche vide : null.
 */
export function searchSettings(query, fields, pages, label = (s) => s) {
  const words = searchText(query).split(/\s+/).filter(Boolean);
  if (!words.length) return null;
  const hit = (...texts) => {
    const haystack = searchText(texts.join(" "));
    return words.every((word) => haystack.includes(word));
  };
  const found = new Set(fields.filter((field) => hit(label(field.label),
    label(field.group), ...(field.options ?? []).map(([, name]) =>
      field.translate === false ? name : label(name)))).map((f) => f.id));
  const pageIds = new Set();
  for (const page of pages) {
    if (hit(label(page.label))
        || fields.some((f) => f.page === page.id && found.has(f.id))) {
      pageIds.add(page.id);
      if (page.parent) pageIds.add(page.parent);
    }
  }
  return { fields: found, pages: pageIds };
}

/** Les valeurs actuelles des champs, par id. */
export function readValues(fields, stores) {
  return Object.fromEntries(fields.map((f) => [f.id, f.get(stores)]));
}

/** Les champs dont le brouillon diffère de la valeur actuelle. */
export function changedFields(fields, stores, draft) {
  return fields.filter((f) => f.id in draft && draft[f.id] !== f.get(stores));
}

/** Le brouillon remis aux valeurs par défaut des champs de `pageIds`. */
export function resetDraft(fields, draft, pageIds) {
  const next = { ...draft };
  for (const f of fields) {
    if (pageIds.includes(f.page)) next[f.id] = f.default;
  }
  return next;
}

/** Une saisie de nombre gardée dans ses bornes, entière ou arrondie à
 *  `field.decimals` ; la virgule vaut le point ; illisible, la valeur
 *  d'avant. */
export function clampNumber(field, raw, previous) {
  const scale = 10 ** (field.decimals ?? 0);
  const value = Math.round(Number(String(raw).replace(",", ".")) * scale) / scale;
  if (String(raw).trim() === "" || !Number.isFinite(value)) return previous;
  return Math.min(field.max ?? value, Math.max(field.min ?? value, value));
}

/** Les sous-pages juste après leur parent, chacune avec sa profondeur. */
export function pageTree(pages, tab) {
  const inTab = pages.filter((p) => p.tab === tab);
  const out = [];
  const add = (parent, depth) => {
    for (const page of inTab.filter((p) => (p.parent ?? null) === parent)) {
      out.push({ ...page, depth });
      add(page.id, depth + 1);
    }
  };
  add(null, 0);
  return out;
}

/**
 * Le panneau lui-même. `root` est l'élément #settings-dialog (caché) ;
 * `call` la fonction d'appel du moteur ; `stores`, les réglages qu'il
 * règle, chacun `{ read, apply }` : ribbonLabels, reverseWheel,
 * zoomToCursor, sketchSnaps, sketchPrefs, display, selectFilter,
 * flatTree, docOptions (null sans document : l'onglet est grisé) ;
 * `openShortcuts` ouvre le panneau des raccourcis clavier.
 */
export function createSettingsDialog({
  root, doc, win, call, stores: given = {}, openShortcuts, storage, navigatorLang,
}) {
  const bridge = desktopBridge(win);
  const stores = {
    lang: { read: () => readLang(storage, navigatorLang),
            apply: (lang) => writeLang(storage, lang) },
    theme: { read: () => readTheme(storage),
             apply: (theme) => writeTheme(storage, theme) },
    ...given,
  };
  // Les champs dont le réglage est fourni ; lus à l'ouverture seulement
  // (l'esquisse est créée après le panneau).
  const fields = settingsFields(navigatorLang).filter((f) => f.store in stores);
  const T = (text, vars) => esc(t(text, vars));
  let pendingUpdate = null;
  let draft = {};
  let tab = "system";
  let page = "general";

  function pageLabel(id) {
    return SETTINGS_PAGES.find((p) => p.id === id)?.label ?? "";
  }

  /** Un onglet s'ouvre si l'un de ses champs a une valeur (les
   *  propriétés du document attendent un document). */
  function tabOpen(id) {
    return fields.some((f) => draft[f.id] !== undefined
      && SETTINGS_PAGES.find((p) => p.id === f.page)?.tab === id);
  }

  function fieldHtml(field) {
    const value = draft[field.id];
    const attrs = `data-field="${esc(field.id)}"`;
    const name = (text) => field.translate === false ? esc(text) : T(text);
    const note = field.note ? `<span class="settings-note">${T(field.note)}</span>` : "";
    const reload = field.reload
      ? `<span class="settings-note">${T("la page se recharge à la validation")}</span>` : "";
    let control;
    if (field.kind === "check") {
      return `<div class="settings-field" ${attrs}>
          <label><input type="checkbox" ${attrs} ${value ? "checked" : ""}> ${T(field.label)}</label>${note}
        </div>`;
    } else if (field.kind === "radio") {
      control = field.options.map(([id, text]) => `<label><input type="radio"
          name="${esc(field.name ?? field.id)}" value="${esc(id)}" ${attrs}
          ${id === value ? "checked" : ""}> ${name(text)}</label>`).join("");
      return `<div class="settings-field" ${attrs}><span>${T(field.label)}</span>
          <div class="settings-choices">${control}</div>${note}</div>`;
    } else if (field.kind === "select") {
      control = `<select id="settings-${esc(field.id)}" ${attrs}>${field.options.map(([id, text]) =>
        `<option value="${esc(id)}" ${id === value ? "selected" : ""}>${name(text)}</option>`).join("")}</select>`;
    } else {
      control = `<input id="settings-${esc(field.id)}" type="number" ${attrs}
          min="${field.min}" max="${field.max}" step="${10 ** -(field.decimals ?? 0)}"
          value="${esc(value)}">`;
    }
    return `<div class="settings-field" ${attrs}>
        <label for="settings-${esc(field.id)}">${T(field.label)}</label>${control}${note}${reload}
      </div>`;
  }

  function pageHtml(id) {
    if (id === "about") return aboutHtml();
    const mine = fields.filter((f) => f.page === id);
    const groups = [...new Set(mine.map((f) => f.group))];
    const extra = id === "general" && openShortcuts
      ? `<fieldset class="settings-group"><legend>${T("Raccourcis")}</legend>
          <div class="settings-field">
            <button type="button" data-action="shortcuts">${T("Raccourcis clavier…")}</button>
          </div></fieldset>` : "";
    const head = id === "units"
      ? `<fieldset class="settings-group"><legend>${T("Système d'unités")}</legend>
          <div class="settings-field"><span>${T("Unités : millimètre, gramme, seconde")}</span></div>
        </fieldset>` : "";
    return head + groups.map((group) => `<fieldset class="settings-group">
        <legend>${T(group)}</legend>
        ${mine.filter((f) => f.group === group).map(fieldHtml).join("")}
      </fieldset>`).join("") + extra;
  }

  function aboutHtml() {
    return `<fieldset class="settings-group"><legend>${T("FreeSolid et le moteur")}</legend>
        <dl class="settings-info"></dl>
        <div class="settings-links">
          <button type="button" data-url="${REPO_URL}">${T("Dépôt GitHub")}</button>
          <button type="button" data-url="${ISSUES_URL}">${T("Signaler un problème")}</button>
          <button type="button" data-url="${RELEASES_URL}">${T("Versions")}</button>
          <button type="button" data-url="${LICENSE_URL}">${T("Licence AGPL-3.0")}</button>
        </div>
      </fieldset>
      <fieldset class="settings-group"><legend>${T("Mises à jour")}</legend>
        <div class="settings-update">
          ${bridge
            ? `<button type="button" data-action="check-update">${T("Rechercher des mises à jour")}</button>
               <button type="button" data-action="install-update" hidden>${T("Installer et relancer")}</button>`
            : ""}
          <span class="settings-update-status">${bridge ? "" : esc(updateStatus("browser"))}</span>
        </div>
      </fieldset>`;
  }

  function render() {
    const tabs = SETTINGS_TABS.map(([id]) => [id, pageTree(SETTINGS_PAGES, id)]);
    root.innerHTML = `
      <div class="settings-card" role="dialog" aria-modal="true" aria-labelledby="settings-title">
        <div class="settings-head">
          <h2 id="settings-title"></h2>
          <button type="button" class="settings-close" data-action="close" title="${T("Annuler")}">×</button>
        </div>
        <p class="settings-warn">${T("Version de développement, non fonctionnelle : un prototype pour essayer et remonter des problèmes.")}</p>
        <div class="settings-top">
          <div class="settings-tabs" role="tablist">
            ${SETTINGS_TABS.map(([id, label]) => `<button type="button" role="tab"
              data-tab="${id}" ${tabOpen(id) ? "" : `disabled title="${T("Aucun document ouvert")}"`}>${T(label)}</button>`).join("")}
          </div>
          <input type="search" class="settings-search" placeholder="${T("Rechercher une option")}"
            aria-label="${T("Rechercher une option")}">
        </div>
        <div class="settings-body">
          <nav class="settings-tree" aria-label="${T("Pages")}">
            ${tabs.map(([id, tree]) => `<div data-tab="${id}" hidden>
              ${tree.map((p) => `<button type="button" data-page="${p.id}"
                style="--depth: ${p.depth}">${T(p.label)}</button>`).join("")}</div>`).join("")}
            <p class="settings-none" hidden>${T("Aucune option trouvée")}</p>
          </nav>
          <div class="settings-pages">
            ${tabs.flatMap(([, tree]) => tree).map((p) => `<section class="settings-page"
              id="settings-${p.id}" data-page="${p.id}" hidden>${pageHtml(p.id)}</section>`).join("")}
          </div>
        </div>
        <div class="settings-actions">
          <div class="settings-reset">
            <button type="button" data-action="reset">${T("Réinitialiser…")}</button>
            <div class="settings-reset-menu" hidden>
              <button type="button" data-reset="page">${T("Cette page")}</button>
              <button type="button" data-reset="tab">${T("Toutes les options de l'onglet")}</button>
            </div>
          </div>
          <button type="button" class="primary" data-action="ok">${T("OK")}</button>
          <button type="button" data-action="close">${T("Annuler")}</button>
        </div>
      </div>`;
    wire();
    syncEnabled();
    showPage(page);
  }

  /** Les lignes « À propos », une fois le moteur interrogé. */
  function renderInfo(ping, extra) {
    const el = root.querySelector(".settings-info");
    if (!el) return;
    el.innerHTML = infoRows(ping, extra)
      .map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");
  }

  /** Montrer une page, et son onglet ; une page inconnue (ou d'un
   *  onglet grisé) : la première de l'onglet ouvert. */
  function showPage(id) {
    const known = SETTINGS_PAGES.find((p) => p.id === id && tabOpen(p.tab));
    if (known) tab = known.tab;
    else if (!tabOpen(tab)) tab = "system";
    page = known ? id : pageTree(SETTINGS_PAGES, tab)[0].id;
    for (const el of root.querySelectorAll(".settings-page")) {
      el.hidden = el.dataset.page !== page;
    }
    for (const el of root.querySelectorAll(".settings-tree [data-page]")) {
      el.classList.toggle("on", el.dataset.page === page);
    }
    for (const el of root.querySelectorAll(".settings-tree [data-tab]")) {
      el.hidden = el.dataset.tab !== tab;
    }
    for (const el of root.querySelectorAll(".settings-tabs [data-tab]")) {
      el.classList.toggle("on", el.dataset.tab === tab);
      el.setAttribute("aria-selected", String(el.dataset.tab === tab));
    }
    const tabLabel = SETTINGS_TABS.find(([id]) => id === tab)?.[1] ?? "";
    root.querySelector("#settings-title").textContent =
      `${t(tabLabel)} — ${t(pageLabel(page))}`;
  }

  /** Un champ qu'un autre active (les sortes d'accrochage) suit son
   *  brouillon. */
  function syncEnabled() {
    for (const field of fields.filter((f) => f.enabledBy)) {
      const on = [field.enabledBy].flat().every((id) => draft[id]);
      for (const input of root.querySelectorAll(`input[data-field="${field.id}"]`)) {
        input.disabled = !on;
      }
    }
  }

  /** Le brouillon dans les champs (après Réinitialiser). */
  function syncInputs() {
    for (const field of fields) {
      for (const input of root.querySelectorAll(
        `input[data-field="${field.id}"], select[data-field="${field.id}"]`)) {
        if (input.type === "checkbox") input.checked = !!draft[field.id];
        else if (input.type === "radio") input.checked = input.value === draft[field.id];
        else input.value = draft[field.id];
      }
    }
    syncEnabled();
  }

  function onInput(event) {
    const field = fields.find((f) => f.id === event.target.dataset.field);
    if (!field) return;
    const input = event.target;
    if (field.kind === "check") draft[field.id] = input.checked;
    else if (field.kind === "number") {
      draft[field.id] = clampNumber(field, input.value, draft[field.id]);
      input.value = draft[field.id];
    } else if (input.type !== "radio" || input.checked) draft[field.id] = input.value;
    syncEnabled();
  }

  function search(query) {
    // Pas dans un onglet grisé.
    const pages = SETTINGS_PAGES.filter((p) => tabOpen(p.tab));
    const found = searchSettings(query, fields.filter((f) => draft[f.id] !== undefined),
      pages, t);
    for (const el of root.querySelectorAll(".settings-tree [data-page]")) {
      el.hidden = !!found && !found.pages.has(el.dataset.page);
    }
    for (const el of root.querySelectorAll(".settings-field[data-field]")) {
      el.classList.toggle("hit", !!found?.fields.has(el.dataset.field));
    }
    root.querySelector(".settings-none").hidden = !found || found.pages.size > 0;
    if (found && found.pages.size && !found.pages.has(page)) {
      // La première page qui a une option trouvée, sinon la première
      // dont le nom répond.
      const first = fields.find((f) => found.fields.has(f.id))?.page
        ?? [...found.pages][0];
      showPage(first);
    }
    // La première option trouvée de la page montrée, dans la vue.
    root.querySelector(`.settings-page[data-page="${page}"] .settings-field.hit`)
      ?.scrollIntoView?.({ block: "nearest" });
  }

  function setUpdateStatus(kind, detail) {
    const el = root.querySelector(".settings-update-status");
    if (el) el.textContent = updateStatus(kind, detail);
  }

  async function openUrl(url) {
    if (bridge) {
      try { await bridge.openUrl(url); return; } catch { /* repli navigateur */ }
    }
    win.open(url, "_blank", "noopener");
  }

  async function checkUpdate() {
    const checkBtn = root.querySelector('[data-action="check-update"]');
    const installBtn = root.querySelector('[data-action="install-update"]');
    if (checkBtn) checkBtn.disabled = true;
    setUpdateStatus("checking");
    try {
      pendingUpdate = await bridge.checkUpdate();
      if (!pendingUpdate) {
        setUpdateStatus("none");
      } else {
        setUpdateStatus("available", pendingUpdate.version);
        if (installBtn) installBtn.hidden = false;
      }
    } catch (error) {
      setUpdateStatus("error", error?.message || String(error));
    } finally {
      if (checkBtn) checkBtn.disabled = false;
    }
  }

  async function installUpdate() {
    if (!pendingUpdate) return;
    const installBtn = root.querySelector('[data-action="install-update"]');
    if (installBtn) installBtn.disabled = true;
    let total = 0, done = 0;
    setUpdateStatus("downloading");
    try {
      await pendingUpdate.downloadAndInstall((ev) => {
        if (ev.event === "Started") total = ev.data?.contentLength || 0;
        else if (ev.event === "Progress") {
          done += ev.data?.chunkLength || 0;
          setUpdateStatus("downloading",
            total ? `${Math.round(100 * done / total)} %` : `${(done / 1048576).toFixed(0)} Mo`);
        } else if (ev.event === "Finished") setUpdateStatus("installed");
      });
      await bridge.relaunch();
    } catch (error) {
      setUpdateStatus("error", error?.message || String(error));
      if (installBtn) installBtn.disabled = false;
    }
  }

  function wire() {
    for (const btn of root.querySelectorAll("[data-url]")) {
      btn.addEventListener("click", () => openUrl(btn.dataset.url));
    }
    for (const btn of root.querySelectorAll('[data-action="close"]')) {
      btn.addEventListener("click", close);
    }
    root.querySelector('[data-action="ok"]').addEventListener("click", accept);
    root.querySelector('[data-action="check-update"]')
      ?.addEventListener("click", checkUpdate);
    root.querySelector('[data-action="install-update"]')
      ?.addEventListener("click", installUpdate);
    root.querySelector('[data-action="shortcuts"]')
      ?.addEventListener("click", () => {
        // Le panneau des raccourcis s'ouvre à la place : les changements
        // en attente sont validés d'abord.
        accept();
        openShortcuts();
      });
    for (const btn of root.querySelectorAll(".settings-tree [data-page]")) {
      btn.addEventListener("click", () => showPage(btn.dataset.page));
    }
    for (const btn of root.querySelectorAll(".settings-tabs [data-tab]")) {
      // La première page de l'onglet que la recherche laisse voir.
      btn.addEventListener("click", () => showPage(root.querySelector(
        `.settings-tree [data-tab="${btn.dataset.tab}"] [data-page]:not([hidden])`)
        ?.dataset.page ?? pageTree(SETTINGS_PAGES, btn.dataset.tab)[0].id));
    }
    root.querySelector(".settings-pages").addEventListener("change", onInput);
    root.querySelector(".settings-search")
      .addEventListener("input", (event) => search(event.target.value));
    const resetMenu = root.querySelector(".settings-reset-menu");
    root.querySelector('[data-action="reset"]').addEventListener("click", () => {
      resetMenu.hidden = !resetMenu.hidden;
    });
    for (const btn of resetMenu.querySelectorAll("[data-reset]")) {
      btn.addEventListener("click", () => {
        resetMenu.hidden = true;
        const pages = btn.dataset.reset === "page" ? [page]
          : SETTINGS_PAGES.filter((p) => p.tab === tab).map((p) => p.id);
        draft = resetDraft(fields, draft, pages);
        syncInputs();
      });
    }
  }

  /** OK : chaque changement appliqué, puis la page rechargée si l'un
   *  d'eux le demande (langue, thème). */
  function accept() {
    const changed = changedFields(fields, stores, draft);
    for (const field of changed) field.set(stores, draft[field.id]);
    close();
    if (changed.some((f) => f.reload)) win.location?.reload?.();
  }

  function onKey(event) {
    if (event.key !== "Escape") return;
    event.stopPropagation();
    const resetMenu = root.querySelector(".settings-reset-menu");
    if (resetMenu && !resetMenu.hidden) resetMenu.hidden = true;
    else close();
  }

  /** `section` : l'id d'une page (« snaps ») à montrer. */
  async function open(section = null) {
    root.hidden = false;
    draft = readValues(fields, stores);
    tab = SETTINGS_PAGES.find((p) => p.id === section)?.tab ?? "system";
    page = section ?? "general";
    render();
    renderInfo(null, { engineUrl: win.location?.origin || "" });
    doc.addEventListener("keydown", onKey, true);
    let ping = null;
    try { ping = await call("ping"); } catch { ping = null; }
    const extra = { engineUrl: win.location?.origin || "" };
    if (bridge) {
      try { extra.appVersion = await bridge.appVersion(); } catch { /* version du moteur */ }
      try { extra.logPath = await bridge.engineLogPath(); } catch { /* pas de journal */ }
    }
    if (!root.hidden) renderInfo(ping, extra);
  }

  /** Fermer sans appliquer (Annuler, Échap, ×). */
  function close() {
    root.hidden = true;
    doc.removeEventListener("keydown", onKey, true);
  }

  function toggle() {
    if (root.hidden) open(); else close();
  }

  return { open, close, toggle, isOpen: () => !root.hidden };
}
