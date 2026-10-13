// FreeSolid — side property panel:
// it replaces the feature tree while a command runs, carries the feature
// icon + name, OK (green check) / Cancel (red cross), collapsible group
// boxes, selection boxes fed by viewport picks, Enter/Escape.
//
// Pure DOM + callbacks: the panel knows nothing about the engine. Each
// command describes itself as a spec; onApply receives the values.
//
// Spec shape:
//   {
//     icon: "nodes_extrude",
//     title: "Extrusion",
//     groups: [{ label, rows: [row…] }],
//     note?: string,
//     noApply?: boolean,   // panneau info : pas de bouton OK
//     autoFocus?: boolean, // false : ne pas voler le focus clavier
//     actions?: [{ label, title?, className?, onClick(values) }],
//     onApply(values), onCancel?(), onChange?(values),
//     onClose?() — à chaque fermeture (OK, annuler, panneau remplacé)
//   }
// Rows: { type: "number", key, label, value, unit?, min?, step?, showIf? }
//       { type: "select", key, options: [[value, label]…], value, label? }
//       { type: "check",  key, label, value }
//       { type: "selection", key, label?, hint?, value?, accepts?, multiple? }
//       { type: "text", key, label, value?, placeholder?, unit? }
//       { type: "list", items: [{ label, onDelete?, onEdit?, editable? }], empty? }
//       { type: "note", text, readonly?, onClick? }
//       { type: "points", key, value: [[x, y, z]…], extra? } — liste
//         éditable, alimentée aussi par les clics « point3d » de la vue ;
//         extra: { label, value } ajoute une 4e colonne (hauteur…)
//       { type: "segments", key, pointsKey } — une règle par segment entre
//         points consécutifs : axe imposé (X/Y/Z), angle avec le segment
//         d'avant, longueur cotée
//       points : linksKey? — liste parallèle ; un point lié porte ⛓ et se
//         délie dès qu'on retape une de ses coordonnées ; head: n — les n
//         premières valeurs nomment la ligne (lecture seule, headText(p)
//         pour les écrire autrement) ; titles —
//         infobulles des colonnes éditables
//
// invalidateSelections() : vide les rows `selection` (ids périmés au rebuild).

import { t } from "./i18n.js";
import { iconSrc } from "./icons.js";

/** Que fait Entrée dans le panneau ? Une valeur tout juste tapée dans un
 *  champ est d'abord appliquée (l'aperçu suit, le panneau reste ouvert) ;
 *  un second appui — ou Entrée hors d'un champ modifié — valide la
 *  fonction. */
export function enterAction({ tag, edited, noApply }) {
  if (tag === "SELECT" || tag === "TEXTAREA") return "none";
  if (tag === "INPUT" && edited) return "commit";
  return noApply ? "none" : "apply";
}

/** Une zone de sélection contient déjà quelque chose. */
export function selectionFilled(value) {
  if (!value) return false;
  if (value.items) return value.items.length > 0;
  if (value.kind === "edges") return value.edges.length > 0;
  if (value.kind === "face") return value.face != null;
  return true;
}

/** Vrai si une ligne de sélection est vide : elle affiche déjà quoi choisir. */
export function selectionLineGuides(groups, values) {
  for (const group of groups ?? []) {
    for (const row of group.rows ?? []) {
      if (row.type === "selection" && !selectionFilled(values?.[row.key])) {
        return true;
      }
    }
  }
  return false;
}

/** Bandeau du panneau. Une consigne (`tone: "guide"`) est neutre et
 *  disparaît si une ligne de sélection la dit déjà. Une chaîne, ou
 *  `tone: "error"`, reste une erreur (rouge). */
export function panelNotice(notice, { selectionGuides = false } = {}) {
  if (notice == null || notice === "") return null;
  if (typeof notice === "string") return { text: notice, tone: "error" };
  const text = notice.text;
  if (typeof text !== "string" || text === "") return null;
  const tone = notice.tone === "guide" ? "guide" : "error";
  if (tone === "guide" && selectionGuides) return null;
  return { text, tone };
}

/** Deux choix d'une zone multiple désignent-ils la même chose ? Une
 *  face par son numéro, un bord par objet + arête, le reste par nom. */
export function samePick(a, b) {
  if (b.kind === "point") return false;
  if (b.kind === "surfface") {
    return a.kind === "surfface" && a.name === b.name && a.face === b.face;
  }
  if (b.face != null) return a.face === b.face;
  if (b.kind === "boundary") {
    return a.kind === "boundary" && a.name === b.name && a.edge === b.edge;
  }
  return a.name === b.name;
}

/** Texte d'une zone remplie de bords (arêtes de surface, de courbe, du
 *  solide) ou d'esquisses entières. */
export function boundaryText(items, tr = (s, v) => s.replace(/\{(\w+)\}/g,
  (_, k) => v?.[k] ?? "")) {
  if (items.length > 3) return tr("{n} éléments", { n: items.length });
  return items.map((i) => (i.kind !== "boundary" || i.curve ? i.label
    : `${i.label} · ${tr("Arête {n}", { n: i.edge })}`)).join(", ");
}

export function createPropertyPanel({ say, onClose, onToggle, onPicks }) {
  const aside = document.querySelector("aside");
  const panelEl = document.getElementById("panel");

  let active = null; // { spec, values }
  let editedInput = null; // champ modifié depuis le dernier Entrée
  let hintEl = null;      // message d'aide (ce qui manque encore)
  let previewOn = true;   // bascule de l'aperçu (œil de l'en-tête)

  /** Message d'aide : ce qu'il manque pour pouvoir valider. */
  function updateHint() {
    if (!hintEl || !active) return;
    const notice = panelNotice(active.spec.hint?.({ ...active.values }), {
      selectionGuides: selectionLineGuides(active.spec.groups, active.values),
    });
    hintEl.hidden = !notice;
    hintEl.textContent = notice ? t(notice.text) : "";
    hintEl.classList.toggle("guide", notice?.tone === "guide");
    hintEl.classList.toggle("error", notice?.tone === "error");
  }

  // Chaque modification de valeur notifie la commande — c'est ce qui
  // alimente l'aperçu jaune en temps réel.
  function changed() {
    const focused = document.activeElement;
    if (focused?.tagName === "INPUT" && panelEl.contains(focused)) {
      editedInput = focused;
    }
    updateHint();
    if (active?.spec.onPreview && !previewOn) return; // aperçu coupé
    active?.spec.onChange?.({ ...active.values });
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = t(text);
    return node;
  }

  // ---------- lifecycle ----------

  function open(spec) {
    // Remplacer un panneau ouvert : silencieux (la présélection d'arbre
    // doit survivre, ex. esquisse → Extrusion). Fermer/Échap passent par
    // close(false) qui appelle onCancel.
    if (active) close(false, { silent: true });
    active = { spec, values: {} };
    editedInput = null;
    previewOn = true;
    for (const group of spec.groups) {
      for (const row of group.rows ?? []) {
        if (row.key !== undefined) active.values[row.key] = row.value ?? null;
      }
    }
    render();
    aside.classList.add("panel-open");
    onToggle?.();
    document.addEventListener("keydown", onKey, true);
    if (spec.autoFocus !== false) {
      // La première valeur à taper (pas une liste ni une case), sélectionnée :
      // la frappe la remplace au lieu de s'y ajouter.
      const field = panelEl.querySelector(
        'input:not([type="checkbox"]):not([type="radio"])')
        ?? panelEl.querySelector("select");
      field?.focus();
      if (field?.select) field.select();
    }
    changed(); // premier aperçu avec les valeurs par défaut
    // Rien n'a encore été tapé : la première Entrée valide (OK), elle
    // n'a pas de valeur à prendre.
    editedInput = null;
  }

  function close(apply, { silent = false } = {}) {
    if (!active) return;
    const { spec, values } = active;
    active = null;
    aside.classList.remove("panel-open");
    document.removeEventListener("keydown", onKey, true);
    panelEl.innerHTML = "";
    onClose?.(); // efface l'aperçu avant d'appliquer ou d'abandonner
    onPicks?.([]);
    spec.onClose?.(); // l'outil range ses écouteurs, quoi qu'il arrive
    onToggle?.();
    if (apply) spec.onApply?.({ ...values });
    else if (!silent) spec.onCancel?.();
  }

  function onKey(event) {
    // Une saisie flottante (boîte de cote) gère ses propres touches.
    if (event.target?.closest?.("[data-own-keys]")) return;
    if (event.key === "Enter") {
      const action = enterAction({
        tag: event.target.tagName,
        edited: event.target === editedInput,
        noApply: active?.spec.noApply,
      });
      if (action === "none") return;
      event.preventDefault();
      event.stopPropagation(); // le mode esquisse écoute aussi le clavier
      if (action === "commit") {
        editedInput = null;
        event.target.select?.(); // la valeur est prise : on la montre
        return;
      }
      close(true);
    } else if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      close(false);
    }
  }

  // The viewport and the tree report picks here; a selection row that
  // accepts this kind absorbs them. Values: {kind: "face", face},
  // {kind: "edges", edges: […]}, {kind: "sketch", name, label} or, for
  // multiple rows, {kind, items: […]} (a second click on the same item
  // removes it).
  function notifyPick(kind, value) {
    if (!active) return false;
    const rows = [];
    for (const group of active.spec.groups) {
      for (const row of group.rows ?? []) {
        // Une zone masquée (showIf) n'absorbe pas les clics.
        if (row.type === "selection"
            && (row.accepts ?? ["face"]).includes(kind)
            && (!row.showIf || row.showIf(active.values))) {
          rows.push(row);
        }
      }
    }
    const pointsRow = kind === "point3d" && findPointsRow();
    if (pointsRow) {
      const list = [...(active.values[pointsRow.key] ?? [])];
      const point = [value.x, value.y, value.z];
      if (pointsRow.extra) point.push(pointsRow.extra.value ?? 0);
      list.push(point);
      active.values[pointsRow.key] = list;
      render();
      changed();
      return true;
    }
    if (!rows.length) return false;
    const multiRow = rows.find((r) => r.multiple);
    if (multiRow) {
      const current = active.values[multiRow.key] ?? { kind, items: [] };
      const at = current.items.findIndex((i) => samePick(i, value));
      if (at >= 0) current.items.splice(at, 1);
      else current.items.push(value);
      active.values[multiRow.key] = { ...current };
    } else {
      // Première zone vide, sinon la dernière est remplacée — le
      // balayage remplit Profil puis Trajectoire en deux clics.
      const target = rows.find(
        (r) => !selectionFilled(active.values[r.key]))
        ?? rows[rows.length - 1];
      active.values[target.key] = value;
    }
    render();
    changed();
    reportPicks();
    return true;
  }

  function findPointsRow() {
    for (const group of active.spec.groups) {
      for (const row of group.rows ?? []) {
        if (row.type === "points") return row;
      }
    }
    return null;
  }

  function selectionRows(kind) {
    const rows = [];
    for (const group of active?.spec.groups ?? []) {
      for (const row of group.rows ?? []) {
        if (row.type === "selection"
            && (row.accepts ?? ["face"]).includes(kind)
            && (!row.showIf || row.showIf(active.values))) rows.push(row);
      }
    }
    return rows;
  }

  /** Tous les choix des zones de sélection — la vue les surligne. */
  function reportPicks() {
    if (!onPicks) return;
    const items = [];
    for (const group of active?.spec.groups ?? []) {
      for (const row of group.rows ?? []) {
        if (row.type !== "selection") continue;
        const value = active.values[row.key];
        if (value?.items) items.push(...value.items);
        else if (value) items.push(value);
      }
    }
    onPicks(items);
  }

  // Les ids de faces/arêtes meurent à chaque rebuild. Le viewport vide
  // ses picks ; le panneau de propriétés doit faire de même — un Congé ouvert
  // ne doit pas appliquer des ids périmés après un Ctrl+Z.
  function invalidateSelections() {
    if (!active) return 0;
    let cleared = 0;
    for (const group of active.spec.groups) {
      for (const row of group.rows ?? []) {
        if (row.type !== "selection") continue;
        if (!selectionFilled(active.values[row.key])) continue;
        active.values[row.key] = row.multiple ? { items: [] } : null;
        cleared++;
      }
    }
    if (!cleared) return 0;
    render();
    changed();
    return cleared;
  }

  // ---------- rendering ----------

  function render() {
    const { spec } = active;
    panelEl.innerHTML = "";

    const head = el("div", "phead-main");
    const icon = document.createElement("img");
    icon.src = iconSrc(spec.icon);
    icon.alt = "";
    head.append(icon, el("span", "ptitle", spec.title));
    if (spec.onPreview) {
      const eye = el("button", previewOn ? "peye" : "peye off");
      eye.innerHTML = '<svg viewBox="0 0 20 14" aria-hidden="true">'
        + '<path d="M1 7c2.5-4 5.5-6 9-6s6.5 2 9 6c-2.5 4-5.5 6-9 6s-6.5-2-9-6z"/>'
        + '<circle cx="10" cy="7" r="2.6"/></svg>';
      eye.title = t("Aperçu : afficher ou masquer");
      eye.addEventListener("click", () => {
        previewOn = !previewOn;
        eye.classList.toggle("off", !previewOn);
        active.spec.onPreview(previewOn, { ...active.values });
      });
      head.append(eye);
    }
    if (spec.actions) {
      for (const action of spec.actions) {
        const btn = el("button", action.className ?? "pok", action.label);
        if (action.title) btn.title = t(action.title);
        btn.addEventListener("click", () => {
          const values = { ...active.values };
          const run = action.onClick;
          close(false, { silent: true });
          run?.(values);
        });
        head.append(btn);
      }
    }
    if (!spec.noApply) {
      const ok = el("button", "pok", "✓");
      ok.title = t("OK (Entrée)");
      ok.addEventListener("click", () => close(true));
      head.append(ok);
    }
    const cancel = el("button",
      spec.noApply ? "pcancel pcancel-text" : "pcancel",
      spec.noApply ? "Fermer" : "✕");
    cancel.title = t(spec.noApply ? "Fermer (Échap)" : "Annuler (Échap)");
    cancel.addEventListener("click", () => close(false));
    head.append(cancel);
    panelEl.append(head);
    hintEl = el("div", "phint");
    hintEl.setAttribute("role", "status");
    panelEl.append(hintEl);
    updateHint();

    for (const group of spec.groups) {
      const box = el("div", "pgroup");
      const header = el("div", "phead");
      header.append(el("span", "", group.label), el("span", "parrow", "▾"));
      header.addEventListener("click", () =>
        box.classList.toggle("closed"));
      const body = el("div", "pbody");
      for (const row of group.rows ?? []) {
        const rendered = renderRow(row);
        if (rendered) body.append(rendered);
      }
      box.append(header, body);
      panelEl.append(box);
    }
    if (spec.note) panelEl.append(el("div", "pnote", spec.note));
  }

  function renderRow(row) {
    const { values } = active;
    if (row.showIf && !row.showIf(values)) return null;
    if (row.type === "note") {
      const note = el("div", row.readonly ? "pnote readonly" : "pnote", row.text);
      if (row.onClick) {
        note.addEventListener("click", row.onClick);
      }
      return note;
    }

    if (row.type === "list") {
      const wrap = el("div", "plist");
      if (!row.items.length) {
        wrap.append(el("div", "pnote", row.empty ?? "— aucune —"));
      }
      for (const item of row.items) {
        const line = el("div",
          item.editable ? "plist-item editable"
            : item.onEdit ? "plist-item"
              : "plist-item readonly");
        const label = el("span", "", item.label);
        line.append(label);
        if (item.onEdit) {
          line.addEventListener("click", (event) => {
            if (event.target.closest(".pdel")) return;
            item.onEdit();
          });
        }
        if (item.onDelete) {
          const remove = el("button", "pdel", "✕");
          remove.title = "Supprimer";
          remove.addEventListener("click", (event) => {
            event.stopPropagation();
            item.onDelete();
          });
          line.append(remove);
        }
        wrap.append(line);
      }
      return wrap;
    }

    if (row.type === "points") return renderPoints(row);
    if (row.type === "segments") return renderSegments(row);

    if (row.type === "selection") {
      const box = el("div", "pselect-box");
      const value = values[row.key];
      if (!selectionFilled(value)) {
        box.textContent =
          t(row.hint ?? "Cliquez une face dans la zone graphique");
        return box;
      }
      if (value.items && value.items.every((i) => i.kind === "point")) {
        box.textContent = t("{n} position(s)", { n: value.items.length });
      } else if (value.items && value.items.every((i) => i.kind === "surfface")) {
        box.textContent = value.items.length <= 3
          ? value.items.map((i) => `${i.label} · ${t("Face {n}", { n: i.face })}`)
            .join(", ")
          : t("{n} faces", { n: value.items.length });
      } else if (value.kind === "surfface") {
        box.textContent = `${value.label} · ${t("Face {n}", { n: value.face })}`;
      } else if (value.items && value.items.every((i) => i.face != null)) {
        box.textContent = value.items.length <= 4
          ? value.items.map((i) => t("Face {n}", { n: i.face })).join(", ")
          : t("{n} faces", { n: value.items.length });
      } else if (value.items && (value.items.some((i) => i.kind === "boundary")
                 || (row.accepts ?? []).includes("boundary"))) {
        box.textContent = boundaryText(value.items, t);
      } else if (value.kind === "boundary") {
        box.textContent = boundaryText([value], t);
      } else if (value.kind === "vertex") {
        box.textContent = t("Sommet ({x} ; {y} ; {z})", {
          x: +value.x.toFixed(2), y: +value.y.toFixed(2),
          z: +value.z.toFixed(2) });
      } else if (value.kind === "surfpoint") {
        box.textContent = t("{s} — partie cliquée", { s: value.label });
      } else if (value.items && value.items.every((i) => i.kind === "feature")) {
        // Fonctions à répéter : une liste, pas un ordre de profils.
        const labels = value.items.map((i) => i.label).join(", ");
        box.textContent = value.items.length <= 2 ? labels
          : t("{n} fonctions : ", { n: value.items.length }) + labels;
      } else if (value.items) {
        box.textContent = value.items.length <= 2
          ? value.items.map((i) => i.label).join(" → ")
          : t("{n} profils : ", { n: value.items.length })
            + value.items.map((i) => i.label).join(" → ");
      } else if (value.kind === "edges") {
        box.textContent = value.edges.length <= 3
          ? value.edges.map((e) => t("Arête {n}", { n: e })).join(", ")
          : t("{n} arêtes", { n: value.edges.length });
      } else if (value.kind === "sketch" || value.kind === "surface") {
        box.textContent = value.label;
      } else if (value.kind === "asmface") {
        box.textContent = `${value.componentLabel} · `
          + t("Face {n}", { n: value.face });
      } else {
        box.textContent = t("Face {n}", { n: value.face });
      }
      box.classList.add("filled");
      return box;
    }

    const rowEl = el("div", "prow");
    if (row.type === "text") {
      // Texte libre : noms de cotes, valeurs OU expressions (« 2*Largeur »).
      const input = document.createElement("input");
      input.type = "text";
      input.value = values[row.key] ?? "";
      if (row.placeholder) input.placeholder = t(row.placeholder);
      input.addEventListener("input", () => {
        values[row.key] = input.value;
        changed();
      });
      rowEl.append(el("label", "", row.label), input);
      if (row.unit) rowEl.append(el("span", "punit", row.unit));
    } else if (row.type === "number") {
      const input = document.createElement("input");
      input.type = "number";
      input.value = values[row.key];
      input.step = row.step ?? "any";
      input.dataset.key = row.key;
      if (row.min !== undefined) input.min = row.min;
      input.addEventListener("input", () => {
        values[row.key] = input.value;
        changed();
      });
      rowEl.append(el("label", "", row.label), input);
      if (row.unit) rowEl.append(el("span", "punit", row.unit));
    } else if (row.type === "select") {
      const select = document.createElement("select");
      for (const [value, label] of row.options) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = t(label);
        select.append(option);
      }
      select.value = values[row.key];
      select.addEventListener("change", () => {
        values[row.key] = select.value;
        render(); // showIf rows may appear/disappear
        changed();
      });
      if (row.label) rowEl.append(el("label", "", row.label));
      rowEl.append(select);
    } else if (row.type === "check") {
      const input = document.createElement("input");
      input.type = "checkbox";
      input.checked = !!values[row.key];
      input.addEventListener("change", () => {
        values[row.key] = input.checked;
        render(); // showIf rows may appear/disappear
        changed();
      });
      const label = el("label", "pcheck", row.label);
      label.prepend(input);
      rowEl.append(label);
    }
    return rowEl;
  }

  // Liste de points x, y, z : chaque coordonnée se corrige au clavier,
  // ✕ retire le point. Les clics de la vue en ajoutent (« point3d »).
  function renderPoints(row) {
    const wrap = el("div", "plist ppoints");
    const list = active.values[row.key] ?? [];
    if (!list.length) {
      wrap.append(el("div", "pnote",
        row.empty ?? "Cliquez des points dans la zone graphique"));
    }
    list.forEach((point, index) => {
      const line = el("div", "plist-item ppoint");
      const linked = row.linksKey && (active.values[row.linksKey] ?? [])[index];
      const head = row.head ?? 0;
      const name = el("span", "ppoint-name", head
        ? (row.headText?.(point) ?? point.slice(0, head).join(", "))
        : linked ? `P${index + 1}⛓` : `P${index + 1}`);
      if (linked) name.title = t("Lié à la géométrie — suit la pièce");
      line.append(name);
      point.forEach((coord, axis) => {
        if (axis < head) return;
        const input = document.createElement("input");
        input.type = "text";
        input.inputMode = "decimal";
        input.className = "ppoint-coord";
        input.value = String(Math.round(coord * 1000) / 1000);
        input.title = row.titles ? row.titles[axis - head] ?? ""
          : axis < 3 ? ["X", "Y", "Z"][axis] : t(row.extra?.label ?? "");
        input.addEventListener("change", () => {
          const parsed = Number(input.value.replace(",", "."));
          if (!Number.isFinite(parsed)) {
            input.value = String(point[axis]);
            return;
          }
          const next = (active.values[row.key] ?? []).map((p) => [...p]);
          next[index][axis] = parsed;
          active.values[row.key] = next;
          if (linked && axis < 3) {
            // Une coordonnée retapée : le point quitte la géométrie.
            const links = [...(active.values[row.linksKey] ?? [])];
            links[index] = null;
            active.values[row.linksKey] = links;
          }
          changed();
        });
        line.append(input);
      });
      const remove = el("button", "pdel", "✕");
      remove.title = t("Retirer le point");
      remove.addEventListener("click", () => {
        const next = [...(active.values[row.key] ?? [])];
        next.splice(index, 1);
        active.values[row.key] = next;
        if (row.linksKey) {
          const links = [...(active.values[row.linksKey] ?? [])];
          links.splice(index, 1);
          active.values[row.linksKey] = links;
        }
        render();
        changed();
      });
      line.append(remove);
      wrap.append(line);
    });
    return wrap;
  }

  // Règles des segments d'une esquisse 3D : axe et longueur. Une
  // longueur vide laisse le segment libre (sa longueur actuelle en gris).
  function renderSegments(row) {
    const wrap = el("div", "plist psegments");
    const pts = active.values[row.pointsKey] ?? [];
    const rules = active.values[row.key] ?? [];
    if (pts.length < 2) {
      wrap.append(el("div", "pnote", "Au moins deux points"));
      return wrap;
    }
    const update = (index, patchRule) => {
      const next = [...(active.values[row.key] ?? [])];
      while (next.length < pts.length - 1) next.push({ axis: "", length: null });
      next[index] = { ...next[index], ...patchRule };
      active.values[row.key] = next;
      changed();
    };
    for (let i = 0; i + 1 < pts.length; i++) {
      const rule = rules[i] ?? { axis: "", length: null };
      const [a, b] = [pts[i], pts[i + 1]];
      const length = Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]);
      const line = el("div", "plist-item ppoint");
      line.append(el("span", "ppoint-name", `S${i + 1}`));
      const axis = document.createElement("select");
      axis.className = "ppoint-coord";
      axis.title = t("Axe imposé");
      for (const [value, label] of [["", "—"], ["X", "X"], ["Y", "Y"],
        ["Z", "Z"]]) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = label;
        axis.append(option);
      }
      axis.value = rule.axis ?? "";
      axis.addEventListener("change", () => update(i, { axis: axis.value }));
      const size = document.createElement("input");
      size.type = "text";
      size.inputMode = "decimal";
      size.className = "ppoint-coord";
      size.title = t("Longueur cotée (vide : libre)");
      size.placeholder = String(Math.round(length * 100) / 100);
      size.value = rule.length == null ? "" : String(rule.length);
      size.addEventListener("change", () => {
        const text = size.value.trim().replace(",", ".");
        const parsed = Number(text);
        if (text !== "" && !(Number.isFinite(parsed) && parsed > 0)) {
          size.value = rule.length == null ? "" : String(rule.length);
          return;
        }
        update(i, { length: text === "" ? null : parsed });
      });
      const turn = document.createElement("input");
      turn.type = "text";
      turn.inputMode = "decimal";
      turn.className = "ppoint-coord";
      turn.title = t("Angle avec le segment d'avant (vide : libre)");
      turn.placeholder = "°";
      turn.disabled = i === 0;
      turn.value = rule.angle == null ? "" : String(rule.angle);
      turn.addEventListener("change", () => {
        const text = turn.value.trim().replace(",", ".");
        const parsed = Number(text);
        if (text !== "" && !(Number.isFinite(parsed) && parsed >= 0
                             && parsed <= 180)) {
          turn.value = rule.angle == null ? "" : String(rule.angle);
          return;
        }
        update(i, { angle: text === "" ? null : parsed });
      });
      line.append(axis, turn, size, el("span", "punit", "mm"));
      wrap.append(line);
    }
    return wrap;
  }

  return {
    open,
    close: (opts) => close(false, opts),
    /** Une zone de sélection accepte ce genre de choix. */
    accepts: (kind) => active !== null
      && (selectionRows(kind).length > 0
          || (kind === "point3d" && findPointsRow() !== null)),
    /** Parmi `kinds`, celui qu'attend la première zone vide (dans
     *  l'ordre du panneau), ou null. */
    firstNeeded: (kinds) => {
      for (const group of active?.spec.groups ?? []) {
        for (const row of group.rows ?? []) {
          if (row.type !== "selection") continue;
          if (row.showIf && !row.showIf(active.values)) continue;
          if (selectionFilled(active.values[row.key])) continue;
          const kind = kinds.find((k) => (row.accepts ?? ["face"]).includes(k));
          if (kind) return kind;
        }
      }
      return null;
    },
    /** Une zone de sélection VIDE attend ce genre de choix. */
    needs: (kind) => selectionRows(kind).some(
      (row) => !selectionFilled(active.values[row.key])),
    /** OK, comme le bouton ✓ — sans effet sur un panneau d'information. */
    apply: () => { if (active && !active.spec.noApply) close(true); },
    notifyPick,
    invalidateSelections,
    /** Remet des valeurs dans le panneau ouvert (après un refus du moteur). */
    restore(values) {
      if (!active) return;
      active.values = { ...active.values, ...values };
      render();
      changed();
    },
    get active() { return active !== null; },
    /** Un panneau de commande (avec OK) est ouvert. */
    get applicable() { return active !== null && !active.spec.noApply; },
  };
}
