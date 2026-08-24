import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { createPluginApi, loadClientPlugins, pluginEntryUrl } from "../../app/plugins.js";

describe("pluginEntryUrl", () => {
  it("n'accepte que /plugins/<nom>/plugin.js avec le même nom", () => {
    assert.equal(
      pluginEntryUrl("bijouterie", "/plugins/bijouterie/plugin.js"),
      "/plugins/bijouterie/plugin.js",
    );
    assert.equal(
      pluginEntryUrl("bijouterie", "/plugins/autre/plugin.js"),
      "",
    );
    assert.equal(
      pluginEntryUrl("bijouterie", "/plugins/bijouterie/../x.js"),
      "",
    );
    assert.equal(
      pluginEntryUrl("bijouterie", "https://evil.example/plugin.js"),
      "",
    );
    assert.equal(pluginEntryUrl("bijouterie", "/app/main.js"), "");
    assert.equal(pluginEntryUrl("", "/plugins/bijouterie/plugin.js"), "");
    assert.equal(pluginEntryUrl("bijouterie", null), "");
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
      (tree) => tree.gems ?? [],
      (gem) => ({ name: gem.name }),
    );
    runtime.renderTreeRows(
      { gems: [{ name: "Semis" }, { name: "Semis001" }] },
      { append: (row) => rows.push(row) },
    );
    assert.deepEqual(rows, [{ name: "Semis" }, { name: "Semis001" }]);
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
});
