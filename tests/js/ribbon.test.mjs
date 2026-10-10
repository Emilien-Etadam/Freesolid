// Le ruban du noyau : la disposition (ribbon.json) et son rendu
// (ribbon.js). Le DOM est un bouchon minimal — assez pour vérifier
// l'ordre, les classes et la table onglet → bandeau, sans navigateur.

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { existsSync } from "node:fs";

import {
  buildRibbonElement,
  buildTabButton,
  installCoreRibbons,
  isButtonId,
  safeIconSrc,
} from "../../app/ribbon.js";
import { iconSrc } from "../../app/icons.js";
import { FEATURES } from "../../app/features.js";
import LAYOUT from "../../app/ribbon.json" with { type: "json" };

// -- bouchon DOM ---------------------------------------------------------

function element(tag) {
  const el = {
    tagName: tag,
    id: "",
    className: "",
    dataset: {},
    children: [],
    _listeners: {},
    addEventListener(type, fn) {
      (el._listeners[type] ??= []).push(fn);
    },
    click() {
      for (const fn of el._listeners.click ?? []) fn();
    },
    parentElement: null,
    textContent: "",
    appendChild(child) {
      child.parentElement = el;
      el.children.push(child);
      return child;
    },
    insertBefore(child, ref) {
      child.parentElement = el;
      const at = el.children.indexOf(ref);
      el.children.splice(at < 0 ? el.children.length : at, 0, child);
      return child;
    },
    classList: {
      add(name) {
        const parts = el.className ? el.className.split(" ") : [];
        if (!parts.includes(name)) parts.push(name);
        el.className = parts.join(" ");
      },
    },
  };
  return el;
}

function fakeDoc() {
  const header = element("header");
  const topbar = element("div");
  topbar.id = "topbar";
  const push = element("span");
  push.className = "push";
  const sketchbar = element("div");
  sketchbar.id = "sketchbar";
  topbar.appendChild(push);
  header.appendChild(topbar);
  header.appendChild(sketchbar);
  return {
    header, topbar, push, sketchbar,
    createElement: (tag) => element(tag),
    createTextNode: (text) => ({ text }),
    querySelector: (sel) => (sel === "#topbar .push" ? push : null),
    getElementById(id) {
      const walk = (el) => {
        if (el.id === id) return el;
        for (const child of el.children ?? []) {
          if (!child.children) continue;
          const hit = walk(child);
          if (hit) return hit;
        }
        return null;
      };
      return walk(header);
    },
  };
}

/** Texte visible d'un bouton : textContent + nœuds texte ajoutés. */
function buttonText(btn) {
  return btn.textContent
    + btn.children.filter((c) => !c.children).map((c) => c.text).join("");
}

function layoutButtons() {
  const all = [];
  for (const onglet of LAYOUT.onglets) {
    for (const groupe of onglet.groupes ?? []) {
      for (const bouton of groupe.boutons ?? []) {
        if (!bouton.sep) all.push(bouton);
      }
    }
  }
  return all;
}

// -- la disposition elle-même -------------------------------------------

describe("ribbon.json", () => {
  it("couvre chaque fonction du registre FEATURES", () => {
    const ids = new Set(layoutButtons().map((b) => b.id));
    for (const entry of FEATURES) {
      assert.ok(ids.has(entry.button),
        `${entry.button} est dans FEATURES mais pas dans ribbon.json`);
    }
  });

  it("n'a que des ids valides, sans doublon", () => {
    const seen = new Set();
    for (const bouton of layoutButtons()) {
      assert.ok(isButtonId(bouton.id), `id invalide : ${bouton.id}`);
      assert.ok(!seen.has(bouton.id), `id en double : ${bouton.id}`);
      seen.add(bouton.id);
    }
  });

  it("ne référence que des icônes présentes dans app/", () => {
    for (const bouton of layoutButtons()) {
      if (!bouton.icon) continue;
      const src = safeIconSrc(bouton.icon);
      assert.equal(src, iconSrc(bouton.icon));
      assert.match(src, /^icons\/[A-Za-z0-9_.-]+\.svg$/);
      const disk = new URL("../../app/" + src, import.meta.url);
      assert.ok(existsSync(disk), `icône absente : ${bouton.icon}`);
    }
  });

  it("donne un libellé et un titre à chaque bouton", () => {
    for (const bouton of layoutButtons()) {
      assert.ok(bouton.libelle, `libellé absent : ${bouton.id}`);
      assert.ok(bouton.titre, `titre absent : ${bouton.id}`);
    }
  });
});

// -- l'organisation du ruban compact ------------------------------------
// La référence est la maquette validée (docs/maquettes/entete.html) : les
// commandes de tête en grand (deux lignes du ruban), les autres empilées
// deux par deux à leur suite ; l'outil de profil en tête d'onglet.

function groupe(ongletId, libelle) {
  const onglet = LAYOUT.onglets.find((o) => o.id === ongletId);
  return onglet.groupes.find((g) => g.libelle === libelle);
}

function sequence(g) {
  return g.boutons.map((b) => (b.sep ? "|" : b.id));
}

describe("l'organisation transposée", () => {
  it("ordonne Modélisation : volumes de base en grand, puis le reste", () => {
    assert.deepEqual(sequence(groupe("features", "Modélisation")), [
      "btn-pad", "btn-revolution", "btn-pocket", "btn-groove", "btn-hole",
      "btn-loft", "btn-sweep", "btn-helix", "btn-text",
      "btn-graph-feature", "btn-boolean",
    ]);
  });

  it("ouvre l'onglet Fonctions par la préparation, esquisse en tête", () => {
    assert.deepEqual(sequence(groupe("features", "Préparation")),
      ["btn-sketch", "btn-body", "btn-datum"]);
  });

  it("ordonne l'habillage et les transformations", () => {
    assert.deepEqual(sequence(groupe("features", "Habillage")),
      ["btn-fillet", "btn-chamfer", "btn-shell", "btn-draft"]);
    assert.deepEqual(sequence(groupe("features", "Transformations")),
      ["btn-linpattern", "btn-polpattern", "btn-mirror",
        "btn-repeat-variable"]);
  });

  it("met en avant les commandes de tête (taille large)", () => {
    const larges = layoutButtons().filter((b) => b.taille).map((b) => b.id);
    assert.deepEqual(larges, [
      "btn-sketch", "btn-pad", "btn-revolution", "btn-pocket", "btn-groove",
      "btn-hole", "btn-fillet", "btn-chamfer", "btn-shell",
      "btn-linpattern", "btn-curve3d", "ribbon-mass", "btn-newasm",
    ]);
    for (const bouton of layoutButtons()) {
      if (bouton.taille !== undefined) assert.equal(bouton.taille, "large");
    }
  });

  it("met l'outil de profil en tête de l'onglet Surfaces", () => {
    const onglet = LAYOUT.onglets.find((o) => o.id === "surfaces");
    assert.deepEqual(onglet.groupes.map((g) => g.libelle),
      ["Courbes", "Surfaces", "Opérations"]);
  });

  it("ordonne l'assemblage : créer, résoudre, insérer, répéter, éclater", () => {
    const onglet = LAYOUT.onglets.find((o) => o.id === "assembly");
    assert.deepEqual(onglet.groupes.map((g) => g.libelle),
      ["Assemblage", "Liaisons"]);
    assert.deepEqual(sequence(groupe("assembly", "Assemblage")),
      ["btn-newasm", "btn-solve", "btn-insert", "btn-array-comp",
        "btn-explode"]);
    assert.deepEqual(sequence(groupe("assembly", "Liaisons")),
      ["btn-move", "btn-joint"]);
  });

  it("regroupe mesurer, la masse, les équations, la mise en plan et les interférences", () => {
    const onglet = LAYOUT.onglets.find((o) => o.id === "evaluate");
    assert.equal(onglet.libelle, "Évaluer");
    assert.deepEqual(sequence(groupe("evaluate", "Évaluer")), [
      "ribbon-measure", "ribbon-mass", "ribbon-equations", "ribbon-drawing",
      "btn-interf",
    ]);
    const byId = Object.fromEntries(
      groupe("evaluate", "Évaluer").boutons.map((button) => [button.id, button]));
    assert.equal(byId["ribbon-measure"].relais, "btn-measure");
    assert.equal(byId["ribbon-measure"].libelle, "Mesurer");
    assert.equal(byId["ribbon-mass"].relais, "btn-evaluate");
    assert.equal(byId["ribbon-mass"].libelle, "Évaluer");
    assert.equal(byId["ribbon-equations"].relais, "btn-equations");
    assert.equal(byId["ribbon-equations"].libelle, "Équations");
    assert.equal(byId["ribbon-drawing"].relais, "btn-drawing");
    assert.equal(byId["btn-interf"].libelle, "Interférences");
    assert.equal(byId["btn-interf"].relais, undefined);
  });
});

// -- le rendu ------------------------------------------------------------

describe("installCoreRibbons", () => {
  it("rend la table, les onglets et les bandeaux dans l'ordre", () => {
    const doc = fakeDoc();
    const map = installCoreRibbons(doc, LAYOUT);
    assert.deepEqual(map, {
      features: "ribbon-features",
      sketch: "sketchbar",
      surfaces: "ribbon-surfaces",
      evaluate: "ribbon-evaluate",
      assembly: "ribbon-assembly",
    });

    const tabs = doc.topbar.children.filter((c) => c.className?.includes("tab"));
    assert.deepEqual(tabs.map((t) => t.dataset.tab),
      ["features", "sketch", "surfaces", "evaluate", "assembly"]);
    assert.deepEqual(tabs.map((t) => t.textContent),
      ["Fonctions", "Esquisse", "Surfaces", "Évaluer", "Assemblage"]);
    // Les onglets précèdent .push (la droite de la topbar reste à droite).
    assert.equal(doc.topbar.children.at(-1), doc.push);

    // Le premier onglet est actif, et lui seul.
    assert.deepEqual(tabs.map((t) => t.className),
      ["tab active", "tab", "tab", "tab", "tab"]);

    // Les bandeaux construits précèdent #sketchbar, dans l'ordre du JSON.
    const bars = doc.header.children.filter((c) => c !== doc.topbar);
    assert.deepEqual(bars.map((b) => b.id),
      ["ribbon-features", "ribbon-surfaces", "ribbon-evaluate",
        "ribbon-assembly", "sketchbar"]);
    assert.equal(bars[0].className, "ribbon active");
    assert.equal(bars[1].className, "ribbon");
  });

  it("rend le bandeau Fonctions conforme au smoke", () => {
    const doc = fakeDoc();
    installCoreRibbons(doc, LAYOUT);
    const features = doc.getElementById("ribbon-features");
    const labels = features.children.map(
      (g) => g.children.find((c) => c.className === "ribbon-group-label"));
    assert.deepEqual(labels.map((l) => l.textContent),
      ["Préparation", "Modélisation", "Habillage", "Transformations"]);

    const pad = doc.getElementById("btn-pad");
    assert.equal(pad.title, "Extrusion");
    assert.equal(buttonText(pad), "Extrusion");
    const img = pad.children.find((c) => c.tagName === "img");
    assert.equal(img.src, "icons/nodes_extrude.svg");

    // Icône et libellé : l'icône d'abord, le texte ensuite.
    const solve = doc.getElementById("btn-solve");
    assert.equal(solve.children[0].tagName, "img");
    assert.equal(buttonText(solve), "Résoudre");
  });

  it("mappe l'onglet esquisse sur le bandeau déjà présent", () => {
    const doc = fakeDoc();
    const map = installCoreRibbons(doc, LAYOUT);
    assert.equal(map.sketch, "sketchbar");
    // Aucun ribbon-sketch construit : l'élément existant sert de bandeau.
    assert.equal(doc.getElementById("ribbon-sketch"), null);
  });

  it("ignore un onglet invalide, en double, ou sans élément", () => {
    const doc = fakeDoc();
    const map = installCoreRibbons(doc, {
      onglets: [
        { id: "un", libelle: "Un", groupes: [] },
        { id: "un", libelle: "Doublon", groupes: [] },
        { id: "Maj", libelle: "Id refusé", groupes: [] },
        { id: "absent", libelle: "Élément fantôme", element: "nulle-part" },
      ],
    });
    assert.deepEqual(map, { un: "ribbon-un" });
    const tabs = doc.topbar.children.filter((c) => c.className?.includes("tab"));
    assert.equal(tabs.length, 1);
  });
});

describe("buildRibbonElement", () => {
  it("rend la classe large pour taille \"large\", et rien d'autre", () => {
    const doc = fakeDoc();
    const ribbon = buildRibbonElement(doc, "essai", [{
      libelle: "G",
      boutons: [
        { id: "btn-grand", libelle: "Grand", taille: "large" },
        { id: "btn-moyen", libelle: "Moyen" },
        { id: "btn-inconnu", libelle: "Inconnu", taille: "xl" },
      ],
    }]);
    const btns = ribbon.children[0].children[0].children;
    assert.deepEqual(btns.map((b) => b.className), ["large", "", ""]);
  });

  it("rend un séparateur pour une entrée { sep: true }", () => {
    const doc = fakeDoc();
    const ribbon = buildRibbonElement(doc, "essai", [{
      libelle: "G",
      boutons: [
        { id: "btn-a", libelle: "A" },
        { sep: true },
        { id: "btn-b", libelle: "B" },
      ],
    }]);
    const rangee = ribbon.children[0].children[0].children;
    assert.deepEqual(
      rangee.map((el) => (el.className === "sep" ? "|" : el.id)),
      ["btn-a", "|", "btn-b"]);
  });

  it("un relais déclenche le bouton déjà présent", () => {
    const doc = fakeDoc();
    const target = doc.createElement("button");
    target.id = "btn-measure";
    let clicks = 0;
    target.addEventListener("click", () => { clicks += 1; });
    doc.header.appendChild(target);
    const ribbon = buildRibbonElement(doc, "evaluate", [{
      libelle: "Évaluer",
      boutons: [{ id: "ribbon-measure", libelle: "Mesurer",
        relais: "btn-measure" }],
    }]);
    ribbon.children[0].children[0].children[0].click();
    assert.equal(clicks, 1);
  });

  it("filtre les ids et les icônes dangereuses, honore disabled", () => {
    const doc = fakeDoc();
    const ribbon = buildRibbonElement(doc, "essai", [{
      libelle: "G",
      boutons: [
        { id: "btn-ok", libelle: "Ok", icon: "../evil.svg" },
        { id: "btn-off", libelle: "Off", disabled: true },
        { id: "<script>", libelle: "Refusé" },
        { id: "btn-http", libelle: "Http", icon: "https://evil.example/x.svg" },
      ],
    }]);
    const btns = ribbon.children[0].children[0].children;
    assert.deepEqual(btns.map((b) => b.id), ["btn-ok", "btn-off", "btn-http"]);
    for (const btn of btns) {
      assert.ok(!btn.children.some((c) => c.tagName === "img"),
        `icône filtrée attendue sur ${btn.id}`);
    }
    assert.equal(btns[1].disabled, true);
  });
});

describe("buildTabButton", () => {
  it("retombe sur l'id quand le libellé manque", () => {
    const doc = fakeDoc();
    assert.equal(buildTabButton(doc, "bijoux", "  ").textContent, "bijoux");
    assert.equal(buildTabButton(doc, "bijoux", "Bijoux").textContent, "Bijoux");
  });
});
