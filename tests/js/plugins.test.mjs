import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { createPluginApi, loadClientPlugins, pluginEntryUrl } from "../../app/plugins.js";

describe("pluginEntryUrl", () => {
  it("n'accepte que /plugins/<nom>/plugin.js avec le même nom", () => {
    assert.equal(
      pluginEntryUrl("exemple", "/plugins/exemple/plugin.js"),
      "/plugins/exemple/plugin.js",
    );
    assert.equal(
      pluginEntryUrl("exemple", "/plugins/autre/plugin.js"),
      "",
    );
    assert.equal(
      pluginEntryUrl("exemple", "/plugins/exemple/../x.js"),
      "",
    );
    assert.equal(
      pluginEntryUrl("exemple", "https://evil.example/plugin.js"),
      "",
    );
    assert.equal(pluginEntryUrl("exemple", "/app/main.js"), "");
    assert.equal(pluginEntryUrl("", "/plugins/exemple/plugin.js"), "");
    assert.equal(pluginEntryUrl("exemple", null), "");
  });
});

describe("loadClientPlugins", () => {
  it("importe dans l'ordre et appelle register(api)", async () => {
    const seen = [];
    const api = { tag: "host" };
    const call = async (op) => {
      assert.equal(op, "list_plugins");
      return {
        plugins: [
          { nom: "alpha", entree: "/plugins/alpha/plugin.js" },
          { nom: "zeta", entree: "/plugins/zeta/plugin.js" },
        ],
      };
    };
    const importer = async (url) => ({
      register(received) {
        seen.push({ url, api: received });
      },
    });
    const loaded = await loadClientPlugins(call, api, importer);
    assert.deepEqual(loaded, ["alpha", "zeta"]);
    assert.equal(seen.length, 2);
    assert.equal(seen[0].url, "/plugins/alpha/plugin.js");
    assert.equal(seen[0].api, api);
    assert.equal(seen[1].url, "/plugins/zeta/plugin.js");
  });

  it("ignore une entrée dont l'URL ne correspond pas au nom", async () => {
    const importer = async () => {
      throw new Error("ne doit pas importer");
    };
    const loaded = await loadClientPlugins(
      async () => ({
        plugins: [{ nom: "alpha", entree: "/plugins/zeta/plugin.js" }],
      }),
      {},
      importer,
    );
    assert.deepEqual(loaded, []);
  });

  it("un module cassé n'empêche pas le suivant", async () => {
    const seen = [];
    const importer = async (url) => {
      if (url.includes("alpha")) throw new Error("boom");
      return { register() { seen.push(url); } };
    };
    const loaded = await loadClientPlugins(
      async () => ({
        plugins: [
          { nom: "alpha", entree: "/plugins/alpha/plugin.js" },
          { nom: "beta", entree: "/plugins/beta/plugin.js" },
        ],
      }),
      {},
      importer,
    );
    assert.deepEqual(loaded, ["beta"]);
    assert.deepEqual(seen, ["/plugins/beta/plugin.js"]);
  });

  it("list_plugins injoignable : aucun chargement, pas d'exception", async () => {
    const loaded = await loadClientPlugins(
      async () => { throw new Error("moteur"); },
      {},
      async () => { throw new Error("ne doit pas importer"); },
    );
    assert.deepEqual(loaded, []);
  });
});

describe("createPluginApi", () => {
  it("dispatchKey s'arrête au premier handler qui rend true", () => {
    const seen = [];
    const host = {
      call() {}, refresh() {}, say() {}, tree: () => null,
    };
    const runtime = createPluginApi(host);
    runtime.api.key((event) => {
      seen.push("a");
      return event.key === "a";
    });
    runtime.api.key((event) => {
      seen.push("b");
      return event.key === "b";
    });
    assert.equal(runtime.dispatchKey({ key: "a" }), true);
    assert.deepEqual(seen, ["a"]);
    seen.length = 0;
    assert.equal(runtime.dispatchKey({ key: "b" }), true);
    assert.deepEqual(seen, ["a", "b"]);
    seen.length = 0;
    assert.equal(runtime.dispatchKey({ key: "c" }), false);
    assert.deepEqual(seen, ["a", "b"]);
  });

  it("treeRow itère le predicat et append les lignes", () => {
    const rows = [];
    const host = {
      call() {}, refresh() {}, say() {}, tree: () => null,
    };
    const runtime = createPluginApi(host);
    runtime.api.treeRow(
      (tree) => tree.pieces ?? [],
      (piece) => ({ name: piece.name }),
    );
    runtime.renderTreeRows(
      { pieces: [{ name: "Piece" }, { name: "Piece001" }] },
      { append: (row) => rows.push(row) },
    );
    assert.deepEqual(rows, [{ name: "Piece" }, { name: "Piece001" }]);
  });

  it("featureButton et combineTools passent par l'hôte", () => {
    const seen = [];
    const host = {
      call() {}, refresh() {}, say() {}, tree: () => null,
      addFeatureButton: (id, core) => seen.push(["button", id, core]),
      addCombineTools: (hooks) => seen.push(["combine", typeof hooks.options]),
    };
    const { api } = createPluginApi(host);
    api.featureButton("btn-exemple-combine", "btn-boolean");
    api.featureButton(null, "btn-boolean");
    api.combineTools({ options: () => [] });
    api.combineTools({});
    assert.deepEqual(seen, [
      ["button", "btn-exemple-combine", "btn-boolean"],
      ["combine", "function"],
    ]);
  });

  it("progress : chaque sondage atteint les plugins, un plugin cassé n'arrête pas", () => {
    const seen = [];
    const runtime = createPluginApi({
      call() {}, refresh() {}, say() {}, tree: () => null,
    });
    runtime.api.progress(() => { throw new Error("boum"); });
    runtime.api.progress((progress, now) => seen.push([progress.op, now]));
    runtime.api.progress("pas une fonction");
    runtime.dispatchProgress({ op: "add_boolean" }, 12);
    assert.deepEqual(seen, [["add_boolean", 12]]);
  });

  it("viewport : onClear puis onMesh, les objets sont ajoutés au groupe", () => {
    const log = [];
    const group = { add(obj) { log.push(["add", obj.id]); } };
    const host = {
      call() {}, refresh() {}, say() {}, tree: () => null,
    };
    const runtime = createPluginApi(host);
    runtime.api.viewport({
      onClear() { log.push("clear"); },
      onMesh(mesh) {
        log.push(["mesh", mesh.tag]);
        return [{ id: "g1" }, { id: "g2" }];
      },
    });
    runtime.applyViewport({ tag: "t" }, { volumesGroup: group }, (obj) => {
      log.push(["detach", obj.id]);
    });
    assert.deepEqual(log, [
      "clear",
      ["mesh", "t"],
      ["add", "g1"],
      ["add", "g2"],
    ]);
    log.length = 0;
    runtime.applyViewport({ tag: "u" }, { volumesGroup: group }, (obj) => {
      log.push(["detach", obj.id]);
    });
    assert.deepEqual(log, [
      "clear",
      ["detach", "g1"],
      ["detach", "g2"],
      ["mesh", "u"],
      ["add", "g1"],
      ["add", "g2"],
    ]);
  });

  it("pointer : le premier true arrête down/move/up ; idle court à la fin", () => {
    const log = [];
    const host = {
      call() {}, refresh() {}, say() {}, tree: () => null,
    };
    const runtime = createPluginApi(host);
    runtime.api.pointer({
      down() { log.push("a-down"); return true; },
      move() { log.push("a-move"); return false; },
      up() { log.push("a-up"); return false; },
      idle() { log.push("a-idle"); },
    });
    runtime.api.pointer({
      down() { log.push("b-down"); return true; },
      move() { log.push("b-move"); return true; },
      up() { log.push("b-up"); return true; },
      idle() { log.push("b-idle"); },
    });
    assert.equal(runtime.dispatchPointer("down", {}, {}), true);
    assert.deepEqual(log, ["a-down"]);
    log.length = 0;
    assert.equal(runtime.dispatchPointer("move", {}, {}), true);
    assert.deepEqual(log, ["a-move", "b-move"]);
    log.length = 0;
    assert.equal(runtime.dispatchPointer("up", {}, {}), true);
    assert.deepEqual(log, ["a-up", "b-up"]);
    log.length = 0;
    runtime.runPointerIdle({});
    assert.deepEqual(log, ["a-idle", "b-idle"]);
  });
});
