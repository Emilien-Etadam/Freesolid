// Esquisse : les commandes de la barre (symétrie, répétitions,
// transformations, calques, texte, équation, réparation, blocs, décalage,
// image, conversion, terminer / quitter). Chaque bouton ouvre son panneau
// ou appelle le moteur ; le geste de dessin reste dans sketch.js.

import * as THREE from "three";
import { t } from "../i18n.js";
import { LAYER_COLORS, layersFromPanel } from "../sketchtools.js";
import { num } from "../num.js";

export function installCommandes(sk) {
  const {
    call, say, panel, mode, loadSketchImage, applyState, safe, entityPicks,
    abandonEntityPanel, exit,
  } = sk;

  // Symétrie d'entités : la sélection SAUF la dernière est symétrisée,
  // la dernière entité sélectionnée est l'axe.
  document.getElementById("sk-mirror").addEventListener("click", () => {
    if (!mode.state) return;
    const picks = entityPicks();
    if (picks.length < 2) {
      say("Symétrie : sélectionnez les entités PUIS la ligne d'axe " +
          "en dernier", true);
      return;
    }
    const geos = picks.slice(0, -1).map((s) => s.geo);
    const axis = picks[picks.length - 1]?.geo;
    safe(call("sketch_mirror",
      { sketch: mode.state.sketch, geos, axis }));
  });

  document.getElementById("sk-array").addEventListener("click", () => {
    if (!mode.state) return;
    if (!entityPicks().length) {
      say("Répétition : sélectionnez d'abord des entités", true);
      return;
    }
    const geos = entityPicks().map((s) => s.geo);
    abandonEntityPanel();
    panel.open({
      icon: "sketch_array",
      title: t("Réseau d'esquisse"),
      groups: [{
        label: t("Paramètres"),
        rows: [
          { type: "number", key: "dx", label: t("Pas X"), value: 15,
            unit: "mm" },
          { type: "number", key: "dy", label: t("Pas Y"), value: 0,
            unit: "mm" },
          { type: "number", key: "cols", label: t("Colonnes"), value: 3,
            min: 1, step: 1 },
          { type: "number", key: "rows", label: t("Lignes"), value: 1,
            min: 1, step: 1 },
        ],
      }],
      note: t("Le pas est piloté par des lignes de construction — " +
            "cotables ensuite."),
      onApply: (v) => safe(call("sketch_array", {
        sketch: mode.state.sketch, geos,
        dx: num(v.dx) ?? 0, dy: num(v.dy) ?? 0,
        cols: parseInt(v.cols, 10) || 1,
        rows: parseInt(v.rows, 10) || 1 })),
    });
  });

  // Déplacer, copier, tourner, mettre à l'échelle : un panneau par
  // geste, le même moteur (sketch_transform).
  const TRANSFORMS = {
    "sk-move": { icon: "sk_move", title: "Déplacer", copy: false,
      rows: [["dx", "Déplacement X", 10], ["dy", "Déplacement Y", 0]] },
    "sk-copy": { icon: "sk_copy", title: "Copier", copy: true,
      rows: [["dx", "Déplacement X", 10], ["dy", "Déplacement Y", 0]] },
    "sk-rotate": { icon: "sk_rotate", title: "Tourner", copy: false,
      rows: [["angle", "Angle (°)", 90], ["cx", "Centre X", 0],
             ["cy", "Centre Y", 0]], copyOption: true },
    "sk-scale": { icon: "sk_scale", title: "Échelle", copy: false,
      rows: [["scale", "Facteur", 2], ["cx", "Centre X", 0],
             ["cy", "Centre Y", 0]], copyOption: true },
  };
  for (const [id, spec] of Object.entries(TRANSFORMS)) {
    document.getElementById(id).addEventListener("click", () => {
      if (!mode.state) return;
      if (!entityPicks().length) {
        say(t("{title} : sélectionnez d'abord des entités",
          { title: t(spec.title) }), true);
        return;
      }
      const geos = [...new Set(entityPicks().map((s) => s.geo))];
      abandonEntityPanel();
      const rows = spec.rows.map(([key, label, value]) => ({
        type: "number", key, label: t(label), value,
        ...(key === "scale" ? { min: 0.001 } : {}),
        ...(key === "angle" ? {} : { unit: key === "scale" ? "" : "mm" }) }));
      if (spec.copyOption) {
        rows.push({ type: "check", key: "copy", label: t("Garder l'original (copie)"),
                    value: false });
      }
      panel.open({
        icon: spec.icon,
        title: t(spec.title),
        groups: [{ label: t("Paramètres"), rows }],
        note: t("Les relations internes à la sélection suivent ; celles "
          + "vers le reste de l'esquisse tombent en tournant ou en "
          + "changeant d'échelle."),
        onApply: (v) => safe(call("sketch_transform", {
          sketch: mode.state.sketch, geos,
          dx: num(v.dx) ?? 0, dy: num(v.dy) ?? 0, angle: num(v.angle) ?? 0,
          cx: num(v.cx) ?? 0, cy: num(v.cy) ?? 0, scale: num(v.scale) ?? 1,
          copy: spec.copy || !!v.copy })),
      });
    });
  }

  document.getElementById("sk-polar").addEventListener("click", () => {
    if (!mode.state) return;
    if (!entityPicks().length) {
      say("Répétition circulaire : sélectionnez d'abord des entités", true);
      return;
    }
    const geos = [...new Set(entityPicks().map((s) => s.geo))];
    abandonEntityPanel();
    panel.open({
      icon: "sk_polar",
      title: t("Répétition circulaire"),
      groups: [{
        label: t("Paramètres"),
        rows: [
          { type: "number", key: "count", label: t("Exemplaires"), value: 6,
            min: 2, step: 1 },
          { type: "number", key: "angle", label: t("Angle total (°)"),
            value: 360 },
          { type: "number", key: "cx", label: t("Centre X"), value: 0,
            unit: "mm" },
          { type: "number", key: "cy", label: t("Centre Y"), value: 0,
            unit: "mm" },
        ],
      }],
      note: t("Les exemplaires (l'original compris) sont répartis sur "
        + "l'angle ; 360° : un tour complet."),
      onApply: (v) => safe(call("sketch_polar_array", {
        sketch: mode.state.sketch, geos,
        count: parseInt(v.count, 10) || 2, angle: num(v.angle) ?? 360,
        cx: num(v.cx) ?? 0, cy: num(v.cy) ?? 0 })),
    });
  });

  // Références liées : arêtes de la face porteuse, intersection du plan
  // avec le solide, percée des courbes 3D.
  document.getElementById("sk-silhouette").addEventListener("click", async () => {
    if (!mode.state) return;
    const request = call("sketch_silhouette", { sketch: mode.state.sketch });
    await safe(request);
    const state = await request.catch(() => null);
    if (state?.referenced != null) {
      say(t("Silhouette : {n} arête(s) projetée(s)", { n: state.referenced }));
    }
  });

  for (const [id, mode_, done] of [
    ["sk-ref-edges", "edges", "Arêtes liées : {n} — elles suivent la pièce"],
    ["sk-ref-intersection", "intersection",
     "Courbe d'intersection : {n} arête(s) liée(s)"],
    ["sk-ref-pierce", "pierce", "Points de percée : {n}"],
  ]) {
    document.getElementById(id).addEventListener("click", async () => {
      if (!mode.state) return;
      const request = call("sketch_reference",
        { sketch: mode.state.sketch, mode: mode_ });
      await safe(request);
      const state = await request.catch(() => null);
      if (state?.referenced != null) {
        say(t(done, { n: state.referenced }));
      }
    });
  }

  for (const [id, key, on, off] of [
    ["sk-grid", "gridSnap", "Accrochage à la grille : actif",
     "Accrochage à la grille : coupé"],
    ["sk-comb", "showComb", "Peigne de courbure affiché",
     "Peigne de courbure masqué"],
  ]) {
    const button = document.getElementById(id);
    button.addEventListener("click", () => {
      mode[key] = !mode[key];
      button.classList.toggle("on", mode[key]);
      say(t(mode[key] ? on : off));
      sk.redraw();
    });
  }

  // L'interrupteur des accrochages : gardé d'une séance à l'autre, avec
  // le détail des sortes (Paramètres). L'accrochage rapide passe outre.
  const snapButton = document.getElementById("sk-snap");
  snapButton.classList.toggle("on", mode.snapSettings.enabled);
  snapButton.addEventListener("click", () => {
    sk.setSnapSettings({ ...mode.snapSettings, enabled: !mode.snapSettings.enabled });
    say(t(mode.snapSettings.enabled ? "Accrochages actifs"
      : "Accrochages coupés — le clic droit offre encore l'accrochage rapide"));
    sk.redraw();
  });

  // Affichés par défaut : le bouton enfoncé montre, relâché masque.
  for (const [id, key, on, off] of [
    ["sk-show-rel", "showRelations", "Symboles de relation affichés",
     "Symboles de relation masqués"],
    ["sk-show-dims", "showDims", "Cotes affichées", "Cotes masquées"],
  ]) {
    const button = document.getElementById(id);
    button.classList.add("on");
    button.addEventListener("click", () => {
      mode[key] = mode[key] === false;
      button.classList.toggle("on", mode[key]);
      say(t(mode[key] ? on : off));
      sk.redraw();
    });
  }

  document.getElementById("sk-layers").addEventListener("click", () => {
    if (!mode.state) return;
    const layers = mode.state.layers ?? [];
    const geos = [...new Set(entityPicks().map((s) => s.geo))]
      .filter((g) => g >= 0);
    abandonEntityPanel();
    const colors = LAYER_COLORS.map(([value, label]) => [value, t(label)]);
    panel.open({
      icon: "sk_layers",
      title: t("Calques d'esquisse"),
      groups: [
        ...layers.map((layer, i) => ({ label: layer.name, rows: [
          { type: "text", key: `name${i}`, label: t("Nom"), value: layer.name },
          { type: "select", key: `color${i}`, label: t("Couleur"),
            options: colors, value: layer.color ?? "" },
          { type: "check", key: `visible${i}`, label: t("Visible"),
            value: layer.visible !== false },
          { type: "check", key: `delete${i}`, label: t("Supprimer ce calque"),
            value: false },
        ] })),
        { label: t("Nouveau calque"), rows: [
          { type: "text", key: "newName", label: t("Nom"), value: "",
            placeholder: t("Cotes, axes, contours…") },
        ] },
        ...(geos.length ? [{ label: t("Sélection ({n} entité(s))", { n: geos.length }),
          rows: [{ type: "select", key: "assign", label: t("Ranger sur"),
            options: [["", t("(ne rien changer)")],
                      ["@new", t("Le nouveau calque")],
                      ["@default", t("Calque par défaut")],
                      ...layers.map((l) => [l.name, l.name])],
            value: "" }] }] : []),
      ],
      note: t("Un calque masqué cache ses entités à l'écran ; elles restent "
        + "dans l'esquisse et dans le profil."),
      onApply: async (v) => {
        const next = layersFromPanel(v, layers);
        if (!next) {
          say(t("Calques : chaque calque a un nom, différent des autres"), true);
          return;
        }
        const sketch = mode.state.sketch;
        await safe(call("sketch_layers", { sketch, layers: next }));
        if (v.assign && geos.length) {
          const renamed = next.find((l) => l.rename === v.assign);
          const fresh = String(v.newName ?? "").trim();
          if (v.assign === "@new" && !fresh) {
            say(t("Calques : donnez un nom au nouveau calque"), true);
            return;
          }
          const layer = v.assign === "@default" ? ""
            : v.assign === "@new" ? fresh
              : (renamed ? renamed.name : v.assign);
          await safe(call("sketch_set_layer", { sketch, geos, layer }));
        }
      },
    });
  });

  document.getElementById("sk-text").addEventListener("click", () => {
    if (!mode.state) return;
    abandonEntityPanel();
    panel.open({
      icon: "sk_text",
      title: t("Texte d'esquisse"),
      groups: [{ label: t("Paramètres"), rows: [
        { type: "text", key: "text", label: t("Texte"), value: "FreeSolid" },
        { type: "number", key: "size", label: t("Hauteur"), value: 8,
          unit: "mm", min: 0.1 },
        { type: "number", key: "x", label: t("X"), value: 0, unit: "mm" },
        { type: "number", key: "y", label: t("Y"), value: 0, unit: "mm" },
        { type: "number", key: "angle", label: t("Angle (°)"), value: 0 },
      ] }],
      note: t("Les contours des lettres deviennent des entités bloquées : "
        + "à extruder, graver ou découper."),
      onApply: (v) => safe(call("sketch_add_text", {
        sketch: mode.state.sketch, text: String(v.text ?? ""),
        size: num(v.size) ?? 8, x: num(v.x) ?? 0, y: num(v.y) ?? 0,
        angle: num(v.angle) ?? 0 })),
    });
  });

  document.getElementById("sk-equation").addEventListener("click", () => {
    if (!mode.state) return;
    abandonEntityPanel();
    panel.open({
      icon: "sk_equation",
      title: t("Courbe par équation"),
      groups: [{ label: t("Équation"), rows: [
        { type: "text", key: "x", label: t("x(t)"), value: "t" },
        { type: "text", key: "y", label: t("y(t)"), value: "10*sin(t)" },
        { type: "number", key: "t0", label: t("t début"), value: 0 },
        { type: "number", key: "t1", label: t("t fin"), value: 6.2832 },
      ] }],
      note: t("Fonctions : sin, cos, tan, sqrt, exp, log, abs, pow… ; "
        + "constantes pi et e. x(t) = t : la courbe y = f(x)."),
      onApply: (v) => safe(call("sketch_add_equation", {
        sketch: mode.state.sketch, x: String(v.x ?? "t"),
        y: String(v.y ?? "0"), t0: num(v.t0) ?? 0, t1: num(v.t1) ?? 1 })),
    });
  });

  document.getElementById("sk-repair").addEventListener("click", async () => {
    if (!mode.state) return;
    const request = call("sketch_repair", { sketch: mode.state.sketch });
    await safe(request);
    const state = await request.catch(() => null);
    if (state?.repair) {
      const { redundant, conflicts, joined } = state.repair;
      say(t("Réparation : {r} relation(s) en trop, {c} conflit(s) levé(s), {j} jonction(s)",
        { r: redundant, c: conflicts, j: joined }));
    }
  });

  document.getElementById("sk-define").addEventListener("click", async () => {
    if (!mode.state) return;
    const request = call("sketch_fully_define", { sketch: mode.state.sketch });
    await safe(request);
    const state = await request.catch(() => null);
    if (state?.added != null) {
      say(t("Définir entièrement : {n} cote(s) ajoutée(s)", { n: state.added }));
    }
  });

  document.getElementById("sk-block-save").addEventListener("click", () => {
    if (!mode.state) return;
    if (!entityPicks().length) {
      say(t("Bloc : sélectionnez d'abord des entités"), true);
      return;
    }
    const geos = [...new Set(entityPicks().map((s) => s.geo))];
    abandonEntityPanel();
    panel.open({
      icon: "sk_block",
      title: t("Créer un bloc"),
      groups: [{ label: t("Bloc"), rows: [
        { type: "text", key: "name", label: t("Nom"), value: "" },
      ] }],
      note: t("Les entités choisies et leurs relations sont rangées sous "
        + "ce nom ; on les réinsère ensuite où l'on veut."),
      onApply: (v) => {
        const blockName = String(v.name ?? "").trim();
        if (!blockName) {
          say(t("donnez un nom au bloc"), true);
          return;
        }
        call("sketch_block_save", { sketch: mode.state.sketch, geos,
          name: blockName })
          .then(() => say(t("Bloc « {name} » enregistré", { name: blockName })))
          .catch((error) => say(error.message, true));
      },
    });
  });

  document.getElementById("sk-block-insert").addEventListener("click", async () => {
    if (!mode.state) return;
    let blocks = [];
    try {
      ({ blocks } = await call("sketch_blocks"));
    } catch (error) {
      say(error.message, true);
      return;
    }
    if (!blocks.length) {
      say(t("Aucun bloc : créez-en un depuis une sélection"), true);
      return;
    }
    abandonEntityPanel();
    panel.open({
      icon: "sk_block_insert",
      title: t("Insérer un bloc"),
      groups: [{ label: t("Bloc"), rows: [
        { type: "select", key: "name", label: t("Bloc"),
          options: blocks.map((b) => [b.name, b.name]),
          value: blocks[0].name },
        { type: "number", key: "x", label: t("X"), value: 0, unit: "mm" },
        { type: "number", key: "y", label: t("Y"), value: 0, unit: "mm" },
        { type: "number", key: "angle", label: t("Angle (°)"), value: 0 },
        { type: "number", key: "scale", label: t("Échelle"), value: 1,
          min: 0.001 },
      ] }],
      onApply: (v) => safe(call("sketch_block_insert", {
        sketch: mode.state.sketch, name: v.name, x: num(v.x) ?? 0,
        y: num(v.y) ?? 0, angle: num(v.angle) ?? 0,
        scale: num(v.scale) ?? 1 })),
    });
  });

  let offsetPreviewGen = 0;

  async function previewOffset(geos, v) {
    const gen = ++offsetPreviewGen;
    const distance = num(v.distance);
    if (!sk.previewLine || !mode.state || !(distance > 0)) return;
    try {
      const { points } = await call("sketch_offset_preview", {
        sketch: mode.state.sketch, geos, distance, reversed: !!v.reversed });
      if (gen !== offsetPreviewGen || !panel.active) return;
      sk.previewLine.geometry.setFromPoints(
        points.map(([x, y]) => new THREE.Vector3(x, y, 0)));
      sk.previewLine.visible = true;
    } catch {
      if (gen === offsetPreviewGen) sk.previewLine.visible = false;
    }
  }

  document.getElementById("sk-offset").addEventListener("click", () => {
    if (!mode.state) return;
    if (!entityPicks().length) {
      say("Décaler : sélectionnez d'abord une chaîne d'entités", true);
      return;
    }
    const geos = entityPicks().map((s) => s.geo);
    // Arêtes projetées (bloquées) : on veut la copie seule dans le profil.
    const blocked = new Set((mode.state.constraints ?? [])
      .filter((c) => c.type === "Block").map((c) => c.geos[0]));
    const projected = geos.every((geo) => blocked.has(geo));
    abandonEntityPanel();
    panel.open({
      icon: "offset",
      title: t("Décaler"),
      groups: [{
        label: t("Paramètres"),
        rows: [
          { type: "number", key: "distance", label: t("Distance"), value: 5,
            unit: "mm", min: 0.01 },
          { type: "check", key: "reversed", label: t("Inverser le côté"),
            value: false },
          { type: "check", key: "construction",
            label: t("Originaux en construction"), value: projected },
        ],
      }],
      note: t("Les copies restent libres — le décalage paramétrique " +
            "viendra plus tard."),
      // Aperçu : la copie se dessine avant de valider — on voit le côté.
      onChange: (v) => previewOffset(geos, v),
      onCancel: () => { if (sk.previewLine) sk.previewLine.visible = false; },
      onApply: (v) => safe(call("sketch_offset", {
        sketch: mode.state.sketch, geos,
        distance: num(v.distance) ?? 5,
        reversed: !!v.reversed, construction: !!v.construction })
        .finally(() => { if (sk.previewLine) sk.previewLine.visible = false; })),
    });
  });

  const imageInput = document.getElementById("sk-image-file");
  document.getElementById("sk-image").addEventListener("click", () => {
    if (!mode.active || !mode.state) {
      say("Image d'esquisse : ouvrez d'abord une esquisse.", true);
      return;
    }
    imageInput.value = "";
    imageInput.click();
  });
  imageInput.addEventListener("change", () => {
    const file = imageInput.files?.[0];
    if (!file) return;
    loadSketchImage(file);
  });

  // Convertir les entités : le contour de la face porteuse arrive en
  // géométrie réelle bloquée — le point de départ classique.
  document.getElementById("sk-convert").addEventListener("click", () => {
    if (!mode.active || !mode.state) return;
    call("sketch_convert", { sketch: mode.state.sketch })
      .then((state) => {
        applyState(state);
        say(t("Converti : {n} entité(s)", { n: state.converted })
          + (state.skipped ? t(" — {n} ignorée(s)", { n: state.skipped }) : ""));
      })
      .catch((error) => say(error.message, true));
  });
  document.getElementById("sk-finish").addEventListener("click", () => exit(true));
  document.getElementById("sk-cancel").addEventListener("click", () => exit(false));
}
