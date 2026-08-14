// Parse un nombre JSON ou saisi (virgule française acceptée).
// NaN / vide / non-fini → null. Ne jamais utiliser `|| 0` : 0 est une
// valeur valide, le défaut se pose avec `num(v) ?? défaut`.

export function num(value) {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  const parsed = parseFloat(String(value).trim().replace(",", "."));
  return Number.isFinite(parsed) ? parsed : null;
}
