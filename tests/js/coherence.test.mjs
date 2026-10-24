// Cohérence d'une fonction entre les deux côtés : ce que déclare une entrée
// de FEATURES (app/features/…) face au catalogue du moteur (engine/ops/…),
// et ce qu'une op annulable doit avoir côté app (libellé d'historique,
// traduit). Le catalogue est pur Python : on le lit avec python3.
// Une fonction incomplète échoue ici, avec son nom dans le message.

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { FEATURES } from "../../app/features.js";
import { STEP_LABELS, STEP_PREFIXES, undoStepLabel } from "../../app/history.js";
import { DICTIONARIES } from "../../app/i18n.js";
import LAYOUT from "../../app/ribbon.json" with { type: "json" };

const ROOT = fileURLToPath(new URL("../../", import.meta.url));
const FAMILIES = new URL("../../app/features/", import.meta.url);

const DUMP = `
import json
from engine import ops
print(json.dumps([{"name": o.name, "undo": o.undo, "preview": o.preview}
                  for o in ops.CORE_OPS]))
`;
const run = spawnSync("python3", ["-c", DUMP], { cwd: ROOT, encoding: "utf8" });
if (run.status !== 0) {
  throw new Error(`lecture du catalogue engine/ops/ impossible : ${run.stderr || run.error}`);
}
const CATALOGUE = new Map(JSON.parse(run.stdout).map((op) => [op.name, op]));
const EN = DICTIONARIES.en;
const opsOf = (entry) => [entry.op].flat().filter(Boolean);

function ribbonIds(node, out = new Set()) {
  if (Array.isArray(node)) node.forEach((n) => ribbonIds(n, out));
  else if (node && typeof node === "object") {
    if (typeof node.id === "string") out.add(node.id);
    Object.values(node).forEach((n) => ribbonIds(n, out));
  }
  return out;
}

describe("entrées de FEATURES face au catalogue du moteur", () => {
  it("chaque entrée déclare son op (champ op)", () => {
    const sans = FEATURES.filter((e) => !opsOf(e).length).map((e) => e.button);
    assert.deepEqual(sans, []);
  });

  it("chaque op déclarée existe dans engine/ops/", () => {
    const inconnues = FEATURES.flatMap((e) => opsOf(e)
      .filter((op) => !CATALOGUE.has(op)).map((op) => `${e.button} → ${op}`));
    assert.deepEqual(inconnues, []);
  });

  it("chaque op d'un panneau est un pas d'annulation (undo=True)", () => {
    const hors = FEATURES.flatMap((e) => opsOf(e)
      .filter((op) => CATALOGUE.get(op) && !CATALOGUE.get(op).undo)
      .map((op) => `${e.button} → ${op}`));
    assert.deepEqual(hors, []);
  });

  it("un panneau avec aperçu pointe vers une op prévisualisable (preview=True)", () => {
    const hors = FEATURES.filter((e) => e.preview !== false).flatMap((e) => opsOf(e)
      .filter((op) => CATALOGUE.get(op) && !CATALOGUE.get(op).preview)
      .map((op) => `${e.button} → ${op}`));
    assert.deepEqual(hors, []);
  });

  it("chaque entrée a son bouton dans le ruban (ribbon.json)", () => {
    const ids = ribbonIds(LAYOUT);
    const sans = FEATURES.filter((e) => !ids.has(e.button)).map((e) => e.button);
    assert.deepEqual(sans, []);
  });

  it("aucune op du catalogue n'est appelée par app/features/ sans être déclarée", () => {
    // Une op écrite en toutes lettres dans un fichier de famille (le plus
    // souvent dans build) doit figurer dans le champ op d'une entrée.
    const declared = new Set(FEATURES.flatMap(opsOf));
    const oubliees = [];
    for (const file of readdirSync(FAMILIES)) {
      const src = readFileSync(new URL(file, FAMILIES), "utf8");
      for (const [, name] of src.matchAll(/"([a-z][a-z0-9_]*)"/g)) {
        if (CATALOGUE.has(name) && !declared.has(name)) oubliees.push(`${file} : ${name}`);
      }
    }
    assert.deepEqual([...new Set(oubliees)], []);
  });
});

describe("ops annulables : libellé d'historique", () => {
  const undoable = [...CATALOGUE.values()].filter((op) => op.undo).map((op) => op.name);

  it("chacune a sa ligne dans STEP_LABELS ou un préfixe de STEP_PREFIXES", () => {
    // Le repli « Fonction » / « Modification » de undoStepLabel est pour
    // les ops des plugins ; une op du noyau ne doit pas en dépendre.
    const sans = undoable.filter((name) => !Object.hasOwn(STEP_LABELS, name)
      && !STEP_PREFIXES.some(([prefix]) => name.startsWith(prefix)));
    assert.deepEqual(sans, []);
  });

  it("chaque libellé est traduit (app/lang/en.json)", () => {
    const sans = undoable.map((name) => [name, undoStepLabel(name)])
      .filter(([, label]) => !Object.hasOwn(EN, label))
      .map(([name, label]) => `${name} → ${label}`);
    assert.deepEqual(sans, []);
  });

  it("STEP_LABELS ne nomme que des ops du catalogue", () => {
    const orphelines = Object.keys(STEP_LABELS).filter((name) => !CATALOGUE.has(name));
    assert.deepEqual(orphelines, []);
  });
});
