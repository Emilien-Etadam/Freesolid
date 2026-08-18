import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { buildGraph } from "../../app/graph.js";

function byName(graph) {
  return Object.fromEntries(graph.nodes.map((node) => [node.name, node]));
}

function paramEdges(graph) {
  return graph.edges.filter((edge) => edge.kind === "param");
}

describe("buildGraph", () => {
  it("une chaîne esquisse → bossage → congé donne trois couches croissantes", () => {
    const graph = buildGraph({
      features: [
        { name: "Sketch", label: "Esquisse1", kind: "Esquisse", order: 0 },
        { name: "Pad", label: "Bossage1", kind: "Bossage/Base extrudé",
          order: 1, deps: ["Sketch"] },
        { name: "Fillet", label: "Congé1", kind: "Congé",
          order: 2, deps: ["Pad"] },
      ],
    });
    const nodes = byName(graph);
    assert.equal(nodes.Sketch.layer, 0);
    assert.equal(nodes.Pad.layer, 1);
    assert.equal(nodes.Fillet.layer, 2);
    assert.ok(nodes.Sketch.x < nodes.Pad.x);
    assert.ok(nodes.Pad.x < nodes.Fillet.x);
  });

  it("est déterministe : deux appels, mêmes coordonnées", () => {
    const tree = {
      planes: [{ id: "XZ", name: "XZ_Plane", label: "Plan de face" }],
      variables: [{ name: "largeur", value: 20 }],
      features: [
        { name: "Sketch", label: "Esquisse1", kind: "Esquisse", order: 1,
          deps: ["XZ_Plane"] },
        { name: "Pad", label: "Bossage1", kind: "Bossage/Base extrudé",
          order: 2, deps: ["Sketch"],
          driven: { Length: "2 * largeur + 5" } },
      ],
    };
    const a = buildGraph(tree);
    const b = buildGraph(tree);
    assert.deepEqual(
      a.nodes.map((n) => ({ name: n.name, x: n.x, y: n.y, layer: n.layer })),
      b.nodes.map((n) => ({ name: n.name, x: n.x, y: n.y, layer: n.layer })),
    );
    assert.deepEqual(a.edges, b.edges);
  });

  it("compare des identifiants entiers : larg ne matche pas largeur", () => {
    const graph = buildGraph({
      variables: [
        { name: "larg", value: 10 },
        { name: "largeur", value: 20 },
      ],
      features: [{
        name: "Pad", label: "Bossage1", kind: "Bossage/Base extrudé",
        order: 1, driven: { Length: "2 * largeur + 5" },
      }],
    });
    const param = paramEdges(graph);
    assert.equal(param.length, 1);
    assert.equal(param[0].from, "largeur");
    assert.equal(param[0].to, "Pad");
    assert.equal(
      param.some((edge) => edge.from === "larg"),
      false,
    );
  });

  it("plusieurs variables dans une expression → une arête par variable", () => {
    const graph = buildGraph({
      variables: [
        { name: "largeur", value: 20 },
        { name: "hauteur", value: 10 },
      ],
      features: [{
        name: "Pad", label: "Bossage1", kind: "Bossage/Base extrudé",
        order: 1, driven: { Length: "largeur + hauteur / 2" },
      }],
    });
    const param = paramEdges(graph);
    assert.equal(param.length, 2);
    const from = new Set(param.map((edge) => edge.from));
    assert.deepEqual([...from].sort(), ["hauteur", "largeur"]);
    assert.ok(param.every((edge) => edge.to === "Pad"));
  });

  it("aucune extrémité d'arête hors des nœuds", () => {
    const graph = buildGraph({
      planes: [{ id: "XZ", name: "XZ_Plane", label: "Plan de face" }],
      variables: [
        { name: "larg", value: 10 },
        { name: "largeur", value: 20 },
      ],
      features: [
        {
          name: "Sketch", label: "Esquisse1", kind: "Esquisse", order: 1,
          type: "Sketcher::SketchObject", deps: ["XZ_Plane"],
        },
        {
          name: "Pad", label: "Bossage1", kind: "Bossage/Base extrudé",
          order: 2, deps: ["Sketch", "Fantome"],
          driven: { Length: "2 * largeur + 5" },
          children: [{
            name: "SketchIn", label: "Esquisse2", kind: "Esquisse",
            type: "Sketcher::SketchObject", order: 1,
          }],
        },
        {
          name: "Bool", label: "Combiner", kind: "Combiner",
          order: 3, deps: ["Body001"],
        },
      ],
      surfaces: [{
        name: "Extrude", label: "Surface extrudée", order: 4,
        deps: ["SketchSurf"],
        children: [{
          name: "SketchSurf", label: "Esquisse3", kind: "Esquisse",
          type: "Sketcher::SketchObject", order: 3,
        }],
      }],
      bodies: [
        { name: "Body", label: "Corps" },
        { name: "Body001", label: "Corps2" },
      ],
    });
    const names = new Set(graph.nodes.map((node) => node.name));
    for (const edge of graph.edges) {
      assert.ok(names.has(edge.from), `from manquant : ${edge.from}`);
      assert.ok(names.has(edge.to), `to manquant : ${edge.to}`);
    }
    assert.equal(names.has("Fantome"), false);
    assert.equal(names.has("Body"), false);
    assert.equal(names.has("Body001"), true);
    assert.equal(names.has("larg"), true);
    assert.equal(
      graph.edges.some((e) => e.from === "larg" || e.to === "larg"),
      false,
    );
  });

  it("arbre vide ou sections absentes → graphe vide, pas d'exception", () => {
    assert.deepEqual(buildGraph(null), { nodes: [], edges: [] });
    assert.deepEqual(buildGraph(undefined), { nodes: [], edges: [] });
    assert.deepEqual(buildGraph({}), { nodes: [], edges: [] });
    assert.deepEqual(buildGraph({ features: null, planes: null }),
      { nodes: [], edges: [] });
    assert.deepEqual(buildGraph({ features: [], surfaces: [],
      planes: [], bodies: [], variables: [] }),
      { nodes: [], edges: [] });
  });
});
