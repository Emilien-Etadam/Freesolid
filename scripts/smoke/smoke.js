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
      await page.click('#panel [title^="Annuler"], #panel [title^="Fermer"]');
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

  await page.click("#btn-settings");
  await sleep(200);
  await page.screenshot({ path: path.join(SHOTS, "0b-menu-reglages.png") });
  await page.click('[data-ribbon-labels="icons-only"]');
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
  await page.click('[data-ribbon-labels="icons-and-text"]');
  await sleep(200);
  const iconsAndText = await page.evaluate(() =>
    !document.body.classList.contains("ribbon-icons-only")
    && localStorage.getItem("freesolid.ribbonLabels") === "icons-and-text");
  if (!iconsAndText) errors.push("Icônes et texte : classe encore posée");
  await step("réglages ruban");

  // 1. Esquisse — choix du plan dans le viewport
  await page.click("#btn-sketch");
  await sleep(1200);
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
  const sketchState = () => page.evaluate(async () => {
    const r = await fetch("/api", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ op: "sketch_state",
                             params: { sketch: "Sketch" } }) });
    const j = await r.json();
    return j.ok ? j.result : null;
  });
  const flatten = (state) => (state?.entities ?? [])
    .flatMap((e) => [...(e.p1 ?? []), ...(e.p2 ?? []), ...(e.c ?? [])]);
  const beforeEdge = flatten(await sketchState());
  await page.mouse.move(cx, cy - 70);
  await page.mouse.down();
  for (let i = 1; i <= 10; i++) {
    await page.mouse.move(cx + i * 3, cy - 70 + i * 4);
    await sleep(25);
  }
  await page.mouse.up();
  await sleep(1200);
  const afterEdge = flatten(await sketchState());
  const moved = beforeEdge.length === afterEdge.length
    && beforeEdge.some((v, i) => Math.abs(v - afterEdge[i]) > 1);
  if (!moved) {
    errors.push("drag d'arête : la géométrie n'a pas bougé "
      + "(le pas a raté l'arête ou le drag est cassé)");
  }
  await step("drag arête");
  await page.screenshot({ path: path.join(SHOTS, "2b-drag-edge.png") });

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

  // 5. Undo / redo — jetons anti-course + invalidation des sélections
  await page.keyboard.press("Control+z");
  await sleep(2500);
  await step("après Ctrl+Z");
  await page.keyboard.press("Control+y");
  await sleep(2500);
  await step("après Ctrl+Y");
  await page.screenshot({ path: path.join(SHOTS, "5-final.png") });

  console.log(errors.length
    ? "ERREURS:\n" + errors.join("\n")
    : "AUCUNE ERREUR console/page");
  await browser.close();
  process.exit(errors.length ? 1 : 0);
})();
