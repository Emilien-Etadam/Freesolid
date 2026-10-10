// Aspect de la scène 3D : fond en dégradé, éclairage qui suit la caméra,
// grille qui s'estompe au loin. THREE est passé en argument : les
// fonctions pures restent testables sous Node, sans la carte d'imports.

/** Pas de la grille (mm) pour une pièce de ce rayon : 1, 2 ou 5 × 10^n,
 *  environ un dixième du rayon, 10 mm pour une pièce moyenne. */
export function gridSpacing(radius) {
  const target = Math.max(radius, 1) / 10;
  const power = 10 ** Math.floor(Math.log10(target));
  const step = [1, 2, 5, 10].find((k) => k * power >= target) * power;
  return Math.max(step, 1);
}

/** Rayon (mm) où la grille commence à s'estomper, et celui où elle
 *  disparaît, autour du centre de la pièce. */
export function gridFade(radius) {
  const r = Math.max(radius, 20);
  return { start: r * 1.6, end: r * 4 };
}

// Lumières exprimées dans le repère de la caméra (x à droite, y en haut,
// z vers l'observateur) : la pièce garde le même modelé sous tous les
// angles, comme sous une lampe tenue au-dessus de l'épaule.
const CAMERA_LIGHTS = [
  { position: [-0.6, 0.9, 1.0], intensity: 3.4 },   // principale
  { position: [1.0, -0.3, 0.6], intensity: 0.8 },   // d'appoint
  { position: [0.2, 0.6, -1.0], intensity: 0.6 },   // contre-jour
];

const BACKGROUND_TOP = "#2c323a";
const BACKGROUND_BOTTOM = "#121417";

const GRID_VERTEX = /* glsl */ `
  varying vec2 vWorld;
  void main() {
    vec4 world = modelMatrix * vec4(position, 1.0);
    vWorld = world.xy;
    gl_Position = projectionMatrix * viewMatrix * world;
  }
`;

// Traits anti-crénelés (fwidth) : pas fin, pas majeur tous les cinq,
// les deux axes un peu plus marqués ; l'opacité tombe avec la distance
// au centre de la pièce.
const GRID_FRAGMENT = /* glsl */ `
  uniform float uStep;
  uniform vec2 uCenter;
  uniform float uFadeStart;
  uniform float uFadeEnd;
  uniform vec3 uMinor;
  uniform vec3 uMajor;
  uniform vec3 uAxis;
  varying vec2 vWorld;

  float lineAt(vec2 coord) {
    vec2 g = abs(fract(coord - 0.5) - 0.5) / fwidth(coord);
    return 1.0 - min(min(g.x, g.y), 1.0);
  }

  void main() {
    float minor = lineAt(vWorld / uStep);
    float major = lineAt(vWorld / (uStep * 5.0));
    vec2 a = abs(vWorld) / fwidth(vWorld);
    float axis = 1.0 - min(min(a.x, a.y), 1.0);
    vec3 color = uMinor;
    float alpha = minor * 0.35;
    if (major > 0.0) { color = mix(color, uMajor, major); alpha = max(alpha, major * 0.6); }
    if (axis > 0.0) { color = mix(color, uAxis, axis); alpha = max(alpha, axis * 0.8); }
    float fade = 1.0 - smoothstep(uFadeStart, uFadeEnd, distance(vWorld, uCenter));
    alpha *= fade;
    if (alpha < 0.01) discard;
    gl_FragColor = vec4(color, alpha);
  }
`;

export function createSceneLook(THREE, scene) {
  // Fond : un dégradé vertical, texture de canvas (chaque fenêtre en
  // charge sa copie dans son propre contexte WebGL).
  const canvas = document.createElement("canvas");
  canvas.width = 2;
  canvas.height = 256;
  const ctx = canvas.getContext("2d");
  const gradient = ctx.createLinearGradient(0, 0, 0, canvas.height);
  gradient.addColorStop(0, BACKGROUND_TOP);
  gradient.addColorStop(1, BACKGROUND_BOTTOM);
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  const background = new THREE.CanvasTexture(canvas);
  background.colorSpace = THREE.SRGBColorSpace;
  scene.background = background;

  // Ciel au-dessus (Z), sol en dessous : les faces du dessus restent les
  // plus claires.
  const hemi = new THREE.HemisphereLight(0xe4eaf1, 0x2a2e34, 1.2);
  hemi.position.set(0, 0, 1);
  scene.add(hemi);
  const rig = new THREE.Group();
  for (const spec of CAMERA_LIGHTS) {
    const light = new THREE.DirectionalLight(0xffffff, spec.intensity);
    light.position.set(...spec.position);
    rig.add(light);
    rig.add(light.target); // la cible à l'origine du repère : direction fixe
  }
  scene.add(rig);

  const gridMaterial = new THREE.ShaderMaterial({
    uniforms: {
      uStep: { value: 10 },
      uCenter: { value: new THREE.Vector2() },
      uFadeStart: { value: 150 },
      uFadeEnd: { value: 400 },
      uMinor: { value: new THREE.Color(0x3a414a) },
      uMajor: { value: new THREE.Color(0x4c545e) },
      uAxis: { value: new THREE.Color(0x66707c) },
    },
    vertexShader: GRID_VERTEX,
    fragmentShader: GRID_FRAGMENT,
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    // Derrière les faces posées sur le plan XY (pièce vue de dessous).
    polygonOffset: true, polygonOffsetFactor: 2, polygonOffsetUnits: 8,
  });
  const grid = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), gridMaterial);
  grid.raycast = () => {};
  grid.renderOrder = -1;
  scene.add(grid);

  /** Recadre la grille sur la pièce : pas, étendue, fondu. */
  function fitGrid(center, radius) {
    const fade = gridFade(radius);
    const u = gridMaterial.uniforms;
    u.uStep.value = gridSpacing(radius);
    u.uCenter.value.set(center.x, center.y);
    u.uFadeStart.value = fade.start;
    u.uFadeEnd.value = fade.end;
    grid.position.set(center.x, center.y, 0);
    grid.scale.set(fade.end * 2, fade.end * 2, 1);
  }
  fitGrid({ x: 0, y: 0 }, 90);

  /** Avant chaque rendu : les lumières suivent la caméra qui dessine. */
  function follow(camera) {
    rig.quaternion.copy(camera.quaternion);
    rig.updateMatrixWorld(true);
  }

  return { grid, fitGrid, follow, backgroundTop: BACKGROUND_TOP };
}
