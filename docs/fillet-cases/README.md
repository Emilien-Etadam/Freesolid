# Hard fillet cases

Six small fillet cases that B-rep kernels find hard, written so that any
kernel can replay them: OpenCascade (through FreeCAD), truck, or another.
They come from FreeSolid, a CAD interface built on FreeCAD, and the first
one comes from a real user test.

## What is in this folder

| File | Content |
|---|---|
| `inputs/*.step` | The input solid of each case, before the fillet |
| `cases.json` | Each fillet: a point lying on the edge, the radius, and the expected result. The edge is picked by a point, not by a FreeCAD edge index, so any kernel can find it |
| `fillet_cases.py` | Builds the inputs, runs every case with FreeCAD (`Part::Fillet`) and writes `cases.json`, `inputs/` and `results.md` |
| `results.md` | Results of the last run, with the FreeCAD and OpenCascade versions |

Run it with:

```bash
freecadcmd docs/fillet-cases/fillet_cases.py
```

Each case ends up in one of three classes:

- **PASS**: a valid single solid comes back, and its volume changes in the
  expected direction.
- **INVALID**: a shape comes back but it is broken. This is the dangerous
  outcome, because FreeCAD can still mark the feature as up to date.
- **FAIL**: the kernel refuses, and no shape comes back.

## The cases

| Case | Geometry | Fillet |
|---|---|---|
| 01-flush-cylinder | Cylinder R25 on a plate whose rounded end is the same circle (coaxial, same radius) | R3 on the cylinder/plate top arc |
| 02-tangent-cylinder | Cylinder R10 on a box, tangent to the box side face | R2 on the circular junction, which touches the box edge at one point |
| 03-corner-three-radii | Box corner where three edges meet | R4, R6 and R8, one per edge (vertex blend) |
| 04-overflow-step | Concave edge at the foot of a 2 mm step | R4, larger than the step face, so it must overflow onto the step top |
| 05-across-seam | Tab fused to a cylinder exactly across its seam line | R1.5 on the three junction edges |
| 06-tight-chain | Rounded-rectangle boss (corner R1.5) on a plate | R3 on the whole tangent chain at its base, larger than the corner radius |

## Results on FreeCAD 1.1.3 (OpenCascade 7.8.1)

| Case | Result |
|---|---|
| 01-flush-cylinder | **INVALID**: broken solid, yet FreeCAD reports "Up-to-date" |
| 02-tangent-cylinder | **FAIL** |
| 03-corner-three-radii | PASS |
| 04-overflow-step | **FAIL** |
| 05-across-seam | PASS |
| 06-tight-chain | PASS |

`results.md` holds the details of the last run.

### Known workaround for case 01

Making the cylinder 0.0002 mm or more larger than the plate end lets the
fillet pass with a valid solid. With 0.0001 mm or less, the solid is still
broken. Shrinking the cylinder instead makes the fillet fail outright. This
was measured with PartDesign features on FreeCAD 1.1.3. It points to the
exact coincidence of the two cylindrical surfaces as the cause.
