// Dialogue de fichiers. Le moteur liste le dossier (prison de chemins) ;
// ici on filtre, on joint le nom et on confirme un écrasement.

import { t } from "./i18n.js";

const FILE_DIR_KEY = "freesolid.filedir";

const FILE_MODES = {
  open: {
    title: "Ouvrir",
    accept: "Ouvrir",
    mustExist: true,
    overwrite: false,
    defaultName: "",
    filters: [
      { label: "Pièce (.FCStd)", extensions: [".FCStd"] },
      { label: "STEP", extensions: [".step", ".stp"] },
      { label: "IGES", extensions: [".iges", ".igs"] },
      // Lus par le lecteur d'OpenSW, embarqué (engine/foreign.py).
      { label: "Pièce SLDPRT", extensions: [".SLDPRT"] },
      { label: "Parasolid", extensions: [".x_t", ".x_b"] },
      { label: "Tous les fichiers autorisés",
        extensions: [".FCStd", ".step", ".stp", ".iges", ".igs",
          ".SLDPRT", ".x_t", ".x_b"] },
    ],
  },
  save: {
    title: "Enregistrer sous",
    accept: "Enregistrer",
    mustExist: false,
    overwrite: true,
    defaultName: "piece-freesolid.FCStd",
    filters: [
      { label: "Pièce (.FCStd)", extensions: [".FCStd"] },
    ],
  },
  export: {
    title: "Exporter",
    accept: "Exporter",
    mustExist: false,
    overwrite: true,
    defaultName: "piece-freesolid.stl",
    filters: [
      { label: "Maillage (.stl)", extensions: [".stl"] },
      { label: "3MF", extensions: [".3mf"] },
      { label: "STEP", extensions: [".step", ".stp"] },
    ],
  },
};

function readFileDir(storage) {
  try {
    return storage?.getItem(FILE_DIR_KEY) || "";
  } catch {
    return "";
  }
}

export function writeFileDir(storage, path) {
  if (!path) return false;
  try {
    storage?.setItem(FILE_DIR_KEY, path);
    return true;
  } catch {
    return false;
  }
}

/** Dossiers toujours, fichiers du filtre seulement. */
export function visibleEntries(entries, extensions) {
  const allowed = new Set(extensions.map((ext) => ext.toLowerCase()));
  return (entries || []).filter((entry) => {
    if (entry?.kind === "dir") return true;
    const name = String(entry?.name || "");
    const dot = name.lastIndexOf(".");
    const ext = dot >= 0 ? name.slice(dot).toLowerCase() : "";
    return [...allowed].some((item) => item.toLowerCase() === ext);
  });
}

/**
 * Nom de fichier sûr, avec l'extension du filtre.
 * Refuse un séparateur ou « .. ».
 */
export function withExtension(typed, extensions) {
  const name = String(typed || "").trim();
  if (!name || /[\\/]/.test(name) || name.includes("..")) return "";
  const dot = name.lastIndexOf(".");
  const stem = dot > 0 ? name.slice(0, dot) : name;
  const ext = dot > 0 ? name.slice(dot) : "";
  if (!stem || stem.startsWith(".")) return "";
  const match = extensions.find((item) => item.toLowerCase() === ext.toLowerCase());
  return stem + (match || extensions[0]);
}

export function joinPath(dir, name) {
  if (!dir || !name) return "";
  const sep = dir.includes("\\") ? "\\" : "/";
  return dir.endsWith(sep) ? dir + name : dir + sep + name;
}

/** Le nom tel que le dossier l'écrit, casse comprise, ou "". */
export function existingName(entries, name) {
  const wanted = String(name || "").toLowerCase();
  const found = (entries || []).find((entry) =>
    entry?.kind === "file" && String(entry.name).toLowerCase() === wanted);
  return found ? String(found.name) : "";
}

export function needsOverwrite(entries, name) {
  return existingName(entries, name) !== "";
}

/** `listDir(path)` résout le dossier. `pick(mode)` renvoie un chemin ou null. */
export function installFileDialog(doc, { listDir, storage, confirmReplace } = {}) {
  const root = doc.getElementById("file-dialog");
  if (!root) return async () => null;
  const ask = confirmReplace || ((name) =>
    doc.defaultView.confirm(t("Remplacer « {name} » ?", { name })));
  let listing = null;
  let mode = null;
  let filterIndex = 0;
  let finish = null;

  function extensions() {
    return mode.filters[filterIndex].extensions;
  }

  function close(path) {
    root.hidden = true;
    root.replaceChildren();
    const done = finish;
    finish = null;
    listing = null;
    mode = null;
    done?.(path ?? null);
  }

  function render() {
    const filter = mode.filters[filterIndex];
    const shown = visibleEntries(listing?.entries, filter.extensions);
    const selected = root.querySelector(".file-name input")?.value
      ?? mode.defaultName;
    root.replaceChildren();
    const card = doc.createElement("div");
    card.className = "file-card";
    card.setAttribute("role", "dialog");
    card.setAttribute("aria-modal", "true");
    const title = doc.createElement("h2");
    title.textContent = t(mode.title);
    card.appendChild(title);
    const path = doc.createElement("p");
    path.className = "file-path";
    path.textContent = listing?.path || "";
    card.appendChild(path);
    const row = doc.createElement("div");
    row.className = "file-row";
    const up = doc.createElement("button");
    up.type = "button";
    up.textContent = t("Dossier parent");
    up.disabled = !listing?.parent;
    up.addEventListener("click", () => openDir(listing.parent));
    const select = doc.createElement("select");
    mode.filters.forEach((item, index) => {
      const option = doc.createElement("option");
      option.value = String(index);
      option.textContent = t(item.label);
      if (index === filterIndex) option.selected = true;
      select.appendChild(option);
    });
    select.addEventListener("change", () => {
      filterIndex = Number(select.value) || 0;
      const field = root.querySelector(".file-name input");
      if (field) {
        field.value = withExtension(field.value, extensions()) || field.value;
      }
      render();
    });
    row.append(up, select);
    card.appendChild(row);
    const list = doc.createElement("div");
    list.className = "file-list";
    for (const entry of shown) {
      const button = doc.createElement("button");
      button.type = "button";
      button.textContent = entry.kind === "dir" ? entry.name + "/" : entry.name;
      if (entry.kind === "dir") button.className = "dir";
      button.addEventListener("click", () => {
        if (entry.kind === "dir") {
          openDir(joinPath(listing.path, entry.name));
          return;
        }
        const input = card.querySelector(".file-name input");
        if (input) input.value = entry.name;
        for (const other of list.querySelectorAll("button")) {
          other.classList.toggle("on", other === button);
        }
      });
      button.addEventListener("dblclick", () => {
        if (entry.kind === "file") accept(entry.name);
      });
      list.appendChild(button);
    }
    card.appendChild(list);
    const nameRow = doc.createElement("label");
    nameRow.className = "file-name";
    const nameLabel = doc.createElement("span");
    nameLabel.textContent = t("Nom du fichier");
    const input = doc.createElement("input");
    input.type = "text";
    input.value = selected;
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        accept(input.value);
      }
    });
    nameRow.append(nameLabel, input);
    card.appendChild(nameRow);
    const error = doc.createElement("p");
    error.className = "file-error";
    error.hidden = true;
    card.appendChild(error);
    const actions = doc.createElement("div");
    actions.className = "file-actions";
    const cancel = doc.createElement("button");
    cancel.type = "button";
    cancel.textContent = t("Annuler (Échap)");
    cancel.addEventListener("click", () => close(null));
    const ok = doc.createElement("button");
    ok.type = "button";
    ok.className = "ok";
    ok.textContent = t(mode.accept);
    ok.addEventListener("click", () => accept(input.value));
    actions.append(cancel, ok);
    card.appendChild(actions);
    root.appendChild(card);
    input.focus();
    input.select();
  }

  function showError(message, translate = true) {
    const error = root.querySelector(".file-error");
    if (!error) return;
    error.hidden = false;
    error.textContent = translate ? t(message) : message;
  }

  async function accept(typed) {
    let name = withExtension(typed, extensions());
    if (!name || !listing?.path) {
      showError("Fichier introuvable.");
      return;
    }
    if (mode.mustExist) {
      // Le filtre impose sa casse (« cube.step ») ; le disque garde la
      // sienne (« cube.STEP ») et il est sensible à la casse sous Linux.
      name = existingName(listing.entries, name);
      if (!name) {
        showError("Fichier introuvable.");
        return;
      }
    }
    if (mode.overwrite && needsOverwrite(listing.entries, name) && !ask(name)) {
      return;
    }
    const full = joinPath(listing.path, name);
    writeFileDir(storage, listing.path);
    close(full);
  }

  function openDir(path) {
    load(path).catch((error) => {
      showError(error?.message || t("Fichier introuvable."), false);
    });
  }

  async function load(path) {
    const next = await listDir(path || "");
    listing = next;
    render();
  }

  async function pick(which) {
    const spec = FILE_MODES[which];
    if (!spec) return null;
    if (finish) close(null);
    mode = spec;
    filterIndex = 0;
    listing = null;
    root.hidden = false;
    return new Promise((resolve) => {
      finish = resolve;
      const start = readFileDir(storage);
      load(start).catch(() => {
        if (!finish) return;
        if (!start) {
          close(null);
          return;
        }
        load("").catch(() => {
          if (finish) close(null);
        });
      });
    });
  }

  doc.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !root.hidden && finish) {
      event.preventDefault();
      event.stopImmediatePropagation();
      close(null);
    }
  }, true);

  return pick;
}
