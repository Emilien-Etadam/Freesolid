// Esquisse : le calque d'image (photo, plan scanné) sous le dessin —
// chargement, panneau de calage, enregistrement avec l'esquisse.

import * as THREE from "three";
import { t } from "../i18n.js";
import { num } from "../num.js";

export function installImage(sk) {
  const { call, say, panel, group, mode, abandonEntityPanel } = sk;

  // Calque d'image d'esquisse : mesh + texture alloués ici. Une seule
  // image à la fois ; enregistrée avec l'esquisse (jusqu'à 5 Mo), elle
  // revient à la réouverture.
  const MAX_SKETCH_IMAGE_BYTES = 25 * 1024 * 1024;
  const MAX_SAVED_IMAGE_BYTES = 5 * 1024 * 1024;
  let imageSaveTimer = null;

  /** Enregistre l'image (ou l'efface) avec l'esquisse ouverte. */
  function saveImageLayer() {
    if (!mode.state) return;
    clearTimeout(imageSaveTimer);
    const sketch = mode.state.sketch;
    const picture = sk.imageLayer?.data
      ? { data: sk.imageLayer.data, fileName: sk.imageLayer.fileName,
          ...sk.imageLayer.params }
      : {};
    imageSaveTimer = setTimeout(() => {
      call("sketch_picture", { sketch, picture }).catch((error) =>
        say(error.message, true));
    }, 400);
  }

  let pendingImageUrl = null;

  function revokePendingImageUrl() {
    if (!pendingImageUrl) return;
    URL.revokeObjectURL(pendingImageUrl);
    pendingImageUrl = null;
  }

  function disposeImageLayer() {
    if (!sk.imageLayer) return;
    const mesh = sk.imageLayer.mesh;
    if (mesh) {
      group.remove(mesh);
      mesh.geometry?.dispose();
      const mat = mesh.material;
      if (mat?.userData?.own) { mat.map?.dispose(); mat.dispose(); }
    }
    sk.imageLayer = null;
  }

  function applyImageLayer(values) {
    if (!sk.imageLayer?.mesh) return;
    const width = Math.max(0.01, num(values.width) ?? 100);
    const height = width / (sk.imageLayer.aspect || 1);
    const x = num(values.x) ?? 0;
    const y = num(values.y) ?? 0;
    const deg = num(values.rotation) ?? 0;
    let opacity = num(values.opacity);
    if (opacity === null) opacity = 0.5;
    opacity = Math.min(1, Math.max(0.1, opacity));
    sk.imageLayer.mesh.position.set(x, y, 0);
    sk.imageLayer.mesh.rotation.set(0, 0, deg * Math.PI / 180);
    sk.imageLayer.mesh.scale.set(width, height, 1);
    sk.imageLayer.mesh.material.opacity = opacity;
    sk.imageLayer.params = { width, x, y, rotation: deg, opacity };
  }

  function openImagePanel() {
    const params = sk.imageLayer?.params ?? {
      width: 100, x: 0, y: 0, rotation: 0, opacity: 0.5,
    };
    abandonEntityPanel();
    panel.open({
      icon: "Sketcher_Sketch",
      title: t("Image d'esquisse"),
      groups: [
        {
          label: t("Placement"),
          rows: [
            { type: "number", key: "width", label: t("Largeur"),
              value: params.width, unit: "mm", min: 0.01 },
            { type: "number", key: "x", label: t("X"),
              value: params.x, unit: "mm" },
            { type: "number", key: "y", label: t("Y"),
              value: params.y, unit: "mm" },
            { type: "number", key: "rotation", label: t("Rotation"),
              value: params.rotation, unit: "°" },
            { type: "number", key: "opacity", label: t("Opacité"),
              value: params.opacity, min: 0.1, step: 0.05 },
          ],
        },
        {
          label: t("Calque"),
          rows: [{
            type: "list",
            items: [{
              label: sk.imageLayer?.fileName || "image",
              onDelete: () => {
                disposeImageLayer();
                saveImageLayer();
                say("Image d'esquisse supprimée.");
                document.querySelector("#panel .pcancel")?.click();
              },
            }],
          }],
        },
      ],
      note: sk.imageLayer?.data
        ? t("L'image est enregistrée avec l'esquisse.")
        : t("Image de plus de 5 Mo : calque de travail, non enregistré."),
      onChange: (v) => {
        applyImageLayer(v);
        if (sk.imageLayer?.data) saveImageLayer();
      },
      onApply: () => {},
    });
  }

  function loadSketchImage(file) {
    if (!mode.active) return;
    if (file.size > MAX_SKETCH_IMAGE_BYTES) {
      say("Image trop lourde (max 25 Mo).", true);
      return;
    }
    const type = file.type || "";
    const name = file.name || "";
    const okType = type.startsWith("image/")
      || /\.(png|jpe?g|gif|webp|svg)$/i.test(name);
    if (!okType) {
      say("Fichier non reconnu comme image (PNG, JPEG, SVG…).", true);
      return;
    }

    if (file.size <= MAX_SAVED_IMAGE_BYTES) {
      // Petite image : lue en data: URL, elle part avec l'esquisse.
      const reader = new FileReader();
      const gen = ++sk.imageLoadGen;
      reader.onload = () => {
        if (gen !== sk.imageLoadGen || !mode.active) return;
        showImage(String(reader.result), name || "image", null, true);
      };
      reader.readAsDataURL(file);
      return;
    }
    revokePendingImageUrl();
    const url = URL.createObjectURL(file);
    pendingImageUrl = url;
    showImage(url, name || "image", null, false);
  }

  /** Pose le calque ; `data` (data: URL) est gardé pour l'enregistrer,
   *  `params` replace une image relue. */
  function showImage(url, name, params, persist) {
    const gen = ++sk.imageLoadGen;
    const img = new Image();
    img.onload = () => {
      if (pendingImageUrl === url) {
        URL.revokeObjectURL(url);
        pendingImageUrl = null;
      }
      if (gen !== sk.imageLoadGen || !mode.active) return;
      const w = img.naturalWidth || img.width;
      const h = img.naturalHeight || img.height;
      if (!w || !h) {
        say("Impossible de lire l'image (dimensions nulles).", true);
        return;
      }
      const texture = new THREE.Texture(img);
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.needsUpdate = true;
      disposeImageLayer();
      const material = new THREE.MeshBasicMaterial({
        map: texture,
        transparent: true,
        opacity: 0.5,
        depthTest: false,
        depthWrite: false,
        side: THREE.DoubleSide,
      });
      material.userData.own = true;
      const mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), material);
      mesh.renderOrder = 0;
      // Décor : ni snap, ni sélection, ni drag. nearestEntity() ne
      // parcourt que les entités serveur ; ce no-op protège un
      // éventuel raycast du groupe.
      mesh.raycast = () => {};
      sk.imageLayer = {
        mesh,
        aspect: w / h,
        fileName: name || "image",
        data: url.startsWith("data:") ? url : null,
        params: params ?? { width: 100, x: 0, y: 0, rotation: 0, opacity: 0.5 },
      };
      applyImageLayer(sk.imageLayer.params);
      group.add(mesh);
      if (params) return; // image relue à l'ouverture : pas de panneau
      openImagePanel();
      if (persist) saveImageLayer();
      say(persist ? t("Image d'esquisse posée — enregistrée avec l'esquisse.")
        : t("Image d'esquisse posée — calque de travail, non enregistré."));
    };
    img.onerror = () => {
      if (pendingImageUrl === url) {
        URL.revokeObjectURL(url);
        pendingImageUrl = null;
      }
      if (gen !== sk.imageLoadGen) return;
      say("Impossible de charger l'image.", true);
    };
    img.src = url;
  }

  return {
    revokePendingImageUrl, disposeImageLayer, loadSketchImage, showImage,
  };
}
