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

  // 0. Ids des 22 panneaux (registry FEATURES) + bascule libellés du ruban.
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
  if (FEATURE_PANELS.length !== 22) {
    errors.push("harnais : 22 panneaux attendus, "
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
    errors.push("trop peu de panneaux ouverts : " + opened + "/22");
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

  // 1. Esquisse — choix du plan dans le viewport. Le clic peut être
  // avalé juste après le balayage des panneaux (menu/panneau en cours
  // de fermeture) : réessayer tant que le statut ne change pas.
  for (let i = 0; i < 4; i++) {
    await page.click("#btn-sketch");
    await sleep(1200);
    if ((await status()).includes("Esquisse")) break;
  }
  await step("choix plan");
  const canvas = await page.locator("#viewport canvas").first().boundingBox();
  const cx = canvas.x + canvas.width / 2, cy = canvas.y + canvas.height / 2;
  await page.mouse.click(cx, cy - 40);
  await sleep(1800);
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

  console.log(errors.length
    ? "ERREURS:\n" + errors.join("\n")
    : "AUCUNE ERREUR console/page");
  await browser.close();
  process.exit(errors.length ? 1 : 0);
})();
