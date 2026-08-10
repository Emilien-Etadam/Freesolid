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

    def _close_current(self):
        """Drop the engine's previous document, if any.

        A lingering document keeps recomputing in the background and its
        warnings land in the terminal attributed to a part the user thinks
        is gone — one document per engine, by construction.
        """
        if self._doc is not None:
            try:
                self._app().closeDocument(self._doc.Name)
            except Exception:
                pass
        self._doc = self._body = None

    def new_part(self, name="Pièce"):
        App = self._app()
        self._close_current()
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

    def add_pad(self, length, sketch=None):
        body = self._require_body()
        doc = self._require_doc()
        if sketch is not None:
            profile = self._get_sketch(sketch)
        else:
            sketches = [o for o in body.Group
                        if o.TypeId == "Sketcher::SketchObject"]
            if not sketches:
                raise KernelError("aucune esquisse à extruder")
            profile = sketches[-1]
        pad = body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = profile
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
        """Move the rollback bar: the part rebuilds up to this feature.

        Only PartDesign features qualify: setting Tip to a sketch made
        FreeCAD log "Linked object is not a PartDesign feature" on every
        recompute (seen on 1.1.3 via the tree's context menu).
        """
        body = self._require_body()
        obj = self._require_doc().getObject(feature)
        if obj is None:
            raise KernelError("fonction inconnue : {}".format(feature))
        if not obj.isDerivedFrom("PartDesign::Feature"):
            raise KernelError(
                "la barre de retour se pose sur une fonction (bossage, "
                "enlèvement…), pas sur une esquisse")
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
        self._close_current()
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

    # -- M2 : sketch editing --------------------------------------------

    #: Exact-match tolerance for auto-constraints. The client snaps and
    #: sends identical coordinates; this only recognizes that decision.
    _SNAP_TOL = 1e-7

    def _get_sketch(self, name):
        obj = self._require_doc().getObject(name)
        if obj is None or obj.TypeId != "Sketcher::SketchObject":
            raise KernelError("esquisse inconnue : {}".format(name))
        return obj

    def sketch_start(self, face=None):
        """Open a new empty sketch (XY plane, or a picked face)."""
        body = self._require_body()
        doc = self._require_doc()
        sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
        body.addObject(sketch)
        sketch.Label = "Esquisse"
        if face is not None:
            self._attach_to_face(sketch, face)
        doc.recompute()  # resolves the placement before the client reads it
        return self.sketch_state(sketch.Name)

    def sketch_edit(self, feature):
        """Re-enter an existing sketch."""
        return self.sketch_state(self._get_sketch(feature).Name)

    def sketch_state(self, sketch):
        """Everything the client needs to draw the sketch.

        Geometry in sketch-local 2D, dimensional constraints with values,
        degrees of freedom, and the placement matrix (row-major, which is
        what THREE.Matrix4.set expects) to position the plane in 3D.
        """
        sk = self._get_sketch(sketch)
        entities = []
        for gid, geo in enumerate(sk.Geometry):
            if geo.TypeId == "Part::GeomLineSegment":
                entities.append({
                    "id": gid, "type": "line",
                    "p1": [geo.StartPoint.x, geo.StartPoint.y],
                    "p2": [geo.EndPoint.x, geo.EndPoint.y]})
            elif geo.TypeId == "Part::GeomCircle":
                entities.append({
                    "id": gid, "type": "circle",
                    "c": [geo.Center.x, geo.Center.y],
                    "r": float(geo.Radius)})
            else:
                entities.append({"id": gid, "type": "other",
                                 "kind": geo.TypeId})
        dims = []
        for cid, constraint in enumerate(sk.Constraints):
            if constraint.Type in ("Distance", "DistanceX", "DistanceY",
                                   "Radius", "Diameter", "Angle"):
                dims.append({"id": cid, "type": constraint.Type,
                             "value": float(constraint.Value),
                             "geo": constraint.First})
        try:
            sk.solve()
        except Exception:
            pass
        dof = None
        try:
            dof = int(sk.getLastDoF())
        except Exception:
            pass
        matrix = sk.Placement.Matrix.A
        return {
            "sketch": sk.Name,
            "label": sk.Label,
            "entities": entities,
            "dims": dims,
            "dof": dof,
            "fullyConstrained": bool(getattr(sk, "FullyConstrained", False)),
            "placement": [float(v) for v in matrix],
        }

    def _auto_constrain_line(self, sk, gid):
        """The SolidWorks reflexes: snap becomes coincident, near-axis
        becomes horizontal/vertical.

        The client decides (it snapped and sent exact coordinates); this
        turns that decision into constraints so the solver holds it.
        """
        import Sketcher
        C = Sketcher.Constraint
        geo = sk.Geometry[gid]
        for pos, point in ((1, geo.StartPoint), (2, geo.EndPoint)):
            for other in range(len(sk.Geometry)):
                if other == gid:
                    continue
                og = sk.Geometry[other]
                if og.TypeId != "Part::GeomLineSegment":
                    continue
                matched = False
                for opos, opoint in ((1, og.StartPoint), (2, og.EndPoint)):
                    if point.distanceToPoint(opoint) < self._SNAP_TOL:
                        sk.addConstraint(C("Coincident", gid, pos,
                                           other, opos))
                        matched = True
                        break
                if matched:
                    break
        dx = abs(geo.EndPoint.x - geo.StartPoint.x)
        dy = abs(geo.EndPoint.y - geo.StartPoint.y)
        if dx > self._SNAP_TOL or dy > self._SNAP_TOL:  # not degenerate
            if dy < self._SNAP_TOL:
                sk.addConstraint(C("Horizontal", gid))
            elif dx < self._SNAP_TOL:
                sk.addConstraint(C("Vertical", gid))

    def sketch_add_line(self, sketch, x1, y1, x2, y2):
        import Part
        sk = self._get_sketch(sketch)
        V = self._app().Vector
        gid = sk.addGeometry(Part.LineSegment(
            V(float(x1), float(y1), 0), V(float(x2), float(y2), 0)), False)
        self._auto_constrain_line(sk, gid)
        return self.sketch_state(sketch)

    def sketch_add_circle(self, sketch, cx, cy, r):
        import Part
        sk = self._get_sketch(sketch)
        if float(r) <= 0:
            raise KernelError("le rayon doit être positif")
        App = self._app()
        sk.addGeometry(Part.Circle(
            App.Vector(float(cx), float(cy), 0),
            App.Vector(0, 0, 1), float(r)), False)
        return self.sketch_state(sketch)

    def sketch_move(self, sketch, geo, point, x, y):
        """Drag: move one point, let the solver follow. ``point`` is the
        Sketcher convention — 1 start, 2 end, 3 center, 0 whole curve."""
        sk = self._get_sketch(sketch)
        try:
            sk.movePoint(int(geo), int(point),
                         self._app().Vector(float(x), float(y), 0), 0)
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_dim(self, sketch, geo, value=None):
        """Smart dimension: length on a line, radius on a circle.

        Driving, SolidWorks-style: dimension it and the geometry obeys.
        """
        import Sketcher
        sk = self._get_sketch(sketch)
        gid = int(geo)
        if gid < 0 or gid >= len(sk.Geometry):
            raise KernelError("géométrie inconnue : {}".format(geo))
        target = sk.Geometry[gid]
        try:
            if target.TypeId == "Part::GeomLineSegment":
                length = (value if value is not None
                          else target.StartPoint.distanceToPoint(
                              target.EndPoint))
                sk.addConstraint(Sketcher.Constraint(
                    "Distance", gid, float(length)))
            elif target.TypeId == "Part::GeomCircle":
                radius = value if value is not None else target.Radius
                sk.addConstraint(Sketcher.Constraint(
                    "Radius", gid, float(radius)))
            else:
                raise KernelError("cote non gérée sur ce type de géométrie")
        except KernelError:
            raise
        except Exception as exc:  # noqa: BLE001 - over-constrained, mostly
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_set_dim(self, sketch, dim, value):
        """Edit a dimension's value — the double-click-a-dim gesture."""
        sk = self._get_sketch(sketch)
        try:
            sk.setDatum(int(dim), float(value))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_delete_geo(self, sketch, geo):
        sk = self._get_sketch(sketch)
        try:
            sk.delGeometry(int(geo))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_finish(self, sketch):
        """Close the sketch: recompute and hand back the feature tree."""
        self._get_sketch(sketch)
        self._recompute()
        return self.get_tree()

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

        # M2: draw a rectangle line by line the way the viewport does —
        # auto-constraints, a driving dimension, a solver-followed drag —
        # then pad the drawn profile.
        state = self.sketch_start()
        name = state["sketch"]
        self.sketch_add_line(name, 0, 0, 80, 0)
        self.sketch_add_line(name, 80, 0, 80, 40)
        self.sketch_add_line(name, 80, 40, 0, 40)
        state = self.sketch_add_line(name, 0, 40, 0, 0)
        constraints = len(self._get_sketch(name).Constraints)
        # 4 lines snapped into a loop: 4 coincidents + 2 H + 2 V expected.
        report["m2_autoconstraints"] = constraints
        report["m2_autoconstraints_ok"] = constraints >= 8
        state = self.sketch_move(name, 1, 2, 85, 45)
        state = self.sketch_dim(name, 0)
        dim = max(d["id"] for d in state["dims"])
        state = self.sketch_set_dim(name, dim, 90)
        report["m2_dim_drives"] = any(
            abs(d["value"] - 90) < 1e-6 for d in state["dims"])
        report["m2_dof"] = state["dof"]
        self.sketch_finish(name)
        tree = self.add_pad(8, sketch=name)
        report["m2_pad_on_drawn_sketch_ok"] = not any(
            f["error"] for f in tree["features"])

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
