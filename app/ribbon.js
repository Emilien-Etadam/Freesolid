// Le ruban (CommandManager) : la disposition vit dans ribbon.json, le
// rendu vit ici. Un seul constructeur pour les onglets du noyau et ceux
// des plugins — mêmes classes CSS, mêmes règles de validation. Les
// fonctions prennent `doc` en paramètre pour tourner au banc Node.

/** Id d'onglet : minuscules, chiffres, underscore — jamais de balisage. */
export function isPluginId(id) {
  return typeof id === "string" && /^[a-z][a-z0-9_]*$/.test(id);
}

/** Id de bouton : un nom sûr pour getElementById. */
export function isButtonId(id) {
  return typeof id === "string" && /^[A-Za-z][A-Za-z0-9_-]*$/.test(id);
}

/** Chemin d'icône jailé : pas de remontée, pas d'antislash, pas de schéma. */
export function safeIconSrc(icon) {
  if (typeof icon !== "string" || !icon) return "";
  if (icon.includes("..") || icon.includes("\\") || icon.includes(":")) {
    return "";
  }
  if (!/^[A-Za-z0-9_./-]+$/.test(icon)) return "";
  return icon;
}

/** Un onglet de l'en-tête (le bouton seul, sans écouteur). */
export function buildTabButton(doc, id, libelle) {
  const tab = doc.createElement("button");
  tab.className = "tab";
  tab.dataset.tab = id;
  tab.textContent = typeof libelle === "string" && libelle.trim()
    ? libelle.trim() : id;
  return tab;
}

/** `Node` n'existe qu'en navigateur — au banc Node.js, jamais un nœud. */
function isDomNode(value) {
  return typeof Node !== "undefined" && value instanceof Node;
}

/** Le bandeau d'un onglet : groupes puis boutons, dans l'ordre du spec. */
export function buildRibbonElement(doc, id, groupes) {
  const ribbon = doc.createElement("div");
  ribbon.id = "ribbon-" + id;
  ribbon.className = "ribbon";
  const liste = Array.isArray(groupes) ? groupes : [];
  for (const groupe of liste) {
    const group = doc.createElement("div");
    group.className = "ribbon-group";
    const btns = doc.createElement("div");
    btns.className = "ribbon-group-btns";
    if (isDomNode(groupe.node)) {
      btns.appendChild(groupe.node);
    } else {
      for (const specBtn of groupe.boutons ?? []) {
        if (!isButtonId(specBtn.id)) continue;
        const btn = doc.createElement("button");
        btn.id = specBtn.id;
        if (specBtn.titre) btn.title = String(specBtn.titre);
        if (specBtn.disabled) btn.disabled = true;
        const icon = safeIconSrc(specBtn.icon);
        if (icon) {
          const img = doc.createElement("img");
          img.src = icon;
          img.alt = "";
          btn.appendChild(img);
        }
        if (specBtn.libelle) {
          btn.appendChild(doc.createTextNode(String(specBtn.libelle)));
        }
        btns.appendChild(btn);
      }
    }
    group.appendChild(btns);
    const label = doc.createElement("div");
    label.className = "ribbon-group-label";
    label.textContent = typeof groupe.libelle === "string" ? groupe.libelle : "";
    group.appendChild(label);
    ribbon.appendChild(group);
  }
  return ribbon;
}

/**
 * Installe les onglets du noyau depuis la disposition JSON : les onglets
 * avant `.push` de la topbar, les bandeaux avant `#sketchbar`, le premier
 * onglet actif. Un onglet `element` (l'esquisse) référence un bandeau
 * déjà dans la page au lieu d'en construire un.
 * @returns {Object<string, string>} clé d'onglet → id d'élément bandeau
 */
export function installCoreRibbons(doc, layout) {
  const map = {};
  const push = doc.querySelector("#topbar .push");
  const sketchbar = doc.getElementById("sketchbar");
  let first = true;
  for (const onglet of layout?.onglets ?? []) {
    if (!isPluginId(onglet?.id) || map[onglet.id]) continue;
    let ribbonEl;
    if (Array.isArray(onglet.groupes)) {
      ribbonEl = buildRibbonElement(doc, onglet.id, onglet.groupes);
      if (sketchbar) sketchbar.parentElement.insertBefore(ribbonEl, sketchbar);
    } else if (isButtonId(onglet.element)) {
      ribbonEl = doc.getElementById(onglet.element);
    }
    if (!ribbonEl) continue;
    const tab = buildTabButton(doc, onglet.id, onglet.libelle);
    if (push) push.parentElement.insertBefore(tab, push);
    if (first) {
      tab.classList.add("active");
      ribbonEl.classList.add("active");
      first = false;
    }
    map[onglet.id] = ribbonEl.id;
  }
  return map;
}
