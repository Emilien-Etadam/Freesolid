// Avancement d'une opération longue — formatage pur, sans DOM.
//
// Un PartDesign::Boolean est un appel OCCT opaque : pas de pourcentage.
// Ce module n'en invente pas. Il formate une phase nommée, un compteur
// de pierres quand la boucle est comptable, et les secondes écoulées.
//
// P040 : le coût n'explose pas avec le nombre ni avec la courbure, mais
// quand les sièges se chevauchent (entraxe < diamètre). Sur un jonc de
// 9 mm, 30 pierres à +0,085 mm d'écart : 1,1 s / 0,27 GiB ; les mêmes
// à −0,12 mm : 81 s / 4,7 GiB. P039 à entraxe = Ø sur un jonc de 12 mm
// a explosé ; à 48 mm, 200 pierres qui se frôlent passent en 41 s.

/**
 * Écart (entraxe − diamètre) au-dessous duquel on alarme. 0 = frôlement
 * ou chevauchement. C à +0,085 mm passe ; A et C n'explosent qu'en
 * négatif.
 */
export const COMBINE_MEMORY_WARN_GAP_MM = 0;

/**
 * Rayon au-delà duquel un entraxe nul n'a pas explosé (P039, 47,75 mm,
 * 200 pierres, 41 s / 1,9 GiB). Une bague fait 8 à 10 mm.
 */
export const COMBINE_MEMORY_WARN_RADIUS_MM = 12;

/** Sous ce seuil, une boîte de dialogue coûterait plus que l'attente. */
export const COMBINE_CONFIRM_MIN_SECONDS = 5;

/**
 * Échantillon de session : ce que la dernière combinaison a réellement
 * coûté, sur cette machine, pour cette gemme. `null` tant qu'on n'a
 * rien mesuré — et alors on ne promet rien.
 *
 * @typedef {{ count: number, totalSeconds: number, compoundSeconds: number|null }} CombineSample
 */

/** @type {CombineSample|null} */
let sessionSample = null;

/** Marque interne : débit du compound pendant l'op en cours. */
let compoundMark = null;

export function resetCombineSample() {
  sessionSample = null;
  compoundMark = null;
}

export function currentCombineSample() {
  return sessionSample;
}

/**
 * Observe le callback d'avancement existant (P037), sans le modifier :
 * le compound est comptable et arrive en premier, son débit est une
 * mesure, pas une constante.
 *
 * @param {{ op?: string|null, phase?: string, fait?: number, total?: number, depuis?: number }|null} progress
 */
export function noteProgressForCalibration(progress, nowSeconds) {
  if (!progress || progress.op == null) return;
  const total = Number(progress.total) || 0;
  const fait = Number(progress.fait) || 0;
  if (total <= 0 || fait < total) return;
  const elapsed = Math.max(
    0, Number(nowSeconds) - Number(progress.depuis || 0));
  if (!Number.isFinite(elapsed)) return;
  compoundMark = { count: total, compoundSeconds: elapsed };
}

/**
 * Enregistre le coût réel d'une combinaison qui a abouti.
 * La prochaine annonce de la session s'en sert.
 *
 * @param {number} count
 * @param {number} totalSeconds
 */
export function rememberCombineFinished(count, totalSeconds) {
  const n = Number(count);
  const total = Number(totalSeconds);
  if (!Number.isFinite(n) || n <= 0) return;
  if (!Number.isFinite(total) || total < 0) return;
  const marked = (compoundMark && compoundMark.count === n)
    ? compoundMark.compoundSeconds : null;
  sessionSample = {
    count: n,
    totalSeconds: total,
    compoundSeconds: Number.isFinite(marked) ? marked : null,
  };
  compoundMark = null;
}

/**
 * Estimation en secondes, ou `null` si on n'a pas de mesure comparable.
 * Jamais une constante universelle. N'extrapole pas au-delà de 1,5×
 * l'échantillon — 25 pierres à 0,74 s ne disent rien de 50 à 12 GiB.
 *
 * @param {number} count
 * @param {CombineSample|null} [sample]
 * @returns {number|null}
 */
export function estimateCombineSeconds(count, sample) {
  const n = Number(count);
  if (!Number.isFinite(n) || n <= 0) return null;
  const measured = sample === undefined ? sessionSample : sample;
  if (!measured || !Number.isFinite(measured.count) || measured.count <= 0) {
    return null;
  }
  if (!Number.isFinite(measured.totalSeconds) || measured.totalSeconds < 0) {
    return null;
  }
  if (!_similarCount(n, measured.count)) return null;
  const compound = Number(measured.compoundSeconds);
  let seconds;
  if (Number.isFinite(compound) && compound > 1e-6
      && measured.totalSeconds >= compound) {
    const scale = (measured.totalSeconds - compound) / compound;
    seconds = (compound / measured.count) * n * (1 + scale);
  } else {
    seconds = measured.totalSeconds * (n / measured.count);
  }
  if (!Number.isFinite(seconds) || seconds < 0) return null;
  return Math.max(1, Math.round(seconds));
}

function _similarCount(n, sampleCount) {
  if (n <= sampleCount) return true;
  return n <= sampleCount * 1.5;
}

function _stoneWord(n) {
  return n === 1 ? "pierre" : "pierres";
}

function _finiteNumber(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

/**
 * Écart entre sièges (entraxe − diamètre), ou null si le moteur n'a
 * pas encore fourni de géométrie.
 *
 * @param {{ entraxe_mm?: number, diametre?: number, ecart_sieges_mm?: number }|null|undefined} gem
 * @returns {number|null}
 */
export function seatingGapMm(gem) {
  if (!gem) return null;
  const stored = _finiteNumber(gem.ecart_sieges_mm);
  if (stored != null) return stored;
  const entraxe = _finiteNumber(gem.entraxe_mm);
  const diametre = _finiteNumber(gem.diametre);
  if (entraxe == null || diametre == null) return null;
  return entraxe - diametre;
}

/**
 * True si A/C ont explosé pour cette géométrie : chevauchement, ou
 * frôlement (écart ≤ 0) sur un jonc de bague.
 *
 * @param {{ rayon_mm?: number, entraxe_mm?: number, diametre?: number, ecart_sieges_mm?: number, chevauchement?: boolean }|null|undefined} gem
 */
export function combineNeedsMemoryWarning(gem) {
  if (!gem) return false;
  if (gem.chevauchement === true) return true;
  const gap = seatingGapMm(gem);
  if (gap == null) return false;
  if (gap < COMBINE_MEMORY_WARN_GAP_MM) return true;
  if (gap > COMBINE_MEMORY_WARN_GAP_MM) return false;
  const radius = _finiteNumber(gem.rayon_mm);
  if (radius == null) return false;
  return radius <= COMBINE_MEMORY_WARN_RADIUS_MM;
}

/**
 * Message de confirmation, ou null si trop court / pas un semis.
 * Sans mesure locale : se taire, sauf semis trop serré — jamais un
 * point inventé, jamais d'alarme calée sur le seul effectif.
 *
 * @param {{ gems?: Array<{ name: string, count: number, rayon_mm?: number, entraxe_mm?: number, diametre?: number, ecart_sieges_mm?: number, chevauchement?: boolean }> }|null|undefined} tree
 * @param {string} toolName
 * @param {CombineSample|null} [sample]
 */
export function combineConfirmMessage(tree, toolName, sample) {
  const gem = (tree?.gems ?? []).find((item) => item.name === toolName);
  if (!gem) return null;
  const n = Number(gem.count);
  if (!Number.isFinite(n) || n <= 0) return null;
  const measured = sample === undefined ? sessionSample : sample;
  const pierre = _stoneWord(n);

  if (combineNeedsMemoryWarning(gem)) {
    return `${n} ${pierre} — les sièges se frôlent ou se chevauchent. `
      + "Cette opération peut demander plusieurs Go de mémoire et ne "
      + "pas aboutir. Enregistrez avant de continuer. Reculez la barre "
      + "de reprise et combinez par lots plus petits, en plusieurs "
      + "fonctions : sur une bague serrée, c'est la voie normale. "
      + "Continuer ?";
  }

  const seconds = estimateCombineSeconds(n, measured);
  if (seconds != null) {
    if (seconds < COMBINE_CONFIRM_MIN_SECONDS) return null;
    return `${n} ${pierre} — environ ${seconds} secondes, `
      + "d'après la dernière combinaison sur cette machine. Continuer ?";
  }

  return null;
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
