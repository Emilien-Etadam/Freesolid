// Avancement d'une opération longue — formatage pur, sans DOM.
//
// Un PartDesign::Boolean est un appel OCCT opaque : pas de pourcentage.
// Ce module n'en invente pas. Il formate une phase nommée, un compteur
// quand la boucle est comptable, et les secondes écoulées.

/** Texte de barre d'état. Jamais un pourcentage. */
export function formatProgressStatus(progress, nowSeconds) {
  if (!progress || progress.op == null) return "";
  const phase = String(progress.phase || "");
  const elapsed = Math.max(
    0, Math.floor(Number(nowSeconds) - Number(progress.depuis || 0)));
  const clock = Number.isFinite(elapsed) && elapsed > 0
    ? ` (${elapsed} s)` : "";
  const fait = Number(progress.fait) || 0;
  const total = Number(progress.total) || 0;
  if (total > 0) {
    const label = phase || "Combiner";
    return `${label} — ${fait} / ${total}${clock}`;
  }
  if (phase) return `${phase}${clock}`;
  return "";
}
