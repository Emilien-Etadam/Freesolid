// Interface client de la bijouterie — ruban, panneau, HUD, touches,
// ligne d'arbre, viewport. Le drag reste dans le noyau jusqu'à la
// chaîne du pointeur (commit suivant).

import * as THREE from "three";
import { createDimSprite } from "/sketch.js";
import { dressup, hasSelection } from "/features.js";
import { num } from "/num.js";
import {
  formatMmFr,
  gemDiametreDeltaFromButton,
  gemDiametreDeltaFromKey,
  gemRibbonState,
} from "./gem-controls.js";

const GEM_MIN_MM = 0.1;
const GEM_IDLE_COLOR = new THREE.Color(0xffffff);
const GEM_SELECTED_COLOR = new THREE.Color(0xffb040);

export function register(api) {
  const gemMaterial = new THREE.MeshStandardMaterial({
    color: 0xd4e4f2, metalness: 0.35, roughness: 0.22,
  });
  const warnedSplineFaces = new Set();
  let gemMeshes = [];
  let selectedGem = null;
  let gemDiametreOverride = {};
  let gemResizeInflight = false;
  let gemResizeWanted = null;
  const gemGapGroup = new THREE.Group();
  gemGapGroup.renderOrder = 25;
  api.scene.add(gemGapGroup);

  function applyPackedGeometry(geometry, packed) {
    geometry.setAttribute("position",
      new THREE.Float32BufferAttribute(packed.positions, 3));
    if (packed.indices) geometry.setIndex(packed.indices);
    if (packed.normals && packed.normals.length === packed.positions.length) {
      geometry.setAttribute("normal",
        new THREE.Float32BufferAttribute(packed.normals, 3));
    } else {
      geometry.computeVertexNormals();
    }
  }

  function ownedMaterial(source) {
    const material = source.clone();
    material.userData.own = true;
    return material;
  }

  function gemMatrixFromHit(point, normal, spinDeg, lift) {
    const origin = point.clone().add(
      normal.clone().normalize().multiplyScalar(lift || 0));
    const quat = new THREE.Quaternion().setFromUnitVectors(
      new THREE.Vector3(0, 0, 1), normal.clone().normalize());
    if (spinDeg) {
      quat.multiply(new THREE.Quaternion().setFromAxisAngle(
        new THREE.Vector3(0, 0, 1), spinDeg * Math.PI / 180));
    }
    return new THREE.Matrix4().compose(
      origin, quat, new THREE.Vector3(1, 1, 1));
  }

  function gemScreenPoint() {
    const mesh = gemMeshes[0];
    if (!mesh || mesh.count < 1) return null;
    const matrix = new THREE.Matrix4();
    mesh.getMatrixAt(0, matrix);
    const point = new THREE.Vector3().setFromMatrixPosition(matrix);
    point.project(api.camera);
    const rect = api.renderer?.domElement?.getBoundingClientRect();
    if (!rect) return null;
    return {
      name: mesh.userData.gem?.name ?? null,
      x: (point.x * 0.5 + 0.5) * rect.width + rect.left,
      y: (-point.y * 0.5 + 0.5) * rect.height + rect.top,
      count: gemMeshes.reduce((n, item) => n + item.count, 0),
    };
  }

  function gemWorldPositions() {
    const out = [];
    const matrix = new THREE.Matrix4();
    const point = new THREE.Vector3();
    for (const mesh of gemMeshes) {
      for (let i = 0; i < mesh.count; i += 1) {
        mesh.getMatrixAt(i, matrix);
        point.setFromMatrixPosition(matrix);
        out.push({
          name: mesh.userData.gem?.name ?? "",
          index: i,
          x: point.x, y: point.y, z: point.z,
          diametre: mesh.userData.gem?.diametre ?? null,
        });
      }
    }
    return out;
  }

  function currentGemDiametre(name, fallback) {
    if (Object.hasOwn(gemDiametreOverride, name)) {
      return gemDiametreOverride[name];
    }
    const gem = (api.tree?.gems ?? []).find((item) => item.name === name);
    if (gem && Number.isFinite(gem.diametre)) return gem.diametre;
    return fallback;
  }

  function allStones() {
    return gemWorldPositions().map((stone) => ({
      ...stone,
      diametre: currentGemDiametre(stone.name, stone.diametre),
    }));
  }

  function pairMetrics(a, b) {
    const dx = a.x - b.x;
    const dy = a.y - b.y;
    const dz = a.z - b.z;
    const entraxe = Math.hypot(dx, dy, dz);
    const d1 = Number(a.diametre) || 0;
    const d2 = Number(b.diametre) || 0;
    return { entraxe, ecart: entraxe - (d1 + d2) / 2, a, b };
  }

  function nearestOf(stones, origin) {
    let best = null;
    for (const stone of stones) {
      if (stone.name === origin.name && stone.index === origin.index) continue;
      const pair = pairMetrics(origin, stone);
      if (!best || pair.entraxe < best.entraxe) best = pair;
    }
    return best;
  }

  function tightestPair(stones) {
    let best = null;
    for (let i = 0; i < stones.length; i += 1) {
      for (let j = i + 1; j < stones.length; j += 1) {
        const pair = pairMetrics(stones[i], stones[j]);
        if (!best || pair.entraxe < best.entraxe) best = pair;
      }
    }
    return best;
  }

  function clearGemGap() {
    for (const child of [...gemGapGroup.children]) {
      gemGapGroup.remove(child);
      child.traverse?.((obj) => {
        obj.geometry?.dispose();
        const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
        for (const m of mats) {
          if (m && m.userData?.own) { m.map?.dispose(); m.dispose(); }
        }
      });
    }
  }

  function drawGemGap(pair) {
    clearGemGap();
    if (!pair) return;
    const negative = pair.ecart < 0;
    const color = negative ? 0xd4655c : 0x7fc4ff;
    const geometry = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(pair.a.x, pair.a.y, pair.a.z),
      new THREE.Vector3(pair.b.x, pair.b.y, pair.b.z),
    ]);
    const material = new THREE.LineBasicMaterial({
      color, depthTest: false, toneMapped: false,
    });
    material.userData.own = true;
    const line = new THREE.Line(geometry, material);
    line.renderOrder = 25;
    gemGapGroup.add(line);
    const mid = new THREE.Vector3(
      (pair.a.x + pair.b.x) / 2,
      (pair.a.y + pair.b.y) / 2,
      (pair.a.z + pair.b.z) / 2,
    );
    const sprite = createDimSprite(
      `${formatMmFr(pair.ecart)} mm`, mid.x, mid.y, mid.z,
      negative ? "#d4655c" : "#7fc4ff");
    sprite.renderOrder = 26;
    gemGapGroup.add(sprite);
  }

  function updateGapOverlay() {
    const stones = allStones();
    const drag = window.__freesolidDebug?.gemDrag;
    if (drag?.moved) {
      const origin = stones.find(
        (stone) => stone.name === drag.name && stone.index === drag.index);
      drawGemGap(origin ? nearestOf(stones, origin) : null);
      return;
    }
    if (!selectedGem) {
      clearGemGap();
      return;
    }
    drawGemGap(tightestPair(stones));
  }

  function paintGemSelection() {
    for (const mesh of gemMeshes) {
      const name = mesh.userData.gem?.name;
      for (let i = 0; i < mesh.count; i += 1) {
        const on = selectedGem
          && name === selectedGem.name
          && i === selectedGem.index;
        mesh.setColorAt(i, on ? GEM_SELECTED_COLOR : GEM_IDLE_COLOR);
      }
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    }
  }

  function updateGemRibbon() {
    const minus = document.getElementById("btn-gem-minus");
    const plus = document.getElementById("btn-gem-plus");
    const readout = document.getElementById("gem-diametre-readout");
    if (!minus || !plus || !readout) return;
    const gem = selectedGem
      ? (api.tree?.gems ?? []).find((item) => item.name === selectedGem.name)
      : null;
    const diametre = gem ? currentGemDiametre(gem.name, gem.diametre) : NaN;
    const state = gemRibbonState(!!gem, diametre);
    minus.disabled = state.disabled;
    plus.disabled = state.disabled;
    minus.title = state.minusTitle;
    plus.title = state.plusTitle;
    if (minus.parentElement?.classList.contains("ribbon-tip")) {
      minus.parentElement.title = state.minusTitle;
    }
    if (plus.parentElement?.classList.contains("ribbon-tip")) {
      plus.parentElement.title = state.plusTitle;
    }
    readout.textContent = state.label;
  }

  function updateGemHud() {
    updateGemRibbon();
    const hud = document.getElementById("gem-hud");
    const diametreEl = document.getElementById("gem-hud-diametre");
    const ecartEl = document.getElementById("gem-hud-ecart");
    if (!hud || !diametreEl || !ecartEl) return;
    if (!selectedGem) {
      hud.hidden = true;
      return;
    }
    const gem = (api.tree?.gems ?? []).find(
      (item) => item.name === selectedGem.name);
    if (!gem) {
      hud.hidden = true;
      return;
    }
    const diametre = currentGemDiametre(gem.name, gem.diametre);
    const count = Number(gem.count) || 0;
    const pierre = count === 1 ? "pierre" : "pierres";
    diametreEl.textContent =
      `Ø ${formatMmFr(diametre)} mm · ${count} ${pierre}`;
    let ecart = gem.ecart_min_mm;
    if (Object.hasOwn(gemDiametreOverride, gem.name)) {
      const pair = tightestPair(allStones());
      if (pair && Number.isFinite(pair.ecart)) ecart = pair.ecart;
    }
    if (!Number.isFinite(ecart)) {
      ecartEl.textContent = "écart mini —";
      ecartEl.classList.remove("negative");
    } else {
      ecartEl.textContent = `écart mini ${formatMmFr(ecart)} mm`;
      ecartEl.classList.toggle("negative", ecart < 0);
    }
    hud.hidden = false;
  }

  function restoreGemSelection() {
    if (selectedGem) {
      const names = (api.tree?.gems ?? []).map((item) => item.name);
      if (!names.includes(selectedGem.name)) {
        selectedGem = null;
        gemDiametreOverride = {};
      }
    }
    paintGemSelection();
    updateGemHud();
    updateGapOverlay();
  }

  function selectGem(name, index) {
    selectedGem = { name, index };
    paintGemSelection();
    updateGemHud();
    updateGapOverlay();
  }

  function clearGemSelection() {
    selectedGem = null;
    gemDiametreOverride = {};
    gemResizeWanted = null;
    paintGemSelection();
    updateGemHud();
    clearGemGap();
  }

  function applyGemMoved(tree) {
    const moved = tree?.gem_moved;
    if (!moved || typeof moved.gem !== "string") return;
    const index = Number(moved.index);
    if (!Number.isInteger(index) || index < 0) return;
    selectedGem = { name: moved.gem, index };
  }

  function sendGemResize(name, diametre) {
    if (gemResizeInflight) {
      gemResizeWanted = { name, diametre };
      return;
    }
    gemResizeInflight = true;
    api.refresh(api.call("resize_gem", { gem: name, diametre })).finally(() => {
      gemResizeInflight = false;
      const pending = gemResizeWanted;
      gemResizeWanted = null;
      if (pending) sendGemResize(pending.name, pending.diametre);
      else delete gemDiametreOverride[name];
    });
  }

  function applyGemDiametre(delta) {
    if (!selectedGem) return;
    const gem = (api.tree?.gems ?? []).find(
      (item) => item.name === selectedGem.name);
    if (!gem) return;
    const current = currentGemDiametre(gem.name, gem.diametre);
    const next = Math.round((current + delta) * 10) / 10;
    if (next < GEM_MIN_MM - 1e-9) return;
    if (Math.abs(next - current) < 1e-9) return;
    gemDiametreOverride[gem.name] = next;
    updateGemHud();
    updateGapOverlay();
    sendGemResize(gem.name, next);
  }

  const reglage = document.createElement("span");
  reglage.style.display = "contents";
  const minusTip = document.createElement("span");
  minusTip.className = "ribbon-tip";
  minusTip.title = "Sélectionnez une pierre pour régler le diamètre";
  const minus = document.createElement("button");
  minus.id = "btn-gem-minus";
  minus.title = minusTip.title;
  minus.disabled = true;
  minus.textContent = "Ø −";
  minusTip.appendChild(minus);
  const readout = document.createElement("span");
  readout.id = "gem-diametre-readout";
  readout.textContent = "Ø —";
  const plusTip = document.createElement("span");
  plusTip.className = "ribbon-tip";
  plusTip.title = "Sélectionnez une pierre pour régler le diamètre";
  const plus = document.createElement("button");
  plus.id = "btn-gem-plus";
  plus.title = plusTip.title;
  plus.disabled = true;
  plus.textContent = "Ø +";
  plusTip.appendChild(plus);
  reglage.append(minusTip, readout, plusTip);

  api.ribbon({
    id: "jewel",
    libelle: "Bijouterie",
    groupes: [
      {
        libelle: "Pierres",
        boutons: [{
          id: "btn-gem",
          titre: "Pierre — poser sur une face, aimantée à la surface",
          icon: "icons/nodes_cylinder.svg",
          libelle: "Pierre",
        }],
      },
      { libelle: "Réglage", node: reglage },
      {
        libelle: "Contrôle",
        boutons: [{
          id: "btn-gem-combine",
          titre: "Combiner deux corps : Soustraire / Ajouter / Intersection",
          icon: "icons/PartDesign_Boolean.svg",
          libelle: "Combiner",
        }],
      },
    ],
  });

  minus.addEventListener("click", () =>
    applyGemDiametre(gemDiametreDeltaFromButton("minus")));
  plus.addEventListener("click", () =>
    applyGemDiametre(gemDiametreDeltaFromButton("plus")));

  api.feature(dressup({
    button: "btn-gem",
    icon: "nodes_cylinder.svg",
    title: "Pierre",
    selectionLabel: "Face d'appui",
    hint: "Cliquez une face dans la zone graphique — la pierre s'y aimante",
    group: "Pierre",
    rows: [
      { type: "number", key: "diametre", label: "Diamètre", value: 1.5,
        unit: "mm", min: 0.01 },
      { type: "number", key: "spin", label: "Rotation", value: 0,
        unit: "°" },
      { type: "number", key: "lift", label: "Enfoncement", value: 0,
        unit: "mm" },
    ],
    noteFn: (ctx, extras) => extras?.spline
      ? "Sur une surface libre, l'ancrage peut glisser de quelques "
        + "dixièmes de millimètre si la surface se déforme — la pierre "
        + "reste collée, mais pas au même endroit."
      : "La pierre reste collée à la face : changer une cote de la pièce "
        + "la recale. Poser n'enlève pas de matière.",
    build: (v, ctx) => {
      const diametre = num(v.diametre);
      const hit = ctx.lastFaceHit;
      if (!hasSelection(v.sel) || !(diametre > 0) || !hit
          || hit.face !== v.sel.face) {
        return null;
      }
      const params = {
        face: v.sel.face, x: hit.x, y: hit.y, z: hit.z, diametre,
      };
      const spin = num(v.spin);
      const lift = num(v.lift);
      if (spin != null) params.spin = spin;
      if (lift != null) params.lift = lift;
      return { op: "place_gem", params };
    },
    invalid: (v, ctx) => {
      if (!hasSelection(v.sel)) {
        return "Pierre : cliquez d'abord une face dans la zone graphique";
      }
      if (!(num(v.diametre) > 0)) return "Diamètre invalide";
      if (!ctx.lastFaceHit || ctx.lastFaceHit.face !== v.sel.face) {
        return "Pierre : recliquez la face pour viser le point de pose";
      }
      return "Valeurs invalides";
    },
  }));

  const hud = document.createElement("div");
  hud.id = "gem-hud";
  hud.hidden = true;
  const hudDiametre = document.createElement("div");
  hudDiametre.id = "gem-hud-diametre";
  const hudEcart = document.createElement("div");
  hudEcart.id = "gem-hud-ecart";
  hud.append(hudDiametre, hudEcart);
  api.hud(hud);

  api.key((event) => {
    if (!event.ctrlKey && !event.metaKey && !event.altKey && selectedGem) {
      const delta = gemDiametreDeltaFromKey(event);
      if (delta) {
        event.preventDefault();
        applyGemDiametre(delta);
        return true;
      }
    }
    if (event.key === "Escape" && selectedGem) {
      event.preventDefault();
      clearGemSelection();
      return true;
    }
    return false;
  });

  api.treeRow(
    (tree) => tree.gems ?? [],
    (gem, { treeIcon, openMenu }) => {
      const row = document.createElement("li");
      row.classList.add("feat");
      row.dataset.feat = gem.name;
      if (gem.error) row.classList.add("error");
      row.appendChild(treeIcon("LinkArray.svg"));
      row.appendChild(document.createTextNode(gem.label));
      const detail = gem.error_message
        ? gem.error_message
        : (gem.spline
          ? "Semis de pierres — surface libre : l'ancrage peut glisser"
          : "Semis de pierres — clic droit : supprimer");
      row.title = detail;
      row.addEventListener("contextmenu", (event) => openMenu(event, {
        name: gem.name, label: gem.label, type: "App::Link", kind: gem.kind,
      }));
      return row;
    },
  );

  api.viewport({
    onClear() {
      gemMeshes = [];
      clearGemGap();
    },
    onMesh(mesh, ctx) {
      const packed = ctx.applyPackedGeometry ?? applyPackedGeometry;
      const materialOf = ctx.ownedMaterial ?? ownedMaterial;
      const created = [];
      for (const gem of Array.isArray(mesh.gems) ? mesh.gems : []) {
        if (!gem.indices?.length || !gem.instances?.length) continue;
        const geometry = new THREE.BufferGeometry();
        packed(geometry, gem);
        const count = gem.instances.length;
        const material = materialOf(gemMaterial);
        const inst = new THREE.InstancedMesh(geometry, material, count);
        inst.userData.gem = {
          name: gem.name,
          label: gem.label,
          faceId: gem.face_id,
          spline: !!gem.spline,
          diametre: gem.diametre,
          spins: gem.instances.map((item) => item.spin ?? 0),
          lifts: gem.instances.map((item) => item.lift ?? 0),
        };
        const dummy = new THREE.Matrix4();
        gem.instances.forEach((item, i) => {
          if (item.matrix?.length === 16) dummy.set(...item.matrix);
          else dummy.identity();
          inst.setMatrixAt(i, dummy);
        });
        inst.instanceMatrix.needsUpdate = true;
        inst.frustumCulled = false;
        created.push(inst);
        if (gem.spline && gem.face_id != null
            && !warnedSplineFaces.has(gem.face_id)) {
          warnedSplineFaces.add(gem.face_id);
          api.say("Surface libre : l'ancrage peut glisser si la surface se déforme.");
        }
      }
      gemMeshes = created;
      restoreGemSelection();
      return created;
    },
  });

  const debug = window.__freesolidDebug;
  if (debug) {
    Object.defineProperties(debug, {
      gemMeshCount: {
        configurable: true,
        get: () => gemMeshes.length,
      },
      gemInstanceCount: {
        configurable: true,
        get: () => gemMeshes.reduce((n, mesh) => n + mesh.count, 0),
      },
      gemScreenPoint: {
        configurable: true,
        get: () => gemScreenPoint(),
      },
      gemWorldPositions: {
        configurable: true,
        get: () => gemWorldPositions(),
      },
      selectedGem: {
        configurable: true,
        get: () => selectedGem,
      },
      gemMeshes: {
        configurable: true,
        get: () => gemMeshes,
      },
    });
    debug.selectGem = selectGem;
    debug.clearGemSelection = clearGemSelection;
    debug.applyGemMoved = applyGemMoved;
    debug.gemMatrixFromHit = gemMatrixFromHit;
    debug.updateGapOverlay = updateGapOverlay;
  }
}
