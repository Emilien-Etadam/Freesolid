// Étiquettes de cote et symboles de relation : des sprites dessinés sur
// un canevas. sketch.js ré-exporte createDimSprite (lu par main.js,
// sketch3d.js et les plugins via /sketch.js) et DIM_TEXT_PX.

import * as THREE from "three";
import { cssHex, cssRgba } from "../theme.js";
import { sceneTheme } from "./commun.js";

/** Hauteur du texte d'une cote à l'écran, en pixels CSS. */
export const DIM_TEXT_PX = 12;
// Le canevas est dessiné 4 fois plus grand : texte net une fois réduit.
const DIM_TEXT_OVERSAMPLE = 4;
/** Hauteur de l'étiquette (texte + marge) rapportée à celle du texte. */
export const DIM_LABEL_RATIO = 1.4;

/** Étiquette de cote : le texte seul, à sa longueur, cerné d'un halo de la
 *  couleur du fond pour rester lisible sur un trait ou une face — pas de
 *  pavé. `userData.aspect` : largeur / hauteur, pour la mise à l'échelle. */
export function createDimSprite(text, x, y, z = 0.01, color = cssHex(sceneTheme.dim)) {
  const k = DIM_TEXT_OVERSAMPLE;
  const font = `500 ${DIM_TEXT_PX * k}px system-ui, sans-serif`;
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  ctx.font = font;
  const pad = 4 * k;
  canvas.width = Math.ceil(ctx.measureText(text).width) + pad * 2;
  canvas.height = Math.round(DIM_TEXT_PX * DIM_LABEL_RATIO * k);
  ctx.font = font; // un canevas redimensionné oublie sa police
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.lineJoin = "round";
  ctx.lineWidth = 3 * k;
  ctx.strokeStyle = cssRgba(sceneTheme.bg, 0.75);
  ctx.strokeText(text, canvas.width / 2, canvas.height / 2);
  ctx.fillStyle = color;
  ctx.fillText(text, canvas.width / 2, canvas.height / 2);
  const texture = new THREE.CanvasTexture(canvas);
  texture.minFilter = THREE.LinearFilter;
  texture.generateMipmaps = false;
  const material = new THREE.SpriteMaterial({ map: texture, depthTest: false });
  material.userData.own = true;
  const sprite = new THREE.Sprite(material);
  sprite.userData.aspect = canvas.width / canvas.height;
  sprite.position.set(x, y, z);
  // Cotes de fonction en 3D : hauteur en unités du modèle.
  sprite.scale.set(3.2 * sprite.userData.aspect, 3.2, 1);
  return sprite;
}

/** Petit symbole de relation (H, V, ∥…) : pastille ronde lisible. */
export function createGlyphSprite(text) {
  const canvas = document.createElement("canvas");
  canvas.width = 48; canvas.height = 48;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = cssRgba(sceneTheme.bg, 0.85);
  ctx.beginPath();
  ctx.arc(24, 24, 22, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = cssHex(sceneTheme.successSoft);
  ctx.lineWidth = 2;
  ctx.stroke();
  ctx.font = "bold 26px system-ui";
  ctx.fillStyle = cssHex(sceneTheme.successSoft);
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, 24, 26);
  const material = new THREE.SpriteMaterial({
    map: new THREE.CanvasTexture(canvas), depthTest: false });
  material.userData.own = true;
  return new THREE.Sprite(material);
}
