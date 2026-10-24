// Appels au moteur, sondage de la progression et barre d'état.
// `statusSticky` reste dans main.js : refresh() l'efface quand une op
// réussit. Ici on le lit et l'écrit via ctx.

import { formatProgressStatus } from "../progress.js";
import { currentLang, t } from "../i18n.js";

export function installApi(ctx) {
  const { statusEl } = ctx;

  async function call(op, params = {}) {
    const response = await fetch("/api", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // La langue de l'interface part avec chaque requête : le moteur nomme
      // ce qu'il crée et rédige ses erreurs dans cette langue.
      body: JSON.stringify({ op, params, lang: currentLang() }),
    });
    const text = await response.text();
    let payload = null;
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
    // {ok:false} (HTTP 200 ou 4xx protocole) : message moteur / protocole.
    if (payload && payload.ok === false) {
      throw new Error(payload.error + (payload.hint ? ` (${payload.hint})` : ""));
    }
    if (!response.ok || !payload || payload.ok !== true) {
      const excerpt = text.slice(0, 180).replace(/\s+/g, " ").trim();
      throw new Error(
        `HTTP ${response.status}${excerpt ? ` — ${excerpt}` : ""}`);
    }
    return payload.result;
  }

  const PROGRESS_MS = 300;
  let progressTimer = null;
  let progressWatchers = 0;
  let progressGen = 0;

  async function pollProgressOnce(gen) {
    if (gen !== progressGen || ctx.statusSticky) return;
    try {
      const progress = await call("progress");
      if (gen !== progressGen || ctx.statusSticky) return;
      const now = Date.now() / 1000;
      ctx.pluginRuntime?.dispatchProgress(progress, now);
      const text = formatProgressStatus(progress, now);
      if (text) say(text);
    } catch {
      // Le sondage ne doit jamais masquer l'op en cours ni son erreur.
    }
  }

  function startProgressWatch() {
    progressWatchers += 1;
    if (progressWatchers > 1) return;
    const gen = ++progressGen;
    document.body.classList.add("op-en-cours");
    document.body.setAttribute("aria-busy", "true");
    pollProgressOnce(gen);
    progressTimer = setInterval(() => pollProgressOnce(gen), PROGRESS_MS);
  }

  function stopProgressWatch() {
    progressWatchers = Math.max(0, progressWatchers - 1);
    if (progressWatchers > 0) return;
    progressGen += 1;
    if (progressTimer != null) {
      clearInterval(progressTimer);
      progressTimer = null;
    }
    document.body.classList.remove("op-en-cours");
    document.body.removeAttribute("aria-busy");
  }

  function say(text, isError = false) {
    if (ctx.statusSticky && !isError) return;
    if (!isError) ctx.statusSticky = false;
    statusEl.textContent = t(text);
    statusEl.className = isError ? "err" : "";
    if (ctx.statusSticky) statusEl.classList.add("sticky");
    // Le texte entier en infobulle : la barre l'abrège s'il est trop long.
    statusEl.title = ctx.statusSticky ? t("Cliquer pour fermer") : statusEl.textContent;
  }

  /** Erreur qui reste jusqu'à ce que l'utilisateur clique la barre d'état. */
  function sayUntilAck(text) {
    ctx.statusSticky = true;
    say(text, true);
  }

  statusEl.addEventListener("click", () => {
    if (!ctx.statusSticky) return;
    ctx.statusSticky = false;
    statusEl.classList.remove("sticky");
    statusEl.title = "";
  });

  return { call, startProgressWatch, stopProgressWatch, say, sayUntilAck };
}
