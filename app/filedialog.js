// Dialogue de fichiers. Dans l'application de bureau, celui du système
// (Tauri), qui rend le vrai chemin. Dans un navigateur, une page ne peut pas
// obtenir de chemin : le moteur liste le dossier (prison de chemins), et
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
      { label: "Tous les fichiers autorisés", all: true,
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

/** Le dialogue du système, dans la fenêtre de l'application de bureau ;
 *  null dans un navigateur. */
export function nativeFileDialog(win) {
  const dialog = win?.__TAURI__?.dialog;
  return typeof dialog?.open === "function" && typeof dialog?.save === "function"
    ? dialog : null;
}

/** Filtres au format du dialogue natif : sans point, telle qu'écrite
 *  (« FCStd ») puis dans les deux casses — GTK compare les extensions à la
 *  lettre. Le filtre « tous » d'abord : c'est celui que le système choisit
 *  d'office. */
export function nativeFilters(filters) {
  const list = filters.map((filter) => ({
    all: Boolean(filter.all),
    name: t(filter.label),
    extensions: [...new Set(filter.extensions.flatMap((ext) => {
      const bare = ext.replace(/^\./, "");
      return [bare, bare.toLowerCase(), bare.toUpperCase()];
    }))],
  }));
  return [...list.filter((f) => f.all), ...list.filter((f) => !f.all)]
    .map(({ name, extensions }) => ({ name, extensions }));
}

/** Le dossier d'un chemin, quel que soit le séparateur. */
export function parentDir(path) {
  const text = String(path || "");
  const cut = Math.max(text.lastIndexOf("/"), text.lastIndexOf("\\"));
  if (cut < 0) return "";
  if (cut === 0) return text[0];
  const dir = text.slice(0, cut);
  return /^[A-Za-z]:$/.test(dir) ? dir + text[cut] : dir;
}

/** Le nom de fichier d'un chemin, quel que soit le séparateur. */
export function baseName(path) {
  const text = String(path || "");
  return text.slice(parentDir(text).length).replace(/^[\\/]/, "");
}

/** Le chemin du dialogue natif, avec une extension permise : certains
 *  systèmes n'ajoutent pas celle du filtre au nom tapé. */
export function withAllowedExtension(path, extensions) {
  const name = baseName(path);
  const dot = name.lastIndexOf(".");
  const ext = dot > 0 ? name.slice(dot).toLowerCase() : "";
  return extensions.some((item) => item.toLowerCase() === ext)
    ? path : path + extensions[0];
}

/** Choisit un fichier dans le dialogue natif ; chemin ou null. */
export async function pickNative(dialog, spec, { storage, listDir, ask } = {}) {
  const dir = readFileDir(storage);
  const options = { title: t(spec.title), filters: nativeFilters(spec.filters) };
  let path;
  if (spec.mustExist) {
    if (dir) options.defaultPath = dir;
    path = await dialog.open({ ...options, multiple: false, directory: false });
  } else {
    options.defaultPath = dir ? joinPath(dir, spec.defaultName) : spec.defaultName;
    path = await dialog.save(options);
  }
  if (Array.isArray(path)) path = path[0];
  if (!path || typeof path !== "string") return null;
  if (!spec.mustExist) {
    const fixed = withAllowedExtension(
      path, spec.filters.flatMap((filter) => filter.extensions));
    // Le système a confirmé l'écrasement du nom tapé, pas celui du nom
    // complété : on le demande pour celui-là.
    if (fixed !== path && spec.overwrite && listDir && ask) {
      let listing = null;
      try {
        listing = await listDir(parentDir(fixed));
      } catch {
        listing = null;
      }
      const name = baseName(fixed);
      if (needsOverwrite(listing?.entries, name) && !ask(name)) return null;
    }
    path = fixed;
  }
  writeFileDir(storage, parentDir(path));
  return path;
}

/** `listDir(path)` résout le dossier. `pick(mode)` renvoie un chemin ou
 *  null. `native` : le dialogue du système (``nativeFileDialog``), essayé
 *  d'abord ; s'il échoue, le dialogue web prend le relais. */
export function installFileDialog(doc, { listDir, storage, confirmReplace, native } = {}) {
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
    if (native) {
      try {
        return await pickNative(native, spec, { storage, listDir, ask });
      } catch {
        // Permission refusée, plateforme sans dialogue : le web prend le relais.
      }
    }
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
