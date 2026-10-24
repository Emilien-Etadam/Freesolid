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
// Récursif : un sous-dossier (features/…) est une source de l'interface ;
// vendor/ n'est pas à nous et lang/ est le dictionnaire lui-même.
const APP_FILES = readdirSync(APP, { recursive: true })
  .filter((f) => !/^(vendor|lang)[\\/]/.test(f));

afterEach(() => setLang("fr"));

describe("t()", () => {
  it("rend le texte source en français, la traduction en anglais", () => {
    assert.equal(t("Extrusion"), "Extrusion");
    setLang("en");
    assert.equal(t("Extrusion"), "Extrude");
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
  const sources = APP_FILES
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

  it("couvre les textes des panneaux : groupes, champs, aides, choix, refus", () => {
    // Deux contextes : sans esquisse, puis avec une esquisse libre (des
    // lignes n'apparaissent qu'avec un profil).
    const sketch = { name: "Sketch", label: "Esquisse", type: "Sketcher::SketchObject" };
    const contexts = [
      { selection: () => null, selectedSketch: null, lastTree: { features: [] } },
      { selection: () => null, selectedSketch: sketch, lastTree: { features: [sketch] } },
    ];
    const texts = () => {
      const out = [];
      const add = (button, text) => {
        if (typeof text === "string" && text.trim()) out.push([button, text]);
      };
      for (const entry of FEATURES) {
        add(entry.button, entry.note);
        if (typeof entry.invalid === "string") add(entry.button, entry.invalid);
        for (const ctx of contexts) {
          for (const group of entry.groups(ctx) ?? []) {
            add(entry.button, group.label);
            for (const row of group.rows ?? []) {
              add(entry.button, row.label);
              add(entry.button, row.hint);
              add(entry.button, row.placeholder);
              if (row.type === "note") add(entry.button, row.text);
              for (const [, label] of row.options ?? []) add(entry.button, label);
            }
          }
          if (typeof entry.invalid === "function") {
            let refusal = null;
            try { refusal = entry.invalid({}, ctx); } catch { /* saisie vide sans objet */ }
            add(entry.button, typeof refusal === "string" ? refusal : refusal?.text);
          }
        }
      }
      return out;
    };
    const fr = texts();
    setLang("en");
    const en = texts();
    // Un texte fixe est traduit à l'affichage (panel.js, say()) : il lui
    // faut son entrée. Un texte composé par t() change avec la langue. Un
    // code sans minuscule (« REF-001 ») reste tel quel.
    const missing = fr.filter(([, text], i) => !Object.hasOwn(EN, text)
      && en[i]?.[1] === text && /[a-zà-ÿ]/.test(text))
      .map(([button, text]) => `${button} : ${text}`);
    assert.deepEqual([...new Set(missing)], []);
  });

  it("garde les mêmes variables que le texte source", () => {
    const vars = (s) => (s.match(/\{\w+\}/g) ?? []).sort().join(",");
    const bad = Object.entries(EN).filter(([fr, en]) => vars(fr) !== vars(en));
    assert.deepEqual(bad, []);
  });
});

describe("pas d'ombre sur t()", () => {
  it("aucun fichier de app/ ne déclare une variable locale nommée t", () => {
    // Un `const t = …` local masquerait l'import et casserait t("…")
    // dans sa portée (vu sur le panneau Gravure).
    const shadows = APP_FILES
      .filter((f) => f.endsWith(".js"))
      .map((f) => [f, readFileSync(new URL(f, APP), "utf8")])
      .filter(([, src]) => /from "(\.\.?\/)+i18n\.js"/.test(src))
      .filter(([, src]) => /\b(const|let|var)\s+t\s*=/.test(src))
      .map(([f]) => f);
    assert.deepEqual(shadows, []);
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
