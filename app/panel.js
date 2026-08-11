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
//     title: "Bossage/Base extrudé",
//     groups: [{ label, rows: [row…] }],
//     note?: string,
//     onApply(values), onCancel?()
//   }
// Rows: { type: "number", key, label, value, unit?, min?, step?, showIf? }
//       { type: "select", key, options: [[value, label]…], value, label? }
//       { type: "check",  key, label, value }
//       { type: "selection", key, label?, hint?, value? }   // face picks
//       { type: "note", text }

export function createPropertyPanel({ say, onClose }) {
  const aside = document.querySelector("aside");
  const panelEl = document.getElementById("panel");

  let active = null; // { spec, values }

  // Chaque modification de valeur notifie la commande — c'est ce qui
  // alimente l'aperçu jaune en temps réel.
  function changed() {
    active?.spec.onChange?.({ ...active.values });
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // ---------- lifecycle ----------

  function open(spec) {
    if (active) close(false); // une commande à la fois, comme SolidWorks
    active = { spec, values: {} };
    for (const group of spec.groups) {
      for (const row of group.rows ?? []) {
        if (row.key !== undefined) active.values[row.key] = row.value ?? null;
      }
    }
    render();
    aside.classList.add("panel-open");
    document.addEventListener("keydown", onKey, true);
    panelEl.querySelector("input, select")?.focus();
    changed(); // premier aperçu avec les valeurs par défaut
  }

  function close(apply) {
    if (!active) return;
    const { spec, values } = active;
    active = null;
    aside.classList.remove("panel-open");
    document.removeEventListener("keydown", onKey, true);
    panelEl.innerHTML = "";
    onClose?.(); // efface l'aperçu avant d'appliquer ou d'abandonner
    if (apply) spec.onApply({ ...values });
    else spec.onCancel?.();
  }

  function onKey(event) {
    if (event.key === "Enter" && event.target.tagName !== "SELECT") {
      event.preventDefault();
      close(true);
    } else if (event.key === "Escape") {
      event.preventDefault();
      close(false);
    }
  }

  // The viewport reports picks here; a selection row that accepts this
  // kind absorbs them. Values are {kind: "face", face} or
  // {kind: "edges", edges: [...]}.
  function notifyPick(kind, value) {
    if (!active) return false;
    for (const group of active.spec.groups) {
      for (const row of group.rows ?? []) {
        if (row.type === "selection"
            && (row.accepts ?? ["face"]).includes(kind)) {
          active.values[row.key] = value;
          render();
          changed();
          return true;
        }
      }
    }
    return false;
  }

  // ---------- rendering ----------

  function render() {
    const { spec } = active;
    panelEl.innerHTML = "";

    const head = el("div", "phead-main");
    const icon = document.createElement("img");
    icon.src = "icons/" + spec.icon;
    icon.alt = "";
    const ok = el("button", "pok", "✓");
    ok.title = "OK (Entrée)";
    ok.addEventListener("click", () => close(true));
    const cancel = el("button", "pcancel", "✕");
    cancel.title = "Annuler (Échap)";
    cancel.addEventListener("click", () => close(false));
    head.append(icon, el("span", "ptitle", spec.title), ok, cancel);
    panelEl.append(head);

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
    if (row.type === "note") return el("div", "pnote", row.text);

    if (row.type === "selection") {
      const box = el("div", "pselect-box");
      const value = values[row.key];
      const empty = !value
        || (value.kind === "edges" && !value.edges.length)
        || (value.kind === "face" && value.face == null);
      if (empty) {
        box.textContent =
          row.hint ?? "Cliquez une face dans la zone graphique";
      } else if (value.kind === "edges") {
        box.textContent = value.edges.length <= 3
          ? value.edges.map((e) => `Arête ${e}`).join(", ")
          : `${value.edges.length} arêtes`;
        box.classList.add("filled");
      } else {
        box.textContent = `Face ${value.face}`;
        box.classList.add("filled");
      }
      return box;
    }

    const rowEl = el("div", "prow");
    if (row.type === "number") {
      const input = document.createElement("input");
      input.type = "number";
      input.value = values[row.key];
      input.step = row.step ?? "any";
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
        option.textContent = label;
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
    notifyPick,
    get active() { return active !== null; },
  };
}
