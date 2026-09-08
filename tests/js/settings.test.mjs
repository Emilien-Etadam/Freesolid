// Panneau Paramètres : les décisions pures (langue, lignes d'information,
// pont bureau, textes d'état), sans DOM.

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  LANG_KEY,
  REPO_URL,
  desktopBridge,
  detectLang,
  infoRows,
  readLang,
  updateStatus,
  writeLang,
} from "../../app/settings.js";

function fakeStorage(initial = {}) {
  const data = { ...initial };
  return {
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => { data[k] = String(v); },
    data,
  };
}

describe("langue", () => {
  it("détecte fr/en depuis navigator.language, français sinon", () => {
    assert.equal(detectLang("fr-FR"), "fr");
    assert.equal(detectLang("en_US"), "en");
    assert.equal(detectLang("EN"), "en");
    assert.equal(detectLang("de-DE"), "fr");
    assert.equal(detectLang(undefined), "fr");
  });

  it("préfère le choix enregistré, ignore une valeur inconnue", () => {
    assert.equal(readLang(fakeStorage({ [LANG_KEY]: "en" }), "fr-FR"), "en");
    assert.equal(readLang(fakeStorage({ [LANG_KEY]: "klingon" }), "en-GB"), "en");
    assert.equal(readLang(null, "en"), "en");
  });

  it("n'enregistre que les langues livrées, sans planter sans stockage", () => {
    const st = fakeStorage();
    assert.equal(writeLang(st, "en"), true);
    assert.equal(st.data[LANG_KEY], "en");
    assert.equal(writeLang(st, "xx"), false);
    assert.equal(writeLang(null, "fr"), true);
  });
});

describe("infoRows", () => {
  it("dit que le moteur est injoignable sans ping", () => {
    const rows = infoRows(null, { engineUrl: "http://127.0.0.1:8787" });
    assert.deepEqual(rows, [
      ["FreeSolid", "inconnue"],
      ["Moteur", "injoignable"],
      ["Adresse du moteur", "http://127.0.0.1:8787"],
    ]);
  });

  it("montre la référence FreeCAD seulement si elle diffère", () => {
    const ping = {
      freesolid: "0.1.0", freecad: "1.1.3", freecad_reference: "1.1.3",
      freecadcmd: "/opt/fc/bin/freecadcmd",
    };
    assert.deepEqual(infoRows(ping), [
      ["FreeSolid", "0.1.0"],
      ["FreeCAD", "1.1.3"],
      ["freecadcmd", "/opt/fc/bin/freecadcmd"],
    ]);
    const other = infoRows({ ...ping, freecad: "1.0.0" });
    assert.equal(other[1][1], "1.0.0 (référence 1.1.3)");
  });

  it("préfère la version de l'application de bureau et ajoute le journal", () => {
    const rows = infoRows({ freesolid: "0.1.0", freecad: "1.1.3" },
      { appVersion: "0.2.0", logPath: "C:\\\\logs\\\\engine.log" });
    assert.equal(rows[0][1], "0.2.0");
    assert.deepEqual(rows.at(-1), ["Journal du moteur", "C:\\\\logs\\\\engine.log"]);
  });
});

describe("desktopBridge", () => {
  it("est nul hors de Tauri", () => {
    assert.equal(desktopBridge(undefined), null);
    assert.equal(desktopBridge({}), null);
    assert.equal(desktopBridge({ __TAURI__: {} }), null);
  });

  it("expose les fonctions présentes et refuse proprement les absentes", async () => {
    const calls = [];
    const win = { __TAURI__: {
      core: { invoke: async (cmd) => { calls.push(cmd); return "/log"; } },
      updater: { check: async () => null },
      app: { getVersion: async () => "0.1.0" },
    } };
    const bridge = desktopBridge(win);
    assert.equal(await bridge.appVersion(), "0.1.0");
    assert.equal(await bridge.checkUpdate(), null);
    assert.equal(await bridge.engineLogPath(), "/log");
    assert.deepEqual(calls, ["engine_log_path"]);
    await assert.rejects(bridge.relaunch());
    await assert.rejects(bridge.openUrl("https://x"));
  });
});

describe("textes", () => {
  it("couvre chaque état de mise à jour", () => {
    assert.equal(updateStatus("none"), "FreeSolid est à jour.");
    assert.equal(updateStatus("available", "0.2.0"), "Version 0.2.0 disponible.");
    assert.match(updateStatus("downloading", "40 %"), /40 %/);
    assert.match(updateStatus("error", "boom"), /boom/);
    assert.match(updateStatus("browser"), /application de bureau/);
    assert.equal(updateStatus("autre"), "");
  });

  it("le dépôt du panneau est celui du moteur (engine/platform.py)", () => {
    const py = readFileSync(new URL("../../engine/platform.py", import.meta.url), "utf8");
    assert.match(py, new RegExp(`REPO_URL = "${REPO_URL}"`));
  });
});
