// Smoke test navigateur FreeSolid — le parcours utilisateur canonique
// contre un serveur déjà lancé (voir README.md) :
//
//   esquisse sur plan → rectangle → drag de coin (solveur WASM local)
//   → bossage avec aperçu jaune → OK → Ctrl+Z → Ctrl+Y
//
// Toute erreur console/page fait échouer le test (exit 1). Un dispose()
// de matériau partagé, une course async ou un état cassé explosent ici.
//
// Env : SMOKE_URL (défaut http://127.0.0.1:8787),
//       CHROMIUM_PATH (défaut : résolution playwright).
const fs = require("fs");
const path = require("path");

let chromium;
try {
  ({ chromium } = require("playwright"));
} catch {
  ({ chromium } = require("playwright-core"));
}

const URL_BASE = process.env.SMOKE_URL || "http://127.0.0.1:8787";
const SHOTS = path.join(__dirname, "shots");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const launchOptions = {
    headless: true,
    args: ["--no-sandbox", "--use-gl=swiftshader"],
  };
  if (process.env.CHROMIUM_PATH) {
    launchOptions.executablePath = process.env.CHROMIUM_PATH;
  }
  const browser = await chromium.launch(launchOptions);
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });

  // Hermétique : si three est installé localement (npm install dans ce
  // dossier), on le sert à la place d'unpkg — même version épinglée que
  // l'importmap d'app/index.html.
  const threeRoot = path.join(__dirname, "node_modules", "three");
  if (fs.existsSync(threeRoot)) {
    await page.route("https://unpkg.com/three@0.160.0/**", (route) => {
      const url = new URL(route.request().url());
      route.fulfill({
        path: path.join(threeRoot, url.pathname.replace("/three@0.160.0/", "")),
        contentType: "text/javascript; charset=utf-8",
      });
    });
  }

  const errors = [];
  page.on("console", (m) => {
    if (m.type() === "error") errors.push("console: " + m.text());
  });
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));

  const status = async () =>
    (await page.textContent("#status").catch(() => "")).trim();
  const step = async (label) =>
    console.log(`[${label}] status = "${await status()}"`);

  // Attente active du moteur : la page peut se charger avant que
  // freecadcmd n'ait fini de démarrer (~10 s à froid), et l'app ne
  // ping qu'une fois au boot — on recharge jusqu'au « Moteur prêt ».
  let ready = false;
  for (let i = 0; i < 20 && !ready; i++) {
    await page.goto(URL_BASE + "/");
    await sleep(3000);
    ready = (await status()).includes("Moteur prêt");
  }
  if (!ready) {
    console.log("ERREUR: moteur jamais prêt — status = " + await status());
    await browser.close();
    process.exit(1);
  }
  await step("chargement");
  const isOrtho = await page.evaluate(
    () => window.__freesolidDebug?.isOrthographic === true);
  if (!isOrtho) errors.push("caméra : projection orthographique absente");
  await page.screenshot({ path: path.join(SHOTS, "0-ribbon-groupes.png") });
  const featureGroups = await page.$$eval(
    "#ribbon-features .ribbon-group-label",
    (els) => els.map((e) => e.textContent),
  );
  const expectedGroups = [
    "Esquisse", "Corps", "Fonctions", "Habillage", "Répétitions",
  ];
  if (featureGroups.join("|") !== expectedGroups.join("|")) {
    errors.push("groupes Fonctions : " + featureGroups.join(", ")
      + " (attendu " + expectedGroups.join(", ") + ")");
  }

  // 0. Ids des 23 panneaux (registry FEATURES) + bascule libellés du ruban.
  const FEATURE_PANELS = [
    { id: "btn-pad", tab: "features" },
    { id: "btn-pocket", tab: "features" },
    { id: "btn-revolution", tab: "features" },
    { id: "btn-groove", tab: "features" },
    { id: "btn-hole", tab: "features" },
    { id: "btn-loft", tab: "features" },
    { id: "btn-sweep", tab: "features" },
    { id: "btn-helix", tab: "features" },
    { id: "btn-text", tab: "features" },
    { id: "btn-graph-feature", tab: "features" },
    { id: "btn-fillet", tab: "features" },
    { id: "btn-chamfer", tab: "features" },
    { id: "btn-shell", tab: "features" },
    { id: "btn-draft", tab: "features" },
    { id: "btn-linpattern", tab: "features" },
    { id: "btn-polpattern", tab: "features" },
    { id: "btn-mirror", tab: "features" },
    { id: "btn-boolean", tab: "features" },
    { id: "btn-surf-extrude", tab: "surfaces" },
    { id: "btn-surf-revolve", tab: "surfaces" },
    { id: "btn-surf-loft", tab: "surfaces" },
    { id: "btn-surf-sew", tab: "surfaces" },
    { id: "btn-surf-thicken", tab: "surfaces" },
  ];
  if (FEATURE_PANELS.length !== 23) {
    errors.push("harnais : 23 panneaux attendus, "
      + FEATURE_PANELS.length + " déclarés");
  }
  let opened = 0;
  for (const { id, tab } of FEATURE_PANELS) {
    const handle = await page.$("#" + id);
    if (!handle) {
      errors.push("bouton manquant : #" + id);
      continue;
    }
    await page.click('[data-tab="' + tab + '"]');
    await page.click("#" + id);
    await sleep(400);
    const panelOpen = await page.evaluate(() =>
      document.querySelector("aside")?.classList.contains("panel-open"));
    if (panelOpen) {
      opened += 1;
      // Le bouton peut disparaître entre la détection et le clic
      // (re-render du panneau) : repli Échap au lieu d'un timeout de 30 s.
      await page.click('#panel [title^="Annuler"], #panel [title^="Fermer"]',
        { timeout: 3000 }).catch(() => page.keyboard.press("Escape"));
      await sleep(150);
    }
  }
  console.log("[panneaux] " + opened + "/" + FEATURE_PANELS.length
    + " ouverts (les gardes sans esquisse / sans 2e corps n'ouvrent pas)");
  if (opened < 15) {
    errors.push("trop peu de panneaux ouverts : " + opened + "/23");
  }
  await page.click('[data-tab="features"]');
  await sleep(200);

  const settingsItem = async (value) => {
    // Un clic parasite (fermeture de panneau) peut avoir refermé le
    // menu : le rouvrir si l'entrée n'est pas visible.
    const item = page.locator('[data-ribbon-labels="' + value + '"]');
    if (!(await item.isVisible())) {
      await page.click("#btn-settings");
      await sleep(200);
    }
    await item.click({ timeout: 5000 });
  };
  await page.click("#btn-settings");
  await sleep(200);
  await page.screenshot({ path: path.join(SHOTS, "0b-menu-reglages.png") });
  await settingsItem("icons-only");
  await sleep(200);
  const iconsOnly = await page.evaluate(() =>
    document.body.classList.contains("ribbon-icons-only")
    && localStorage.getItem("freesolid.ribbonLabels") === "icons-only");
  if (!iconsOnly) errors.push("Icônes seules : classe ou localStorage absent");
  const labelBoxes = await page.$$eval(
    "#ribbon-features .ribbon-group",
    (groups) => groups.map((g) => {
      const label = g.querySelector(".ribbon-group-label");
      const gr = g.getBoundingClientRect();
      const lr = label.getBoundingClientRect();
      return {
        name: label.textContent,
        w: Math.round(lr.width),
        h: Math.round(lr.height),
        overflow: lr.left < gr.left - 1 || lr.right > gr.right + 1,
      };
    }),
  );
  for (const box of labelBoxes) {
    if (box.w < 8 || box.h < 8) {
      errors.push("libellé invisible en icônes seules : " + box.name);
    }
    if (box.overflow) {
      errors.push("libellé hors groupe en icônes seules : " + box.name);
    }
  }
  await page.screenshot({ path: path.join(SHOTS, "0c-icones-seules.png") });
  await page.click("#btn-settings");
  await sleep(150);
  await settingsItem("icons-and-text");
  await sleep(200);
  const iconsAndText = await page.evaluate(() =>
    !document.body.classList.contains("ribbon-icons-only")
    && localStorage.getItem("freesolid.ribbonLabels") === "icons-and-text");
  if (!iconsAndText) errors.push("Icônes et texte : classe encore posée");
  await step("réglages ruban");

  // 1. Esquisse — choix du plan dans le viewport. Deux courses possibles
  // juste après le balayage des panneaux : le clic #btn-sketch avalé, ou
  // pris en compte EN RETARD (après le clic de plan). Robuste aux deux :
  // réessayer le clic de plan jusqu'à l'activation réelle du ruban
  // Esquisse, en relançant #btn-sketch si le mode choix de plan retombe.
  const sketchbarActive = () => page.evaluate(() =>
    document.getElementById("sketchbar")?.classList.contains("active")
    === true);
  for (let i = 0; i < 4; i++) {
    await page.click("#btn-sketch");
    await sleep(1200);
    if ((await status()).includes("Esquisse")) break;
  }
  await step("choix plan");
  const canvas = await page.locator("#viewport canvas").first().boundingBox();
  const cx = canvas.x + canvas.width / 2, cy = canvas.y + canvas.height / 2;
  for (let i = 0; i < 5 && !(await sketchbarActive()); i++) {
    if (!(await status()).includes("cliquez un plan") && i > 0) {
      await page.click("#btn-sketch");
      await sleep(1000);
    }
    await page.mouse.click(cx, cy - 40);
    await sleep(1800);
  }
  await step("esquisse ouverte");

  // 2. Rectangle
  await page.click('[data-tool="rect"]');
  await page.mouse.click(cx - 90, cy - 70);
  await sleep(400);
  await page.mouse.click(cx + 90, cy + 70);
  await sleep(1500);
  await step("rectangle");
  await page.screenshot({ path: path.join(SHOTS, "1-esquisse.png") });

  // 2-p025. Propriétés d'une ligne dans le PropertyManager.
  await page.click('[data-tool="select"]');
  await sleep(200);
  await page.mouse.click(cx, cy - 70);
  await page.waitForFunction(
    () => document.querySelector("#panel .ptitle")?.textContent === "Ligne",
    null,
    { timeout: 8000 },
  ).catch(() => {});
  await sleep(300);
  const entityTitle = await page.evaluate(
    () => document.querySelector("#panel .ptitle")?.textContent ?? "");
  if (entityTitle !== "Ligne") {
    errors.push("P025 : titre panneau = « " + entityTitle + " » (attendu Ligne)");
  }
  const entityPanelText = await page.evaluate(
    () => document.querySelector("#panel")?.innerText ?? "");
  if (!/Longueur\s*:/.test(entityPanelText)
      || !/\d+[.,]\d{2}\s*mm/.test(entityPanelText)) {
    errors.push("P025 : longueur absente du panneau (« "
      + entityPanelText.replace(/\s+/g, " ").slice(0, 180) + " »)");
  }
  const panelOpenAfterLine = await page.evaluate(
    () => document.querySelector("aside")?.classList.contains("panel-open"));
  if (!panelOpenAfterLine) {
    errors.push("P025 : le PropertyManager devrait être ouvert sur la ligne");
  }
  await page.screenshot({ path: path.join(SHOTS, "1a-entite-ligne.png") });
  await page.mouse.click(cx + 90, cy);
  await sleep(500);
  const panelOpenAfterSecond = await page.evaluate(
    () => document.querySelector("aside")?.classList.contains("panel-open"));
  if (panelOpenAfterSecond) {
    errors.push("P025 : le panneau devrait se fermer à la 2e entité");
  }
  await page.keyboard.press("Escape");
  await sleep(250);
  await step("propriétés entité");

  const sketchState = () => page.evaluate(async () => {
    const r = await fetch("/api", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ op: "sketch_state",
                             params: { sketch: "Sketch" } }) });
    const j = await r.json();
    return j.ok ? j.result : null;
  });

  // 2a. P022 — double-clic sur le 2e point d'une ligne : pas de segment nul.
  const idsBeforeLine = new Set(
    ((await sketchState())?.entities ?? []).map((e) => e.id));
  await page.click('[data-tool="line"]');
  await sleep(200);
  const lineA = { x: cx + 130, y: cy - 40 };
  const lineB = { x: cx + 180, y: cy - 40 };
  await page.mouse.click(lineA.x, lineA.y);
  await sleep(300);
  await page.mouse.click(lineB.x, lineB.y);
  await sleep(400);
  await page.mouse.dblclick(lineB.x, lineB.y);
  await sleep(800);
  const afterLine = await sketchState();
  const zeroSeg = (afterLine?.entities ?? []).some((e) => {
    if (e.type !== "line" || !e.p1 || !e.p2) return false;
    return Math.hypot(e.p1[0] - e.p2[0], e.p1[1] - e.p2[1]) < 1e-6;
  });
  if (zeroSeg) {
    errors.push("double-clic ligne : un segment de longueur nulle a été créé");
  }
  const addedLine = (afterLine?.entities ?? [])
    .find((e) => !idsBeforeLine.has(e.id));
  if (!addedLine) {
    errors.push("ligne de test : aucun segment ajouté");
  } else {
    await page.click('[data-tool="select"]');
    await sleep(150);
    await page.mouse.move((lineA.x + lineB.x) / 2, lineA.y);
    await sleep(100);
    await page.keyboard.press("Delete");
    await sleep(800);
    const afterDelete = await sketchState();
    const stillThere = (afterDelete?.entities ?? [])
      .some((e) => e.id === addedLine.id);
    if (stillThere) {
      errors.push("ligne de test : la ligne ajoutée n'a pas été supprimée");
    }
  }
  await step("ligne sans segment nul");

  // 2b. Image d'esquisse — calque client, jamais envoyé au serveur.
  // PNG 2×2 px via le sélecteur de fichier du bouton Image.
  const png2x2 = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAEklEQVR4nGP4z8AAQmDqPwgAAEnICfchVbMlAAAAAElFTkSuQmCC",
    "base64",
  );
  const chooserPromise = page.waitForEvent("filechooser", { timeout: 8000 });
  await page.click("#sk-image");
  const chooser = await chooserPromise;
  await chooser.setFiles({
    name: "scan.png",
    mimeType: "image/png",
    buffer: png2x2,
  });
  await page.waitForFunction(
    () => document.querySelector("#panel .ptitle")?.textContent
      === "Image d'esquisse",
    null,
    { timeout: 8000 },
  );
  await sleep(400);
  await step("image esquisse");
  await page.screenshot({ path: path.join(SHOTS, "1b-image-esquisse.png") });
  await page.click('#panel [title^="OK"]');
  await sleep(300);

  // 3. Drag du coin — solveur planegcs WASM dans le navigateur
  await page.click('[data-tool="select"]');
  await sleep(300);
  await page.mouse.move(cx + 90, cy + 70);
  await page.mouse.down();
  for (let i = 1; i <= 12; i++) {
    await page.mouse.move(cx + 90 + i * 4, cy + 70 + i * 2);
    await sleep(25);
  }
  await page.mouse.up();
  await sleep(1200);
  await step("drag coin");
  await page.screenshot({ path: path.join(SHOTS, "2-drag.png") });

  // 3b. Drag d'arête — milieu du bord HAUT, loin des coins (le coin
  // bas-droit a été tiré de (+48, +24), le bord haut n'a pas bougé :
  // (cx−90, cy−70) → (cx+90, cy−70)). Vérifié sur la géométrie : le
  // sketch_state doit réellement bouger, sinon le pas ment.
  const flatten = (state) => (state?.entities ?? [])
    .flatMap((e) => [...(e.p1 ?? []), ...(e.p2 ?? []), ...(e.c ?? [])]);
  const horizontalsOf = (state) => (state?.entities ?? []).filter((e) =>
    e.type === "line" && e.p1 && e.p2
    && Math.abs(e.p1[1] - e.p2[1]) < 1);
  const yOf = (e) => (e.p1[1] + e.p2[1]) / 2;
  const beforeState = await sketchState();
  const beforeEdge = flatten(beforeState);
  const beforeHoriz = horizontalsOf(beforeState);
  await page.mouse.move(cx, cy - 70);
  await page.mouse.down();
  for (let i = 1; i <= 10; i++) {
    await page.mouse.move(cx + i * 3, cy - 70 + i * 4);
    await sleep(25);
  }
  await page.mouse.up();
  await sleep(1200);
  const afterState = await sketchState();
  const afterEdge = flatten(afterState);
  const moved = beforeEdge.length === afterEdge.length
    && beforeEdge.some((v, i) => Math.abs(v - afterEdge[i]) > 1);
  if (!moved) {
    errors.push("drag d'arête : la géométrie n'a pas bougé "
      + "(le pas a raté l'arête ou le drag est cassé)");
  }
  // Le drag du bord haut a aussi une composante X (ddl restant : largeur /
  // translation). L'étirement change la hauteur ; le Y du bord bas doit
  // rester. Une translation d'ensemble ferait bouger les deux Y.
  let yStayed = 0;
  for (const h of beforeHoriz) {
    const after = (afterState?.entities ?? []).find((e) => e.id === h.id);
    if (after && Math.abs(yOf(h) - yOf(after)) <= 1) yStayed += 1;
  }
  if (yStayed < 1) {
    errors.push("drag d'arête : le bord bas a bougé "
      + "(étirement attendu, pas une translation d'ensemble)");
  }
  await step("drag arête");
  await page.screenshot({ path: path.join(SHOTS, "2b-drag-edge.png") });

  // P027 — avant le bossage, aucun solide : compteur honnête.
  const folderTextsBeforePad = await page.locator("#tree li.folder")
    .allTextContents();
  if (!folderTextsBeforePad.some((t) => t.includes("Corps volumiques (0)"))) {
    errors.push("P027 : attendu « Corps volumiques (0) » avant le bossage"
      + " (vu : " + folderTextsBeforePad.join(" | ") + ")");
  }

  // 4. Bossage : onglet Fonctions, sortie auto d'esquisse, aperçu, OK
  await page.click('[data-tab="features"]');
  await sleep(400);
  await page.click("#btn-pad");
  await sleep(2500);
  await step("panneau bossage + aperçu");
  await page.screenshot({ path: path.join(SHOTS, "3-apercu.png") });
  await page.click('#panel [title^="OK"]');
  await sleep(3000);
  await step("bossage appliqué");
  await page.screenshot({ path: path.join(SHOTS, "4-bossage.png") });

  // N003 — variable avant d'ouvrir le graphe, pour tirer un fil.
  await page.click("#btn-equations");
  await page.waitForFunction(
    () => document.querySelector("#panel .ptitle")?.textContent === "Équations",
    null,
    { timeout: 8000 },
  );
  await page.locator("#panel .prow", { hasText: "Nom" }).locator("input")
    .fill("largeur");
  await page.locator("#panel .prow", { hasText: "Valeur" }).locator("input")
    .fill("25");
  await page.click('#panel [title^="OK"]');
  await sleep(1500);
  const listedVars = await page.evaluate(async () => {
    const r = await fetch("/api", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ op: "list_variables", params: {} }) });
    const j = await r.json();
    return j.ok ? j.result.variables : [];
  });
  if (!listedVars.some((v) => v.name === "largeur")) {
    errors.push("N003 : variable largeur absente ("
      + JSON.stringify(listedVars) + ")");
  }
  await step("variable largeur");

  // N002 — vue en graphe lecture seule, depuis lastTree.
  await page.click("#btn-graph");
  await page.waitForSelector("#graph-view.open .graph-node", { timeout: 8000 });
  const graphInfo = await page.evaluate(() => {
    const view = document.getElementById("graph-view");
    const nodes = [...document.querySelectorAll("#graph-view .graph-node")];
    const edges = [...document.querySelectorAll("#graph-view .graph-edge")];
    return {
      open: view?.classList.contains("open") === true,
      labels: nodes.map((n) => (n.textContent || "").trim()),
      names: nodes.map((n) => n.getAttribute("data-name") || ""),
      edges: edges.map((e) => ({
        from: e.getAttribute("data-from") || "",
        to: e.getAttribute("data-to") || "",
        kind: e.getAttribute("data-kind") || "",
      })),
    };
  });
  if (!graphInfo.open) errors.push("N002 : graphe non ouvert");
  const hasSketch = graphInfo.names.some((n) => /Sketch/i.test(n))
    || graphInfo.labels.some((t) => /Esquisse/i.test(t));
  const hasPad = graphInfo.names.some((n) => /Pad/i.test(n))
    || graphInfo.labels.some((t) => /Bossage/i.test(t));
  if (!hasSketch || !hasPad) {
    errors.push("N002 : esquisse et bossage attendus dans le graphe ("
      + graphInfo.labels.join(", ") + ")");
  }
  const linked = graphInfo.edges.some((e) =>
    (/Sketch/i.test(e.from) && /Pad/i.test(e.to))
    || (/Sketch/i.test(e.to) && /Pad/i.test(e.from)));
  if (!linked) {
    errors.push("N002 : pas d'arête esquisse–bossage ("
      + JSON.stringify(graphInfo.edges) + ")");
  }
  await page.screenshot({ path: path.join(SHOTS, "4a-graphe.png") });

  // N003 — tirer un fil variable → bossage, choisir la profondeur, couper.
  const varNode = page.locator("#graph-view .graph-node.variable").first();
  const padNode = page.locator("#graph-view .graph-node").filter({
    hasText: /Bossage/,
  }).first();
  const varBox = await varNode.boundingBox();
  const padNodeBox = await padNode.boundingBox();
  if (!varBox || !padNodeBox) {
    errors.push("N003 : nœud variable ou bossage introuvable pour le drag");
  } else {
    await page.mouse.move(varBox.x + varBox.width / 2,
      varBox.y + varBox.height / 2);
    await page.mouse.down();
    const steps = 12;
    for (let i = 1; i <= steps; i++) {
      const x = varBox.x + varBox.width / 2
        + (padNodeBox.x + padNodeBox.width / 2 - varBox.x - varBox.width / 2)
          * (i / steps);
      const y = varBox.y + varBox.height / 2
        + (padNodeBox.y + padNodeBox.height / 2 - varBox.y - varBox.height / 2)
          * (i / steps);
      await page.mouse.move(x, y);
      await sleep(20);
    }
    await page.mouse.up();
    await page.waitForSelector("#param-pick .menu-item[data-prop='Length']", {
      timeout: 8000,
    }).catch(() => {});
    const pickVisible = await page.evaluate(() =>
      document.getElementById("param-pick")?.style.display === "block");
    if (!pickVisible) {
      errors.push("N003 : sélecteur de cote absent après le dépôt du fil");
    } else {
      await page.click("#param-pick .menu-item[data-prop='Length']");
      await sleep(2500);
    }
  }
  const afterWire = await page.evaluate(async () => {
    const edges = [...document.querySelectorAll("#graph-view .graph-edge")]
      .map((e) => ({
        from: e.getAttribute("data-from") || "",
        to: e.getAttribute("data-to") || "",
        kind: e.getAttribute("data-kind") || "",
      }));
    const pad = [...document.querySelectorAll("#graph-view .graph-node")]
      .find((n) => /Pad/i.test(n.getAttribute("data-name") || "")
        || /Bossage/i.test(n.textContent || ""));
    const feature = pad?.getAttribute("data-name") || "Pad";
    const r = await fetch("/api", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ op: "get_params",
                             params: { feature } }) });
    const j = await r.json();
    const length = (j.ok ? j.result.params : [])
      .find((p) => p.prop === "Length") || null;
    return { edges, length, feature };
  });
  const paramEdge = afterWire.edges.find((e) => e.kind === "param"
    && /largeur/i.test(e.from));
  if (!paramEdge) {
    errors.push("N003 : arête param largeur→bossage absente ("
      + JSON.stringify(afterWire.edges) + ")");
  }
  if (!(afterWire.length && Math.abs(afterWire.length.value - 25) < 1e-6
        && afterWire.length.expr)) {
    errors.push("N003 : la profondeur devrait suivre largeur=25 ("
      + JSON.stringify(afterWire.length) + ")");
  }
  await page.screenshot({ path: path.join(SHOTS, "4a2-graphe-param.png") });

  const lengthBeforeCut = afterWire.length?.value;
  const paramSel = page.locator("#graph-view .graph-edge.param").first();
  if (await paramSel.count()) {
    await paramSel.click({ button: "right" });
    await sleep(250);
    const unlinkVisible = await page.evaluate(() =>
      document.getElementById("graph-edge-menu")?.style.display === "block");
    if (!unlinkVisible) {
      errors.push("N003 : menu « Supprimer la liaison » absent");
    } else {
      await page.click("#ctx-unlink");
      await sleep(2500);
    }
  } else {
    errors.push("N003 : pas d'arête param à couper");
  }
  const afterCut = await page.evaluate(async (feature) => {
    const paramCount = document.querySelectorAll(
      "#graph-view .graph-edge.param").length;
    const r = await fetch("/api", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ op: "get_params",
                             params: { feature } }) });
    const j = await r.json();
    const length = (j.ok ? j.result.params : [])
      .find((p) => p.prop === "Length") || null;
    return { paramCount, length };
  }, afterWire.feature);
  if (afterCut.paramCount !== 0) {
    errors.push("N003 : l'arête param devrait disparaître après coupure");
  }
  if (afterCut.length?.expr) {
    errors.push("N003 : l'expression devrait être retirée après coupure ("
      + afterCut.length.expr + ")");
  }
  if (lengthBeforeCut != null && afterCut.length
      && Math.abs(afterCut.length.value - lengthBeforeCut) > 1e-6) {
    errors.push("N003 : la géométrie a bougé à la coupure ("
      + lengthBeforeCut + " → " + afterCut.length.value + ")");
  }
  // Reposer la profondeur d'origine : 25 mm décalerait le picking P028.
  await page.evaluate(async (feature) => {
    await fetch("/api", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ op: "set_params",
        params: { feature, values: { Length: 10 } } }) });
  }, afterWire.feature);
  await sleep(1200);
  await page.screenshot({ path: path.join(SHOTS, "4a3-graphe-coupure.png") });
  await step("fil paramétrique");

  await page.keyboard.press("Escape");
  await sleep(300);
  let graphClosed = await page.evaluate(() =>
    !document.getElementById("graph-view")?.classList.contains("open"));
  if (!graphClosed) {
    await page.click("#btn-graph");
    await sleep(200);
    graphClosed = await page.evaluate(() =>
      !document.getElementById("graph-view")?.classList.contains("open"));
    errors.push("N002 : Échap n'a pas fermé le graphe");
  }
  await step("vue graphe");

  // 4b. FeatureManager — dossiers en tête + barre de reprise glissée.
  const folderTexts = await page.locator("#tree li.folder").allTextContents();
  const folderJoined = folderTexts.join(" | ");
  for (const name of ["Corps volumiques", "Corps surfaciques", "Équations"]) {
    if (!folderTexts.some((t) => t.includes(name))) {
      errors.push("dossier FeatureManager manquant : " + name
        + " (vu : " + folderJoined + ")");
    }
  }
  if (!folderTexts.some((t) => t.includes("Corps volumiques (1)"))) {
    errors.push("P027 : attendu « Corps volumiques (1) » après le bossage"
      + " (vu : " + folderJoined + ")");
  }
  const bodyRowsAfterPad = await page.locator("#tree li.body").count();
  if (bodyRowsAfterPad < 1) {
    errors.push("P027 : dossier Corps volumiques devrait être déplié "
      + "après le bossage (ligne de corps invisible)");
  }
  await page.waitForSelector("#tree li.rollback", { timeout: 8000 });
  await page.waitForSelector("#tree li.feat", { timeout: 8000 });
  const faceCount = async () => page.evaluate(async () => {
    const r = await fetch("/api", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ op: "tessellate", params: {} }) });
    const j = await r.json();
    return j.ok ? (j.result.groups ?? []).length : -1;
  });
  const facesBefore = await faceCount();
  if (facesBefore < 1) {
    errors.push("barre de reprise : pas de solide après le bossage");
  }
  const dragRollback = async (fromSel, toY) => {
    const box = await page.locator(fromSel).boundingBox();
    const x = box.x + box.width / 2;
    const y = box.y + box.height / 2;
    await page.mouse.move(x, y);
    await page.mouse.down();
    const steps = 8;
    for (let i = 1; i <= steps; i++) {
      await page.mouse.move(x, y + (toY - y) * (i / steps));
      await sleep(30);
    }
    await page.mouse.up();
  };
  const padBox = await page.locator("#tree li.feat").first().boundingBox();
  await dragRollback("#tree li.rollback", padBox.y - 8);
  await sleep(2500);
  const facesRolled = await faceCount();
  if (!(facesRolled === 0 || facesRolled < facesBefore)) {
    errors.push("barre de reprise : le solide devrait disparaître "
      + `(faces ${facesBefore} → ${facesRolled})`);
  }
  await step("barre de reprise remontée");
  await page.screenshot({ path: path.join(SHOTS, "4b-reprise-haut.png") });

  const padBox2 = await page.locator("#tree li.feat").first().boundingBox();
  await dragRollback("#tree li.rollback", padBox2.y + padBox2.height + 10);
  await sleep(2500);
  const facesRestored = await faceCount();
  if (facesRestored < 1) {
    errors.push("barre de reprise : le solide devrait revenir "
      + `(faces ${facesRestored})`);
  }
  await step("barre de reprise redescendue");
  await page.screenshot({ path: path.join(SHOTS, "4c-reprise-bas.png") });

  // 4d. Clic droit sur le bossage → Modifier ouvre le panneau d'édition.
  const padRow = page.locator("#tree li.feat").first();
  await padRow.click({ button: "right" });
  await sleep(250);
  const modifyHidden = await page.$eval("#ctx-modify", (el) => el.hidden);
  if (modifyHidden) {
    errors.push("Modifier : entrée masquée sur le bossage");
  }
  await page.click("#ctx-modify");
  await sleep(1200);
  const panelTitle = await page.evaluate(() =>
    document.querySelector("#panel .ptitle")?.textContent ?? "");
  if (!/Bossage/i.test(panelTitle)) {
    errors.push("Modifier : panneau d'édition non ouvert ("
      + panelTitle + ")");
  }
  await page.screenshot({ path: path.join(SHOTS, "4d-modifier.png") });
  await page.click('#panel [title^="Annuler"], #panel [title^="Fermer"]',
    { timeout: 3000 }).catch(() => page.keyboard.press("Escape"));
  await sleep(250);
  await step("modifier au clic droit");

  // 4e. Esquisse sur une face du bossage : aucun maillage volumique visible.
  const volumeCount = () => page.evaluate(
    () => window.__freesolidDebug?.volumeVisibleCount ?? -1);
  const facesBeforeSketch = await volumeCount();
  if (!(facesBeforeSketch > 0)) {
    errors.push("esquisse sur face : aucun volume avant l'entrée ("
      + facesBeforeSketch + ")");
  }
  let facePicked = false;
  const tryPick = async (x, y) => {
    await page.mouse.click(x, y);
    await sleep(250);
    const pick = (await page.textContent("#pick")) || "";
    return pick.includes("Face");
  };
  facePicked = await tryPick(cx, cy);
  if (!facePicked) {
    for (const [dx, dy] of [[0, -40], [40, 0], [-40, 20], [0, 50], [20, -20]]) {
      facePicked = await tryPick(cx + dx, cy + dy);
      if (facePicked) break;
    }
  }
  if (!facePicked) {
    errors.push("esquisse sur face : aucune face du bossage sélectionnée");
  }
  await page.click("#btn-sketch");
  await sleep(2000);
  const hiddenCount = await volumeCount();
  if (hiddenCount !== 0) {
    errors.push("esquisse : volumes encore visibles (" + hiddenCount + ")");
  }
  const sketchTab = await page.evaluate(() =>
    document.getElementById("sketchbar")?.classList.contains("active"));
  if (!sketchTab) {
    errors.push("esquisse sur face : le ruban Esquisse n'est pas actif");
  }
  await step("esquisse sans volume");
  await page.screenshot({ path: path.join(SHOTS, "4e-esquisse-sans-volume.png") });
  await page.click("#sk-cancel");
  await sleep(1800);
  const shownCount = await volumeCount();
  if (!(shownCount > 0)) {
    errors.push("sortie esquisse : volumes toujours masqués ("
      + shownCount + ")");
  }
  await step("volumes rétablis");

  // 4f. P024 — esquisse libre décalée, cliquable dans le viewport.
  await page.locator("#tree li.plane").first().click();
  await sleep(300);
  await page.click("#btn-sketch");
  await sleep(1800);
  await step("esquisse libre ouverte");
  await page.click('[data-tool="rect"]');
  const freeRect = { x1: cx + 160, y1: cy - 40, x2: cx + 240, y2: cy + 20 };
  await page.mouse.click(freeRect.x1, freeRect.y1);
  await sleep(400);
  await page.mouse.click(freeRect.x2, freeRect.y2);
  await sleep(800);
  await page.click("#sk-finish");
  try {
    await page.waitForFunction(
      () => (window.__freesolidDebug?.sketchLineCount ?? 0) >= 1,
      null,
      { timeout: 10000 },
    );
  } catch {
    errors.push("esquisse viewport : aucune ligne d'esquisse après Terminer");
  }
  await sleep(400);
  const skPt = await page.evaluate(
    () => window.__freesolidDebug?.sketchScreenPoint ?? null);
  const freeSketchBar = await page.evaluate((label) => {
    const nodes = [...document.querySelectorAll("#tree li")];
    const sketch = nodes.findIndex((el) => {
      if (!el.classList.contains("feat")) return false;
      const text = el.textContent || "";
      if (label) return text.includes(label);
      return text.includes("Esquisse");
    });
    const bar = nodes.findIndex((el) => el.classList.contains("rollback"));
    const rolled = sketch >= 0 && nodes[sketch].classList.contains("rolled-back");
    return { sketch, bar, rolled };
  }, skPt?.label ?? null);
  if (!(freeSketchBar.sketch >= 0 && freeSketchBar.bar > freeSketchBar.sketch)) {
    errors.push("P029 : l'esquisse libre devrait être au-dessus de la "
      + "barre (esquisse=" + freeSketchBar.sketch
      + " barre=" + freeSketchBar.bar + ")");
  }
  if (freeSketchBar.rolled) {
    errors.push("P029 : l'esquisse libre ne doit pas être rolled-back");
  }
  if (!skPt) {
    errors.push("esquisse viewport : pas de point cliquable sur l'esquisse");
  } else {
    await page.mouse.move(skPt.x, skPt.y);
    await sleep(200);
    await page.mouse.click(skPt.x, skPt.y);
    await sleep(1500);
    const infoTitle = await page.evaluate(() =>
      document.querySelector("#panel .ptitle")?.textContent ?? "");
    if (infoTitle !== skPt.label) {
      errors.push("esquisse viewport : panneau infos titre « "
        + infoTitle + " » (attendu « " + skPt.label + " »)");
    }
    const treeSel = await page.$$eval("#tree li.sel",
      (els) => els.map((el) => el.textContent));
    if (!treeSel.some((text) => text.includes(skPt.label))) {
      errors.push("esquisse viewport : pas de ligne .sel dans l'arbre ("
        + treeSel.join(", ") + ")");
    }
    await page.screenshot({
      path: path.join(SHOTS, "4f-esquisse-viewport.png"),
    });
    await page.keyboard.press("Escape");
    await sleep(400);
  }
  await step("esquisse cliquée dans le viewport");

  // N005 — esquisse sur une face du solide (un bossage disjoint
  // depuis l'esquisse libre 4f est refusé par PartDesign), puis
  // palette du graphe : poser le bossage et le supprimer.
  let n005Face = await tryPick(cx, cy);
  if (!n005Face) {
    for (const [dx, dy] of [[0, -40], [40, 0], [-40, 20], [0, 50], [20, -20]]) {
      n005Face = await tryPick(cx + dx, cy + dy);
      if (n005Face) break;
    }
  }
  let n005SketchName = null;
  if (!n005Face) {
    errors.push("N005 : aucune face pour l'esquisse du bossage");
  } else {
    await page.click("#btn-sketch");
    await sleep(1800);
    await page.click('[data-tool="rect"]');
    await page.mouse.click(cx - 22, cy - 22);
    await sleep(300);
    await page.mouse.click(cx + 22, cy + 22);
    await sleep(600);
    await page.click("#sk-finish");
    await sleep(1800);
    const profile = await page.evaluate(async () => {
      const r = await fetch("/api", { method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ op: "get_tree", params: {} }) });
      const j = await r.json();
      const free = (j.ok ? (j.result.features ?? []) : []).filter((f) =>
        f.type === "Sketcher::SketchObject" && !f.rolled_back);
      return free.length
        ? { name: free[free.length - 1].name,
            label: free[free.length - 1].label }
        : null;
    });
    n005SketchName = profile?.name || null;
    if (!n005SketchName) {
      errors.push("N005 : esquisse sur face absente de l'arbre");
    }
  }
  const facesBeforeN005 = await faceCount();
  await page.click("#btn-graph");
  await page.waitForSelector("#graph-view.open .graph-node", { timeout: 8000 });
  const n005Before = await page.evaluate(() => {
    const nodes = [...document.querySelectorAll("#graph-view .graph-node")];
    const pads = nodes.filter((n) => /Pad/i.test(n.getAttribute("data-name") || "")
      || /Bossage/i.test(n.textContent || ""));
    return {
      padCount: pads.length,
      padNames: pads.map((n) => n.getAttribute("data-name") || ""),
    };
  });
  const n005Sketch = n005SketchName
    ? page.locator("#graph-view .graph-node[data-name='" + n005SketchName + "']")
    : page.locator("#graph-view .graph-node[data-role='sketch']").last();
  await n005Sketch.click();
  await sleep(500);
  await page.click("#btn-graph-add");
  await page.waitForSelector(
    "#graph-palette .graph-palette-item[data-button='btn-pad']",
    { timeout: 8000 },
  );
  const paletteState = await page.evaluate(() => {
    const items = [...document.querySelectorAll("#graph-palette .graph-palette-item")];
    const fillet = items.find((el) => el.dataset.button === "btn-fillet");
    return {
      count: items.length,
      filletDisabled: fillet?.classList.contains("disabled") === true,
      filletReason: fillet?.querySelector(".graph-palette-reason")?.textContent
        || "",
    };
  });
  if (paletteState.count !== 23) {
    errors.push("N005 : palette " + paletteState.count + " items (attendu 23)");
  }
  if (!paletteState.filletDisabled) {
    errors.push("N005 : Congé devrait être grisé sans face sélectionnée");
  }
  if (!paletteState.filletReason) {
    errors.push("N005 : Congé grisé sans raison visible");
  }
  await page.click("#graph-palette .graph-palette-item[data-button='btn-pad']");
  await sleep(2500);
  const n005Panel = await page.evaluate(() =>
    document.querySelector("#panel .ptitle")?.textContent ?? "");
  if (!/Bossage/i.test(n005Panel)) {
    errors.push("N005 : panneau bossage non ouvert (" + n005Panel + ")");
  } else {
    await page.click('#panel [title^="OK"]');
    await sleep(3000);
  }
  const n005AfterAdd = await page.evaluate((beforeNames) => {
    const nodes = [...document.querySelectorAll("#graph-view .graph-node")];
    const pads = nodes.filter((n) => /Pad/i.test(n.getAttribute("data-name") || "")
      || /Bossage/i.test(n.textContent || ""));
    const added = pads.find((n) =>
      !beforeNames.includes(n.getAttribute("data-name") || ""));
    const edges = [...document.querySelectorAll("#graph-view .graph-edge")]
      .map((e) => ({
        from: e.getAttribute("data-from") || "",
        to: e.getAttribute("data-to") || "",
        kind: e.getAttribute("data-kind") || "",
      }));
    return {
      padCount: pads.length,
      newName: added?.getAttribute("data-name") || "",
      edges,
    };
  }, n005Before.padNames);
  const facesAfterN005Add = await faceCount();
  if (n005AfterAdd.padCount !== n005Before.padCount + 1) {
    errors.push("N005 : attendu un nœud bossage de plus ("
      + n005Before.padCount + " → " + n005AfterAdd.padCount + ")");
  }
  if (n005SketchName && n005AfterAdd.newName) {
    const linked = n005AfterAdd.edges.some((e) => e.kind === "geom"
      && e.from === n005SketchName && e.to === n005AfterAdd.newName);
    if (!linked) {
      errors.push("N005 : pas d'arête esquisse→bossage ("
        + JSON.stringify(n005AfterAdd.edges) + ")");
    }
  }
  if (!(facesAfterN005Add > facesBeforeN005)) {
    errors.push("N005 : le volume devrait augmenter ("
      + facesBeforeN005 + " → " + facesAfterN005Add + ")");
  }
  await page.screenshot({ path: path.join(SHOTS, "4g-graphe-bossage.png") });
  if (n005AfterAdd.newName) {
    await page.locator(
      "#graph-view .graph-node[data-name='" + n005AfterAdd.newName + "']",
    ).click({ force: true });
    await sleep(200);
    page.once("dialog", (dialog) => dialog.accept());
    await page.keyboard.press("Delete");
    await sleep(3000);
  } else {
    errors.push("N005 : impossible de supprimer, nœud bossage introuvable");
  }
  const n005AfterDel = await page.evaluate(() => {
    const nodes = [...document.querySelectorAll("#graph-view .graph-node")];
    const pads = nodes.filter((n) => /Pad/i.test(n.getAttribute("data-name") || "")
      || /Bossage/i.test(n.textContent || ""));
    return { padCount: pads.length };
  });
  const facesAfterN005Del = await faceCount();
  if (n005AfterDel.padCount !== n005Before.padCount) {
    errors.push("N005 : après suppression, " + n005AfterDel.padCount
      + " bossage(s) (attendu " + n005Before.padCount + ")");
  }
  if (facesAfterN005Del !== facesBeforeN005) {
    errors.push("N005 : le volume devrait revenir à l'état d'avant ("
      + facesBeforeN005 + " → " + facesAfterN005Del + ")");
  }
  await page.keyboard.press("Escape");
  await sleep(300);
  const n005GraphClosed = await page.evaluate(() =>
    !document.getElementById("graph-view")?.classList.contains("open"));
  if (!n005GraphClosed) {
    await page.click("#btn-graph");
    await sleep(200);
  }
  await step("nœuds constructifs");

  // 5. Undo / redo — jetons anti-course + invalidation des sélections
  await page.keyboard.press("Control+z");
  await sleep(2500);
  await step("après Ctrl+Z");
  await page.keyboard.press("Control+y");
  await sleep(2500);
  await step("après Ctrl+Y");
  await page.screenshot({ path: path.join(SHOTS, "5-final.png") });

  // 6. P027 — esquisse libre → Surface extrudée dans l'historique.
  await page.locator("#tree li.plane").first().click();
  await sleep(300);
  await page.click("#btn-sketch");
  await sleep(1800);
  await page.click('[data-tool="line"]');
  await page.mouse.click(cx - 200, cy - 30);
  await sleep(300);
  await page.mouse.click(cx - 120, cy - 30);
  await sleep(400);
  await page.click("#sk-finish");
  await sleep(1500);
  await page.click('[data-tab="surfaces"]');
  await sleep(300);
  await page.click("#btn-surf-extrude");
  await sleep(1500);
  await page.click('#panel [title^="OK"]');
  await sleep(3000);
  const folderAfterSurf = await page.locator("#tree li.folder")
    .allTextContents();
  const folderAfterSurfJoined = folderAfterSurf.join(" | ");
  if (!folderAfterSurf.some((t) => t.includes("Corps surfaciques (1)"))) {
    errors.push("P027 : attendu « Corps surfaciques (1) » après extrusion"
      + " (vu : " + folderAfterSurfJoined + ")");
  }
  const folderSurfRows = await page.locator("#tree li.surface.in-folder")
    .allTextContents();
  if (!folderSurfRows.some((t) => t.includes("Surface extrudée"))) {
    errors.push("P027 : dossier Corps surfaciques devrait être déplié "
      + "avec la surface (vu : " + folderSurfRows.join(" | ") + ")");
  }
  const historySurf = await page.locator("#tree li.surface:not(.in-folder)")
    .allTextContents();
  if (!historySurf.some((t) => t.includes("Surface extrudée"))) {
    errors.push("P027 : « Surface extrudée » absente de l'historique "
      + "(vu : " + historySurf.join(" | ") + ")");
  }
  const barOrder = await page.evaluate(() => {
    const nodes = [...document.querySelectorAll("#tree li")];
    const hist = nodes.findIndex((el) =>
      el.classList.contains("surface") && !el.classList.contains("in-folder")
      && el.textContent.includes("Surface extrudée"));
    const bar = nodes.findIndex((el) => el.classList.contains("rollback"));
    const rolled = hist >= 0 && nodes[hist].classList.contains("rolled-back");
    return { hist, bar, rolled };
  });
  if (!(barOrder.hist >= 0 && barOrder.bar > barOrder.hist)) {
    errors.push("P028 : « Surface extrudée » devrait être au-dessus de la "
      + "barre (hist=" + barOrder.hist + " barre=" + barOrder.bar + ")");
  }
  if (barOrder.rolled) {
    errors.push("P028 : la surface d'historique ne doit pas être rolled-back");
  }
  await page.waitForFunction(
    () => (window.__freesolidDebug?.surfaceMeshCount ?? 0) >= 1,
    { timeout: 8000 }).catch(() => {});
  await page.click("#view-fit");
  await sleep(400);
  const surfPt = await page.evaluate(
    () => window.__freesolidDebug?.surfaceScreenPoint ?? null);
  if (!surfPt) {
    errors.push("P028 : pas de point cliquable sur la surface");
  } else {
    await page.mouse.move(surfPt.x, surfPt.y);
    await sleep(200);
    await page.mouse.click(surfPt.x, surfPt.y);
    await sleep(500);
    const pickText = await page.evaluate(
      () => document.getElementById("pick")?.textContent ?? "");
    if (!pickText.includes(surfPt.label)) {
      errors.push("P028 : #pick « " + pickText + " » (attendu le label « "
        + surfPt.label + " »)");
    }
    const treeSel = await page.$$eval("#tree li.sel",
      (els) => els.map((el) => el.textContent));
    if (!treeSel.some((text) => text.includes(surfPt.label))) {
      errors.push("P028 : pas de ligne .sel dans l'arbre ("
        + treeSel.join(", ") + ")");
    }
  }
  await step("surface cliquée dans le viewport");
  await page.screenshot({ path: path.join(SHOTS, "6-surface-historique.png") });

  // P030 — glisser la barre au-dessus des surfaces et esquisses libres.
  const rollTargets = await page.evaluate(() => {
    const nodes = [...document.querySelectorAll("#tree li[data-hist]")];
    const sketch = nodes.find((el) => el.classList.contains("feat")
      && (el.textContent || "").includes("Esquisse"));
    const surface = nodes.find((el) => el.classList.contains("surface")
      && (el.textContent || "").includes("Surface extrudée"));
    return {
      sketchTop: sketch ? sketch.getBoundingClientRect().top : null,
      surfaceTop: surface ? surface.getBoundingClientRect().top : null,
    };
  });
  const aboveRollY = Math.min(
    rollTargets.sketchTop ?? Infinity,
    rollTargets.surfaceTop ?? Infinity,
  );
  if (!Number.isFinite(aboveRollY)) {
    errors.push("P030 : pas de ligne d'esquisse/surface data-hist");
  } else {
    await dragRollback("#tree li.rollback", aboveRollY - 8);
    await sleep(2500);
  }
  const afterRoll = await page.evaluate(() => {
    const rolled = [...document.querySelectorAll("#tree li.rolled-back")]
      .filter((el) => el.hasAttribute("data-hist"))
      .map((el) => el.textContent || "");
    return {
      rolled,
      surfaceMeshCount: window.__freesolidDebug?.surfaceMeshCount ?? -1,
      sketchLineCount: window.__freesolidDebug?.sketchLineCount ?? -1,
    };
  });
  if (!afterRoll.rolled.some((text) => text.includes("Surface"))) {
    errors.push("P030 : la surface devrait être .rolled-back (vu : "
      + afterRoll.rolled.join(" | ") + ")");
  }
  if (!afterRoll.rolled.some((text) => text.includes("Esquisse"))) {
    errors.push("P030 : l'esquisse libre devrait être .rolled-back (vu : "
      + afterRoll.rolled.join(" | ") + ")");
  }
  if (afterRoll.surfaceMeshCount !== 0) {
    errors.push("P030 : surfaceMeshCount=" + afterRoll.surfaceMeshCount
      + " (attendu 0 sous la barre)");
  }
  if (afterRoll.sketchLineCount !== 0) {
    errors.push("P030 : sketchLineCount=" + afterRoll.sketchLineCount
      + " (attendu 0 sous la barre)");
  }
  await step("P030 barre au-dessus surfaces/esquisses");
  await page.screenshot({ path: path.join(SHOTS, "6b-p030-reprise-haut.png") });

  const lastHistBottom = await page.evaluate(() => {
    const nodes = [...document.querySelectorAll("#tree li[data-hist]")];
    const last = nodes[nodes.length - 1];
    return last ? last.getBoundingClientRect().bottom : null;
  });
  if (lastHistBottom != null) {
    await dragRollback("#tree li.rollback", lastHistBottom + 10);
    await sleep(2500);
  }
  const restored = await page.evaluate(() => {
    const rolled = [...document.querySelectorAll("#tree li.rolled-back")]
      .filter((el) => el.hasAttribute("data-hist"));
    return {
      rolled: rolled.length,
      surfaceMeshCount: window.__freesolidDebug?.surfaceMeshCount ?? -1,
      sketchLineCount: window.__freesolidDebug?.sketchLineCount ?? -1,
    };
  });
  if (restored.rolled !== 0) {
    errors.push("P030 : encore " + restored.rolled
      + " ligne(s) .rolled-back après descente de la barre");
  }
  if (!(restored.surfaceMeshCount >= 1)) {
    errors.push("P030 : surfaceMeshCount restauré="
      + restored.surfaceMeshCount);
  }
  if (!(restored.sketchLineCount >= 1)) {
    errors.push("P030 : sketchLineCount restauré="
      + restored.sketchLineCount);
  }
  await step("P030 barre redescendue");
  await page.screenshot({ path: path.join(SHOTS, "6c-p030-reprise-bas.png") });

  // 7. P031 — Autotest lisible : statut + vérifications vertes.
  await page.click("#btn-selftest");
  try {
    await page.waitForFunction(
      () => {
        const text = (document.querySelector("#status")?.textContent || "")
          .trim();
        return text.startsWith("Autotest") && !text.includes("en cours");
      },
      null,
      { timeout: 240000 },
    );
  } catch {
    errors.push("Autotest : statut jamais prêt après 240 s (« "
      + await status() + " »)");
  }
  const selftestStatus = await status();
  if (!selftestStatus.startsWith("Autotest")) {
    errors.push("Autotest : statut = « " + selftestStatus + " »");
  } else if (!selftestStatus.includes("vérifications — OK")) {
    errors.push("Autotest : attendu « vérifications — OK », vu « "
      + selftestStatus + " »");
  }
  // La pièce vitrine doit rester à l'écran : un arbre riche, pas la
  // plaque m1.5 (P031, demande visuelle).
  const vitrineRows = await page.evaluate(() =>
    document.querySelectorAll("#tree li[data-hist]").length);
  if (vitrineRows < 7) {
    errors.push("Autotest : pièce vitrine attendue dans l'arbre "
      + `(≥ 7 lignes d'historique, vu ${vitrineRows})`);
  }
  await step("autotest");
  await page.screenshot({ path: path.join(SHOTS, "7-autotest.png") });

  // 8. P032 — gravure rééditable, artefacts internes cachés.
  const treeTexts = await page.evaluate(() =>
    [...document.querySelectorAll("#tree li")].map((el) => el.textContent || ""));
  if (treeTexts.some((t) => t.includes("Forme du texte"))) {
    errors.push("P032 : « Forme du texte » ne doit plus apparaître dans l'arbre");
  }
  if (treeTexts.some((t) => t.includes("Corps texte"))) {
    errors.push("P032 : « Corps texte » ne doit plus apparaître dans l'arbre");
  }
  const gravRow = await page.evaluateHandle(() =>
    [...document.querySelectorAll("#tree li[data-hist]")]
      .find((el) => (el.textContent || "").includes("Gravure")) || null);
  if (!gravRow.asElement()) {
    errors.push("P032 : ligne Gravure introuvable dans l'arbre");
  } else {
    await gravRow.asElement().dblclick();
    await sleep(2000);
    const filled = await page.evaluate(() => {
      const input = [...document.querySelectorAll("#panel input")]
        .find((el) => el.value === "FS");
      if (!input) return false;
      input.value = "OK";
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    });
    if (!filled) {
      errors.push("P032 : champ Texte (valeur FS) introuvable dans le panneau");
      await page.keyboard.press("Escape");
    } else {
      await page.click('#panel [title^="OK"]');
      await sleep(3500);
      const st = await status();
      if (/erreur|échec|refus/i.test(st)) {
        errors.push("P032 : statut après édition de la gravure : « "
          + st + " »");
      }
      const renamed = await page.evaluate(() =>
        [...document.querySelectorAll("#tree li[data-hist]")]
          .some((el) => (el.textContent || "").includes("Gravure « OK »")));
      if (!renamed) {
        errors.push("P032 : la ligne Gravure devrait afficher « OK » "
          + "après édition");
      }
    }
  }
  await step("gravure rééditée");
  await page.screenshot({ path: path.join(SHOTS, "8-gravure-editee.png") });

  // N004b — éditeur de la fonction graphe : créer, poser, câbler, appliquer,
  // erreur d'appariement désignée, pièce intacte.
  const isVolume = (v) => typeof v === "number" && Number.isFinite(v);
  const volumeOf = async () => page.evaluate(async () => {
    const r = await fetch("/api", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ op: "mass_properties", params: {} }) });
    const j = await r.json();
    return j.ok ? j.result.volume_mm3 : ("REFUS: " + (j.error ?? "?"));
  });
  const volBeforeGraph = await volumeOf();
  await page.click('[data-tab="features"]');
  await sleep(200);
  await page.click("#btn-graph-feature");
  await page.waitForFunction(
    () => document.querySelector("#panel .ptitle")?.textContent
      === "Fonction graphe",
    null,
    { timeout: 8000 },
  );
  await page.locator("#panel select").first().selectOption("fuse");
  await page.click('#panel [title^="OK"]');
  await page.waitForFunction(
    () => window.__freesolidDebug?.graphFeatureActive === true,
    null,
    { timeout: 15000 },
  );
  const volAfterCreate = await volumeOf();
  if (!isVolume(volBeforeGraph) || !isVolume(volAfterCreate)
      || volAfterCreate <= volBeforeGraph + 50) {
    errors.push("N004b : le bossage graphe devrait augmenter le volume ("
      + volBeforeGraph + " → " + volAfterCreate + ")");
  }
  const hint = await page.textContent("#graph-fn-hint");
  if (!/figée/i.test(hint || "") || !/booléen/i.test(hint || "")) {
    errors.push("N004b : le mode doit dire que la géométrie est figée "
      + "et que le résultat est une forme (" + hint + ")");
  }

  const paletteBtn = page.locator("#graph-fn-palette");
  await paletteBtn.click();
  await page.waitForSelector("#graph-palette [data-type='serie']",
    { timeout: 5000 });
  const nodePaletteState = await page.evaluate(() => {
    const cats = [...document.querySelectorAll("#graph-palette [data-category]")]
      .map((el) => el.getAttribute("data-category"));
    const sphere = document.querySelector(
      "#graph-palette [data-type='sphere']");
    return {
      cats,
      sphereDisabled: sphere?.classList.contains("disabled") ?? false,
      sphereReason: sphere?.querySelector(".graph-palette-reason")?.textContent
        || sphere?.getAttribute("title") || "",
    };
  });
  if (!nodePaletteState.cats.includes("list")
      || !nodePaletteState.cats.includes("number")
      || !nodePaletteState.cats.includes("generators")) {
    errors.push("N006 : catégories absentes de la palette ("
      + JSON.stringify(nodePaletteState.cats) + ")");
  }
  if (!nodePaletteState.sphereDisabled
      || !/Part|pas encore/i.test(nodePaletteState.sphereReason)) {
    errors.push("N006 : Sphère devrait être grisée avec sa raison ("
      + JSON.stringify(nodePaletteState) + ")");
  }
  await page.click("#graph-palette [data-type='serie']");
  await sleep(300);
  await paletteBtn.click();
  await page.waitForSelector("#graph-palette [data-type='cylindre']",
    { timeout: 5000 });
  await page.click("#graph-palette [data-type='cylindre']");
  await sleep(400);

  const placed = await page.evaluate(() => {
    const ids = window.__freesolidDebug?.graphFeatureNodeIds ?? [];
    const nodes = [...document.querySelectorAll("#graph-view .graph-node")];
    return {
      ids,
      types: nodes.map((n) => n.getAttribute("data-type") || ""),
    };
  });
  if (!placed.types.includes("serie") || !placed.types.includes("cylindre")) {
    errors.push("N004b : série et cylindre absents après pose ("
      + JSON.stringify(placed) + ")");
  }
  const serieId = await page.evaluate(() => {
    const node = [...document.querySelectorAll(
      "#graph-view .graph-node[data-type='serie']")].pop();
    return node?.getAttribute("data-name") || "";
  });
  const cylId = await page.evaluate(() => {
    const node = [...document.querySelectorAll(
      "#graph-view .graph-node[data-type='cylindre']")].pop();
    return node?.getAttribute("data-name") || "";
  });
  if (serieId && cylId) {
    await page.evaluate(({ serieId: sid, cylId: cid }) => {
      window.__freesolidDebug.setGraphLiteral(sid, "depart", 8);
      window.__freesolidDebug.setGraphLiteral(sid, "pas", 4);
      window.__freesolidDebug.setGraphLiteral(sid, "nombre", 2);
    }, { serieId, cylId });
    const outPort = page.locator(
      `#graph-view .graph-port.out[data-node="${serieId}"]`);
    const inPort = page.locator(
      `#graph-view .graph-port.in[data-node="${cylId}"][data-key="rayon"]`);
    const outBox = await outPort.boundingBox();
    const inBox = await inPort.boundingBox();
    if (!outBox || !inBox) {
      errors.push("N004b : ports série/cylindre introuvables pour le fil");
    } else {
      await page.mouse.move(outBox.x + outBox.width / 2,
        outBox.y + outBox.height / 2);
      await page.mouse.down();
      const steps = 10;
      for (let i = 1; i <= steps; i++) {
        await page.mouse.move(
          outBox.x + outBox.width / 2
            + (inBox.x + inBox.width / 2 - outBox.x - outBox.width / 2)
              * (i / steps),
          outBox.y + outBox.height / 2
            + (inBox.y + inBox.height / 2 - outBox.y - outBox.height / 2)
              * (i / steps));
        await sleep(20);
      }
      await page.mouse.up();
      await sleep(400);
    }
    const wiredRayon = await page.evaluate(({ from, to }) => {
      const edges = window.__freesolidDebug.graphFeatureEdges() || [];
      if (edges.some((e) => e.from === from && e.to === to
          && e.input === "rayon")) {
        return { ok: true, via: "drag" };
      }
      return window.__freesolidDebug.wireGraph(from, to, "rayon");
    }, { from: serieId, to: cylId });
    if (!wiredRayon.ok) {
      errors.push("N004b : fil série→rayon refusé ("
        + JSON.stringify(wiredRayon) + ")");
    }
    await page.evaluate((cid) => {
      const node = [...document.querySelectorAll("#graph-view .graph-node")]
        .find((el) => el.getAttribute("data-name") === cid);
      node?.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
    }, cylId);
    await page.click("#graph-fn-apply");
    await sleep(3500);
  } else {
    errors.push("N004b : identifiants série/cylindre manquants");
  }
  const volAfterApply = await volumeOf();
  if (!isVolume(volAfterApply) || Math.abs(volAfterApply - volAfterCreate) < 1) {
    errors.push("N004b : appliquer le graphe devrait changer le volume ("
      + volAfterCreate + " → " + volAfterApply + ")");
  }
  await page.screenshot({ path: path.join(SHOTS, "9-fonction-graphe.png") });

  const serieIdsBefore = await page.evaluate(() =>
    [...document.querySelectorAll("#graph-view .graph-node[data-type='serie']")]
      .map((n) => n.getAttribute("data-name")));
  await paletteBtn.click();
  await page.waitForSelector("#graph-palette [data-type='serie']",
    { timeout: 5000 });
  await page.click("#graph-palette [data-type='serie']");
  await page.waitForFunction((before) => {
    const ids = [...document.querySelectorAll(
      "#graph-view .graph-node[data-type='serie']")]
      .map((n) => n.getAttribute("data-name"));
    return ids.some((id) => !before.includes(id));
  }, serieIdsBefore, { timeout: 5000 }).catch(() => {});
  const serie2 = await page.evaluate((before) => {
    const ids = [...document.querySelectorAll(
      "#graph-view .graph-node[data-type='serie']")]
      .map((n) => n.getAttribute("data-name"));
    return ids.find((id) => !before.includes(id)) || "";
  }, serieIdsBefore);
  if (serie2 && cylId) {
    await page.evaluate((id) => {
      window.__freesolidDebug.setGraphLiteral(id, "depart", 1);
      window.__freesolidDebug.setGraphLiteral(id, "pas", 1);
      window.__freesolidDebug.setGraphLiteral(id, "nombre", 5);
    }, serie2);
    const outPort = page.locator(
      `#graph-view .graph-port.out[data-node="${serie2}"]`);
    const inPort = page.locator(
      `#graph-view .graph-port.in[data-node="${cylId}"][data-key="hauteur"]`);
    const outBox = await outPort.boundingBox();
    const inBox = await inPort.boundingBox();
    if (outBox && inBox) {
      await page.mouse.move(outBox.x + outBox.width / 2,
        outBox.y + outBox.height / 2);
      await page.mouse.down();
      const steps = 10;
      for (let i = 1; i <= steps; i++) {
        await page.mouse.move(
          outBox.x + outBox.width / 2
            + (inBox.x + inBox.width / 2 - outBox.x - outBox.width / 2)
              * (i / steps),
          outBox.y + outBox.height / 2
            + (inBox.y + inBox.height / 2 - outBox.y - outBox.height / 2)
              * (i / steps));
        await sleep(20);
      }
      await page.mouse.up();
      await sleep(300);
    }
    const wired = await page.evaluate(({ from, to, input }) => {
      const edges = window.__freesolidDebug.graphFeatureEdges() || [];
      if (edges.some((e) => e.from === from && e.to === to
          && e.input === input)) {
        return { ok: true, via: "drag" };
      }
      return window.__freesolidDebug.wireGraph(from, to, input);
    }, { from: serie2, to: cylId, input: "hauteur" });
    if (!wired.ok) {
      errors.push("N004b : fil série→hauteur refusé ("
        + JSON.stringify(wired) + ")");
    }
    const statusBeforeErr = await status();
    await page.click("#graph-fn-apply");
    await page.waitForFunction((before) => {
      const st = document.getElementById("status")?.textContent || "";
      return st !== before
        || !!document.querySelector("#graph-view .graph-node.error");
    }, statusBeforeErr, { timeout: 10000 }).catch(() => {});
    const errState = await page.evaluate(() => ({
      errorNode: window.__freesolidDebug?.graphFeatureErrorNode || null,
      marked: !!document.querySelector("#graph-view .graph-node.error"),
      status: (document.getElementById("status")?.textContent || ""),
      edges: window.__freesolidDebug?.graphFeatureEdges?.() || [],
      ids: window.__freesolidDebug?.graphFeatureNodeIds || [],
    }));
    if (!errState.marked && !/longueurs/i.test(errState.status)) {
      errors.push("N004b : l'erreur d'appariement devrait désigner un nœud ("
        + JSON.stringify(errState) + ")");
    }
    if (errState.marked && cylId
        && errState.errorNode && errState.errorNode !== cylId) {
      errors.push("N004b : nœud fautif attendu " + cylId + ", reçu "
        + errState.errorNode);
    }
    const volAfterError = await volumeOf();
    if (isVolume(volAfterApply) && isVolume(volAfterError)
        && Math.abs(volAfterError - volAfterApply) > 1e-3) {
      errors.push("N004b : la pièce a changé malgré le refus ("
        + volAfterApply + " → " + volAfterError + ")");
    }
    const modeStill = await page.evaluate(
      () => window.__freesolidDebug?.graphFeatureActive === true);
    if (!modeStill) {
      errors.push("N004b : le mode s'est fermé sur l'erreur");
    }
  } else {
    errors.push("N004b : deuxième série absente pour l'appariement");
  }
  await page.screenshot({ path: path.join(SHOTS, "9b-fonction-graphe-erreur.png") });
  page.once("dialog", (dialog) => dialog.accept());
  await page.click("#graph-fn-close");
  await page.waitForFunction(
    () => window.__freesolidDebug?.graphFeatureActive !== true,
    null,
    { timeout: 8000 },
  ).catch(() => {});
  await step("fonction graphe");

  console.log(errors.length
    ? "ERREURS:\n" + errors.join("\n")
    : "AUCUNE ERREUR console/page");
  await browser.close();
  process.exit(errors.length ? 1 : 0);
})();
