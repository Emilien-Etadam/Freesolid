import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  buildGraph,
  composeGraphPayload,
  connectGraphEdge,
  countEdgeCrossings,
  defaultFieldValue,
  defaultPortLiteral,
  edgeCurvePath,
  edgeMidpoint,
  edgeSubCaption,
  expressionForVariable,
  freezeDrivenValues,
  GRAPH_DRESSUP_REASON,
  functionEdgeEnds,
  graphCreateProfile,
  graphFeaturePlaceable,
  graphHasScript,
  graphNodePaletteGroups,
  graphPaletteItems,
  graphParamLine,
  graphScriptSources,
  graphVisibleParams,
  isConstructWireSource,
  isGraphFeature,
  isRepeatFeature,
  isParamWireSource,
  isParamWireTarget,
  layoutFunctionGraph,
  minimalGraphCurve,
  minimalGraphFeature,
  minimalRepeatGraph,
  newGraphNode,
  nextGraphNodeId,
  nodeIdFromGraphError,
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

  it("reporte dep_subs sur l'arête et params sur le nœud", () => {
    const graph = buildGraph({
      features: [
        { name: "Sketch", label: "Esquisse1", kind: "Esquisse", order: 0,
          deps: ["XY_Plane"] },
        { name: "Pad", label: "Bossage1", kind: "Bossage/Base extrudé",
          order: 1, deps: ["Sketch"],
          params: [{ prop: "Length", value: 12 }] },
        { name: "Fillet", label: "Congé1", kind: "Congé",
          order: 2, deps: ["Pad"],
          dep_subs: { Pad: ["Edge3", "Edge7"] } },
      ],
      planes: [{ id: "XY", name: "XY_Plane", label: "Plan de dessus" }],
    });
    const nodes = byName(graph);
    assert.deepEqual(nodes.Pad.params, [{ prop: "Length", value: 12 }]);
    assert.equal(nodes.Pad.height, 32);
    const filletEdge = graph.edges.find(
      (edge) => edge.kind === "geom" && edge.from === "Pad" && edge.to === "Fillet");
    assert.deepEqual(filletEdge.subs, ["Edge3", "Edge7"]);
    const padEdge = graph.edges.find(
      (edge) => edge.kind === "geom" && edge.from === "Sketch" && edge.to === "Pad");
    assert.equal("subs" in padEdge, false);
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

describe("nature des liens N007", () => {
  const labels = { Length: ["Profondeur", "mm"], Radius: ["Rayon", "mm"] };

  it("une arête nomme le sous-élément, +N s'il y en a plusieurs", () => {
    assert.equal(edgeSubCaption(["Face3"]), "Face3");
    assert.equal(edgeSubCaption(["Edge3", "Edge7"]), "Edge3 +1");
    assert.equal(edgeSubCaption(["Edge3", "Edge7", "Edge8"]), "Edge3 +2");
    assert.equal(edgeSubCaption([]), "");
    assert.equal(edgeSubCaption(null), "");
  });

  it("le nœud reprend PROP_LABELS et préfixe Σ une cote pilotée", () => {
    assert.equal(
      graphParamLine({ prop: "Length", value: 12 }, labels),
      "Profondeur 12",
    );
    assert.equal(
      graphParamLine(
        { prop: "Length", value: 25, expr: "2 * Variables.largeur" }, labels),
      "Σ Profondeur 25",
    );
    assert.equal(graphParamLine(null, labels), "");
  });

  it("ne montre que les premières cotes dans le nœud", () => {
    const params = [
      { prop: "Length", value: 12 },
      { prop: "Radius", value: 3 },
      { prop: "Size", value: 1 },
    ];
    assert.equal(graphVisibleParams(params).length, 1);
    assert.equal(graphVisibleParams(params)[0].prop, "Length");
  });

  it("le milieu de l'arête est le centre du segment", () => {
    assert.deepEqual(edgeMidpoint(0, 10, 200, 50), { x: 100, y: 30 });
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
    assert.equal(FEATURES.length, 24);
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
    assert.equal(items.length, 24);
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

const VOCAB = [
  { type: "nombre", label: "Nombre", inputs: [],
    fields: [{ key: "value", label: "Valeur", kind: "number" }], shape: false },
  { type: "serie", label: "Série", inputs: [
    { key: "depart", label: "Départ" },
    { key: "pas", label: "Pas" },
    { key: "nombre", label: "Nombre" },
  ], shape: false },
  { type: "vecteur", label: "Vecteur", inputs: [
    { key: "x", label: "X" }, { key: "y", label: "Y" }, { key: "z", label: "Z" },
  ], shape: false },
  { type: "cylindre", label: "Cylindre", inputs: [
    { key: "rayon", label: "Rayon" },
    { key: "hauteur", label: "Hauteur" },
    { key: "ancrage", label: "Ancrage", kind: "point" },
  ], shape: true },
  { type: "cercle", label: "Cercle", inputs: [
    { key: "rayon", label: "Rayon" },
    { key: "point", label: "Point", kind: "point" },
    { key: "direction", label: "Direction", kind: "point" },
  ], shape: true },
];

describe("composition du graphe interne", () => {
  it("un fil vers un port inconnu est refusé avant l'envoi", () => {
    const draft = {
      nodes: [
        { id: "s", type: "serie", depart: 0, pas: 10, nombre: 3 },
        { id: "c", type: "cylindre", rayon: 3, hauteur: 10,
          ancrage: { x: 0, y: 0, z: 0 } },
      ],
      edges: [{ from: "s", to: "c", input: "diametre" }],
      output: "c",
    };
    const result = composeGraphPayload(draft, VOCAB);
    assert.equal(result.ok, false);
    assert.match(result.error, /entrée inconnue « diametre »/);
    assert.equal(result.node, "c");
    const wired = connectGraphEdge(draft, "s", "c", "diametre", VOCAB);
    assert.equal(wired.ok, false);
    assert.match(wired.error, /entrée inconnue/);
  });

  it("un port sans fil prend son littéral", () => {
    const draft = {
      nodes: [
        { id: "s", type: "serie", depart: 0, pas: 5, nombre: 2 },
        { id: "c", type: "cylindre", rayon: 4, hauteur: 12,
          ancrage: { x: 1, y: 2, z: 3 } },
      ],
      edges: [{ from: "s", to: "c", input: "rayon" }],
      output: "c",
    };
    const result = composeGraphPayload(draft, VOCAB);
    assert.equal(result.ok, true);
    const cyl = result.graph.nodes.find((node) => node.id === "c");
    assert.equal("rayon" in cyl, false);
    assert.equal(cyl.hauteur, 12);
    assert.deepEqual(cyl.ancrage, { x: 1, y: 2, z: 3 });
    assert.deepEqual(result.graph.edges, [
      { from: "s", to: "c", input: "rayon" },
    ]);
    assert.equal(result.graph.output, "c");
  });

  it("la sortie désignée est unique", () => {
    const draft = {
      nodes: [
        { id: "a", type: "cylindre", rayon: 1, hauteur: 1,
          ancrage: { x: 0, y: 0, z: 0 } },
        { id: "b", type: "cylindre", rayon: 2, hauteur: 2,
          ancrage: { x: 0, y: 0, z: 0 } },
      ],
      edges: [],
      output: ["a", "b"],
    };
    const result = composeGraphPayload(draft, VOCAB);
    assert.equal(result.ok, false);
    assert.match(result.error, /unique/);
  });

  it("conserve pos dans le JSON persisté", () => {
    const draft = minimalGraphFeature();
    const result = composeGraphPayload(draft, VOCAB);
    assert.equal(result.ok, true);
    assert.deepEqual(result.graph.nodes[0].pos, [240, 80]);
  });

  it("un cercle pour une courbe, un cylindre pour un solide", () => {
    const solid = minimalGraphFeature();
    assert.equal(solid.nodes[0].type, "cylindre");
    assert.equal(solid.output, "cyl");
    const curve = minimalGraphCurve();
    assert.equal(curve.nodes[0].type, "cercle");
    assert.equal(curve.output, "circ");
    assert.equal(curve.nodes[0].rayon, 10);
    assert.deepEqual(curve.nodes[0].point, { x: 0, y: 0, z: 0 });
    assert.deepEqual(curve.nodes[0].direction, { x: 0, y: 0, z: 1 });
    assert.deepEqual(curve.nodes[0].pos, [240, 80]);
    const composed = composeGraphPayload(curve, VOCAB);
    assert.equal(composed.ok, true);
    assert.equal(composed.graph.nodes[0].type, "cercle");
  });

  it("Fonction graphe : un select, trois choix, pas de contradiction", () => {
    const entry = FEATURES.find((item) => item.button === "btn-graph-feature");
    const select = entry.groups()[0].rows[0];
    assert.equal(select.key, "mode");
    assert.deepEqual(select.options, [
      ["fuse", "Solide — Ajouter"],
      ["cut", "Solide — Soustraire"],
      ["curve", "Courbe ou surface"],
    ]);
    const fused = entry.build({ mode: "fuse" });
    assert.equal(fused.op, "add_graph_feature");
    assert.equal(fused.params.mode, "fuse");
    assert.equal(fused.params.graph.nodes[0].type, "cylindre");
    const cut = entry.build({ mode: "cut" });
    assert.equal(cut.params.mode, "cut");
    const curved = entry.build({ mode: "curve" });
    assert.equal("mode" in curved.params, false);
    assert.equal(curved.params.graph.nodes[0].type, "cercle");
  });

  it("newGraphNode pose les littéraux par défaut du vocabulaire", () => {
    const spec = VOCAB.find((item) => item.type === "cylindre");
    const node = newGraphNode(spec, nextGraphNodeId([]), { x: 10, y: 20 });
    assert.equal(node.id, "n1");
    assert.equal(node.rayon, 1);
    assert.deepEqual(node.ancrage, { x: 0, y: 0, z: 0 });
    assert.deepEqual(node.pos, [10, 20]);
    assert.equal(defaultPortLiteral({ kind: "point" }).x, 0);
  });

  it("le nœud fautif d'un GraphError est l'identifiant, pas le type", () => {
    assert.equal(
      nodeIdFromGraphError("nœud « pts (point) » : listes de longueurs 3 et 5"),
      "pts",
    );
    assert.equal(
      nodeIdFromGraphError("cycle détecté dans le graphe (nœud « a (calcul) »)"),
      "a",
    );
    assert.equal(nodeIdFromGraphError("le graphe n'a pas de nœud de sortie"),
      null);
  });

  it("isGraphFeature lit le champ graph de l'arbre, pas le type FreeCAD", () => {
    assert.equal(isGraphFeature({ graph: { nodes: [] } }), true);
    assert.equal(isGraphFeature({ type: "PartDesign::Boolean" }), false);
    assert.equal(isRepeatFeature({ repeat: { features: [] } }), true);
    assert.equal(isRepeatFeature({ graph: { nodes: [] } }), false);
    assert.equal(minimalRepeatGraph().output, "inst");
    assert.equal(minimalRepeatGraph().nodes[0].type, "instance");
    const repeat = FEATURES.find((entry) => entry.button === "btn-repeat-variable");
    assert.equal(repeat?.title, "Répétition variable");
    assert.equal(repeat?.openGraphEditor, true);
  });

  it("layoutFunctionGraph attache les fils aux ports nommés", () => {
    const draft = {
      nodes: [
        { id: "s", type: "serie", depart: 0, pas: 1, nombre: 2, pos: [0, 0] },
        { id: "c", type: "cylindre", rayon: 3, hauteur: 8,
          ancrage: { x: 0, y: 0, z: 0 }, pos: [200, 0] },
      ],
      edges: [{ from: "s", to: "c", input: "rayon" }],
      output: "c",
    };
    const laid = layoutFunctionGraph(draft, VOCAB);
    const byName = Object.fromEntries(laid.nodes.map((n) => [n.name, n]));
    assert.equal(byName.c.output, true);
    assert.equal(byName.s.inputs.find((p) => p.key === "depart").wired, false);
    assert.equal(byName.c.inputs.find((p) => p.key === "rayon").wired, true);
    const ends = functionEdgeEnds(byName.s, byName.c, "rayon");
    assert.equal(ends.x1, byName.s.x + byName.s.ports.output.x);
    assert.equal(ends.y2, byName.c.y + byName.c.inputs[0].y);
  });

  it("un nœud non implémenté est refusé à la composition", () => {
    const vocab = [
      ...VOCAB,
      { type: "sphere", label: "Sphère", implemented: false,
        reason: "appelle l'API Part — pas encore dans l'évaluateur pur",
        inputs: [{ key: "rayon", label: "Rayon" }], shape: true },
    ];
    const draft = {
      nodes: [{ id: "s", type: "sphere", rayon: 1 }],
      edges: [],
      output: "s",
    };
    const result = composeGraphPayload(draft, vocab);
    assert.equal(result.ok, false);
    assert.match(result.error, /API Part/);
  });
});

describe("palette du catalogue de nœuds", () => {
  it("groupe par catégorie et grise ce qui manque, sans masquer", () => {
    const vocab = [
      { type: "nombre", label: "Nombre", category: "number",
        category_label: "Nombre", icon: "nodes_number.svg",
        implemented: true, inputs: [], shape: false },
      { type: "serie", label: "Série", category: "list",
        category_label: "Liste", icon: "nodes_number_range.svg",
        implemented: true, inputs: [], shape: false },
      { type: "sphere", label: "Sphère", category: "generators",
        category_label: "Générateurs", icon: "nodes_sphere.svg",
        implemented: false,
        reason: "appelle l'API Part — pas encore dans l'évaluateur pur",
        inputs: [], shape: true },
    ];
    const groups = graphNodePaletteGroups(vocab);
    assert.deepEqual(groups.map((g) => g.label),
      ["Nombre", "Liste", "Générateurs"]);
    const sphere = groups[2].items[0];
    assert.equal(sphere.enabled, false);
    assert.match(sphere.reason, /API Part/);
    assert.equal(groups[0].items[0].enabled, true);
    assert.equal(graphNodePaletteGroups(null).length, 0);
  });
});

describe("nœud Python", () => {
  const scriptSpec = {
    type: "script", label: "Python", category: "script",
    category_label: "Python", icon: "nodes_python.svg",
    implemented: true, shape: false,
    inputs: [
      { key: "a", label: "A", kind: "any" },
      { key: "b", label: "B", kind: "any" },
      { key: "c", label: "C", kind: "any" },
    ],
    fields: [{ key: "code", label: "Code", kind: "code" }],
  };

  it("newGraphNode pose le code vide, sans littéraux a/b/c", () => {
    const node = newGraphNode(scriptSpec, "py", { x: 8, y: 9 });
    assert.equal(node.type, "script");
    assert.equal(node.code, "");
    assert.equal("a" in node, false);
    assert.equal("b" in node, false);
    assert.equal("c" in node, false);
    assert.equal(defaultFieldValue({ kind: "code" }), "");
  });

  it("composeGraphPayload conserve le code et les ports optionnels", () => {
    const vocab = [
      ...VOCAB,
      scriptSpec,
    ];
    const draft = {
      nodes: [
        { id: "py", type: "script", code: "return a + 1", a: 4 },
        { id: "c", type: "cylindre", rayon: 3, hauteur: 8,
          ancrage: { x: 0, y: 0, z: 0 } },
      ],
      edges: [{ from: "py", to: "c", input: "rayon" }],
      output: "c",
    };
    const result = composeGraphPayload(draft, vocab);
    assert.equal(result.ok, true);
    const script = result.graph.nodes.find((node) => node.id === "py");
    assert.equal(script.code, "return a + 1");
    assert.equal(script.a, 4);
    assert.equal("b" in script, false);
    assert.equal(graphHasScript(draft), true);
    assert.deepEqual(graphScriptSources(draft), [
      { id: "py", code: "return a + 1" },
    ]);
    assert.equal(graphHasScript(minimalGraphFeature()), false);
  });
});
