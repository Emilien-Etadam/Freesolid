# FreeSolid

A familiar mechanical-CAD interface for FreeCAD — on two tracks.

**Track 1 — the Qt addon** (this repository's root): installable today,
reshapes stock FreeCAD toward SolidWorks habits. Documented below.

**Track 2 — the app** (`engine/` + `app/`): a new web interface (Three.js,
Plasticity-style look, SolidWorks-style FeatureManager) over a **headless
FreeCAD engine** — documents, PartDesign, sketch solver, toponaming fix and
STEP are inherited, only presentation and interaction are rebuilt. See
[`docs/architecture-app.md`](docs/architecture-app.md) for the design and
[`docs/landscape.md`](docs/landscape.md) for why nobody else occupies this
lane. Run milestone M0 with:

```bash
<freecad-appimage>/squashfs-root/usr/bin/freecadcmd engine/server.py
# then open http://localhost:8787
```

FreeSolid is a FreeCAD addon for designers who already know a commercial
parametric CAD package — SolidWorks, Inventor, Solid Edge — and who find
FreeCAD's terminology and panel behaviour disorienting rather than
difficult. It changes no geometry and adds no document object types: it is a
presentation and onboarding layer over FreeCAD's own PartDesign.

> **Alpha.** Version 0.1. The vocabulary and preference tables are covered by
> unit tests; the FreeCAD-facing code has not yet been exercised against a
> real install. See [Status](#status).

## What it does

**A FeatureManager-shaped tree.** FreeCAD greys out every feature except the
Tip, because only one solid is displayed at a time. In SolidWorks, greyed
means *suppressed* — so the native tree reads as "everything is broken" to a
designer coming from there. FreeSolid ships a separate dock that:

- lists features chronologically and never greys a healthy one;
- renders the Tip as a **rollback bar** — which is the mental model it
  actually implements — movable by double-clicking a feature;
- labels Origin planes **Face / Dessus / Droite** instead of XZ / XY / YZ;
- colours genuinely broken features red, and only those.

**Command names you already use.** *Bossage extrudé* runs `PartDesign_Pad`,
*Enlèvement de matière extrudé* runs `PartDesign_Pocket`, *Assistant de
perçage* runs `PartDesign_Hole`. The aliases delegate to FreeCAD's commands;
nothing is reimplemented. The full table lives in
[`freesolid/vocab.py`](freesolid/vocab.py) and is the single source of truth.

**Nouvelle pièce.** One command that creates a document, adds a Body and
activates it — SolidWorks' `File > New > Part`. The missing Body is the
single most common cause of "my feature went somewhere weird".

**A preference pack.** Navigation set to Blender style (middle button
rotates, the closest FreeCAD has to SolidWorks — it has no native SolidWorks
style), PartDesign as the startup workbench, unused workbenches hidden, and
the model tree moved into its own dock so the Tasks panel stops *replacing*
it mid-command.

## Install

Not yet listed in the Addon Manager. Meanwhile:

1. `Tools → Addon manager → ⚙ → Custom repositories`, add this repository's
   URL with branch `main`; **or** clone into `~/.local/share/FreeCAD/Mod/freesolid`
   (`%APPDATA%\FreeCAD\Mod\freesolid` on Windows).
2. Restart FreeCAD, pick the **FreeSolid** workbench.
3. Run **Configurer FreeSolid** once. It reports every setting it changed and
   flags the ones it could not apply.

Requires FreeCAD 1.0 or later and Python 3.10+.

## Status

| Area | State |
|---|---|
| Vocabulary table (`vocab.py`) | ✅ unit-tested |
| Preference table (`prefs.py`) | ✅ unit-tested; 6 of 7 paths verified on a real 1.1.3 install |
| Alias commands + toolbars | ✅ confirmed running on FreeCAD 1.1.3 |
| FeatureManager dock | ⚠️ loads on 1.1.3; modelling feedback pending |
| Contextual "S" bar (`ui/context_bar.py`) | ⚠️ logic unit-tested; Qt side not yet run |
| Guardrail (`guard.py`) | ⚠️ translations unit-tested; observer is best-effort |
| Diagnostics (`diagnostics.py`) | ✅ unit-tested; run it on a real install and paste the report |
| Preference pack `.cfg` | ⚠️ minimal, needs a real-install export |
| Navigation spec (`docs/navigation-spec.md`) | ⚠️ draft, awaiting expert line-by-line validation |

Six preference rows are marked `verified=False` in
[`freesolid/prefs.py`](freesolid/prefs.py): their parameter paths come from
documentation rather than from a run against a real build, and FreeCAD's
parameter paths are not a public API. The Setup command lists them
separately, so a wrong key surfaces as "not applied" instead of a silent
no-op. Checking them against `Tools → Edit parameters` on a real install is
the first task before 0.2.

## Roadmap

- Verify and lock every preference path against FreeCAD 1.0 and 1.1 — run
  **Diagnostic FreeSolid** on a real install and feed the report back.
- A ribbon layout (JSON) for the [FreeCAD-Ribbon](https://github.com/APEbbers/FreeCAD-Ribbon)
  addon, arranging PartDesign, Sketcher and Part into one CommandManager-like
  tab. Deliberately deferred until it can be generated against the addon's
  actual schema on a real install, rather than written blind.
- Validate `docs/navigation-spec.md` line by line, then reopen FreeCAD
  discussion #18635 with it.
- English UI strings and a translation catalogue; the UI is French-first for
  now.

Out of scope, permanently: anything requiring a fork of FreeCAD itself. The
one thing a designer will miss that an addon cannot deliver is **multiple
disconnected solids inside a single Body** — that is a PartDesign
architecture constraint, not a UI choice.

## Development

```bash
python -m pip install pytest
python -m compileall -q freesolid Init.py InitGui.py
python -m pytest -q
```

`vocab.py` and `prefs.py` import nothing from FreeCAD, which is what makes
them testable in CI. Keep it that way: FreeCAD imports belong inside
functions, not at module scope.

**The InitGui.py scoping rule.** FreeCAD `exec()`s Init scripts with separate
globals and locals dictionaries. Names bound at the top level of `InitGui.py`
land in locals, while function and method bodies resolve against globals — so
**a method defined in `InitGui.py` cannot see anything defined in
`InitGui.py`**. Reading a module-level name from a method raises `NameError`
during initialization, and the workbench then silently never appears in the
workbench selector. Hence: `InitGui.py` stays straight-line with no helper
functions, every method imports what it needs inside its own body, and the
real logic lives in the package. `tests/test_initgui_scoping.py` enforces
this by AST inspection.

## Naming and trademarks

FreeSolid is not affiliated with, endorsed by, or derived from any
commercial CAD vendor. Vendor names appear only to describe who this addon
is for, which is nominative use. No vendor icon, dialog or resource is
reproduced. The Qt addon's icons are original; the web UI reuses FreeCAD
SVG icons under LGPL, documented in [`app/icons/README.md`](app/icons/README.md).

An unrelated *FreeSOLID* existed in the 2000s: a collision-detection library
(SOLID, *Software Library for Interference Detection*). It is dormant and in
a different domain; there is no shared code or lineage.

## Licence

LGPL-2.1-or-later, matching FreeCAD.
