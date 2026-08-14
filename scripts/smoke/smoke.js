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

  await page.goto(URL_BASE + "/");
  await sleep(3000);
  await step("chargement");

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
