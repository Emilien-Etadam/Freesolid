// Interface multilingue : le français est la langue source (les textes du
// code et de ribbon.json), les autres langues sont des dictionnaires
// « texte source → traduction » dans app/lang/. Un texte absent du
// dictionnaire s'affiche tel quel : une traduction manquante ne casse rien.
//
//   t("Bossage extrudé")                    → "Extruded Boss" en anglais
//   t("Autotest : {n} étapes", { n: 12 })   → variables entre accolades,
//                                             aussi remplacées en français
//   translateDom(root)                      → textes, title, placeholder
//                                             et aria-label déjà dans le DOM

import EN from "./lang/en.json" with { type: "json" };

/** Langues livrées : code → dictionnaire (le français n'en a pas besoin). */
export const DICTIONARIES = { fr: null, en: EN };

let current = "fr";

/** Choisit la langue ; un code inconnu retombe sur le français. */
export function setLang(code) {
  current = Object.hasOwn(DICTIONARIES, code) ? code : "fr";
  return current;
}

export function currentLang() {
  return current;
}

/** Traduction d'un texte source, avec variables `{nom}` facultatives. */
export function t(text, vars) {
  if (typeof text !== "string") return text;
  const dict = DICTIONARIES[current];
  let out = dict && Object.hasOwn(dict, text) ? dict[text] : text;
  if (vars) {
    out = out.replace(/\{(\w+)\}/g, (match, key) =>
      Object.hasOwn(vars, key) ? String(vars[key]) : match);
  }
  return out;
}

/** Vrai si le texte a une traduction dans la langue courante. */
export function hasTranslation(text) {
  const dict = DICTIONARIES[current];
  return Boolean(dict && Object.hasOwn(dict, text));
}

const ATTRIBUTES = ["title", "placeholder", "aria-label"];

/**
 * Traduit ce qui est déjà dans le DOM : chaque nœud texte dont le contenu
 * (espaces ôtés) a une traduction, et les attributs title, placeholder,
 * aria-label. Idempotent en français ; à appeler une fois au chargement.
 */
export function translateDom(root) {
  if (!root || current === "fr") return 0;
  let count = 0;
  const walker = root.ownerDocument?.createTreeWalker
    ? root.ownerDocument.createTreeWalker(root, 0x4 /* NodeFilter.SHOW_TEXT */)
    : null;
  if (walker) {
    const nodes = [];
    for (let node = walker.nextNode(); node; node = walker.nextNode()) nodes.push(node);
    for (const node of nodes) {
      const parent = node.parentElement;
      if (!parent || parent.tagName === "SCRIPT" || parent.tagName === "STYLE") continue;
      const source = node.nodeValue.trim();
      if (!source || !hasTranslation(source)) continue;
      node.nodeValue = node.nodeValue.replace(source, t(source));
      count += 1;
    }
  }
  const elements = typeof root.querySelectorAll === "function"
    ? root.querySelectorAll(ATTRIBUTES.map((a) => `[${a}]`).join(","))
    : [];
  for (const el of elements) {
    for (const attr of ATTRIBUTES) {
      const value = el.getAttribute(attr);
      if (value && hasTranslation(value)) {
        el.setAttribute(attr, t(value));
        count += 1;
      }
    }
  }
  return count;
}
