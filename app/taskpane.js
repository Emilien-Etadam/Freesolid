// Volet de ressources, replié sur le bord droit : matières (appliquées au
// corps actif), gabarits (une nouvelle pièce), aide (gestes et touches).
// Un bouton ouvre son volet par-dessus la vue ; un second clic, ou Échap,
// le referme.

import { t } from "./i18n.js";

const ICONS = {
  materials: '<circle cx="9" cy="9" r="6.5" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M5 7.5a4.5 4.5 0 0 1 5-3" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
  templates: '<rect x="3" y="2.5" width="12" height="13" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M3 6.5h12" stroke="currentColor" stroke-width="1.4"/>',
  help: '<circle cx="9" cy="9" r="6.5" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M7 7a2 2 0 1 1 2.8 1.8c-.6.3-.8.7-.8 1.4" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><circle cx="9" cy="12.6" r=".9" fill="currentColor"/>',
};

export const PANES = [
  ["materials", "Matières"],
  ["templates", "Gabarits"],
  ["help", "Aide"],
];

/** Gestes et touches de la vue, dans l'ordre de l'aide. */
export const HELP_KEYS = [
  ["S", "Barre de raccourcis sous le pointeur (S encore : chercher)"],
  ["Ctrl+F", "Rechercher une commande"],
  ["Espace", "Boîte d'orientation"],
  ["F", "Cadrer la pièce"],
  ["Ctrl+1 … 7", "Vues standard (face, arrière, gauche, droite, dessus, dessous, iso)"],
  ["Ctrl+8", "Normal à la face choisie"],
  ["Tab", "Masquer ce qui est sous le pointeur"],
  ["Clic droit glissé", "Geste : huit commandes autour du pointeur"],
  ["Entrée / Échap", "Valider / annuler la commande en cours"],
];

export function installTaskPane(ctx) {
  const pane = document.createElement("div");
  pane.id = "taskpane";
  pane.setAttribute("role", "complementary");
  pane.setAttribute("aria-label", t("Volet de ressources"));
  const strip = document.createElement("div");
  strip.className = "taskpane-strip";
  const panel = document.createElement("div");
  panel.className = "taskpane-panel";
  panel.hidden = true;
  pane.append(strip, panel);
  document.body.appendChild(pane);

  let open = null;
  const buttons = {};
  for (const [key, label] of PANES) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.title = t(label);
    btn.setAttribute("aria-label", t(label));
    btn.innerHTML = `<svg viewBox="0 0 18 18" width="18" height="18" aria-hidden="true">${ICONS[key]}</svg>`;
    btn.addEventListener("click", () => toggle(key));
    strip.appendChild(btn);
    buttons[key] = btn;
  }

  function toggle(key) {
    open = open === key ? null : key;
    for (const [k, btn] of Object.entries(buttons)) btn.classList.toggle("on", k === open);
    panel.hidden = open === null;
    if (open) render();
  }

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && open && !ctx.panel?.active) toggle(open);
  });

  function heading(text) {
    const h = document.createElement("h2");
    h.textContent = text;
    return h;
  }

  async function renderMaterials() {
    const body = (ctx.lastTree?.bodies ?? []).find((b) => b.active);
    panel.replaceChildren(heading(t("Matières")));
    if (!body) {
      panel.appendChild(note(t("Ouvrez une pièce : la matière s'applique au corps actif.")));
      return;
    }
    panel.appendChild(note(t("Corps actif : {b}", { b: body.label })));
    const library = await ctx.call("material_library").catch(() => null);
    if (open !== "materials") return;
    const list = document.createElement("ul");
    list.className = "taskpane-list";
    for (const material of library?.materials ?? []) {
      const item = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = body.material?.id === material.id ? "on" : "";
      const swatch = document.createElement("span");
      swatch.className = "taskpane-swatch";
      if (material.color) swatch.style.background = material.color;
      const name = document.createElement("span");
      name.className = "taskpane-name";
      name.textContent = material.name;
      const density = document.createElement("span");
      density.className = "taskpane-meta";
      density.textContent = `${material.density} g/cm³`;
      btn.append(swatch, name, density);
      btn.title = t("Appliquer à {b}", { b: body.label });
      btn.addEventListener("click", () => {
        ctx.refresh(ctx.call("set_body_material", { body: body.name, material: material.id }));
      });
      item.appendChild(btn);
      list.appendChild(item);
    }
    panel.appendChild(list);
  }

  async function renderTemplates() {
    panel.replaceChildren(heading(t("Gabarits")));
    const result = await ctx.call("list_templates").catch(() => null);
    if (open !== "templates") return;
    const templates = result?.templates ?? [];
    if (!templates.length) {
      panel.appendChild(note(t("Aucun gabarit : Fichier → Enregistrer comme gabarit… en crée un depuis la pièce ouverte.")));
      return;
    }
    const list = document.createElement("ul");
    list.className = "taskpane-list";
    for (const template of templates) {
      const name = typeof template === "string" ? template : template.name;
      const item = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = name;
      btn.title = t("Nouvelle pièce depuis ce gabarit");
      btn.addEventListener("click", () => ctx.openTemplate?.(name));
      item.appendChild(btn);
      list.appendChild(item);
    }
    panel.appendChild(list);
  }

  function renderHelp() {
    panel.replaceChildren(heading(t("Aide")));
    const list = document.createElement("dl");
    list.className = "taskpane-keys";
    for (const [key, text] of HELP_KEYS) {
      const dt = document.createElement("dt");
      const kbd = document.createElement("kbd");
      kbd.textContent = t(key);
      dt.appendChild(kbd);
      const dd = document.createElement("dd");
      dd.textContent = t(text);
      list.append(dt, dd);
    }
    panel.appendChild(list);
    const more = document.createElement("button");
    more.type = "button";
    more.className = "taskpane-more";
    more.textContent = t("Raccourcis clavier…");
    more.addEventListener("click", () => ctx.openShortcutPanel?.());
    panel.appendChild(more);
  }

  function note(text) {
    const p = document.createElement("p");
    p.className = "taskpane-note";
    p.textContent = text;
    return p;
  }

  function render() {
    if (open === "materials") renderMaterials();
    else if (open === "templates") renderTemplates();
    else if (open === "help") renderHelp();
  }

  ctx.treeHooks?.push(() => { if (open === "materials") renderMaterials(); });
  return { toggle, get open() { return open; } };
}
