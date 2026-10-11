// Garde-fou de app/ : un nom utilisé sans être déclaré ni importé fait
// échouer la CI. Né du découpage de main.js (Q4), qui avait laissé des
// noms de l'autre côté de la découpe. Lancer depuis la racine :
//   npm ci --prefix scripts/lint
//   npx --prefix scripts/lint eslint -c scripts/lint/eslint.config.mjs app
import globals from "globals";

export default [
  { ignores: ["app/vendor/**"] },
  {
    files: ["app/**/*.js"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: { ...globals.browser },
    },
    rules: { "no-undef": "error" },
  },
];
