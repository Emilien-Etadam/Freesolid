// FreeSolid — PropertyManager-style side panel, SolidWorks anatomy:
// it replaces the FeatureManager while a command runs, carries the feature
// icon + name, OK (green check) / Cancel (red cross), collapsible group
// boxes, selection boxes fed by viewport picks, Enter/Escape.
//
// Pure DOM + callbacks: the panel knows nothing about the engine. Each
// command describes itself as a spec; onApply receives the values.
//
// Spec shape:
//   {
//     icon: "PartDesign_Pad.svg",
//     title: "Extrusion",
//     groups: [{ label, rows: [row…] }],
//     note?: string,
//     noApply?: boolean,   // panneau info : pas de bouton OK
//     autoFocus?: boolean, // false : ne pas voler le focus clavier
//     actions?: [{ label, title?, className?, onClick(values) }],
//     onApply(values), onCancel?(), onChange?(values)
//   }
// Rows: { type: "number", key, label, value, unit?, min?, step?, showIf? }
//       { type: "select", key, options: [[value, label]…], value, label? }
//       { type: "check",  key, label, value }
//       { type: "selection", key, label?, hint?, value?, accepts?, multiple? }
//       { type: "text", key, label, value?, placeholder?, unit? }
//       { type: "list", items: [{ label, onDelete?, onEdit?, editable? }], empty? }
//       { type: "note", text, readonly?, onClick? }
//
// invalidateSelections() : vide les rows `selection` (ids périmés au rebuild).

import { t } from "./i18n.js";

/** Que fait Entrée dans le panneau ? Une valeur tout juste tapée dans un
 *  champ est d'abord appliquée (l'aperçu suit, le panneau reste ouvert) ;
 *  un second appui — ou Entrée hors d'un champ modifié — valide la
 *  fonction. */
export function enterAction({ tag, edited, noApply }) {
  if (tag === "SELECT" || tag === "TEXTAREA") return "none";
  if (tag === "INPUT" && edited) return "commit";
  return noApply ? "none" : "apply";
}

export function createPropertyPanel({ say, onClose, onToggle }) {
  const aside = document.querySelector("aside");
  const panelEl = document.getElementById("panel");

  let active = null; // { spec, values }
  let editedInput = null; // champ modifié depuis le dernier Entrée
  let hintEl = null;      // message d'aide (ce qui manque encore)
  let previewOn = true;   // bascule de l'aperçu (œil de l'en-tête)

  /** Message d'aide : ce qu'il manque pour pouvoir valider. */
  function updateHint() {
    if (!hintEl || !active) return;
    const text = active.spec.hint?.({ ...active.values });
    hintEl.hidden = !text;
    hintEl.textContent = text ? t(text) : "";
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
    // doit survivre, ex. esquisse → Bossage). Fermer/Échap passent par
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
      panelEl.querySelector("input, select")?.focus();
    }
    changed(); // premier aperçu avec les valeurs par défaut
  }

  function close(apply, { silent = false } = {}) {
    if (!active) return;
    const { spec, values } = active;
    active = null;
    aside.classList.remove("panel-open");
    document.removeEventListener("keydown", onKey, true);
    panelEl.innerHTML = "";
    onClose?.(); // efface l'aperçu avant d'appliquer ou d'abandonner
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
  function hasSelectionValue(value) {
    if (!value) return false;
    if (value.items) return value.items.length > 0;
    if (value.kind === "edges") return value.edges.length > 0;
    if (value.kind === "face") return value.face != null;
    return true;
  }

  function notifyPick(kind, value) {
    if (!active) return false;
    const rows = [];
    for (const group of active.spec.groups) {
      for (const row of group.rows ?? []) {
        if (row.type === "selection"
            && (row.accepts ?? ["face"]).includes(kind)) {
          rows.push(row);
        }
      }
    }
    if (!rows.length) return false;
    const multiRow = rows.find((r) => r.multiple);
    if (multiRow) {
      const current = active.values[multiRow.key] ?? { kind, items: [] };
      // Une face n'a pas de nom : son numéro l'identifie.
      const same = (i) => (value.face != null
        ? i.face === value.face : i.name === value.name);
      const at = current.items.findIndex(same);
      if (at >= 0) current.items.splice(at, 1);
      else current.items.push(value);
      active.values[multiRow.key] = { ...current };
    } else {
      // Première zone vide, sinon la dernière est remplacée — le
      // balayage remplit Profil puis Trajectoire en deux clics.
      const target = rows.find(
        (r) => !hasSelectionValue(active.values[r.key]))
        ?? rows[rows.length - 1];
      active.values[target.key] = value;
    }
    render();
    changed();
    return true;
  }

  // Les ids de faces/arêtes meurent à chaque rebuild. Le viewport vide
  // ses picks ; le PropertyManager doit faire de même — un Congé ouvert
  // ne doit pas appliquer des ids périmés après un Ctrl+Z.
  function invalidateSelections() {
    if (!active) return 0;
    let cleared = 0;
    for (const group of active.spec.groups) {
      for (const row of group.rows ?? []) {
        if (row.type !== "selection") continue;
        if (!hasSelectionValue(active.values[row.key])) continue;
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
    icon.src = "icons/" + spec.icon;
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

    if (row.type === "selection") {
      const box = el("div", "pselect-box");
      const value = values[row.key];
      if (!hasSelectionValue(value)) {
        box.textContent =
          t(row.hint ?? "Cliquez une face dans la zone graphique");
        return box;
      }
      if (value.items && value.items.every((i) => i.face != null)) {
        box.textContent = value.items.length <= 4
          ? value.items.map((i) => t("Face {n}", { n: i.face })).join(", ")
          : t("{n} faces", { n: value.items.length });
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

  return {
    open,
    close: (opts) => close(false, opts),
    /** OK, comme le bouton ✓ — sans effet sur un panneau d'information. */
    apply: () => { if (active && !active.spec.noApply) close(true); },
    notifyPick,
    invalidateSelections,
    get active() { return active !== null; },
    /** Un panneau de commande (avec OK) est ouvert. */
    get applicable() { return active !== null && !active.spec.noApply; },
  };
}
