// Spline 3D et choix de bords : fonctions pures (sans Three.js).
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { clickPlane, curveProblem, nextPlane, rayPlane } from "../../app/curve3d.js";
import { boundaryText, samePick } from "../../app/panel.js";
import { boundaryParam, deleteFacesBuild, deleteFacesParams, extendParams,
  surfaceFilletParams }
  from "../../app/features.js";

describe("spline 3D : plan de clic", () => {
  it("le plan passe par le dernier point, normale selon le plan choisi", () => {
    assert.deepEqual(clickPlane("XZ", [1, 2, 3]),
      { normal: [0, 1, 0], point: [1, 2, 3] });
    assert.deepEqual(clickPlane("inconnu").normal, [0, 0, 1]);
  });

  it("un rayon vertical touche le plan de dessus à la hauteur du point", () => {
    const point = rayPlane([5, 6, 100], [0, 0, -1], clickPlane("XY", [0, 0, 20]));
    assert.deepEqual(point, [5, 6, 20]);
  });

  it("rayon parallèle ou plan derrière la caméra : pas de point", () => {
    assert.equal(rayPlane([0, 0, 10], [1, 0, 0], clickPlane("XY")), null);
    assert.equal(rayPlane([0, 0, 10], [0, 0, 1], clickPlane("XY")), null);
  });

  it("Tab fait le tour des trois plans", () => {
    assert.equal(nextPlane("XY"), "XZ");
    assert.equal(nextPlane("XZ"), "YZ");
    assert.equal(nextPlane("YZ"), "XY");
  });

  it("dit ce qui manque avant de créer la courbe", () => {
    assert.match(curveProblem([[0, 0, 0]], false), /deux points/);
    assert.match(curveProblem([[0, 0, 0], [1, 0, 0]], true), /trois points/);
    assert.match(curveProblem([[0, 0, 0], [0, 0, 0]], false), /confondus/);
    assert.equal(curveProblem([[0, 0, 0], [0, 0, 30], [20, 0, 50]], false), null);
  });
});

describe("bords de surfaces et de courbes", () => {
  const edge = (name, n) => ({ kind: "boundary", name, label: name, edge: n });

  it("un bord est identifié par objet ET arête", () => {
    assert.equal(samePick(edge("S", 1), edge("S", 1)), true);
    assert.equal(samePick(edge("S", 1), edge("S", 2)), false);
    assert.equal(samePick(edge("S", 1), edge("T", 1)), false);
    assert.equal(samePick({ name: "Sk" }, { kind: "sketch", name: "Sk" }), true);
  });

  it("texte de la zone : arête nommée, courbe par son nom, total au-delà de 3", () => {
    const tr = (s, v) => s.replace(/\{(\w+)\}/g, (_, k) => v[k]);
    assert.equal(boundaryText([edge("Surface", 2)], tr), "Surface · Arête 2");
    assert.equal(boundaryText([{ ...edge("Spline", 0), curve: true }], tr),
      "Spline");
    assert.equal(boundaryText([1, 2, 3, 4].map((n) => edge("S", n)), tr),
      "4 éléments");
  });

  it("remplissage : arête de surface, du solide, ou esquisse entière", () => {
    assert.deepEqual(boundaryParam(edge("S", 3)), { name: "S", edge: 3 });
    assert.deepEqual(boundaryParam({ kind: "boundary", body: true,
      name: "body", edge: 7 }), { body: true, edge: 7 });
    assert.deepEqual(boundaryParam({ kind: "sketch", name: "Sk" }),
      { name: "Sk" });
  });

  it("prolonger : un bord de surface, ou la surface entière", () => {
    assert.deepEqual(extendParams(edge("S", 2), 10),
      { surface: "S", distance: 10, edge: 2 });
    assert.deepEqual(extendParams({ kind: "surface", name: "S" }, 5),
      { surface: "S", distance: 5 });
    assert.equal(extendParams({ ...edge("C", 0), curve: true }, 5), null);
    assert.equal(extendParams(edge("S", 2), 0), null);
  });
});

describe("faces et arêtes d'une même surface", () => {
  const face = (name, n) => ({ kind: "surfface", name, label: name, face: n });
  const edge = (name, n) => ({ kind: "boundary", name, label: name, edge: n });

  it("une face de surface : objet ET numéro", () => {
    assert.equal(samePick(face("S", 1), face("S", 1)), true);
    assert.equal(samePick(face("S", 1), face("T", 1)), false);
  });

  it("supprimer : les faces d'une seule surface", () => {
    assert.deepEqual(deleteFacesParams([face("S", 0), face("S", 2)]),
      { surface: "S", faces: [0, 2] });
    assert.equal(deleteFacesParams([face("S", 0), face("T", 1)]), null);
    assert.equal(deleteFacesParams([]), null);
  });

  it("supprimer : faces du solide ou d'une surface, pas les deux", () => {
    assert.deepEqual(deleteFacesBuild([{ kind: "face", face: 3 }]),
      { op: "add_delete_face", params: { faces: [3] } });
    assert.equal(deleteFacesBuild([face("S", 1)]).op, "surface_delete_faces");
    assert.equal(deleteFacesBuild([{ kind: "face", face: 3 }, face("S", 1)]),
      null);
  });

  it("congé : arêtes d'une seule surface, rayon positif", () => {
    assert.deepEqual(surfaceFilletParams([edge("S", 4)], 3),
      { surface: "S", edges: [4], radius: 3 });
    assert.equal(surfaceFilletParams([edge("S", 4), edge("T", 1)], 3), null);
    assert.equal(surfaceFilletParams([edge("S", 4)], 0), null);
    assert.equal(surfaceFilletParams([{ ...edge("C", 0), curve: true }], 3),
      null);
  });
});

describe("panneaux de fonctions", () => {
  it("chaque fonction décrit ses groupes par une fonction du contexte", async () => {
    const { FEATURES } = await import("../../app/features.js");
    assert.deepEqual(FEATURES.filter((e) => typeof e.groups !== "function")
      .map((e) => e.button), []);
  });
});
