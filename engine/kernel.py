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

    def _attach_to_face(self, sketch, face_id):
        """Map a sketch flat onto one of the current shape's faces.

        ``face_id`` is the tessellation index, so ``Face{id+1}`` on the Tip
        feature — the same numbering the viewport picked. The attachment
        property was renamed in 1.x, hence the two spellings.
        """
        body = self._require_body()
        tip = getattr(body, "Tip", None)
        if tip is None:
            raise KernelError("pas encore de solide pour accueillir "
                              "une esquisse sur face")
        support = [(tip, ("Face{}".format(int(face_id) + 1),))]
        try:
            sketch.AttachmentSupport = support
        except AttributeError:
            sketch.Support = support
        sketch.MapMode = "FlatFace"

    def add_rect_sketch(self, width, height, face=None):
        """Centered, fully-constrained rectangle.

        On the XY plane by default; with ``face`` (a picked face id), mapped
        flat onto that face — the SolidWorks "click a face, sketch on it"
        gesture. Anchored by symmetry about the sketch origin, driven by
        DistanceX/DistanceY; the interactive part is M2's job.
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
        if face is not None:
            self._attach_to_face(sketch, face)

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

    def _latest_sketch(self):
        body = self._require_body()
        sketches = [o for o in body.Group
                    if o.TypeId == "Sketcher::SketchObject"]
        if not sketches:
            raise KernelError("aucune esquisse disponible")
        return sketches[-1]

    def add_pocket(self, length):
        """Cut with the latest sketch — Extruded Cut, in SolidWorks terms."""
        body = self._require_body()
        doc = self._require_doc()
        pocket = body.newObject("PartDesign::Pocket", "Pocket")
        pocket.Profile = self._latest_sketch()
        pocket.Length = float(length)
        pocket.Label = "Enlèvement de matière"
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(pocket.Name)
            raise
        return self.get_tree()

    def _dressup(self, type_id, label, face, prop, value):
        """Fillet/chamfer share everything but the property they drive.

        The dress-up references the picked face on the Tip feature — the
        shape the viewport tessellated, so the numbering matches by
        construction. PartDesign applies it to every edge of that face.
        """
        body = self._require_body()
        doc = self._require_doc()
        tip = getattr(body, "Tip", None)
        if tip is None:
            raise KernelError("pas de solide à habiller")
        feature = body.newObject(type_id, type_id.split("::")[-1])
        feature.Base = (tip, ["Face{}".format(int(face) + 1)])
        setattr(feature, prop, float(value))
        feature.Label = label
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(feature.Name)
            raise
        return self.get_tree()

    def add_fillet(self, face, radius):
        return self._dressup("PartDesign::Fillet", "Congé", face,
                             "Radius", radius)

    def add_chamfer(self, face, size):
        return self._dressup("PartDesign::Chamfer", "Chanfrein", face,
                             "Size", size)

    #: Properties offered for editing, in display order. A whitelist rather
    #: than full introspection: Pad alone carries a dozen numeric properties
    #: and prompting through Offset/TaperAngle/Length2 buries the one that
    #: matters.
    _EDITABLE_PROPS = ("Length", "Radius", "Size", "Angle", "Thickness")

    def get_params(self, feature):
        """Editable numeric properties of a feature, with current values."""
        doc = self._require_doc()
        obj = doc.getObject(feature)
        if obj is None:
            raise KernelError("fonction inconnue : {}".format(feature))
        params = []
        for prop in self._EDITABLE_PROPS:
            if not hasattr(obj, prop):
                continue
            value = getattr(obj, prop)
            params.append({"prop": prop,
                           "value": float(getattr(value, "Value", value))})
        return {"feature": feature, "label": obj.Label, "params": params}

    def set_tip(self, feature):
        """Move the rollback bar: the part rebuilds up to this feature."""
        body = self._require_body()
        obj = self._require_doc().getObject(feature)
        if obj is None:
            raise KernelError("fonction inconnue : {}".format(feature))
        body.Tip = obj
        self._recompute()
        return self.get_tree()

    def tip_to_end(self):
        """Rollback bar back to the last feature — the final state."""
        body = self._require_body()
        features = [o for o in body.Group
                    if o.isDerivedFrom("PartDesign::Feature")]
        if not features:
            raise KernelError("aucune fonction dans la pièce")
        body.Tip = features[-1]
        self._recompute()
        return self.get_tree()

    def delete_feature(self, feature):
        """Remove one feature. Its sketch stays — deleting it too would be
        a second, separate decision, exactly as in SolidWorks."""
        doc = self._require_doc()
        obj = doc.getObject(feature)
        if obj is None:
            raise KernelError("fonction inconnue : {}".format(feature))
        label = obj.Label
        doc.removeObject(obj.Name)
        try:
            self._recompute()
        except KernelError as exc:
            raise KernelError(
                "{} supprimé, mais l'aval casse : {}".format(label, exc))
        return self.get_tree()

    def open_part(self, path):
        """Open an existing .FCStd — the user's real files, not our demos.

        M1 scope: single active Body. A multi-body file opens on its first
        Body and says so; a file with none (Part-workbench models, meshes)
        is refused with the reason.
        """
        App = self._app()
        path = os.path.expanduser(str(path))
        if not os.path.exists(path):
            raise KernelError("fichier introuvable : {}".format(path))
        doc = App.openDocument(path)
        bodies = [o for o in doc.Objects if o.TypeId == "PartDesign::Body"]
        if not bodies:
            raise KernelError(
                "aucun corps PartDesign dans ce fichier — il vient "
                "probablement de l'atelier Part (booléennes sans historique "
                "de fonctions), que cette interface ne couvre pas encore")
        self._doc, self._body = doc, bodies[0]
        tree = self.get_tree()
        tree["bodies_in_file"] = len(bodies)
        return tree

    def save_part(self, path):
        """Save as a standard .FCStd — openable in stock FreeCAD.

        The exit door stays open by design: nothing this app produces is
        locked into it.
        """
        doc = self._require_doc()
        path = os.path.expanduser(str(path))
        if not path.endswith(".FCStd"):
            path += ".FCStd"
        doc.saveAs(path)
        return {"path": path}

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

    def _top_face_id(self):
        """Index of the upward-facing face with the highest centroid.

        Selftest helper: finds "the top" the way a user's eye does, without
        assuming anything about OCCT's face ordering.
        """
        body = self._require_body()
        best, best_z = None, None
        for i, face in enumerate(body.Shape.Faces):
            u0, u1, v0, v1 = face.ParameterRange
            normal = face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
            if normal.z <= 0.5:
                continue
            z = face.CenterOfMass.z
            if best_z is None or z > best_z:
                best, best_z = i, z
        if best is None:
            raise KernelError("aucune face orientée vers le haut")
        return best

    def selftest(self):
        """Run the whole flow end to end; return stats worth pasting back.

        M0: part, constrained sketch, pad, reparam. M1: sketch attached to a
        picked face, pocket through it, fillet on a face — the exact
        click-a-face gestures the viewport offers, minus the viewport.
        """
        report = {}
        report["ping"] = self.ping()
        self.new_part("Pièce de test")
        self.add_rect_sketch(100, 60)
        tree = self.add_pad(10)
        mesh = self.tessellate()
        report["m0_faces"] = len(mesh["groups"])
        pad = next(f["name"] for f in tree["features"]
                   if f["type"] == "PartDesign::Pad")
        self.set_param(pad, "Length", 25.0)
        report["m0_reparam_ok"] = self.tessellate() != mesh

        top = self._top_face_id()
        report["m1_top_face"] = top
        self.add_rect_sketch(40, 20, face=top)
        self.add_pocket(10)
        report["m1_pocket_faces"] = len(self.tessellate()["groups"])
        tree = self.add_fillet(self._top_face_id(), 3)
        report["m1_fillet_ok"] = not any(f["error"] for f in tree["features"])

        # M1.5: rollback both ways, then a save/open round-trip — the file
        # a user gets back must rebuild identically.
        pad_feature = next(f["name"] for f in tree["features"]
                           if f["type"] == "PartDesign::Pad")
        faces_rolled = len(self.tessellate()["groups"])
        self.set_tip(pad_feature)
        report["m15_rollback_changes_shape"] = (
            len(self.tessellate()["groups"]) != faces_rolled)
        self.tip_to_end()

        import tempfile
        path = os.path.join(tempfile.gettempdir(), "freesolid-selftest.FCStd")
        self.save_part(path)
        tree_before = self.get_tree()
        reopened = self.open_part(path)
        report["m15_roundtrip_ok"] = (
            [f["type"] for f in reopened["features"]]
            == [f["type"] for f in tree_before["features"]])

        report["tree_after_pad"] = self.get_tree()
        mesh = self.tessellate()
        report["mesh_faces"] = len(mesh["groups"])
        report["mesh_triangles"] = len(mesh["indices"]) // 3
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
