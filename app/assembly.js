// Mode assemblage : arbre, maillages, contraintes, glisser et vue éclatée.
// `assemblyState` et `asmGroup` restent dans main.js (le survol et le
// menu les lisent) et sont mis à jour via ctx.

import { t } from "./i18n.js";
import { num } from "./num.js";

/** Un pas de la vue éclatée, vers 0 ou 1. */
export function explodeStep(factor, target, step = 0.06) {
  if (factor === target) return factor;
  return factor + Math.sign(target - factor) * Math.min(step, Math.abs(target - factor));
}

/** Branche l'assemblage. Les fonctions renvoyées sont celles que le
 *  reste de l'application appelle déjà. */
export function installAssembly(ctx) {
  const {
    THREE, scene, sceneTheme, showMesh, showEdgeLines,
    selectedMaterial, baseMaterial,
    call, say, sayUntilAck, panel, prompt,
    startProgressWatch, stopProgressWatch,
    renderTree, updateViewport, treeEl, treeIcon, openMenu,
    closeGraph, updateEditMode, pickEl, clearGhost,
    renderer, raycaster, pointer, camera, setPointerFromEvent,
  } = ctx;

  // ---------- assemblage v1 ----------

  let selectedComponent = null;
  const asmOutlineMaterial = new THREE.LineBasicMaterial({ color: sceneTheme.edge });

  function clearAssemblyView() {
    if (ctx.asmGroup) {
      scene.remove(ctx.asmGroup);
      ctx.asmGroup.traverse((o) => o.geometry?.dispose?.());
      ctx.asmGroup = null;
    }
    ctx.assemblyState = null;
    selectedComponent = null;
  }

  function showAssemblyMeshes(data) {
    if (ctx.asmGroup) {
      scene.remove(ctx.asmGroup);
      ctx.asmGroup.traverse((o) => o.geometry?.dispose?.());
    }
    // Le mode pièce s'efface : maillages, arêtes, corps estompés.
    showMesh({ positions: [], indices: [], groups: [] });
    showEdgeLines({ positions: [], indices: [], groups: [] });
    ctx.asmGroup = new THREE.Group();
    for (const comp of data.components) {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position",
        new THREE.Float32BufferAttribute(comp.mesh.positions, 3));
      geometry.setIndex(comp.mesh.indices);
      geometry.computeVertexNormals();
      const mesh = new THREE.Mesh(geometry,
        comp.name === selectedComponent ? selectedMaterial : baseMaterial);
      mesh.userData.component = comp.name;
      mesh.userData.componentLabel = comp.label;
      mesh.userData.groups = comp.mesh.groups; // picking de faces (joints)
      const outline = new THREE.LineSegments(
        new THREE.EdgesGeometry(geometry, 25),
        asmOutlineMaterial);
      mesh.add(outline);
      ctx.asmGroup.add(mesh);
    }
    scene.add(ctx.asmGroup);
    computeExplodeDirs(); // la vue éclatée survit aux reconstructions
  }

  function selectComponent(name) {
    selectedComponent = name;
    if (ctx.asmGroup) {
      for (const mesh of ctx.asmGroup.children) {
        mesh.material = mesh.userData.component === name
          ? selectedMaterial : baseMaterial;
      }
    }
    if (ctx.assemblyState) renderAssemblyTree(ctx.assemblyState);
    pickEl.textContent = name
      ? t("sél. {s}", { s: ctx.assemblyState?.components.find(
          (c) => c.name === name)?.label ?? name })
      : "";
  }

  async function refreshAssembly(treePromise) {
    const gen = ++ctx.viewGen;
    ctx.lastClearedSelections = false;
    startProgressWatch();
    let ok = false;
    try {
      ctx.assemblyState = await treePromise;
      if (gen !== ctx.viewGen) return;
      renderAssemblyTree(ctx.assemblyState);
      const meshes = await call("tessellate_assembly");
      if (gen !== ctx.viewGen) return;
      showAssemblyMeshes(meshes);
      ok = !ctx.lastClearedSelections;
    } catch (error) {
      if (gen !== ctx.viewGen) return;
      sayUntilAck(error.message);
    } finally {
      stopProgressWatch();
    }
    if (ok) say("Assemblage à jour.");
  }

  // Rafraîchit dans le bon mode — les ops transverses (renommer,
  // supprimer, annuler) renvoient l'arbre du mode courant.
  async function refreshAny(treePromise) {
    const gen = ++ctx.viewGen;
    ctx.lastClearedSelections = false;
    startProgressWatch();
    let ok = false;
    try {
      const tree = await treePromise;
      if (gen !== ctx.viewGen) return;
      if (tree.assembly) {
        ctx.assemblyState = tree;
        renderAssemblyTree(tree);
        const meshes = await call("tessellate_assembly");
        if (gen !== ctx.viewGen) return;
        showAssemblyMeshes(meshes);
      } else {
        renderTree(tree);
        await updateViewport(gen);
        if (gen !== ctx.viewGen) return;
      }
      ok = !ctx.lastClearedSelections;
    } catch (error) {
      if (gen !== ctx.viewGen) return;
      sayUntilAck(error.message);
    } finally {
      stopProgressWatch();
    }
    if (ok) say("À jour.");
  }

  function renderAssemblyTree(tree) {
    ctx.welcomeApi?.hideWelcome();
    ctx.lastTree = null; // le mode pièce est inactif
    queueMicrotask(updateEditMode); // assemblyState est posé par l'appelant
    closeGraph();
    treeEl.innerHTML = "";
    const head = document.createElement("li");
    head.className = "body active";
    head.appendChild(treeIcon("assembly"));
    head.appendChild(document.createTextNode(t("Assemblage")));
    treeEl.appendChild(head);
    for (const comp of tree.components) {
      const item = document.createElement("li");
      if (comp.name === selectedComponent) item.className = "sel-comp";
      item.appendChild(treeIcon("insert"));
      item.appendChild(document.createTextNode(
        comp.label + (comp.grounded ? " " + t("(fixé)") : "")));
      item.title = t("Clic : sélectionner · double-clic : déplacer · " +
        "clic droit : renommer, supprimer");
      item.addEventListener("click", () => selectComponent(comp.name));
      item.addEventListener("dblclick", () => {
        selectComponent(comp.name);
        openMovePanel();
      });
      item.addEventListener("contextmenu", (e) => openMenu(e, comp));
      treeEl.appendChild(item);
    }
    if (!tree.components.length) {
      const empty = document.createElement("li");
      empty.textContent = t("— insérez une pièce (.FCStd) —");
      treeEl.appendChild(empty);
    }
    for (const joint of tree.joints ?? []) {
      const row = document.createElement("li");
      row.className = "child";
      row.appendChild(treeIcon("mate"));
      row.appendChild(document.createTextNode(joint.label));
      row.title = `${joint.type} — ` + t("clic droit : renommer, supprimer");
      row.addEventListener("contextmenu", (e) => openMenu(e, joint));
      treeEl.appendChild(row);
    }
  }

  function openMovePanel() {
    const comp = ctx.assemblyState?.components.find(
      (c) => c.name === selectedComponent);
    if (!comp) {
      say("Déplacer : cliquez d'abord un composant", true);
      return;
    }
    const [x, y, z] = comp.position;
    const [yaw, pitch, roll] = comp.rotation;
    panel.open({
      icon: "nodes_translate",
      title: t("Déplacer — {c}", { c: comp.label }),
      groups: [
        { label: t("Translation"),
          rows: [
            { type: "number", key: "x", label: t("X"), value: +x.toFixed(3), unit: "mm" },
            { type: "number", key: "y", label: t("Y"), value: +y.toFixed(3), unit: "mm" },
            { type: "number", key: "z", label: t("Z"), value: +z.toFixed(3), unit: "mm" },
          ] },
        { label: t("Rotation"),
          rows: [
            { type: "number", key: "yaw", label: t("Lacet (Z)"), value: +yaw.toFixed(2), unit: "°" },
            { type: "number", key: "pitch", label: t("Tangage (Y)"), value: +pitch.toFixed(2), unit: "°" },
            { type: "number", key: "roll", label: t("Roulis (X)"), value: +roll.toFixed(2), unit: "°" },
          ] },
      ],
      note: t("Avec des contraintes posées, le solveur repositionne le "
            + "composant après le déplacement. Astuce : glissez un composant "
            + "libre directement dans la vue."),
      onApply: (v) => refreshAssembly(call("move_component", {
        component: comp.name,
        x: num(v.x) ?? 0, y: num(v.y) ?? 0,
        z: num(v.z) ?? 0,
        yaw: num(v.yaw) ?? 0, pitch: num(v.pitch) ?? 0,
        roll: num(v.roll) ?? 0,
      })),
    });
  }

  // Un assemblage neuf enchaîne sur l'insertion du premier composant
  // (fixé à l'origine), puis propose d'en insérer d'autres.
  document.getElementById("btn-newasm").addEventListener("click", async () => {
    clearGhost();
    await refreshAssembly(call("new_assembly"));
    if (ctx.assemblyState) insertComponents();
  });

  async function insertComponents() {
    for (;;) {
      const first = !ctx.assemblyState?.components.length;
      const path = prompt(first
        ? "Premier composant (chemin .FCStd) — il sera fixé à l'origine :"
        : "Composant suivant (chemin .FCStd) — Annuler pour terminer :",
      "~/piece-freesolid.FCStd");
      if (!path) return;
      await refreshAssembly(call("insert_component", { path }));
    }
  }

  document.getElementById("btn-insert").addEventListener("click", () => {
    if (!ctx.assemblyState) {
      say("Créez d'abord un assemblage (Nouvel assemblage)", true);
      return;
    }
    insertComponents();
  });

  // ---------- déplacer un composant à la souris ----------
  // Bouton gauche glissé sur un composant libre : il suit le curseur dans le
  // plan de l'écran ; au lâcher, sa position part au moteur (qui résout les
  // contraintes posées, comme un glisser de modeleur).

  let asmDrag = null; // { comp, mesh, plane, from, start }

  renderer.domElement.addEventListener("pointerdown", (event) => {
    if (!ctx.assemblyState || !ctx.asmGroup || event.button !== 0 || panel.active) return;
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects(ctx.asmGroup.children, false)[0];
    if (!hit) return;
    const comp = ctx.assemblyState.components.find(
      (c) => c.name === hit.object.userData.component);
    if (!comp || comp.grounded) return;
    const normal = camera.getWorldDirection(new THREE.Vector3());
    asmDrag = {
      comp, mesh: hit.object,
      plane: new THREE.Plane().setFromNormalAndCoplanarPoint(normal, hit.point),
      from: hit.point.clone(),
      start: { x: event.clientX, y: event.clientY },
      moved: false,
    };
  });

  renderer.domElement.addEventListener("pointermove", (event) => {
    if (!asmDrag) return;
    if (Math.hypot(event.clientX - asmDrag.start.x,
                   event.clientY - asmDrag.start.y) > 5) asmDrag.moved = true;
    if (!asmDrag.moved) return;
    setPointerFromEvent(event);
    raycaster.setFromCamera(pointer, camera);
    const at = new THREE.Vector3();
    if (!raycaster.ray.intersectPlane(asmDrag.plane, at)) return;
    asmDrag.mesh.position.copy(at.sub(asmDrag.from));
  });

  renderer.domElement.addEventListener("pointerup", () => {
    const drag = asmDrag;
    asmDrag = null;
    if (!drag?.moved) return;
    const d = drag.mesh.position;
    const [x, y, z] = drag.comp.position;
    const [yaw, pitch, roll] = drag.comp.rotation;
    refreshAssembly(call("move_component", {
      component: drag.comp.name,
      x: x + d.x, y: y + d.y, z: z + d.z, yaw, pitch, roll,
    }));
  });

  document.getElementById("btn-move").addEventListener("click", openMovePanel);

  document.getElementById("btn-joint").addEventListener("click", () => {
    if (!ctx.assemblyState) {
      say("Créez d'abord un assemblage", true);
      return;
    }
    if (ctx.assemblyState.components.length < 2) {
      say("Contrainte : insérez au moins deux composants", true);
      return;
    }
    const MECHANICAL = ["engrenages", "cremaillere", "vis", "courroie"];
    const build = (v) => {
      if (!v.a || !v.b || v.a.component === v.b.component) return null;
      const params = {
        component1: v.a.component, component2: v.b.component,
        sub1: `Face${v.a.face + 1}`, sub2: `Face${v.b.face + 1}`,
        type: v.type,
      };
      if (v.flip) params.flip = true;
      if (v.type === "angle") {
        const a = num(v.angle);
        if (a === null) return null;
        params.angle = a;
      }
      if (v.type === "distance" || MECHANICAL.includes(v.type)) {
        const d = num(v.distance);
        if (d === null || d < 0) return null;
        params.distance = d;
        if (["engrenages", "courroie"].includes(v.type)) {
          const d2 = num(v.distance2);
          if (d2 === null || d2 < 0) return null;
          params.distance2 = d2;
        }
      }
      // Limites optionnelles : champ vide = pas de limite.
      for (const [key, param] of [["angleMin", "angle_min"],
                                  ["angleMax", "angle_max"],
                                  ["lengthMin", "length_min"],
                                  ["lengthMax", "length_max"]]) {
        const raw = String(v[key] ?? "").trim();
        if (raw) {
          const parsed = num(raw);
          if (parsed !== null) params[param] = parsed;
        }
      }
      return params;
    };
    panel.open({
      icon: "mate",
      title: t("Contrainte d'assemblage"),
      groups: [
        { label: t("Type de contrainte"),
          rows: [
            // Standard d'abord (les gestes courants), puis les liaisons
            // cinématiques et mécaniques.
            { type: "select", key: "type", value: "coincidente",
              options: [["coincidente", "Coïncidente"],
                        ["concentrique", "Concentrique"],
                        ["parallele", "Parallèle"],
                        ["perpendiculaire", "Perpendiculaire"],
                        ["tangente", "Tangente"],
                        ["distance", "Distance"], ["angle", "Angle"],
                        ["verrouillage", "Verrouillage"],
                        ["pivot", "Pivot"],
                        ["cylindrique", "Cylindrique"],
                        ["glissiere", "Glissière"], ["rotule", "Rotule"],
                        ["engrenages", "Engrenages"],
                        ["cremaillere", "Crémaillère-pignon"],
                        ["vis", "Vis"], ["courroie", "Courroie"]] },
            { type: "number", key: "angle", label: t("Angle"), value: 90,
              unit: "°", showIf: (v) => v.type === "angle" },
            { type: "check", key: "flip", label: t("Opposé (retourner l'alignement)"),
              value: false,
              showIf: (v) => ["coincidente", "concentrique", "parallele",
                "distance", "tangente", "pivot", "cylindrique",
                "glissiere"].includes(v.type) },
            { type: "number", key: "distance",
              label: t("Distance / rayon 1 / pas"), value: 10,
              unit: "mm", min: 0,
              showIf: (v) => v.type === "distance"
                || MECHANICAL.includes(v.type) },
            { type: "number", key: "distance2", label: t("Rayon 2"), value: 10,
              unit: "mm", min: 0,
              showIf: (v) => ["engrenages", "courroie"].includes(v.type) },
            { type: "note",
              text: "Mécaniques : posez d'abord les pivots des deux " +
                    "composants, la contrainte couple ensuite leurs " +
                    "mouvements.",
              showIf: (v) => MECHANICAL.includes(v.type) },
            { type: "text", key: "angleMin", label: t("Angle min"), unit: "°",
              placeholder: t("aucune limite"),
              showIf: (v) => ["pivot", "cylindrique"].includes(v.type) },
            { type: "text", key: "angleMax", label: t("Angle max"), unit: "°",
              placeholder: t("aucune limite"),
              showIf: (v) => ["pivot", "cylindrique"].includes(v.type) },
            { type: "text", key: "lengthMin", label: t("Longueur min"),
              unit: "mm", placeholder: t("aucune limite"),
              showIf: (v) => ["glissiere", "cylindrique"].includes(v.type) },
            { type: "text", key: "lengthMax", label: t("Longueur max"),
              unit: "mm", placeholder: t("aucune limite"),
              showIf: (v) => ["glissiere", "cylindrique"].includes(v.type) },
          ] },
        { label: t("Élément 1"),
          rows: [{ type: "selection", key: "a", accepts: ["asmface"],
                   hint: t("Cliquez une face du premier composant") }] },
        { label: t("Élément 2"),
          rows: [{ type: "selection", key: "b", accepts: ["asmface"],
                   hint: t("Puis une face du second composant") }] },
      ],
      note: t("Le solveur natif repositionne les composants — le premier " +
            "inséré est fixé."),
      onApply: (v) => {
        const params = build(v);
        if (!params) {
          say("Contrainte : deux faces de deux composants différents", true);
          return;
        }
        refreshAssembly(call("add_joint", params));
      },
    });
  });

  document.getElementById("btn-solve").addEventListener("click", () => {
    if (!ctx.assemblyState) {
      say("Créez d'abord un assemblage", true);
      return;
    }
    refreshAssembly(call("solve_assembly"));
  });

  document.getElementById("btn-array-comp").addEventListener("click", () => {
    const comp = ctx.assemblyState?.components.find(
      (c) => c.name === selectedComponent);
    if (!comp) {
      say("Répéter : cliquez d'abord un composant", true);
      return;
    }
    panel.open({
      icon: "component_array",
      title: t("Répéter — {c}", { c: comp.label }),
      groups: [{
        label: t("Répétition"),
        rows: [
          { type: "number", key: "count", label: t("Occurrences"), value: 3,
            min: 2, step: 1 },
          { type: "number", key: "dx", label: t("Pas X"), value: 30,
            unit: "mm" },
          { type: "number", key: "dy", label: t("Pas Y"), value: 0,
            unit: "mm" },
          { type: "number", key: "dz", label: t("Pas Z"), value: 0,
            unit: "mm" },
        ],
      }],
      onApply: (v) => {
        const count = parseInt(v.count, 10);
        if (!(count >= 2)) { say("Au moins 2 occurrences", true); return; }
        refreshAssembly(call("array_component", {
          component: comp.name, count,
          dx: num(v.dx) ?? 0, dy: num(v.dy) ?? 0,
          dz: num(v.dz) ?? 0 }));
      },
    });
  });

  document.getElementById("btn-interf").addEventListener("click", async () => {
    if (!ctx.assemblyState) {
      say("Créez d'abord un assemblage", true);
      return;
    }
    try {
      const result = await call("check_interference");
      if (!result.interferences.length) {
        say("Aucune interférence entre les composants ✓");
        return;
      }
      panel.open({
        icon: "interference",
        title: t("Interférences"),
        groups: [{
          label: t("{n} interférence(s)", { n: result.interferences.length }),
          rows: [{ type: "list",
            items: result.interferences.map((p) => ({
              label: `${p.a} ↔ ${p.b} : ` +
                `${(p.volume_mm3 / 1000).toFixed(3)} cm³`,
            })) }],
        }],
        note: t("Volume commun réel (booléen OCCT) — à résoudre avant " +
              "impression."),
        onApply: () => {},
      });
    } catch (error) {
      say(error.message, true);
    }
  });

  // ---------- vue éclatée (visuelle) ----------

  let explodeFactor = 0;
  let explodeTarget = 0;

  function applyExplode() {
    if (!ctx.asmGroup) return;
    for (const mesh of ctx.asmGroup.children) {
      const dir = mesh.userData.explodeDir;
      if (dir) mesh.position.copy(dir).multiplyScalar(explodeFactor);
    }
  }

  function computeExplodeDirs() {
    if (!ctx.asmGroup || !ctx.asmGroup.children.length) return;
    const centers = ctx.asmGroup.children.map((mesh) => {
      mesh.geometry.computeBoundingSphere();
      return mesh.geometry.boundingSphere.center.clone();
    });
    const global = centers.reduce((a, c) => a.add(c),
      new THREE.Vector3()).divideScalar(centers.length);
    ctx.asmGroup.children.forEach((mesh, i) => {
      const dir = centers[i].clone().sub(global);
      if (dir.length() < 1e-6) dir.set(0, 0, 1); // composants superposés
      mesh.userData.explodeDir = dir.multiplyScalar(0.9);
    });
    applyExplode();
  }

  document.getElementById("btn-explode").addEventListener("click", () => {
    if (!ctx.assemblyState) {
      say("Créez d'abord un assemblage", true);
      return;
    }
    explodeTarget = explodeTarget ? 0 : 1;
    say(explodeTarget
      ? "Vue éclatée — purement visuelle, re-cliquez pour rassembler"
      : "Vue rassemblée.");
  });


  function tickExplode() {
    if (explodeFactor === explodeTarget) return;
    explodeFactor = explodeStep(explodeFactor, explodeTarget);
    applyExplode();
  }

  return {
    refreshAny, refreshAssembly, showAssemblyMeshes, renderAssemblyTree,
    selectComponent, clearAssemblyView, tickExplode,
  };
}
