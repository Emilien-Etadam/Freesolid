// Panneaux des fonctions de FEATURES : sélection courante, ouverture
// (aperçu, réédition, refus du moteur), poignée de profondeur — à la
// création comme à la réédition —, liaison des boutons du ruban.

import { panelNotice } from "../panel.js";
import { num, plainNumber } from "../num.js";
import { resolveProfileSketch } from "../features.js";
import { combineFinished } from "../combine.js";
import { latestGraphOrRepeat } from "../graph.js";

export function installFeaturePanel(ctx) {
  const {
    panel, confirm, call, say, refresh, updateFilletRadiusBubble,
    schedulePreview, findFeatureInTree, refreshAny, enterGraphFeature,
    featureCommand,
  } = ctx;

  // Dans openFeaturePanel, `ctx` est le contexte des fonctions (FEATURES) :
  // l'état de main.js passe par `app`.
  const app = ctx;

  // Habillages : la zone de sélection du panneau absorbe les clics de la
  // zone graphique (arêtes ou face selon la commande) — on peut ouvrir la
  // commande d'abord et cliquer ensuite, comme dans les modeleurs courants.
  function currentSelection(accepts) {
    if (accepts.includes("edges") && app.selectedEdges.size) {
      return { kind: "edges", edges: [...app.selectedEdges] };
    }
    if (accepts.includes("face") && app.selectedFaceId !== null) {
      return { kind: "face", face: app.selectedFaceId };
    }
    // Surface cliquée avant la commande (décaler, prolonger, ajuster).
    if (accepts.includes("surface") && app.selectedSurface) {
      return { kind: "surface", name: app.selectedSurface.name,
               label: app.selectedSurface.label };
    }
    // Fonction cliquée dans l'arbre avant la commande (répétitions,
    // symétrie) : elle remplit d'emblée la case, comme une face présélectionnée.
    // Pas un réseau de corps, la ligne d'une de ses copies ni un enlèvement
    // venu d'un autre corps (`edits`) : ils ne se répètent pas.
    const feature = accepts.includes("feature")
      && findFeatureInTree(app.lastTree, app.selectedFeatureName);
    if (feature && feature.type_key !== "sketch"
        && feature.type_key !== "body_pattern" && !feature.edits) {
      return { kind: "feature", items: [
        { kind: "feature", name: feature.name, label: feature.label }] };
    }
    return null;
  }

  // Registry : un bind unique pour tous les panneaux « ouvrir → éditer →
  // aperçu → OK ». Les panneaux bespoke (équations, assemblage, datum…)
  // restent plus bas.
  /** Panneau d'une fonction de `FEATURES` — ruban et palette du graphe.
   *  `sketchOverride` : profil imposé par la palette, sinon la sélection. */
  function openFeaturePanel(entry, sketchOverride) {
    const ctx = {
      lastTree: app.lastTree,
      selection: currentSelection,
      selectedSketch: sketchOverride ?? app.selectedSketch,
    };
    Object.defineProperty(ctx, "lastFaceHit", {
      get: () => app.lastFaceHit,
    });
    const blocked = entry.guard?.(ctx);
    if (blocked) { say(blocked, true); return; }
    const spline = app.selectedFaceId != null && app.meshGroups.some(
      (g) => g.faceId === app.selectedFaceId && g.spline);
    const spec = {
      icon: entry.icon,
      title: entry.title,
      groups: entry.groups(ctx),
      note: typeof entry.noteFn === "function"
        ? entry.noteFn(ctx, { spline })
        : entry.note,
      onApply: (v) => {
        const built = entry.build(v, ctx);
        if (!built) {
          const raw = typeof entry.invalid === "function"
            ? entry.invalid(v, ctx)
            : (entry.invalid ?? "Valeurs invalides");
          const notice = panelNotice(raw);
          if (notice) say(notice.text, notice.tone === "error");
          return;
        }
        if (typeof entry.confirm === "function") {
          const question = entry.confirm(v, ctx);
          if (question && !confirm(question)) return;
        }
        const run = entry.refresh === "any" ? refreshAny : refresh;
        const before = ctx.lastTree;
        const started = Date.now();
        const promise = call(built.op, built.params).then((tree) => {
          if (built.op === "add_boolean") {
            combineFinished(before, built.params?.tool,
                            (Date.now() - started) / 1000);
          }
          return tree;
        });
        // Refus du moteur : le panneau revient avec les valeurs saisies, au
        // lieu de les perdre (le message reste dans la barre d'état).
        promise.catch(() => {
          if (panel.active) return;
          openFeaturePanel(entry, sketchOverride);
          panel.restore(v);
        });
        if (entry.openGraphEditor) {
          run(promise.then((tree) => {
            queueMicrotask(() => {
              const created = latestGraphOrRepeat(tree);
              if (created) enterGraphFeature(created);
            });
            return tree;
          }));
        } else {
          run(promise);
        }
      },
    };
    const depthHandle = ["btn-pad", "btn-pocket"].includes(entry.button)
      ? extrudeDepthHandle(entry, ctx) : null;
    if (depthHandle) spec.onClose = () => depthHandle.close();
    if (entry.preview !== false) {
      spec.onChange = (v, how) => {
        schedulePreview(entry.build(v, ctx), how);
        if (entry.button === "btn-fillet") updateFilletRadiusBubble(v);
        depthHandle?.update(v);
      };
      // Œil de l'en-tête : couper l'aperçu (fonction lourde), le rallumer.
      spec.onPreview = (on, v) =>
        schedulePreview(on ? entry.build(v, ctx) : null);
    }
    // Tant que la saisie est incomplète, le panneau dit ce qui manque.
    spec.hint = (v) => (entry.build(v, ctx) ? null
      : typeof entry.invalid === "function" ? entry.invalid(v, ctx)
        : entry.invalid ?? null);
    panel.open(spec);
  }

  /** Flèche de profondeur d'un panneau. `where(v)` la pose pour les
   *  valeurs du panneau — `{ origin, dir, length, factor, key }` — ou rend
   *  null (pas de flèche) ; `ready()` dit qu'elle sait répondre. La tirer
   *  change la cote `key` du panneau (`factor` fois le déplacement),
   *  l'aperçu suit. */
  function depthArrow(where) {
    let ready = false;
    let dragging = false;
    let closed = false;
    let last = null;

    function show(v) {
      last = v;
      if (closed || !ready || dragging) return;
      const at = where(v);
      if (!at) {
        ctx.handles?.hide();
        return;
      }
      let shown = at.length;
      ctx.handles.show({
        origin: at.origin, dir: at.dir, owner: "panel",
        onDrag: (d) => {
          dragging = true;
          const next = Math.max(0.5,
            Math.round((at.length + d * at.factor) * 2) / 2);
          if (next === shown) return;
          shown = next;
          // Le fantôme suit la flèche pendant le glisser.
          panel.restore({ [at.key]: next }, { live: true });
        },
        onEnd: () => {
          dragging = false;
          show(last);
        },
      });
    }

    return {
      update: (v) => show(v),
      ready: () => {
        ready = true;
        if (last) show(last);
      },
      close: () => { closed = true; ctx.handles?.hide(); },
    };
  }

  /** Flèche au bout de l'extrusion (ou de l'enlèvement) qu'on crée.
   *  Profondeur « borgne » ou « plan milieu » seulement. */
  function extrudeDepthHandle(entry, featureCtx) {
    const pocket = entry.button === "btn-pocket";
    const sketch = resolveProfileSketch(featureCtx)?.name;
    let frame = null;
    const arrow = depthArrow((v) => {
      const length = num(v.length);
      if (!(length > 0) || (v.cond !== "borgne" && v.cond !== "milieu")) {
        return null;
      }
      const half = v.cond === "milieu";
      const sign = (pocket ? -1 : 1) * (v.reversed && !half ? -1 : 1);
      const dir = frame.normal.map((c) => c * sign);
      const reach = half ? length / 2 : length;
      return { origin: frame.center.map((c, i) => c + dir[i] * reach), dir,
               length, factor: half ? 2 : 1, key: "length" };
    });
    if (sketch) {
      call("sketch_frame", { sketch }).then((result) => {
        frame = result;
        arrow.ready();
      }).catch(() => {});
    }
    return arrow;
  }

  /** Flèche de la fonction qu'on réédite : le moteur la pose au bout de
   *  l'extrusion ou de l'enlèvement (`feature_drag_info`), ou n'en donne
   *  pas. Une équation tapée dans la cote la retire. */
  function editDepthHandle(feature) {
    let drag = null;
    const arrow = depthArrow((v) => {
      const length = plainNumber(v[drag.key]);
      if (!(length > 0)) return null;
      const shift = (length - drag.value) / drag.factor;
      return { origin: drag.point.map((c, i) => c + drag.normal[i] * shift),
               dir: drag.normal, length, factor: drag.factor, key: drag.key };
    });
    call("feature_drag_info", { feature: feature.name }).then((info) => {
      drag = info.drag;
      if (drag) arrow.ready();
    }).catch(() => {});
    return arrow;
  }

  function bindFeature(entry) {
    const ids = entry.buttons ?? [entry.button];
    for (const id of ids) {
      const el = document.getElementById(id);
      if (!el || el.dataset.boundFeature) continue;
      el.dataset.boundFeature = "1";
      el.addEventListener("click", () =>
        featureCommand(() => openFeaturePanel(entry)));
    }
  }

  return { currentSelection, openFeaturePanel, bindFeature, editDepthHandle };
}
