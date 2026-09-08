// Panneau Paramètres : identité de FreeSolid et du moteur, liens, mises à
// jour (application de bureau), réglages d'interface.
//
// Tout ce qui est décision est une fonction pure et testée (lignes
// d'information, langue, pont Tauri) ; le DOM n'est touché que dans
// createSettingsDialog.

export const REPO_URL = "https://github.com/Emilien-Etadam/Freesolid";
export const RELEASES_URL = REPO_URL + "/releases";
export const ISSUES_URL = REPO_URL + "/issues";
export const LICENSE_URL = REPO_URL + "/blob/main/LICENSE";

export const LANG_KEY = "freesolid.lang";
export const LANGS = [["fr", "Français"], ["en", "English"]];

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
  const version = appVersion || ping?.freesolid || "inconnue";
  rows.push(["FreeSolid", version]);
  if (!ping) {
    rows.push(["Moteur", "injoignable"]);
  } else {
    const ref = ping.freecad_reference;
    const freecad = ping.freecad || "inconnue";
    rows.push(["FreeCAD", ref && ref !== freecad
      ? `${freecad} (référence ${ref})`
      : freecad]);
    if (ping.freecadcmd) rows.push(["freecadcmd", ping.freecadcmd]);
  }
  if (engineUrl) rows.push(["Adresse du moteur", engineUrl]);
  if (logPath) rows.push(["Journal du moteur", logPath]);
  return rows;
}

/** Texte d'état de la recherche de mise à jour. */
export function updateStatus(kind, detail = "") {
  switch (kind) {
    case "checking": return "Recherche en cours…";
    case "none": return "FreeSolid est à jour.";
    case "available": return `Version ${detail} disponible.`;
    case "downloading": return detail ? `Téléchargement… ${detail}` : "Téléchargement…";
    case "installed": return "Mise à jour installée, relance…";
    case "error": return `Mise à jour impossible : ${detail}`;
    case "browser": return "Les mises à jour automatiques existent dans "
      + "l'application de bureau. Dans le navigateur : git pull.";
    default: return "";
  }
}

function esc(text) {
  return String(text).replace(/[&<>"]/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;" }[c]));
}

/**
 * Le panneau lui-même. `root` est l'élément #settings-dialog (caché) ;
 * `call` la fonction d'appel du moteur ; `ribbonLabels` {read, apply}.
 */
export function createSettingsDialog({
  root, doc, win, call, ribbonLabels, storage, navigatorLang,
}) {
  const bridge = desktopBridge(win);
  let pendingUpdate = null;

  function render(ping, extra) {
    const rows = infoRows(ping, extra);
    const lang = readLang(storage, navigatorLang);
    const labelsMode = ribbonLabels.read();
    root.innerHTML = `
      <div class="settings-card" role="dialog" aria-modal="true" aria-labelledby="settings-title">
        <div class="settings-head">
          <h2 id="settings-title">Paramètres</h2>
          <button type="button" class="settings-close" data-action="close" title="Fermer">×</button>
        </div>
        <p class="settings-warn">Version de développement, non fonctionnelle :
          un prototype pour essayer et remonter des problèmes.</p>

        <h3>À propos</h3>
        <dl class="settings-info">
          ${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}
        </dl>
        <div class="settings-links">
          <button type="button" data-url="${REPO_URL}">Dépôt GitHub</button>
          <button type="button" data-url="${ISSUES_URL}">Signaler un problème</button>
          <button type="button" data-url="${RELEASES_URL}">Versions</button>
          <button type="button" data-url="${LICENSE_URL}">Licence LGPL-2.1</button>
        </div>

        <h3>Mises à jour</h3>
        <div class="settings-update">
          ${bridge
            ? `<button type="button" data-action="check-update">Rechercher des mises à jour</button>
               <button type="button" data-action="install-update" hidden>Installer et relancer</button>`
            : ""}
          <span class="settings-update-status">${bridge ? "" : esc(updateStatus("browser"))}</span>
        </div>

        <h3>Interface</h3>
        <div class="settings-field">
          <span>Libellés du ruban</span>
          <label><input type="radio" name="ribbon-labels" value="icons-and-text"
            ${labelsMode === "icons-and-text" ? "checked" : ""}> Icônes et texte</label>
          <label><input type="radio" name="ribbon-labels" value="icons-only"
            ${labelsMode === "icons-only" ? "checked" : ""}> Icônes seules</label>
        </div>
        <div class="settings-field">
          <label for="settings-lang">Langue</label>
          <select id="settings-lang">
            ${LANGS.map(([id, name]) =>
              `<option value="${id}" ${id === lang ? "selected" : ""}>${esc(name)}</option>`).join("")}
          </select>
          <span class="settings-note">traduction de l'interface à venir</span>
        </div>

        <div class="settings-actions">
          <button type="button" data-action="close">Fermer</button>
        </div>
      </div>`;
    wire();
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
    root.querySelector('[data-action="check-update"]')
      ?.addEventListener("click", checkUpdate);
    root.querySelector('[data-action="install-update"]')
      ?.addEventListener("click", installUpdate);
    for (const radio of root.querySelectorAll('input[name="ribbon-labels"]')) {
      radio.addEventListener("change", () => ribbonLabels.apply(radio.value));
    }
    root.querySelector("#settings-lang")
      ?.addEventListener("change", (event) => writeLang(storage, event.target.value));
  }

  function onKey(event) {
    if (event.key === "Escape") {
      event.stopPropagation();
      close();
    }
  }

  function onBackdrop(event) {
    if (event.target === root) close();
  }

  async function open() {
    root.hidden = false;
    render(null, { engineUrl: win.location?.origin || "" });
    doc.addEventListener("keydown", onKey, true);
    root.addEventListener("click", onBackdrop);
    let ping = null;
    try { ping = await call("ping"); } catch { ping = null; }
    const extra = { engineUrl: win.location?.origin || "" };
    if (bridge) {
      try { extra.appVersion = await bridge.appVersion(); } catch { /* version du moteur */ }
      try { extra.logPath = await bridge.engineLogPath(); } catch { /* pas de journal */ }
    }
    if (!root.hidden) render(ping, extra);
  }

  function close() {
    root.hidden = true;
    doc.removeEventListener("keydown", onKey, true);
    root.removeEventListener("click", onBackdrop);
  }

  function toggle() {
    if (root.hidden) open(); else close();
  }

  return { open, close, toggle, isOpen: () => !root.hidden };
}
