import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { loadClientPlugins, pluginEntryUrl } from "../../app/plugins.js";

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
