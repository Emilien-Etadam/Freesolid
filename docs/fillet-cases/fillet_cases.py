# Hard fillet cases for B-rep kernels — FreeCAD / OpenCascade runner.
#
#     freecadcmd docs/fillet-cases/fillet_cases.py
#
# For each case: builds the input solid, writes it to inputs/<name>.step,
# picks the edges by a point lying on each of them (kernel-neutral), runs
# the fillet with Part::Fillet and classifies the result:
#   PASS     valid single solid, volume changed in the expected direction
#   INVALID  a shape comes back but it is broken (the dangerous outcome:
#            FreeCAD may still mark the feature as up to date)
#   FAIL     no shape (the kernel refuses)
# The table is printed and written to results.md next to this file.
#
# freecadcmd imports this file as a module (it does not run it as
# __main__), so the code below runs at import time on purpose.
import json
import math
import os

import FreeCAD as App
import Part

V = App.Vector
HERE = os.path.dirname(os.path.abspath(__file__))
INPUTS = os.path.join(HERE, "inputs")


def _slot(r1, r2, d, h):
    """Tapered slot: circle r1 at (0,0), circle r2 at (d,0), outer tangents."""
    a = math.asin((r2 - r1) / d)
    up = V(-math.sin(a), math.cos(a), 0)
    down = V(up.x, -up.y, 0)
    c2 = V(d, 0, 0)
    edges = [
        Part.Arc(down * r1, V(-r1, 0, 0), up * r1).toShape(),
        Part.LineSegment(up * r1, c2 + up * r2).toShape(),
        Part.Arc(c2 + up * r2, V(d + r2, 0, 0), c2 + down * r2).toShape(),
        Part.LineSegment(c2 + down * r2, down * r1).toShape(),
    ]
    return Part.Face(Part.Wire(edges)).extrude(V(0, 0, h))


def _rounded_rect(x, y, w, l, r, z, h):
    """Rectangle w x l with corner radius r, lower-left corner (x, y)."""
    face = Part.Face(Part.Wire(Part.makePlane(w, l).Edges))
    box = face.extrude(V(0, 0, h))
    box = box.makeFillet(r, [e for e in box.Edges
                             if abs(e.BoundBox.ZLength - h) < 1e-9])
    box.translate(V(x, y, z))
    return box


def _fuse(*shapes):
    out = shapes[0]
    for s in shapes[1:]:
        out = out.fuse(s)
    return out.removeSplitter()


def case_flush_cylinder():
    plate = _slot(12, 25, 70, 10)
    cyl = Part.makeCylinder(25, 22, V(70, 0, 10))
    return _fuse(plate, cyl), [(V(45, 0, 10), 3.0)], +1


def case_tangent_cylinder():
    box = Part.makeBox(60, 40, 10)
    cyl = Part.makeCylinder(10, 20, V(50, 20, 10))   # tangent to x = 60
    return _fuse(box, cyl), [(V(40, 20, 10), 2.0)], +1


def case_corner_three_radii():
    box = Part.makeBox(40, 40, 40)
    return box, [(V(20, 40, 40), 4.0), (V(40, 20, 40), 6.0),
                 (V(40, 40, 20), 8.0)], -1


def case_overflow_step():
    plate = Part.makeBox(40, 30, 10)
    step = Part.makeBox(40, 15, 2, V(0, 15, 10))     # 2 mm high step
    return _fuse(plate, step), [(V(20, 15, 10), 4.0)], +1


def case_across_seam():
    cyl = Part.makeCylinder(10, 20)                  # seam at +X
    tab = Part.makeBox(15, 6, 10, V(5, -3, 0))
    # The top junction arc runs from y = -3 to y = 3 through the seam
    # point (10, 0, 10): pick it on both sides of the seam, away from it.
    def on_circle(y, z):
        return V(math.sqrt(100 - y * y), y, z)
    return _fuse(cyl, tab), [(on_circle(1.5, 10), 1.5),
                             (on_circle(-1.5, 10), 1.5),
                             (on_circle(3, 5), 1.5),
                             (on_circle(-3, 5), 1.5)], +1


def case_tight_chain():
    plate = Part.makeBox(60, 40, 10)
    boss = _rounded_rect(15, 10, 30, 20, 1.5, 10, 8)  # corner R 1.5 < fillet
    solid = _fuse(plate, boss)
    picks = []
    for e in solid.Edges:
        bb = e.BoundBox
        if (abs(bb.ZMin - 10) < 1e-6 and abs(bb.ZMax - 10) < 1e-6
                and bb.XMin > 14 and bb.XMax < 46
                and bb.YMin > 9 and bb.YMax < 31):
            picks.append((e.valueAt(0.5 * (e.FirstParameter
                                           + e.LastParameter)), 3.0))
    return solid, picks, +1


CASES = [
    ("01-flush-cylinder", case_flush_cylinder,
     "Cylinder R25 on a plate whose rounded end is the same circle "
     "(coaxial, same radius). Fillet R3 on the cylinder/plate top arc."),
    ("02-tangent-cylinder", case_tangent_cylinder,
     "Cylinder R10 on a box, tangent to the box side face. Fillet R2 on "
     "the circular junction, which touches the box edge at one point."),
    ("03-corner-three-radii", case_corner_three_radii,
     "Box corner where three edges meet. Fillets R4, R6 and R8, one per "
     "edge, need a vertex blend."),
    ("04-overflow-step", case_overflow_step,
     "Concave edge at the foot of a 2 mm step. Fillet R4 is larger than "
     "the step face and must overflow onto the step top."),
    ("05-across-seam", case_across_seam,
     "Tab fused to a cylinder exactly across its seam line. Fillet R1.5 "
     "on the three junction edges."),
    ("06-tight-chain", case_tight_chain,
     "Rounded-rectangle boss (corner R1.5) on a plate. Fillet R3 on the "
     "whole tangent chain at its base: larger than the corner radius."),
]


def _edge_at(shape, point):
    """Index (1-based) of the only edge through ``point``."""
    vertex = Part.Vertex(point)
    hits = [i + 1 for i, e in enumerate(shape.Edges)
            if e.distToShape(vertex)[0] < 1e-4]
    if len(hits) != 1:
        raise ValueError("{} edges through {}".format(len(hits), point))
    return hits[0]


def describe(name, build, text):
    """Kernel-neutral description: input file, edge points, radii."""
    _, picks, sign = build()
    return {
        "name": name,
        "description": text,
        "input": "inputs/{}.step".format(name),
        "fillets": [{"point_on_edge": [round(c, 6) for c in (p.x, p.y, p.z)],
                     "radius": r} for p, r in picks],
        "expected": "valid single solid, volume {}".format(
            "increases (concave)" if sign > 0 else "decreases (convex)"),
    }


def run_case(name, build):
    solid, picks, sign = build()
    for p, _ in picks:
        _edge_at(solid, p)   # raises before the kernel is involved
    if not os.path.isdir(INPUTS):
        os.makedirs(INPUTS)
    solid.exportStep(os.path.join(INPUTS, name + ".step"))
    doc = App.newDocument("FilletCase")
    try:
        base = doc.addObject("Part::Feature", "Input")
        base.Shape = solid
        fillet = doc.addObject("Part::Fillet", "Fillet")
        fillet.Base = base
        edges = {}
        for p, r in picks:   # two picks may land on the same edge
            edges[_edge_at(solid, p)] = r
        fillet.Edges = [(i, r, r) for i, r in sorted(edges.items())]
        doc.recompute()
        shape = fillet.Shape
        state = ",".join(fillet.State) or "Up-to-date"
        if shape.isNull() or not shape.Solids:
            return "FAIL", state, ""
        try:
            delta = shape.Volume - solid.Volume
        except Exception:
            return "INVALID", state, "volume not computable"
        ok = (shape.isValid() and len(shape.Solids) == 1
              and delta * sign > 0)
        note = "volume {:+.1f} mm3".format(delta)
        if shape.isValid() and delta * sign <= 0:
            note += " (wrong direction)"
        return ("PASS" if ok else "INVALID"), state, note
    except Exception as exc:  # the kernel refused outright
        return "FAIL", "exception", str(exc).strip()[:80]
    finally:
        App.closeDocument(doc.Name)


def main():
    version = ".".join(App.Version()[:3])
    lines = [
        "# Results — FreeCAD {} (OpenCascade {})".format(
            version, getattr(Part, "OCC_VERSION", "?")),
        "",
        "| Case | Result | FreeCAD state | Note |",
        "|---|---|---|---|",
    ]
    for name, build, _ in CASES:
        result, state, note = run_case(name, build)
        lines.append("| {} | {} | {} | {} |".format(name, result, state, note))
    with open(os.path.join(HERE, "cases.json"), "w") as f:
        json.dump([describe(*c) for c in CASES], f, indent=2)
        f.write("\n")
    text = "\n".join(lines) + "\n"
    with open(os.path.join(HERE, "results.md"), "w") as f:
        f.write(text)
    print(text)


main()
