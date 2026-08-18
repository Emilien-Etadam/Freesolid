import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  buildGraph,
  countEdgeCrossings,
  edgeCurvePath,
  expressionForVariable,
  freezeDrivenValues,
  GRAPH_DRESSUP_REASON,
  graphCreateProfile,
  graphFeaturePlaceable,
  graphPaletteItems,
  isConstructWireSource,
  isParamWireSource,
  isParamWireTarget,
  paramChoiceCaption,
} from "../../app/graph.js";
import { FEATURES, NO_SKETCH_AVAILABLE } from "../../app/features.js";

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

  it("les nœuds après la barre portent afterBar, pas les variables", () => {
    const graph = buildGraph({
      tip: "Pad",
      variables: [{ name: "largeur", value: 20 }],
      planes: [{ id: "XZ", name: "XZ_Plane", label: "Plan de face" }],
      features: [
        { name: "Sketch", label: "Esquisse1", kind: "Esquisse",
          type: "Sketcher::SketchObject", order: 0 },
        { name: "Pad", label: "Bossage1", kind: "Bossage/Base extrudé",
          type: "PartDesign::Pad", order: 1, deps: ["Sketch"] },
        { name: "Fillet", label: "Congé1", kind: "Congé",
          type: "PartDesign::Fillet", order: 2, deps: ["Pad"],
          children: [{
            name: "SketchIn", label: "Esquisse2", kind: "Esquisse",
            type: "Sketcher::SketchObject", order: 3,
          }] },
      ],
    });
    const nodes = byName(graph);
    assert.equal(nodes.Pad.afterBar, false);
    assert.equal(nodes.Sketch.afterBar, false);
    assert.equal(nodes.Fillet.afterBar, true);
    assert.equal(nodes.SketchIn.afterBar, true);
    assert.equal(nodes.largeur.afterBar, false);
    assert.equal(nodes.XZ_Plane.afterBar, false);
  });
});

describe("fil paramétrique", () => {
  it("seule une variable est une source, seule une fonction est une cible", () => {
    assert.equal(isParamWireSource("variable"), true);
    assert.equal(isParamWireSource("feature"), false);
    assert.equal(isParamWireSource("sketch"), false);
    assert.equal(isParamWireTarget("feature"), true);
    assert.equal(isParamWireTarget("sketch"), false);
    assert.equal(isParamWireTarget("plane"), false);
    assert.equal(isParamWireTarget("datum"), false);
    assert.equal(isParamWireTarget("surface"), false);
    assert.equal(isParamWireTarget("body"), false);
    assert.equal(isParamWireTarget("variable"), false);
  });

  it("un fil constructif ne part que d'une esquisse", () => {
    assert.equal(isConstructWireSource("sketch"), true);
    assert.equal(isConstructWireSource("feature"), false);
    assert.equal(isConstructWireSource("variable"), false);
    assert.equal(isConstructWireSource("plane"), false);
  });

  it("l'expression posée préfixe le VarSet, pas l'identifiant nu", () => {
    assert.equal(expressionForVariable("largeur"), "Variables.largeur");
    assert.equal(expressionForVariable(""), "");
    assert.equal(expressionForVariable(null), "");
  });

  it("une coupure fige la valeur courante des cotes pilotées, pas zéro", () => {
    const values = freezeDrivenValues([
      { prop: "Length", value: 25, expr: "Variables.largeur" },
      { prop: "Angle", value: 12 },
      { prop: "Radius", value: 3, expr: "2 * largeur + 5" },
    ], "largeur");
    assert.deepEqual(values, { Length: 25, Radius: 3 });
    assert.equal(values.Length === 0, false);
  });

  it("une coupure ne prend pas larg pour largeur", () => {
    const values = freezeDrivenValues([
      { prop: "Length", value: 20, expr: "2 * largeur + 5" },
      { prop: "Angle", value: 8, expr: "larg" },
    ], "largeur");
    assert.deepEqual(values, { Length: 20 });
  });

  it("sans expression, sans tableau, sans identifiant → rien à figer", () => {
    assert.deepEqual(freezeDrivenValues(null, "largeur"), {});
    assert.deepEqual(freezeDrivenValues([], "largeur"), {});
    assert.deepEqual(freezeDrivenValues(
      [{ prop: "Length", value: 10 }], "largeur"), {});
    assert.deepEqual(freezeDrivenValues(
      [{ prop: "Length", value: 10, expr: "Variables.largeur" }], ""), {});
  });

  it("le libellé du choix réutilise PROP_LABELS et signale une cote déjà pilotée", () => {
    const labels = { Length: ["Profondeur", "mm"], Occurrences: ["Nombre d'occurrences", ""] };
    assert.equal(
      paramChoiceCaption({ prop: "Length", value: 10 }, labels),
      "Profondeur (mm)",
    );
    assert.equal(
      paramChoiceCaption(
        { prop: "Length", value: 25, expr: "Variables.largeur" }, labels),
      "Profondeur (mm) — déjà « Variables.largeur »",
    );
    assert.equal(
      paramChoiceCaption({ prop: "Occurrences", value: 3 }, labels),
      "Nombre d'occurrences",
    );
    assert.equal(paramChoiceCaption(null, labels), "");
  });
});

describe("lisibilité du graphe", () => {
  const crossingTree = {
    features: [
      { name: "A", label: "A", order: 0 },
      { name: "B", label: "B", order: 1 },
      { name: "C", label: "C", order: 2, deps: ["B"] },
      { name: "D", label: "D", order: 3, deps: ["A"] },
    ],
  };

  it("le barycentre réduit les croisements par rapport au tri par order", () => {
    const ordered = buildGraph(crossingTree, { reduceCrossings: false });
    const reduced = buildGraph(crossingTree);
    const before = countEdgeCrossings(ordered);
    const after = countEdgeCrossings(reduced);
    assert.equal(before, 1);
    assert.ok(after < before, `croisements ${after} ≮ ${before}`);
    assert.equal(after, 0);
  });

  it("reste déterministe après réduction de croisements", () => {
    const a = buildGraph(crossingTree);
    const b = buildGraph(crossingTree);
    assert.deepEqual(
      a.nodes.map((n) => ({ name: n.name, x: n.x, y: n.y, layer: n.layer })),
      b.nodes.map((n) => ({ name: n.name, x: n.x, y: n.y, layer: n.layer })),
    );
  });

  it("la courbe d'arête est une Bézier cubique à poignées horizontales", () => {
    assert.equal(
      edgeCurvePath(0, 10, 200, 50),
      "M 0,10 C 90,10 110,50 200,50",
    );
    const short = edgeCurvePath(0, 0, 20, 0);
    assert.match(short, /^M 0,0 C /);
    assert.equal(edgeCurvePath(0, 0, 20, 0), edgeCurvePath(0, 0, 20, 0));
  });
});

describe("palette constructive", () => {
  const pad = FEATURES.find((entry) => entry.button === "btn-pad");
  const fillet = FEATURES.find((entry) => entry.button === "btn-fillet");
  const combine = FEATURES.find((entry) => entry.button === "btn-boolean");
  const sketch = { name: "Sketch", label: "Esquisse1" };
  const treeWithSketch = {
    features: [{ name: "Sketch", type: "Sketcher::SketchObject" }],
  };
  const faceSel = { kind: "face", face: 0 };
  const edgeSel = { kind: "edges", edges: [1, 2] };

  it("FEATURES porte les marqueurs dressup / sketchProfile, sans table parallèle", () => {
    assert.equal(FEATURES.length, 22);
    assert.equal(pad?.sketchProfile, true);
    assert.equal(pad?.dressup, undefined);
    assert.equal(fillet?.dressup, true);
    assert.equal(fillet?.sketchProfile, undefined);
    assert.equal(combine?.dressup, undefined);
    assert.equal(combine?.sketchProfile, undefined);
    assert.equal(FEATURES.filter((entry) => entry.dressup).length, 5);
    assert.equal(FEATURES.filter((entry) => entry.sketchProfile).length, 4);
  });

  it("le profil de création est l'esquisse sélectionnée, sinon la dernière libre", () => {
    assert.deepEqual(
      graphCreateProfile({ selectedSketch: sketch, lastTree: treeWithSketch }),
      sketch,
    );
    assert.equal(
      graphCreateProfile({ selectedSketch: sketch, lastTree: { features: [] } })
        ?.name,
      "Sketch",
    );
    assert.equal(
      graphCreateProfile({ selectedSketch: null, lastTree: treeWithSketch })
        ?.name,
      "Sketch",
    );
    assert.equal(graphCreateProfile({ lastTree: { features: [] } }), null);
    assert.equal(graphCreateProfile(null), null);
  });

  it("un habillage est grisé sans face, actif avec une face ou des arêtes", () => {
    const none = graphFeaturePlaceable(fillet, { selection: null });
    assert.equal(none.enabled, false);
    assert.equal(none.reason, GRAPH_DRESSUP_REASON);
    const face = graphFeaturePlaceable(fillet, { selection: faceSel });
    assert.equal(face.enabled, true);
    assert.equal(face.reason, null);
    const edges = graphFeaturePlaceable(fillet, { selection: edgeSel });
    assert.equal(edges.enabled, true);
  });

  it("un bossage est grisé sans esquisse, actif avec une esquisse sélectionnée", () => {
    const none = graphFeaturePlaceable(pad, { lastTree: { features: [] } });
    assert.equal(none.enabled, false);
    assert.equal(none.reason, NO_SKETCH_AVAILABLE);
    assert.equal(none.profile, null);
    const selected = graphFeaturePlaceable(pad, {
      selectedSketch: sketch, lastTree: { features: [] },
    });
    assert.equal(selected.enabled, true);
    assert.equal(selected.profile?.name, "Sketch");
    const latest = graphFeaturePlaceable(pad, {
      selectedSketch: null, lastTree: treeWithSketch,
    });
    assert.equal(latest.enabled, true);
    assert.equal(latest.profile?.name, "Sketch");
  });

  it("la palette reprend icône et titre de FEATURES, et le profil de la création", () => {
    const items = graphPaletteItems(FEATURES, {
      selectedSketch: sketch,
      lastTree: { features: [] },
      selection: null,
    });
    assert.equal(items.length, 22);
    const padItem = items.find((item) => item.button === "btn-pad");
    const filletItem = items.find((item) => item.button === "btn-fillet");
    assert.equal(padItem.title, pad.title);
    assert.equal(padItem.icon, pad.icon);
    assert.equal(padItem.enabled, true);
    assert.equal(padItem.profile?.name, "Sketch");
    assert.equal(filletItem.title, fillet.title);
    assert.equal(filletItem.enabled, false);
    assert.equal(filletItem.reason, GRAPH_DRESSUP_REASON);
    assert.deepEqual(graphPaletteItems(null), []);
  });
});
