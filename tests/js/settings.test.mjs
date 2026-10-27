// Panneau Paramètres : les décisions pures (pages, champs, recherche,
// brouillon, langue, lignes d'information, pont bureau, textes d'état),
// sans DOM.

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  SETTINGS_PAGES,
  SETTINGS_TABS,
  THEME_KEY,
  changedFields,
  clampNumber,
  pageTree,
  readTheme,
  readValues,
  resetDraft,
  searchSettings,
  searchText,
  settingsFields,
  resolveTheme,
  writeTheme,
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

describe("thème", () => {
  const store = (init = {}) => {
    const data = { ...init };
    return { getItem: (k) => data[k] ?? null, setItem: (k, v) => { data[k] = v; }, data };
  };

  it("clair par défaut, valeur inconnue ignorée", () => {
    assert.equal(readTheme(store()), "light");
    assert.equal(readTheme(store({ [THEME_KEY]: "violet" })), "light");
    assert.equal(readTheme(null), "light");
    assert.equal(readTheme(store({ [THEME_KEY]: "dark" })), "dark");
  });

  it("enregistre un thème connu seulement", () => {
    const s = store();
    assert.equal(writeTheme(s, "light"), true);
    assert.equal(readTheme(s), "light");
    assert.equal(writeTheme(s, "violet"), false);
    assert.equal(readTheme(s), "light");
  });

  it("« système » suit la préférence du système", () => {
    assert.equal(resolveTheme("system", true), "light");
    assert.equal(resolveTheme("system", false), "dark");
    assert.equal(resolveTheme("light", false), "light");
    assert.equal(resolveTheme("dark", true), "dark");
  });

  it("le script de tête d'index.html lit la même clé", () => {
    const html = readFileSync(new URL("../../app/index.html", import.meta.url), "utf8");
    const head = html.slice(0, html.indexOf("<style>"));
    assert.ok(head.includes(`localStorage.getItem("${THEME_KEY}")`));
    assert.ok(html.includes(':root[data-theme="light"]'));
  });
});


describe("pages et champs des Paramètres", () => {
  const fields = settingsFields("fr-FR");
  const en = JSON.parse(readFileSync(new URL("../../app/lang/en.json", import.meta.url), "utf8"));

  it("chaque sous-page suit son parent, un cran plus loin", () => {
    const tree = pageTree(SETTINGS_PAGES, "system");
    assert.equal(tree[0].id, "general");
    const sketch = tree.findIndex((p) => p.id === "sketch");
    assert.deepEqual([tree[sketch + 1].id, tree[sketch + 1].depth], ["snaps", 1]);
    assert.equal(tree.at(-1).id, "about");
    assert.ok(tree.every((p) => p.depth === (p.parent ? 1 : 0)));
  });

  it("chaque champ a un id unique, une page connue et une valeur par défaut", () => {
    const ids = fields.map((f) => f.id);
    assert.equal(new Set(ids).size, ids.length);
    const pages = new Set(SETTINGS_PAGES.map((p) => p.id));
    for (const f of fields) {
      assert.ok(pages.has(f.page), f.id);
      assert.equal(typeof f.store, "string", f.id);
      assert.notEqual(f.default, undefined, f.id);
      for (const id of [f.enabledBy ?? []].flat()) assert.ok(ids.includes(id), f.id);
    }
    assert.equal(fields.find((f) => f.id === "lang").default, "fr");
    assert.equal(settingsFields("en-US").find((f) => f.id === "lang").default, "en");
  });

  it("chaque texte des pages et des champs a sa traduction anglaise", () => {
    const texts = [...SETTINGS_TABS.map(([, label]) => label),
      ...SETTINGS_PAGES.map((p) => p.label)];
    for (const f of fields) {
      texts.push(f.label, f.group);
      if (f.note) texts.push(f.note);
      if (f.translate !== false) texts.push(...(f.options ?? []).map(([, name]) => name));
    }
    assert.deepEqual(texts.filter((text) => !(text in en)), []);
  });

  it("la recherche ignore casse et accents, trouve la page et son parent", () => {
    assert.equal(searchText("Sélection Élevée"), "selection elevee");
    assert.equal(searchSettings("  ", fields, SETTINGS_PAGES), null);
    const grid = searchSettings("GRILLE", fields, SETTINGS_PAGES);
    assert.ok(grid.fields.has("sketch.gridSnap"));
    assert.ok(grid.pages.has("snaps") && grid.pages.has("sketch"));
    assert.ok(!grid.pages.has("view"));
    // Tous les mots, dans n'importe quel ordre.
    const zoom = searchSettings("curseur zoom", fields, SETTINGS_PAGES);
    assert.deepEqual([...zoom.fields], ["view.zoomToCursor"]);
    // Le nom d'une page suffit ; un choix d'une liste aussi.
    assert.ok(searchSettings("selection", fields, SETTINGS_PAGES).pages.has("selection"));
    assert.ok(searchSettings("filaire", fields, SETTINGS_PAGES).fields.has("display.style"));
    assert.equal(searchSettings("introuvable", fields, SETTINGS_PAGES).pages.size, 0);
  });

  it("cherche dans la langue affichée", () => {
    const label = (text) => en[text] ?? text;
    assert.ok(searchSettings("snap to grid", fields, SETTINGS_PAGES, label)
      .fields.has("sketch.gridSnap"));
  });

  function fakeStores() {
    const log = [];
    let snaps = { enabled: true, off: ["midpoint"], angleStep: 15 };
    let filter = { faces: true, edges: false };
    let wheel = false;
    return {
      log,
      stores: {
        sketchSnaps: { read: () => snaps, apply: (next) => { snaps = next; log.push("snaps"); } },
        selectFilter: { read: () => filter, apply: (next) => { filter = next; log.push("filter"); } },
        reverseWheel: { read: () => wheel, apply: (next) => { wheel = next; log.push("wheel"); } },
      },
      get snaps() { return snaps; },
      get filter() { return filter; },
    };
  }

  it("le brouillon : seuls les champs changés s'appliquent", () => {
    const fake = fakeStores();
    const known = fields.filter((f) => f.store in fake.stores);
    assert.ok(known.every((f) => /^(snaps|select|view\.reverseWheel)/.test(f.id)));
    const draft = readValues(known, fake.stores);
    assert.equal(draft["snaps.kind.midpoint"], false);
    assert.equal(draft["snaps.kind.center"], true);
    assert.equal(draft["select.sketches"], true); // absent = sélectionnable
    assert.deepEqual(changedFields(known, fake.stores, draft), []);
    draft["snaps.kind.midpoint"] = true;
    draft["snaps.kind.center"] = false;
    draft["select.edges"] = true;
    const changed = changedFields(known, fake.stores, draft);
    assert.deepEqual(changed.map((f) => f.id),
      ["snaps.kind.center", "snaps.kind.midpoint", "select.edges"]);
    for (const f of changed) f.set(fake.stores, draft[f.id]);
    assert.deepEqual(fake.snaps, { enabled: true, off: ["center"], angleStep: 15 });
    assert.deepEqual(fake.filter, { faces: true, edges: true });
    assert.deepEqual(fake.log, ["snaps", "snaps", "filter"]);
  });

  it("réinitialiser : les défauts des pages demandées, dans le brouillon", () => {
    const fake = fakeStores();
    const known = fields.filter((f) => f.store in fake.stores);
    const draft = readValues(known, fake.stores);
    draft["view.reverseWheel"] = true;
    const page = resetDraft(known, draft, ["snaps"]);
    assert.equal(page["snaps.kind.midpoint"], true);
    assert.equal(page["view.reverseWheel"], true);
    assert.equal(draft["snaps.kind.midpoint"], false); // le brouillon d'avant reste
    const all = resetDraft(known, draft, SETTINGS_PAGES.map((p) => p.id));
    assert.equal(all["view.reverseWheel"], false);
    assert.equal(all["select.edges"], true);
  });

  it("un nombre reste entier et dans ses bornes", () => {
    const angle = fields.find((f) => f.id === "snaps.angleStep");
    assert.equal(clampNumber(angle, "7.6", 15), 8);
    assert.equal(clampNumber(angle, "500", 15), 90);
    assert.equal(clampNumber(angle, "0", 15), 1);
    assert.equal(clampNumber(angle, "", 15), 15);
    assert.equal(clampNumber(angle, "abc", 15), 15);
  });

  it("un pas de grille garde deux décimales, la virgule vaut le point", () => {
    const step = fields.find((f) => f.id === "doc.gridStep");
    assert.equal(clampNumber(step, "2,345", 10), 2.35);
    assert.equal(clampNumber(step, "0.001", 10), 0.01);
    assert.equal(clampNumber(step, " ", 10), 10);
  });

  it("les propriétés du document : un onglet à part, les défauts du moteur", () => {
    const engine = readFileSync(new URL("../../engine/docoptions.py", import.meta.url), "utf8");
    const pyDefault = (key) => JSON.parse(engine.match(new RegExp(`"${key}": ([^,\\n]+),`))[1]
      .replace("False", "false").replace("True", "true"));
    const docFields = fields.filter((f) => f.store === "docOptions");
    const tabOf = (f) => SETTINGS_PAGES.find((p) => p.id === f.page).tab;
    assert.ok(docFields.length >= 5 && docFields.every((f) => tabOf(f) === "document"));
    assert.ok(fields.filter((f) => f.store !== "docOptions").every((f) => tabOf(f) === "system"));
    const byKey = { "doc.lengthDecimals": "length_decimals", "doc.angleDecimals": "angle_decimals",
      "doc.gridFixed": "grid_fixed", "doc.gridStep": "grid_step", "doc.quality": "quality" };
    for (const [id, key] of Object.entries(byKey)) {
      assert.equal(fields.find((f) => f.id === id).default, pyDefault(key), id);
    }
    const quality = engine.match(/QUALITY = \{([^}]+)\}/)[1];
    assert.deepEqual(fields.find((f) => f.id === "doc.quality").options.map(([id]) => id),
      [...quality.matchAll(/"(\w+)":/g)].map((m) => m[1]));
    // Lu et écrit dans un seul objet, comme le moteur le renvoie.
    let options = { length_decimals: 2, grid_fixed: false };
    const stores = { docOptions: { read: () => options, apply: (next) => { options = next; } } };
    fields.find((f) => f.id === "doc.gridFixed").set(stores, true);
    assert.deepEqual(options, { length_decimals: 2, grid_fixed: true });
    // Sans document : pas de valeur, rien à appliquer.
    const none = { docOptions: { read: () => null, apply: () => assert.fail() } };
    const draft = readValues(docFields, none);
    assert.ok(Object.values(draft).every((v) => v === undefined));
    assert.deepEqual(changedFields(docFields, none, draft), []);
  });
});
