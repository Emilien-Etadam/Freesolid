// Multilingue : t(), variables, choix de langue, dictionnaire anglais.
// Le français est la langue source : un texte sans traduction reste tel quel.

import { describe, it, afterEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";

import {
  DICTIONARIES, currentLang, hasTranslation, setLang, t, translateDom,
} from "../../app/i18n.js";
import LAYOUT from "../../app/ribbon.json" with { type: "json" };
import { FEATURES } from "../../app/features.js";

const EN = DICTIONARIES.en;
const APP = new URL("../../app/", import.meta.url);

afterEach(() => setLang("fr"));

describe("t()", () => {
  it("rend le texte source en français, la traduction en anglais", () => {
    assert.equal(t("Bossage extrudé"), "Bossage extrudé");
    setLang("en");
    assert.equal(t("Bossage extrudé"), "Extruded Boss");
    assert.equal(currentLang(), "en");
  });

  it("laisse tel quel un texte sans traduction, et les non-textes", () => {
    setLang("en");
    assert.equal(t("Texte qui n'existe nulle part"), "Texte qui n'existe nulle part");
    assert.equal(t(undefined), undefined);
    assert.equal(t(42), 42);
    assert.equal(hasTranslation("Esquisse"), true);
    assert.equal(hasTranslation("zzz"), false);
  });

  it("remplace les variables dans les deux langues", () => {
    assert.equal(t("Moteur prêt — FreeCAD {v}", { v: "1.1.3" }), "Moteur prêt — FreeCAD 1.1.3");
    setLang("en");
    assert.equal(t("Moteur prêt — FreeCAD {v}", { v: "1.1.3" }), "Engine ready — FreeCAD 1.1.3");
    assert.equal(t("{a} et {b}", { a: 1 }), "1 et {b}");
  });

  it("retombe sur le français pour une langue inconnue", () => {
    assert.equal(setLang("klingon"), "fr");
    assert.equal(setLang("en"), "en");
  });
});

describe("dictionnaire anglais", () => {
  const sources = readdirSync(APP)
    .filter((f) => f.endsWith(".js") || f.endsWith(".html") || f.endsWith(".json"))
    .map((f) => readFileSync(new URL(f, APP), "utf8"))
    .join("\n")
    // Littéraux JS coupés par « " + " » : on les recolle avant de chercher.
    .replace(/"\s*\+\s*\n?\s*"/g, "")
    .replace(/\\"/g, "\"")
    .replace(/\\n/g, "\n");

  it("n'a pas d'entrée orpheline : chaque clé existe dans app/", () => {
    const orphans = Object.keys(EN).filter((key) => !sources.includes(key));
    assert.deepEqual(orphans, []);
  });

  it("couvre chaque libellé et infobulle du ruban", () => {
    const missing = [];
    const walk = (x) => {
      if (Array.isArray(x)) return x.forEach(walk);
      if (x && typeof x === "object") {
        for (const [k, v] of Object.entries(x)) {
          if ((k === "libelle" || k === "titre") && typeof v === "string" && !(v in EN)) missing.push(v);
          walk(v);
        }
      }
    };
    walk(LAYOUT);
    assert.deepEqual(missing, []);
  });

  it("couvre les titres des panneaux de fonctions", () => {
    const missing = Object.values(FEATURES)
      .map((f) => f.title).filter((title) => title && !(title in EN));
    assert.deepEqual(missing, []);
  });

  it("garde les mêmes variables que le texte source", () => {
    const vars = (s) => (s.match(/\{\w+\}/g) ?? []).sort().join(",");
    const bad = Object.entries(EN).filter(([fr, en]) => vars(fr) !== vars(en));
    assert.deepEqual(bad, []);
  });
});

describe("translateDom", () => {
  it("ne touche à rien en français et sans DOM", () => {
    assert.equal(translateDom(null), 0);
    assert.equal(translateDom({}), 0);
  });

  it("traduit nœuds texte et attributs avec un DOM minimal", () => {
    setLang("en");
    const text = { nodeValue: "  Esquisse  ", parentElement: { tagName: "BUTTON" } };
    const attrs = { title: "Nouvelle pièce" };
    const el = {
      getAttribute: (k) => attrs[k] ?? null,
      setAttribute: (k, v) => { attrs[k] = v; },
    };
    const root = {
      ownerDocument: { createTreeWalker: () => {
        let done = false;
        return { nextNode: () => (done ? null : (done = true, text)) };
      } },
      querySelectorAll: () => [el],
    };
    assert.equal(translateDom(root), 2);
    assert.equal(text.nodeValue, "  Sketch  ");
    assert.equal(attrs.title, "New part");
  });
});
