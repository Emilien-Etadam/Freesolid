"""The FreeCAD-headless side of the protocol.

One ``Kernel`` instance owns one document. FreeCAD is imported inside
methods (the module stays importable in CI), and every error surfaces
through ``freesolid.guard.friendly_error`` when a translation exists — the
web UI inherits the same designer-facing explanations as the Qt addon.

Untested-against-FreeCAD code is assumed guilty until the ``selftest`` op
has run on a real install — the same verification loop that debugged the
addon's parameter paths.
"""

import os
import sys

# The engine lives beside the freesolid package in the same repo; make the
# repo root importable when freecadcmd runs this file from anywhere.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from freesolid.guard import friendly_error          # noqa: E402
from freesolid.vocab import label_for_type          # noqa: E402


class KernelError(Exception):
    """Operation failed; message is designer-facing when translatable."""


def _explain(exc) -> str:
    text = str(exc)
    return friendly_error(text) or text


class Kernel:
    """Owns one FreeCAD document and executes protocol operations."""

    def __init__(self):
        self._doc = None
        self._body = None

    # -- helpers ---------------------------------------------------------

    def _app(self):
        import FreeCAD as App
        return App

    def _require_doc(self):
        if self._doc is None:
            raise KernelError(
                "aucune pièce ouverte — commencez par new_part")
        return self._doc

    def _require_body(self):
        self._require_doc()
        if self._body is None:
            raise KernelError("aucun corps — commencez par new_part")
        return self._body

    def _recompute(self):
        doc = self._require_doc()
        doc.recompute()
        broken = [o for o in doc.Objects if "Invalid" in (o.State or ())]
        if broken:
            messages = []
            for obj in broken:
                text = ""
                try:
                    text = obj.getStatusString() or ""
                except Exception:
                    pass
                messages.append("{} : {}".format(
                    obj.Label, friendly_error(text) or text or "en erreur"))
            raise KernelError(" ; ".join(messages))

    # -- operations ------------------------------------------------------

    def ping(self):
        App = self._app()
        return {"freecad": ".".join(str(v) for v in App.Version()[:3])}

    def new_part(self, name="Pièce"):
        App = self._app()
        self._doc = App.newDocument("FreeSolid")
        self._body = self._doc.addObject("PartDesign::Body", "Body")
        self._body.Label = name
        self._recompute()
        return self.get_tree()

    def add_rect_sketch(self, width, height):
        """Centered, fully-constrained rectangle on the XY plane.

        Anchored by symmetry about the origin, driven by DistanceX/DistanceY
        — the SolidWorks "sketch a rectangle, dimension it" outcome without
        the interactive part (that is M2's job).
        """
        import Part
        import Sketcher
        body = self._require_body()
        doc = self._require_doc()
        w, h = float(width), float(height)
        if w <= 0 or h <= 0:
            raise KernelError("largeur et hauteur doivent être positives")

        sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
        body.addObject(sketch)
        sketch.Label = "Esquisse"

        V = self._app().Vector
        x, y = w / 2.0, h / 2.0
        corners = [V(-x, -y, 0), V(x, -y, 0), V(x, y, 0), V(-x, y, 0)]
        for i in range(4):
            sketch.addGeometry(
                Part.LineSegment(corners[i], corners[(i + 1) % 4]), False)

        C = Sketcher.Constraint
        for i in range(4):
            sketch.addConstraint(C("Coincident", i, 2, (i + 1) % 4, 1))
        sketch.addConstraint(C("Horizontal", 0))
        sketch.addConstraint(C("Horizontal", 2))
        sketch.addConstraint(C("Vertical", 1))
        sketch.addConstraint(C("Vertical", 3))
        # Symmetry about the origin point pins the rectangle in space.
        sketch.addConstraint(C("Symmetric", 0, 1, 2, 1, -1, 1))
        sketch.addConstraint(C("DistanceX", 0, 1, 0, 2, w))
        sketch.addConstraint(C("DistanceY", 1, 1, 1, 2, h))

        self._recompute()
        return self.get_tree()

    def add_pad(self, length):
        body = self._require_body()
        doc = self._require_doc()
        sketches = [o for o in body.Group
                    if o.TypeId == "Sketcher::SketchObject"]
        if not sketches:
            raise KernelError("aucune esquisse à extruder")
        pad = body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = sketches[-1]
        pad.Length = float(length)
        pad.Label = "Bossage extrudé"
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(pad.Name)
            raise
        return self.get_tree()

    def set_param(self, feature, prop, value):
        """Set one property on one feature by internal name, and recompute.

        This is the whole parametric promise in one operation: the UI edits
        ``Pad.Length`` and the part rebuilds.
        """
        doc = self._require_doc()
        obj = doc.getObject(feature)
        if obj is None:
            raise KernelError("fonction inconnue : {}".format(feature))
        if not hasattr(obj, prop):
            raise KernelError("{} n'a pas de propriété {}".format(
                obj.Label, prop))
        try:
            setattr(obj, prop, value)
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        self._recompute()
        return self.get_tree()

    def get_tree(self):
        """The feature tree, in the vocabulary the designer knows."""
        body = self._require_body()
        items = []
        for obj in body.Group:
            items.append({
                "name": obj.Name,
                "label": obj.Label,
                "kind": label_for_type(obj.TypeId),
                "type": obj.TypeId,
                "error": "Invalid" in (obj.State or ()),
            })
        tip = body.Tip.Name if getattr(body, "Tip", None) else None
        return {"body": body.Label, "tip": tip, "features": items}

    def tessellate(self, deviation=0.1):
        """Per-face tessellation of the body's current shape.

        Face-by-face on purpose — see ``protocol.pack_mesh``: picking works
        by construction because each OCCT face is its own index group.
        """
        from . import protocol
        body = self._require_body()
        shape = getattr(body, "Shape", None)
        if shape is None or not shape.Faces:
            return protocol.pack_mesh([])
        faces = []
        for i, face in enumerate(shape.Faces):
            vertices, triangles = face.tessellate(float(deviation))
            faces.append((i, [(v.x, v.y, v.z) for v in vertices], triangles))
        return protocol.pack_mesh(faces)

    def selftest(self):
        """Run the M0 flow end to end; return stats worth pasting back."""
        report = {}
        report["ping"] = self.ping()
        self.new_part("Pièce de test")
        self.add_rect_sketch(100, 60)
        tree = self.add_pad(10)
        report["tree_after_pad"] = tree
        mesh = self.tessellate()
        report["mesh_faces"] = len(mesh["groups"])
        report["mesh_triangles"] = len(mesh["indices"]) // 3
        pad = next(f["name"] for f in tree["features"]
                   if f["type"] == "PartDesign::Pad")
        self.set_param(pad, "Length", 25.0)
        mesh2 = self.tessellate()
        report["reparam_ok"] = mesh2 != mesh
        return report


def dispatch(kernel: Kernel, op: str, params: dict):
    """Route one validated request to the kernel, normalizing errors."""
    from . import protocol
    try:
        return protocol.ok(getattr(kernel, op)(**params))
    except KernelError as exc:
        return protocol.err(str(exc))
    except Exception as exc:  # noqa: BLE001 - the envelope is the handler
        return protocol.err(_explain(exc),
                            hint="erreur moteur non traduite — à signaler")
