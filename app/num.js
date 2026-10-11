// Nombres saisis et affichés en millimètres.
// NaN / vide / non-fini → null. Ne jamais utiliser `|| 0` : 0 est une
// valeur valide, le défaut se pose avec `num(v) ?? défaut`.

const SIMPLE_DECIMAL = /^-?\d+(?:[.,]\d+)?$/;
const PLAIN_NUMBER = /^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?$/i;

/** Parse un nombre JSON ou saisi (virgule française). « 2*Largeur » → 2. */
export function num(value) {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  const parsed = parseFloat(String(value).trim().replace(",", "."));
  return Number.isFinite(parsed) ? parsed : null;
}

/** Nombre seul, forme scientifique acceptée. Une expression → null. */
export function plainNumber(value) {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  const text = String(value ?? "").trim().replace(",", ".");
  if (!PLAIN_NUMBER.test(text)) return null;
  const parsed = Number(text);
  return Number.isFinite(parsed) ? parsed : null;
}

/** Décimal simple (« 6,5 ») : pas de signe +, d'exposant ni d'expression. */
export function simpleDecimal(value) {
  const text = String(value ?? "").trim();
  if (!SIMPLE_DECIMAL.test(text)) return null;
  const parsed = Number(text.replace(",", "."));
  return Number.isFinite(parsed) ? parsed : null;
}

/** Deux décimales. `snap` ramène un résidu sous 0,005 mm à zéro. */
export function fmtMm(value, { snap = false } = {}) {
  const number = Number(value);
  const shown = snap && Math.abs(number) < 5e-3 ? 0 : number;
  return shown.toFixed(2);
}
