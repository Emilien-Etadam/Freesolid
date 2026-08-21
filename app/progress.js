// Avancement d'une opération longue — formatage pur, sans DOM.
//
// Un PartDesign::Boolean est un appel OCCT opaque : pas de pourcentage.
// Ce module n'en invente pas. Il formate une phase nommée, un compteur
// de pierres quand la boucle est comptable, et les secondes écoulées.

/** Mesure P035 : 200 pierres → 43 s. Coût unitaire de l'annonce. */
export const COMBINE_SECONDS_PER_STONE = 43 / 200;

/** Sous ce seuil, une boîte de dialogue coûterait plus que l'attente. */
export const COMBINE_CONFIRM_MIN_SECONDS = 5;

export function estimateCombineSeconds(count) {
  const n = Number(count);
  if (!Number.isFinite(n) || n <= 0) return 0;
  return Math.max(1, Math.round(n * COMBINE_SECONDS_PER_STONE));
}

/** Message de confirmation, ou null si trop court / pas un semis. */
export function combineConfirmMessage(tree, toolName) {
  const gem = (tree?.gems ?? []).find((item) => item.name === toolName);
  if (!gem) return null;
  const seconds = estimateCombineSeconds(gem.count);
  if (seconds < COMBINE_CONFIRM_MIN_SECONDS) return null;
  const n = gem.count;
  const pierre = n === 1 ? "pierre" : "pierres";
  return `${n} ${pierre} — environ ${seconds} secondes. Continuer ?`;
}

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
