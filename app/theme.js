// Couleurs de la scène 3D. Lues sur :root (getComputedStyle) pour qu'un
// thème clair les change aussi. Sans DOM, ou si la variable manque, la
// valeur de repli est celle du thème sombre actuel.

const SCENE = {
  bg: ["--bg", 0x17191c],
  selection: ["--selection", 0xd9924a],
  accent: ["--accent", 0x4f8fdb],
  ink2: ["--ink-2", 0x8b939d],
  danger: ["--danger", 0xff5c5c],
  bgTop: ["--scene-bg-top", 0x2c323a],
  bgBottom: ["--scene-bg-bottom", 0x121417],
  sky: ["--scene-sky", 0xe4eaf1],
  ground: ["--scene-ground", 0x2a2e34],
  light: ["--scene-light", 0xffffff],
  grid: ["--scene-grid", 0x3a414a],
  gridMajor: ["--scene-grid-major", 0x4c545e],
  gridAxis: ["--scene-grid-axis", 0x66707c],
  part: ["--scene-part", 0xaebccb],
  partMuted: ["--scene-part-muted", 0x5f6b78],
  curve: ["--scene-curve", 0x4fb8a8],
  sketch: ["--scene-sketch", 0x8fa8c8],
  edge: ["--scene-edge", 0x11141a],
  edgeFaint: ["--scene-edge-faint", 0x7d8792],
  edgeOnBg: ["--scene-edge-on-bg", 0xd5dde6],
  ghost: ["--scene-ghost", 0xf2c94c],
  axisX: ["--scene-axis-x", 0xe06666],
  axisY: ["--scene-axis-y", 0x6aa84f],
  axisZ: ["--scene-axis-z", 0x4b9bd5],
  under: ["--scene-under", 0x5aa9ff],
  defined: ["--scene-defined", 0xe8edf2],
  dim: ["--scene-dim", 0x7fc4ff],
  successSoft: ["--success-soft", 0x6fcf97],
};

/** Entier 0xRRGGBB → « #rrggbb ». */
export function cssHex(value) {
  return `#${value.toString(16).padStart(6, "0")}`;
}

/** Entier 0xRRGGBB → « rgba(r, g, b, a) ». */
export function cssRgba(value, alpha) {
  const r = (value >> 16) & 255;
  const g = (value >> 8) & 255;
  const b = value & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function defaultStyle() {
  if (typeof document === "undefined" || !document.documentElement) return null;
  return getComputedStyle(document.documentElement);
}

/** « #rrggbb », « #rgb » ou « rgb(r, g, b) » → entier 0xRRGGBB, sinon null. */
export function parseColor(value) {
  if (value == null) return null;
  const text = String(value).trim();
  if (!text) return null;
  const hex = /^#([0-9a-f]{6})$/i.exec(text);
  if (hex) return Number.parseInt(hex[1], 16);
  const short = /^#([0-9a-f]{3})$/i.exec(text);
  if (short) {
    const [r, g, b] = short[1];
    return Number.parseInt(r + r + g + g + b + b, 16);
  }
  const rgb = /^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i.exec(text);
  if (!rgb) return null;
  const channels = [Number(rgb[1]), Number(rgb[2]), Number(rgb[3])];
  if (channels.some((channel) => channel > 255)) return null;
  return (channels[0] << 16) | (channels[1] << 8) | channels[2];
}

/** Une couleur de scène. `style` null ou absent → repli. */
export function sceneColor(name, style) {
  const spec = SCENE[name];
  if (!spec) throw new Error(`couleur de scène inconnue : ${name}`);
  const [cssName, fallback] = spec;
  const parsed = parseColor(style?.getPropertyValue?.(cssName));
  return parsed == null ? fallback : parsed;
}

/** Toutes les couleurs, lues une fois. Sans argument : le document courant. */
export function readScene(style) {
  const resolved = style === undefined ? defaultStyle() : style;
  const colors = {};
  for (const name of Object.keys(SCENE)) {
    colors[name] = sceneColor(name, resolved);
  }
  return colors;
}
