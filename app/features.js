// Registry déclaratif des panneaux de fonctions mécaniques.
// Le branchement (clic → featureCommand → panel.open) vit dans main.js.
//
// Chaque entrée décrit un panneau « ouvrir → éditer → aperçu → OK ».
// build(v, ctx) rend { op, params } ou null (aperçu éteint, OK bloqué).

import { num } from "./num.js";

export function hasSelection(sel) {
  return !!sel && (sel.kind === "edges"
    ? sel.edges.length > 0 : sel.face != null);
}

export function dressupParams(sel) {
  return sel.kind === "edges"
    ? { edges: sel.edges } : { face: sel.face };
}

function dressup({ button, icon, title, selectionLabel, group, rows, build,
                   accepts = ["face"], hint }) {
  return {
    button, icon, title,
    groups: (ctx) => [
      { label: selectionLabel,
        rows: [{ type: "selection", key: "sel", accepts, hint,
                 value: ctx.selection(accepts) }] },
      { label: group, rows },
    ],
    build: (v) => hasSelection(v.sel) ? build(v) : null,
    invalid: (v) => hasSelection(v.sel)
      ? "Valeur invalide"
      : `${title} : cliquez d'abord dans la zone graphique`,
    refresh: "part",
  };
}

function revolved({ button, op, icon, title }) {
  return {
    button, icon, title,
    groups: () => [{
      label: "Direction 1",
      rows: [
        { type: "number", key: "angle", label: "Angle", value: 360,
          unit: "°", min: 0.01 },
      ],
    }],
    note: "Axe de révolution : l'axe vertical de l'esquisse",
    build: (v) => {
      const angle = num(v.angle);
      return angle ? { op, params: { angle } } : null;
    },
    invalid: "Angle invalide",
    refresh: "part",
  };
}

function surface({ button, icon, title, groups, note, build, invalid }) {
  return {
    button, icon, title,
    groups: typeof groups === "function" ? groups : () => groups,
    note,
    build,
    invalid: invalid ?? "Valeurs invalides",
    // Les ops surfaciques ne sont pas dans _PREVIEWABLE : pas d'aperçu
    // aujourd'hui, donc pas d'onChange (zéro changement de comportement).
    preview: false,
    refresh: "part",
  };
}

export const FEATURES = [
  {
    button: "btn-pad",
    icon: "PartDesign_Pad.svg",
    title: "Bossage/Base extrudé",
    groups: () => [{
      label: "Direction 1",
      rows: [
        { type: "select", key: "cond", value: "borgne",
          options: [["borgne", "Borgne"], ["milieu", "Plan milieu"]] },
        { type: "number", key: "length", label: "Profondeur", value: 10,
          unit: "mm", min: 0.01 },
        { type: "check", key: "reversed", label: "Inverser la direction",
          value: false, showIf: (v) => v.cond !== "milieu" },
      ],
    }],
    build: (v) => {
      const length = Math.abs(num(v.length) ?? 0);
      if (!length) return null;
      return { op: "add_pad",
               params: { length, reversed: !!v.reversed,
                         midplane: v.cond === "milieu" } };
    },
    invalid: "Profondeur invalide",
    refresh: "part",
  },
  {
    button: "btn-pocket",
    icon: "PartDesign_Pocket.svg",
    title: "Enlèvement de matière extrudé",
    groups: () => [{
      label: "Direction 1",
      rows: [
        { type: "select", key: "cond", value: "travers",
          options: [["travers", "À travers tout"], ["borgne", "Borgne"]] },
        { type: "number", key: "length", label: "Profondeur", value: 10,
          unit: "mm", min: 0.01, showIf: (v) => v.cond === "borgne" },
        { type: "check", key: "reversed", label: "Inverser la direction",
          value: false },
      ],
    }],
    build: (v) => {
      const reversed = !!v.reversed;
      if (v.cond === "travers") {
        return { op: "add_pocket", params: { through: true, reversed } };
      }
      const length = Math.abs(num(v.length) ?? 0);
      return length ? { op: "add_pocket", params: { length, reversed } } : null;
    },
    invalid: "Profondeur invalide",
    refresh: "part",
  },
  revolved({
    button: "btn-revolution",
    op: "add_revolution",
    icon: "PartDesign_Revolution.svg",
    title: "Bossage/Base avec révolution",
  }),
  revolved({
    button: "btn-groove",
    op: "add_groove",
    icon: "PartDesign_Groove.svg",
    title: "Enlèvement de matière avec révolution",
  }),
  {
    button: "btn-hole",
    icon: "PartDesign_Hole.svg",
    title: "Assistant de perçage",
    groups: () => [
      {
        label: "Type de perçage",
        rows: [
          { type: "select", key: "cut", value: "none",
            options: [["none", "Perçage"], ["lamage", "Lamage"],
                      ["fraisage", "Fraisage"]] },
          { type: "number", key: "diameter", label: "Diamètre", value: 6,
            unit: "mm", min: 0.01 },
          { type: "number", key: "cutDiameter", label: "Ø de tête",
            value: 11, unit: "mm", min: 0.01,
            showIf: (v) => v.cut !== "none" },
          { type: "number", key: "cutDepth", label: "Prof. lamage",
            value: 3, unit: "mm", min: 0.01,
            showIf: (v) => v.cut === "lamage" },
          { type: "number", key: "cutAngle", label: "Angle", value: 90,
            unit: "°", min: 1, showIf: (v) => v.cut === "fraisage" },
        ],
      },
      {
        label: "Condition de fin",
        rows: [
          { type: "select", key: "cond", value: "travers",
            options: [["travers", "À travers tout"],
                      ["borgne", "Borgne"]] },
          { type: "number", key: "depth", label: "Profondeur", value: 15,
            unit: "mm", min: 0.01, showIf: (v) => v.cond === "borgne" },
        ],
      },
    ],
    note: "Position : la dernière esquisse (un cercle par perçage). " +
          "Le diamètre saisi remplace celui des cercles.",
    build: (v) => {
      const diameter = num(v.diameter);
      if (!(diameter > 0)) return null;
      const params = { diameter, cut: v.cut };
      if (v.cond === "borgne") {
        const depth = num(v.depth);
        if (!(depth > 0)) return null;
        params.depth = depth;
      } else {
        params.through = true;
      }
      if (v.cut !== "none") {
        const cutDiameter = num(v.cutDiameter);
        if (!(cutDiameter > diameter)) return null; // le lamage englobe le trou
        params.cut_diameter = cutDiameter;
        if (v.cut === "lamage") {
          const cutDepth = num(v.cutDepth);
          if (!(cutDepth > 0)) return null;
          params.cut_depth = cutDepth;
        } else {
          const cutAngle = num(v.cutAngle);
          if (cutAngle > 0) params.cut_angle = cutAngle;
        }
      }
      return { op: "add_hole", params };
    },
    invalid: "Valeurs du perçage invalides",
    refresh: "part",
  },
  {
    button: "btn-loft",
    icon: "PartDesign_AdditiveLoft.svg",
    title: "Bossage/Base lissé",
    groups: () => [
      { label: "Profils",
        rows: [{ type: "selection", key: "profiles", accepts: ["sketch"],
                 multiple: true,
                 hint: "Cliquez les esquisses dans l'arbre, dans " +
                       "l'ordre du lissage" }] },
      { label: "Options",
        rows: [
          { type: "check", key: "subtractive",
            label: "Enlèvement de matière", value: false },
          { type: "check", key: "ruled", label: "Lissage droit (réglé)",
            value: false },
          { type: "check", key: "closed", label: "Boucle fermée",
            value: false },
        ] },
    ],
    build: (v) => {
      const items = v.profiles?.items ?? [];
      if (items.length < 2) return null;
      return { op: "add_loft", params: {
        sketches: items.map((i) => i.name),
        subtractive: !!v.subtractive,
        ruled: !!v.ruled,
        closed: !!v.closed } };
    },
    invalid: "Lissage : au moins deux profils",
    refresh: "part",
  },
  {
    button: "btn-sweep",
    icon: "PartDesign_AdditivePipe.svg",
    title: "Bossage/Base balayé",
    groups: () => [
      { label: "Profil",
        rows: [{ type: "selection", key: "profile", accepts: ["sketch"],
                 hint: "Cliquez l'esquisse du profil dans l'arbre" }] },
      { label: "Trajectoire",
        rows: [{ type: "selection", key: "spine", accepts: ["sketch"],
                 hint: "Puis l'esquisse de la trajectoire" }] },
      { label: "Options",
        rows: [{ type: "check", key: "subtractive",
                 label: "Enlèvement de matière", value: false }] },
    ],
    build: (v) => {
      if (!v.profile || !v.spine) return null;
      if (v.profile.name === v.spine.name) return null;
      return { op: "add_sweep", params: {
        profile: v.profile.name,
        spine: v.spine.name,
        subtractive: !!v.subtractive } };
    },
    invalid: "Balayage : un profil puis une trajectoire (différents)",
    refresh: "part",
  },
  {
    button: "btn-helix",
    icon: "PartDesign_AdditiveHelix.svg",
    title: "Hélice",
    groups: () => [{
      label: "Paramètres",
      rows: [
        { type: "number", key: "pitch", label: "Pas", value: 8,
          unit: "mm", min: 0.01 },
        { type: "number", key: "height", label: "Hauteur", value: 40,
          unit: "mm", min: 0.01 },
      ],
    }],
    note: "Le profil (dernière esquisse) tourne autour de l'axe " +
          "vertical de son esquisse — dessinez-le décalé de l'axe.",
    build: (v) => {
      const pitch = num(v.pitch);
      const height = num(v.height);
      return pitch > 0 && height > 0
        ? { op: "add_helix", params: { pitch, height } } : null;
    },
    invalid: "Pas et hauteur doivent être positifs",
    refresh: "part",
  },
  dressup({
    button: "btn-text",
    icon: "Draft_ShapeString.svg", title: "Texte",
    selectionLabel: "Face d'appui",
    group: "Texte",
    rows: [
      { type: "text", key: "content", label: "Texte", value: "",
        placeholder: "REF-001" },
      { type: "number", key: "size", label: "Hauteur", value: 8,
        unit: "mm", min: 0.1 },
      { type: "number", key: "depth", label: "Profondeur", value: 1,
        unit: "mm", min: 0.01 },
      { type: "check", key: "emboss", label: "En relief (bossage)",
        value: false },
      { type: "number", key: "x", label: "Décalage X", value: 0,
        unit: "mm" },
      { type: "number", key: "y", label: "Décalage Y", value: 0,
        unit: "mm" },
    ],
    build: (v) => {
      const content = (v.content ?? "").trim();
      const size = num(v.size);
      const depth = num(v.depth);
      if (!content || !(size > 0) || !(depth > 0)) return null;
      return { op: "add_text", params: {
        text: content, face: v.sel.face, size, depth,
        x: num(v.x) ?? 0, y: num(v.y) ?? 0,
        emboss: !!v.emboss } };
    },
  }),
  dressup({
    button: "btn-fillet",
    icon: "PartDesign_Fillet.svg", title: "Congé",
    selectionLabel: "Éléments à arrondir",
    accepts: ["edges", "face"],
    hint: "Cliquez des arêtes (Ctrl = ajouter) ou une face",
    group: "Paramètres du congé",
    rows: [{ type: "number", key: "radius", label: "Rayon", value: 3,
             unit: "mm", min: 0.01 }],
    build: (v) => {
      const radius = num(v.radius);
      return radius > 0
        ? { op: "add_fillet",
            params: { ...dressupParams(v.sel), radius } }
        : null;
    },
  }),
  dressup({
    button: "btn-chamfer",
    icon: "PartDesign_Chamfer.svg", title: "Chanfrein",
    selectionLabel: "Éléments à chanfreiner",
    accepts: ["edges", "face"],
    hint: "Cliquez des arêtes (Ctrl = ajouter) ou une face",
    group: "Paramètres du chanfrein",
    rows: [{ type: "number", key: "size", label: "Distance", value: 2,
             unit: "mm", min: 0.01 }],
    build: (v) => {
      const size = num(v.size);
      return size > 0
        ? { op: "add_chamfer",
            params: { ...dressupParams(v.sel), size } }
        : null;
    },
  }),
  dressup({
    button: "btn-shell",
    icon: "PartDesign_Thickness.svg", title: "Coque",
    selectionLabel: "Faces à supprimer",
    group: "Paramètres",
    rows: [{ type: "number", key: "thickness", label: "Épaisseur", value: 2,
             unit: "mm", min: 0.01 }],
    build: (v) => {
      const thickness = num(v.thickness);
      return thickness > 0
        ? { op: "add_thickness",
            params: { face: v.sel.face, thickness } }
        : null;
    },
  }),
  dressup({
    button: "btn-draft",
    icon: "PartDesign_Draft.svg", title: "Dépouille",
    selectionLabel: "Faces à dépouiller",
    group: "Angle de dépouille",
    rows: [
      { type: "number", key: "angle", label: "Angle", value: 3,
        unit: "°", min: 0.01 },
      { type: "select", key: "neutral", value: "XY", label: "Plan neutre",
        options: [["XY", "Plan de dessus"], ["XZ", "Plan de face"],
                  ["YZ", "Plan de droite"]] },
    ],
    build: (v) => {
      const angle = num(v.angle);
      return angle > 0
        ? { op: "add_draft",
            params: { face: v.sel.face, angle, neutral: v.neutral } }
        : null;
    },
  }),
  {
    button: "btn-linpattern",
    icon: "PartDesign_LinearPattern.svg",
    title: "Répétition linéaire",
    groups: () => [{
      label: "Direction 1",
      rows: [
        { type: "select", key: "axis", value: "X", label: "Direction",
          options: [["X", "Axe X"], ["Y", "Axe Y"], ["Z", "Axe Z"]] },
        { type: "number", key: "length", label: "Longueur totale",
          value: 40, unit: "mm", min: 0.01 },
        { type: "number", key: "count", label: "Nombre d'occurrences",
          value: 3, min: 2, step: 1 },
      ],
    }],
    note: "S'applique à la dernière fonction (bossage ou enlèvement)",
    build: (v) => {
      const length = num(v.length);
      const count = parseInt(v.count, 10);
      return length && count >= 2
        ? { op: "add_linear_pattern", params: { axis: v.axis, length, count } }
        : null;
    },
    invalid: "Valeurs invalides",
    refresh: "part",
  },
  {
    button: "btn-polpattern",
    icon: "PartDesign_PolarPattern.svg",
    title: "Répétition circulaire",
    groups: () => [{
      label: "Direction 1",
      rows: [
        { type: "number", key: "angle", label: "Angle", value: 360,
          unit: "°", min: 0.01 },
        { type: "number", key: "count", label: "Nombre d'occurrences",
          value: 4, min: 2, step: 1 },
      ],
    }],
    note: "Axe : Z — s'applique à la dernière fonction",
    build: (v) => {
      const angle = num(v.angle);
      const count = parseInt(v.count, 10);
      return angle && count >= 2
        ? { op: "add_polar_pattern", params: { count, angle } } : null;
    },
    invalid: "Valeurs invalides",
    refresh: "part",
  },
  {
    button: "btn-mirror",
    icon: "PartDesign_Mirrored.svg",
    title: "Symétrie",
    groups: () => [{
      label: "Plan de symétrie",
      rows: [
        { type: "select", key: "plane", value: "YZ",
          options: [["YZ", "Plan de droite"], ["XZ", "Plan de face"],
                    ["XY", "Plan de dessus"]] },
      ],
    }],
    note: "S'applique à la dernière fonction (bossage ou enlèvement)",
    build: (v) => ({ op: "add_mirror", params: { plane: v.plane } }),
    refresh: "part",
  },
  {
    button: "btn-boolean",
    icon: "PartDesign_Boolean.svg",
    title: "Combiner",
    guard: (ctx) => {
      const others = (ctx.lastTree?.bodies ?? []).filter((b) => !b.active);
      return others.length ? null
        : "Combiner : créez d'abord un second corps";
    },
    groups: (ctx) => {
      const others = (ctx.lastTree?.bodies ?? []).filter((b) => !b.active);
      return [{
        label: "Opération",
        rows: [
          { type: "select", key: "type", value: "cut",
            options: [["cut", "Soustraire"], ["fuse", "Ajouter"],
                      ["common", "Intersection"]] },
          { type: "select", key: "tool", value: others[0].name,
            label: "Corps outil",
            options: others.map((b) => [b.name, b.label]) },
        ],
      }];
    },
    note: "S'applique au corps actif ; le corps outil est absorbé " +
          "par l'opération.",
    build: (v) => ({ op: "add_boolean",
      params: { tool: v.tool, type: v.type } }),
    refresh: "part",
  },
  surface({
    button: "btn-surf-extrude",
    icon: "Surface_Filling.svg", title: "Surface extrudée",
    groups: [{ label: "Paramètres", rows: [
      { type: "number", key: "length", label: "Longueur", value: 20,
        unit: "mm" },
    ] }],
    note: "Utilise la dernière esquisse — le profil peut être OUVERT.",
    build: (v) => {
      const length = num(v.length);
      return length ? { op: "surface_extrude", params: { length } } : null;
    },
  }),
  surface({
    button: "btn-surf-revolve",
    icon: "PartDesign_Revolution.svg", title: "Surface de révolution",
    groups: [{ label: "Paramètres", rows: [
      { type: "number", key: "angle", label: "Angle", value: 360,
        unit: "°", min: 0.01 },
    ] }],
    note: "Autour de l'axe vertical de la dernière esquisse.",
    build: (v) => {
      const angle = num(v.angle);
      return angle ? { op: "surface_revolve", params: { angle } } : null;
    },
  }),
  surface({
    button: "btn-surf-loft",
    icon: "PartDesign_AdditiveLoft.svg",
    title: "Surface lissée",
    groups: [{ label: "Profils",
      rows: [{ type: "selection", key: "profiles", accepts: ["sketch"],
               multiple: true,
               hint: "Cliquez les esquisses dans l'arbre, dans l'ordre" }] }],
    build: (v) => {
      const items = v.profiles?.items ?? [];
      if (items.length < 2) return null;
      return { op: "surface_loft",
               params: { sketches: items.map((i) => i.name) } };
    },
    invalid: "Surface lissée : au moins deux profils",
  }),
  surface({
    button: "btn-surf-sew",
    icon: "Part_3D_object.svg",
    title: "Coudre",
    groups: [{ label: "Surfaces",
      rows: [{ type: "selection", key: "surfaces", accepts: ["surface"],
               multiple: true,
               hint: "Cliquez les surfaces dans l'arbre" }] }],
    note: "Si la peau cousue est fermée, elle devient un solide.",
    build: (v) => {
      const items = v.surfaces?.items ?? [];
      if (items.length < 2) return null;
      return { op: "surface_sew",
               params: { surfaces: items.map((i) => i.name) } };
    },
    invalid: "Coudre : au moins deux surfaces",
  }),
  surface({
    button: "btn-surf-thicken",
    icon: "PartDesign_Thickness.svg",
    title: "Épaissir",
    groups: [
      { label: "Surface",
        rows: [{ type: "selection", key: "surface", accepts: ["surface"],
                 hint: "Cliquez une surface dans l'arbre" }] },
      { label: "Paramètres",
        rows: [{ type: "number", key: "thickness", label: "Épaisseur",
                 value: 2, unit: "mm" }] },
    ],
    build: (v) => {
      const thickness = num(v.thickness);
      if (!v.surface || !thickness) return null;
      return { op: "surface_thicken",
               params: { surface: v.surface.name, thickness } };
    },
    invalid: "Épaissir : une surface et une épaisseur non nulle",
  }),
];
