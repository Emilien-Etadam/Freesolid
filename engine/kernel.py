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
        self._doc.UndoMode = 1  # les transactions de dispatch() = un Ctrl+Z
        self._body = self._doc.addObject("PartDesign::Body", "Body")
        self._body.Label = name
        self._recompute()
        return self.get_tree()

    def undo(self):
        """Annuler la dernière opération — une transaction par op UI."""
        doc = self._require_doc()
        if not doc.UndoNames:
            raise KernelError("rien à annuler")
        doc.undo()
        doc.recompute()
        return self.get_tree()

    def redo(self):
        doc = self._require_doc()
        if not doc.RedoNames:
            raise KernelError("rien à rétablir")
        doc.redo()
        doc.recompute()
        return self.get_tree()

    def export_part(self, path):
        """Export STL (impression 3D) ou STEP (échange CAO), par extension.

        Exports the body's current shape — what the viewport shows is what
        the printer gets.
        """
        body = self._require_body()
        shape = getattr(body, "Shape", None)
        if shape is None or not shape.Solids:
            raise KernelError("rien à exporter — la pièce n'a pas de solide")
        path = os.path.expanduser(str(path))
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".stl":
                shape.exportStl(path)
            elif ext in (".step", ".stp"):
                shape.exportStep(path)
            else:
                raise KernelError("format inconnu « {} » — utilisez .stl ou "
                                  ".step".format(ext or "aucune extension"))
        except KernelError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return {"path": path, "size": os.path.getsize(path)}

    #: Wire names for the body's origin planes — Dessus/Face/Droite in the
    #: client, following vocab.ORIGIN_PLANES (FreeCAD is Z-up).
    _PLANE_ROLES = {"XY": "XY_Plane", "XZ": "XZ_Plane", "YZ": "YZ_Plane"}

    def _origin_feature(self, role):
        """One of the body's origin planes/axes, by role (XY_Plane, Z_Axis…)."""
        body = self._require_body()
        origin = getattr(body, "Origin", None)
        features = getattr(origin, "OriginFeatures", None) or ()
        for feature in features:
            if getattr(feature, "Role", "") == role:
                return feature
        raise KernelError("élément d'origine introuvable : {}".format(role))

    def _attach_to_support(self, sketch, support):
        try:
            sketch.AttachmentSupport = support
        except AttributeError:
            sketch.Support = support
        sketch.MapMode = "FlatFace"

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
        self._attach_to_support(
            sketch, [(tip, ("Face{}".format(int(face_id) + 1),))])

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

    def add_pad(self, length, sketch=None, reversed=False, midplane=False):
        body = self._require_body()
        doc = self._require_doc()
        if sketch is not None:
            profile = self._get_sketch(sketch)
        else:
            profile = self._latest_sketch()
        pad = body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = profile
        pad.Length = float(length)
        if reversed:
            pad.Reversed = True
        if midplane:
            pad.Midplane = True  # « plan milieu » : symétrique au plan
        pad.Label = "Bossage extrudé"
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(pad.Name)
            raise
        return self.get_tree()

    def _latest_sketch(self):
        """The newest sketch not yet consumed by a feature.

        Root cause of the "passage esquisse → extrusion" confusion: reusing
        an already-extruded profile fails downstream with a cryptic error.
        A profile is used once; the next feature takes the next fresh
        sketch, exactly the SolidWorks mental model.
        """
        body = self._require_body()
        used = set()
        for obj in body.Group:
            profile = getattr(obj, "Profile", None)
            linked = profile[0] if isinstance(profile, tuple) else profile
            if linked is not None:
                used.add(linked.Name)
        sketches = [o for o in body.Group
                    if o.TypeId == "Sketcher::SketchObject"
                    and o.Name not in used]
        if not sketches:
            raise KernelError(
                "aucune esquisse disponible — les esquisses existantes "
                "sont déjà utilisées par des fonctions, dessinez-en une "
                "nouvelle")
        return sketches[-1]

    def add_pocket(self, length=None, through=False, reversed=False):
        """Cut with the latest sketch — Extruded Cut, in SolidWorks terms.

        No length (or ``through``) means « À travers tout » — the option a
        SolidWorks hand reaches for by default on a cut.
        """
        body = self._require_body()
        doc = self._require_doc()
        pocket = body.newObject("PartDesign::Pocket", "Pocket")
        pocket.Profile = self._latest_sketch()
        if through or length is None:
            pocket.Type = "ThroughAll"
        else:
            pocket.Length = float(length)
        if reversed:
            pocket.Reversed = True
        pocket.Label = "Enlèvement de matière"
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(pocket.Name)
            raise
        return self.get_tree()

    #: Ops the yellow ghost preview may run speculatively.
    _PREVIEWABLE = frozenset({
        "add_pad", "add_pocket", "add_revolution", "add_groove",
        "add_fillet", "add_chamfer", "add_thickness", "add_draft",
        "add_mirror", "add_linear_pattern", "add_polar_pattern",
    })

    def preview(self, op, params):
        """Aperçu jaune : exécute la fonction, tesselle, puis annule tout.

        The op runs inside its own transaction which is always aborted —
        the document comes back exactly as it was, whatever happened. The
        client renders the returned mesh as the SolidWorks-style ghost.
        """
        doc = self._require_doc()
        if op not in self._PREVIEWABLE:
            raise KernelError(
                "aperçu non disponible pour {}".format(op))
        if not isinstance(params, dict):
            raise KernelError("params doit être un objet JSON")
        doc.openTransaction("freesolid-preview")
        try:
            getattr(self, op)(**params)
            return self.tessellate()
        finally:
            try:
                doc.abortTransaction()
            except Exception:
                pass
            doc.recompute()

    # -- palier 2 : révolutions, transformations, habillages avancés ------

    def _revolved(self, type_id, angle, sketch):
        """Revolution/Groove share everything but add-vs-cut.

        The axis is the sketch's own vertical axis — draw the profile beside
        it, exactly the SolidWorks revolve reflex.
        """
        body = self._require_body()
        doc = self._require_doc()
        profile = (self._get_sketch(sketch) if sketch is not None
                   else self._latest_sketch())
        feature = body.newObject(type_id, type_id.split("::")[-1])
        feature.Profile = profile
        feature.ReferenceAxis = (profile, ["V_Axis"])
        feature.Angle = float(angle)
        feature.Label = label_for_type(type_id)
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(feature.Name)
            raise
        return self.get_tree()

    def add_revolution(self, angle=360.0, sketch=None):
        """Bossage/Base avec révolution, autour de l'axe vertical de
        l'esquisse."""
        return self._revolved("PartDesign::Revolution", angle, sketch)

    def add_groove(self, angle=360.0, sketch=None):
        """Enlèvement de matière avec révolution."""
        return self._revolved("PartDesign::Groove", angle, sketch)

    _AXIS_ROLES = {"X": "X_Axis", "Y": "Y_Axis", "Z": "Z_Axis"}

    def _last_solid_feature(self):
        """The feature a pattern/mirror duplicates: the latest add/sub one.

        Dress-ups and other transforms don't qualify — PartDesign patterns
        transform additive/subtractive features.
        """
        body = self._require_body()
        features = [o for o in body.Group
                    if o.isDerivedFrom("PartDesign::FeatureAddSub")]
        if not features:
            raise KernelError("aucune fonction à répéter — créez d'abord "
                              "un bossage ou un enlèvement de matière")
        return features[-1]

    def _transform(self, type_id, configure):
        body = self._require_body()
        doc = self._require_doc()
        original = self._last_solid_feature()
        feature = body.newObject(type_id, type_id.split("::")[-1])
        feature.Originals = [original]
        configure(feature)
        feature.Label = label_for_type(type_id)
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(feature.Name)
            raise
        return self.get_tree()

    def add_mirror(self, plane="YZ"):
        """Symétrie de la dernière fonction par rapport à un plan
        d'origine (XY/XZ/YZ = Dessus/Face/Droite)."""
        role = self._PLANE_ROLES.get(str(plane).upper())
        if role is None:
            raise KernelError(
                "plan inconnu « {} » — attendu XY, XZ ou YZ".format(plane))
        plane_obj = self._origin_feature(role)

        def configure(feature):
            feature.MirrorPlane = (plane_obj, [""])
        return self._transform("PartDesign::Mirrored", configure)

    def _origin_axis(self, axis):
        role = self._AXIS_ROLES.get(str(axis).upper())
        if role is None:
            raise KernelError(
                "axe inconnu « {} » — attendu X, Y ou Z".format(axis))
        return self._origin_feature(role)

    def add_linear_pattern(self, length, count, axis="X"):
        """Répétition linéaire de la dernière fonction le long d'un axe.

        ``length`` is the total span, occurrences included — FreeCAD's
        convention, same as SolidWorks' « jusqu'à » spacing mode.
        """
        axis_obj = self._origin_axis(axis)
        occurrences = int(count)
        if occurrences < 2:
            raise KernelError("au moins 2 occurrences")

        def configure(feature):
            feature.Direction = (axis_obj, [""])
            feature.Length = float(length)
            feature.Occurrences = occurrences
        return self._transform("PartDesign::LinearPattern", configure)

    def add_polar_pattern(self, count, angle=360.0, axis="Z"):
        """Répétition circulaire de la dernière fonction autour d'un axe."""
        axis_obj = self._origin_axis(axis)
        occurrences = int(count)
        if occurrences < 2:
            raise KernelError("au moins 2 occurrences")

        def configure(feature):
            feature.Axis = (axis_obj, [""])
            feature.Angle = float(angle)
            feature.Occurrences = occurrences
        return self._transform("PartDesign::PolarPattern", configure)

    def add_thickness(self, face, thickness):
        """Coque : évide la pièce, la face cliquée devient l'ouverture."""
        return self._dressup("PartDesign::Thickness",
                             label_for_type("PartDesign::Thickness"),
                             face, "Value", thickness)

    def add_draft(self, face, angle):
        """Dépouille de la face cliquée ; plan neutre : Plan de dessus."""
        body = self._require_body()
        doc = self._require_doc()
        tip = getattr(body, "Tip", None)
        if tip is None:
            raise KernelError("pas de solide à dépouiller")
        feature = body.newObject("PartDesign::Draft", "Draft")
        feature.Base = (tip, ["Face{}".format(int(face) + 1)])
        feature.Angle = float(angle)
        feature.NeutralPlane = (self._origin_feature("XY_Plane"), [""])
        feature.Label = label_for_type("PartDesign::Draft")
        try:
            self._recompute()
        except KernelError:
            doc.removeObject(feature.Name)
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
    _EDITABLE_PROPS = ("Length", "Radius", "Size", "Angle", "Thickness",
                       "Value", "Occurrences")

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
        doc.UndoMode = 1
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
        current = getattr(obj, prop, None)
        if isinstance(current, int) and not isinstance(current, bool):
            value = int(value)  # Occurrences : FreeCAD refuse 4.0
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

    def sketch_start(self, face=None, plane=None):
        """Open a new empty sketch — XY by default, a picked face, or a
        named origin plane (XY/XZ/YZ = Dessus/Face/Droite)."""
        body = self._require_body()
        doc = self._require_doc()
        sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
        body.addObject(sketch)
        sketch.Label = "Esquisse"
        if face is not None:
            self._attach_to_face(sketch, face)
        elif plane is not None:
            role = self._PLANE_ROLES.get(str(plane).upper())
            if role is None:
                raise KernelError(
                    "plan inconnu « {} » — attendu XY, XZ ou YZ".format(plane))
            self._attach_to_support(
                sketch, [(self._origin_feature(role), ("",))])
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
                entity = {
                    "id": gid, "type": "line",
                    "p1": [geo.StartPoint.x, geo.StartPoint.y],
                    "p2": [geo.EndPoint.x, geo.EndPoint.y]}
            elif geo.TypeId == "Part::GeomCircle":
                entity = {
                    "id": gid, "type": "circle",
                    "c": [geo.Center.x, geo.Center.y],
                    "r": float(geo.Radius)}
            elif geo.TypeId == "Part::GeomArcOfCircle":
                entity = {
                    "id": gid, "type": "arc",
                    "c": [geo.Center.x, geo.Center.y],
                    "r": float(geo.Radius),
                    "p1": [geo.StartPoint.x, geo.StartPoint.y],
                    "p2": [geo.EndPoint.x, geo.EndPoint.y]}
            else:
                entity = {"id": gid, "type": "other", "kind": geo.TypeId}
            entity["construction"] = self._is_construction(sk, gid, geo)
            entities.append(entity)
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

    @staticmethod
    def _endpoints_of(geo):
        """(Sketcher pos, point) pairs a snap can land on — lines and arcs."""
        if geo.TypeId in ("Part::GeomLineSegment", "Part::GeomArcOfCircle"):
            return ((1, geo.StartPoint), (2, geo.EndPoint))
        return ()

    def _auto_constrain(self, sk, gid):
        """The SolidWorks reflexes: snap becomes coincident, near-axis
        becomes horizontal/vertical.

        The client decides (it snapped and sent exact coordinates); this
        turns that decision into constraints so the solver holds it.
        """
        import Sketcher
        C = Sketcher.Constraint
        geo = sk.Geometry[gid]
        for pos, point in self._endpoints_of(geo):
            for other in range(len(sk.Geometry)):
                if other == gid:
                    continue
                matched = False
                for opos, opoint in self._endpoints_of(sk.Geometry[other]):
                    if point.distanceToPoint(opoint) < self._SNAP_TOL:
                        sk.addConstraint(C("Coincident", gid, pos,
                                           other, opos))
                        matched = True
                        break
                if matched:
                    break
        if geo.TypeId != "Part::GeomLineSegment":
            return
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
        self._auto_constrain(sk, gid)
        return self.sketch_state(sketch)

    def sketch_add_arc(self, sketch, cx, cy, r, a1, a2):
        """Arc de cercle — angles en radians, sens trigonométrique."""
        import Part
        sk = self._get_sketch(sketch)
        if float(r) <= 0:
            raise KernelError("le rayon doit être positif")
        App = self._app()
        circle = Part.Circle(App.Vector(float(cx), float(cy), 0),
                             App.Vector(0, 0, 1), float(r))
        gid = sk.addGeometry(
            Part.ArcOfCircle(circle, float(a1), float(a2)), False)
        self._auto_constrain(sk, gid)
        return self.sketch_state(sketch)

    def sketch_add_slot(self, sketch, x1, y1, x2, y2, width):
        """Rainure droite : deux arcs + deux lignes, tangences et rayons
        égaux posés d'emblée — le contour reste une rainure sous le solveur.
        """
        import math
        import Part
        import Sketcher
        sk = self._get_sketch(sketch)
        w = float(width)
        p1x, p1y, p2x, p2y = (float(v) for v in (x1, y1, x2, y2))
        if w <= 0:
            raise KernelError("la largeur doit être positive")
        if math.hypot(p2x - p1x, p2y - p1y) < 1e-9:
            raise KernelError("les deux centres de la rainure sont confondus")
        r = w / 2.0
        theta = math.atan2(p2y - p1y, p2x - p1x)
        ux, uy = math.cos(theta + math.pi / 2), math.sin(theta + math.pi / 2)
        V = self._app().Vector
        z_axis = V(0, 0, 1)
        base = len(sk.Geometry)
        # Cap at p2 (CCW through +direction), top line, cap at p1, bottom.
        sk.addGeometry(Part.ArcOfCircle(
            Part.Circle(V(p2x, p2y, 0), z_axis, r),
            theta - math.pi / 2, theta + math.pi / 2), False)
        sk.addGeometry(Part.LineSegment(
            V(p2x + r * ux, p2y + r * uy, 0),
            V(p1x + r * ux, p1y + r * uy, 0)), False)
        sk.addGeometry(Part.ArcOfCircle(
            Part.Circle(V(p1x, p1y, 0), z_axis, r),
            theta + math.pi / 2, theta + 3 * math.pi / 2), False)
        sk.addGeometry(Part.LineSegment(
            V(p1x - r * ux, p1y - r * uy, 0),
            V(p2x - r * ux, p2y - r * uy, 0)), False)
        C = Sketcher.Constraint
        try:
            # Endpoint-to-endpoint tangency implies coincidence: the
            # standard Sketcher slot recipe.
            sk.addConstraint(C("Tangent", base + 0, 2, base + 1, 1))
            sk.addConstraint(C("Tangent", base + 1, 2, base + 2, 1))
            sk.addConstraint(C("Tangent", base + 2, 2, base + 3, 1))
            sk.addConstraint(C("Tangent", base + 3, 2, base + 0, 1))
            sk.addConstraint(C("Equal", base + 0, base + 2))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_add_polygon(self, sketch, cx, cy, x, y, sides):
        """Polygone régulier (centre + un sommet), via l'outil Sketcher."""
        sk = self._get_sketch(sketch)
        n = int(sides)
        if n < 3:
            raise KernelError("un polygone a au moins 3 côtés")
        try:
            from ProfileLib import RegularPolygon
        except ImportError:
            raise KernelError("outil polygone indisponible sur cette "
                              "version de FreeCAD")
        V = self._app().Vector
        center = V(float(cx), float(cy), 0)
        corner = V(float(x), float(y), 0)
        try:
            RegularPolygon.makeRegularPolygon(sk, n, center, corner, False)
        except TypeError:
            RegularPolygon.makeRegularPolygon(sk, n, center, corner)
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_fillet(self, sketch, geo1, geo2, x1, y1, x2, y2, radius):
        """Congé d'esquisse entre deux lignes, aux points cliqués."""
        sk = self._get_sketch(sketch)
        if float(radius) <= 0:
            raise KernelError("le rayon doit être positif")
        V = self._app().Vector
        try:
            sk.fillet(int(geo1), int(geo2),
                      V(float(x1), float(y1), 0), V(float(x2), float(y2), 0),
                      float(radius))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    def sketch_trim(self, sketch, geo, x, y):
        """Ajuster : supprime le tronçon cliqué jusqu'aux intersections."""
        sk = self._get_sketch(sketch)
        V = self._app().Vector
        try:
            sk.trim(int(geo), V(float(x), float(y), 0))
        except Exception as exc:  # noqa: BLE001
            raise KernelError(_explain(exc))
        return self.sketch_state(sketch)

    #: kind -> (Sketcher name, arité, exige des points)
    _CONSTRAINT_KINDS = {
        "horizontal": ("Horizontal", 1, False),
        "vertical": ("Vertical", 1, False),
        "parallel": ("Parallel", 2, False),
        "perpendicular": ("Perpendicular", 2, False),
        "equal": ("Equal", 2, False),
        "tangent": ("Tangent", 2, False),
        "coincident": ("Coincident", 2, True),
    }

    def sketch_constrain(self, sketch, kind, geo1,
                         point1=None, geo2=None, point2=None):
        """Contrainte manuelle. Points au sens Sketcher : 1 départ, 2 fin,
        3 centre — requis pour coincident."""
        import Sketcher
        sk = self._get_sketch(sketch)
        spec = self._CONSTRAINT_KINDS.get(str(kind))
        if spec is None:
            raise KernelError(
                "contrainte inconnue « {} » — attendu : {}".format(
                    kind, ", ".join(sorted(self._CONSTRAINT_KINDS))))
        name, arity, needs_points = spec
        if arity == 2 and geo2 is None:
            raise KernelError(
                "{} : sélectionnez deux entités".format(kind))
        try:
            if needs_points:
                if point1 is None or point2 is None:
                    raise KernelError("coïncidence : cliquez deux points "
                                      "(extrémités ou centres)")
                sk.addConstraint(Sketcher.Constraint(
                    name, int(geo1), int(point1), int(geo2), int(point2)))
            elif arity == 1:
                sk.addConstraint(Sketcher.Constraint(name, int(geo1)))
            else:
                sk.addConstraint(Sketcher.Constraint(
                    name, int(geo1), int(geo2)))
        except KernelError:
            raise
        except Exception as exc:  # noqa: BLE001 - over-constrained, mostly
            raise KernelError(_explain(exc))
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
        Sketcher convention — 1 start, 2 end, 3 center, 0 whole curve.

        The API was renamed across FreeCAD versions (movePoint →
        moveGeometry, plus a grouped moveGeometries), so this tries the
        known spellings in order — 1.1.3 has no ``movePoint`` at all,
        which the instrumented selftest caught on a real install.
        """
        sk = self._get_sketch(sketch)
        gid, pos = int(geo), int(point)
        target = self._app().Vector(float(x), float(y), 0)
        attempts = (
            ("moveGeometry", lambda fn: fn(gid, pos, target, 0)),
            ("movePoint", lambda fn: fn(gid, pos, target, 0)),
            ("moveGeometries", lambda fn: fn([(gid, pos)], target, False)),
        )
        tried = []
        for name, invoke in attempts:
            fn = getattr(sk, name, None)
            if fn is None:
                continue
            tried.append(name)
            try:
                invoke(fn)
                return self.sketch_state(sketch)
            except TypeError:
                continue  # exists but wants another signature: next spelling
            except Exception as exc:  # noqa: BLE001 - solver refusal
                raise KernelError(_explain(exc))
        raise KernelError(
            "aucune API de déplacement compatible sur cette version de "
            "FreeCAD (essayé : {})".format(", ".join(tried) or "aucune"))

    @staticmethod
    def _point_of(geo, pos):
        """Sketcher point convention: 1 start, 2 end, 3 center."""
        if pos == 3:
            return geo.Center
        if pos == 2:
            return geo.EndPoint
        return geo.StartPoint

    @staticmethod
    def _distance_point_line(p, a, b):
        import math
        abx, aby = b.x - a.x, b.y - a.y
        denominator = math.hypot(abx, aby)
        if denominator < 1e-12:
            return 0.0
        return abs(abx * (p.y - a.y) - aby * (p.x - a.x)) / denominator

    def _dim_two(self, sk, g1, g2, point, point2, value):
        """Smart dimension between two entities — the pair decides the
        constraint, as under the SolidWorks cursor: two points → distance,
        point + line → distance, parallel lines → distance, otherwise angle
        (radians on the wire; the client displays degrees)."""
        import math
        import Sketcher
        C = Sketcher.Constraint
        if point is None and point2 is not None:
            # Normalize "line then point" to "point then line".
            g1, g2 = g2, g1
            point, point2 = point2, None
        e1, e2 = sk.Geometry[g1], sk.Geometry[g2]
        line = "Part::GeomLineSegment"
        if point is not None and point2 is not None:
            v1 = self._point_of(e1, int(point))
            v2 = self._point_of(e2, int(point2))
            distance = value if value is not None else v1.distanceToPoint(v2)
            return C("Distance", g1, int(point), g2, int(point2),
                     float(distance))
        if point is not None and e2.TypeId == line:
            v1 = self._point_of(e1, int(point))
            distance = (value if value is not None else
                        self._distance_point_line(
                            v1, e2.StartPoint, e2.EndPoint))
            return C("Distance", g1, int(point), g2, float(distance))
        if e1.TypeId == line and e2.TypeId == line:
            d1x = e1.EndPoint.x - e1.StartPoint.x
            d1y = e1.EndPoint.y - e1.StartPoint.y
            d2x = e2.EndPoint.x - e2.StartPoint.x
            d2y = e2.EndPoint.y - e2.StartPoint.y
            cross = d1x * d2y - d1y * d2x
            if abs(cross) < 1e-7 * math.hypot(d1x, d1y) * math.hypot(d2x, d2y):
                distance = (value if value is not None else
                            self._distance_point_line(
                                e1.StartPoint, e2.StartPoint, e2.EndPoint))
                return C("Distance", g1, 1, g2, float(distance))
            angle = (value if value is not None else
                     abs(math.atan2(cross, d1x * d2x + d1y * d2y)))
            return C("Angle", g1, g2, float(angle))
        raise KernelError("cote non gérée entre ces deux entités — "
                          "deux points, un point et une ligne, ou deux "
                          "lignes")

    def sketch_dim(self, sketch, geo, value=None,
                   geo2=None, point=None, point2=None):
        """Smart dimension: length on a line, radius on a circle or arc,
        distance/angle between two entities.

        Driving, SolidWorks-style: dimension it and the geometry obeys.
        """
        import Sketcher
        sk = self._get_sketch(sketch)
        gid = int(geo)
        if gid < 0 or gid >= len(sk.Geometry):
            raise KernelError("géométrie inconnue : {}".format(geo))
        try:
            if geo2 is not None:
                g2 = int(geo2)
                if g2 < 0 or g2 >= len(sk.Geometry):
                    raise KernelError("géométrie inconnue : {}".format(geo2))
                sk.addConstraint(
                    self._dim_two(sk, gid, g2, point, point2, value))
                return self.sketch_state(sketch)
            target = sk.Geometry[gid]
            if target.TypeId == "Part::GeomLineSegment":
                length = (value if value is not None
                          else target.StartPoint.distanceToPoint(
                              target.EndPoint))
                sk.addConstraint(Sketcher.Constraint(
                    "Distance", gid, float(length)))
            elif target.TypeId in ("Part::GeomCircle",
                                   "Part::GeomArcOfCircle"):
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

    def _is_construction(self, sk, gid, geo):
        """Construction flag across API generations: attribute on old
        geometry objects, ``getConstruction`` on 1.x facades."""
        flag = getattr(geo, "Construction", None)
        if flag is not None:
            return bool(flag)
        getter = getattr(sk, "getConstruction", None)
        if getter is not None:
            try:
                return bool(getter(gid))
            except Exception:
                pass
        return False

    def sketch_toggle_construction(self, sketch, geo):
        """Basculer une entité en géométrie de construction, et retour."""
        sk = self._get_sketch(sketch)
        try:
            sk.toggleConstruction(int(geo))
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

    def _side_face_id(self):
        """Selftest helper: any vertical (side) face of the current shape."""
        body = self._require_body()
        for i, face in enumerate(body.Shape.Faces):
            u0, u1, v0, v1 = face.ParameterRange
            normal = face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
            if abs(normal.z) < 0.1:
                return i
        raise KernelError("aucune face latérale")

    def selftest(self):
        """Run the whole flow end to end; return stats worth pasting back.

        Every step prints a live marker to the terminal and any failure
        names the step it died in — a silent selftest is worse than a
        failing one (learned when a user reported "the button does
        nothing").
        """
        report = {"steps": []}

        def mark(name):
            report["steps"].append(name)
            print("selftest> {}".format(name), flush=True)

        try:
            mark("ping")
            report["ping"] = self.ping()

            mark("m0: pièce + esquisse contrainte + bossage")
            self.new_part("Pièce de test")
            self.add_rect_sketch(100, 60)
            tree = self.add_pad(10)
            mesh = self.tessellate()
            report["m0_faces"] = len(mesh["groups"])

            mark("m0: reparamétrage 10 → 25")
            pad = next(f["name"] for f in tree["features"]
                       if f["type"] == "PartDesign::Pad")
            self.set_param(pad, "Length", 25.0)
            report["m0_reparam_ok"] = self.tessellate() != mesh

            mark("m1: esquisse sur face + enlèvement à travers tout + congé")
            top = self._top_face_id()
            report["m1_top_face"] = top
            self.add_rect_sketch(40, 20, face=top)
            self.add_pocket(through=True)
            report["m1_pocket_faces"] = len(self.tessellate()["groups"])
            tree = self.add_fillet(self._top_face_id(), 3)
            report["m1_fillet_ok"] = not any(
                f["error"] for f in tree["features"])

            mark("m1.5: barre de retour aller-retour")
            pad_feature = next(f["name"] for f in tree["features"]
                               if f["type"] == "PartDesign::Pad")
            faces_rolled = len(self.tessellate()["groups"])
            self.set_tip(pad_feature)
            report["m15_rollback_changes_shape"] = (
                len(self.tessellate()["groups"]) != faces_rolled)
            self.tip_to_end()

            mark("m1.5: enregistrer puis rouvrir")
            import tempfile
            path = os.path.join(tempfile.gettempdir(),
                                "freesolid-selftest.FCStd")
            self.save_part(path)
            tree_before = self.get_tree()
            reopened = self.open_part(path)
            report["m15_roundtrip_ok"] = (
                [f["type"] for f in reopened["features"]]
                == [f["type"] for f in tree_before["features"]])

            mark("m2: rectangle dessiné ligne à ligne")
            state = self.sketch_start()
            name = state["sketch"]
            self.sketch_add_line(name, 0, 0, 80, 0)
            self.sketch_add_line(name, 80, 0, 80, 40)
            self.sketch_add_line(name, 80, 40, 0, 40)
            self.sketch_add_line(name, 0, 40, 0, 0)
            constraints = len(self._get_sketch(name).Constraints)
            # 4 snapped lines: 4 coincidents + 2 horizontal + 2 vertical.
            report["m2_autoconstraints"] = constraints
            report["m2_autoconstraints_ok"] = constraints >= 8

            mark("m2: drag suivi par le solveur")
            self.sketch_move(name, 1, 2, 85, 45)

            mark("m2: cote pilotante à 90")
            state = self.sketch_dim(name, 0)
            dim = max(d["id"] for d in state["dims"])
            state = self.sketch_set_dim(name, dim, 90)
            report["m2_dim_drives"] = any(
                abs(d["value"] - 90) < 1e-6 for d in state["dims"])
            report["m2_dof"] = state["dof"]

            mark("m2: extrusion du profil dessiné")
            self.sketch_finish(name)
            tree = self.add_pad(8, sketch=name)
            report["m2_pad_on_drawn_sketch_ok"] = not any(
                f["error"] for f in tree["features"])

            mark("p1: annuler / rétablir via transactions")
            state = self.sketch_start()
            sk_name = state["sketch"]
            out = dispatch(self, "sketch_add_line",
                           {"sketch": sk_name,
                            "x1": 0, "y1": 0, "x2": 10, "y2": 0})
            if not out["ok"]:
                raise KernelError(out["error"])
            count = len(self._get_sketch(sk_name).Geometry)
            self.undo()
            report["p1_undo_ok"] = (
                len(self._get_sketch(sk_name).Geometry) == count - 1)
            self.redo()
            report["p1_redo_ok"] = (
                len(self._get_sketch(sk_name).Geometry) == count)

            mark("p1: géométrie de construction")
            state = self.sketch_toggle_construction(sk_name, 0)
            report["p1_construction_ok"] = bool(
                state["entities"][0].get("construction"))
            self.sketch_finish(sk_name)

            mark("p1: esquisse sur plan nommé (XZ = Plan de face)")
            state = self.sketch_start(plane="XZ")
            identity = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0,
                        0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
            report["p1_plane_ok"] = (
                [round(v, 6) for v in state["placement"]] != identity)
            self.sketch_finish(state["sketch"])

            mark("p1: export STL + STEP")
            stl = os.path.join(tempfile.gettempdir(),
                               "freesolid-selftest.stl")
            step = os.path.join(tempfile.gettempdir(),
                                "freesolid-selftest.step")
            report["p1_export_stl_ok"] = self.export_part(stl)["size"] > 0
            report["p1_export_step_ok"] = self.export_part(step)["size"] > 0

            mark("p2: révolution (tube) + enlèvement avec révolution")
            self.new_part("Pièce révolution")
            state = self.sketch_start()
            rev_sk = state["sketch"]
            for line in ((10, 0, 30, 0), (30, 0, 30, 20),
                         (30, 20, 10, 20), (10, 20, 10, 0)):
                self.sketch_add_line(rev_sk, *line)
            self.sketch_finish(rev_sk)
            tree = self.add_revolution(360, sketch=rev_sk)
            report["p2_revolution_ok"] = not any(
                f["error"] for f in tree["features"])
            state = self.sketch_start()
            groove_sk = state["sketch"]
            for line in ((15, 8, 25, 8), (25, 8, 25, 12),
                         (25, 12, 15, 12), (15, 12, 15, 8)):
                self.sketch_add_line(groove_sk, *line)
            self.sketch_finish(groove_sk)
            tree = self.add_groove(360, sketch=groove_sk)
            report["p2_groove_ok"] = not any(
                f["error"] for f in tree["features"])

            mark("p2: symétrie + répétition linéaire")
            self.new_part("Pièce symétrie")
            state = self.sketch_start()
            sym_sk = state["sketch"]
            for line in ((0, -10, 20, -10), (20, -10, 20, 10),
                         (20, 10, 0, 10), (0, 10, 0, -10)):
                self.sketch_add_line(sym_sk, *line)
            self.sketch_finish(sym_sk)
            self.add_pad(10, sketch=sym_sk)
            tree = self.add_mirror(plane="YZ")
            report["p2_mirror_ok"] = not any(
                f["error"] for f in tree["features"])
            tree = self.add_linear_pattern(length=20, count=2, axis="Y")
            report["p2_linear_pattern_ok"] = not any(
                f["error"] for f in tree["features"])

            mark("p2: répétition circulaire (4 perçages)")
            self.new_part("Pièce répétition")
            self.add_rect_sketch(60, 60)
            self.add_pad(6)
            state = self.sketch_start(face=self._top_face_id())
            pat_sk = state["sketch"]
            self.sketch_add_circle(pat_sk, 20, 0, 4)
            self.sketch_finish(pat_sk)
            self.add_pocket(through=True)
            tree = self.add_polar_pattern(count=4)
            report["p2_polar_pattern_ok"] = not any(
                f["error"] for f in tree["features"])

            mark("p2: dépouille + coque")
            self.new_part("Pièce coque")
            self.add_rect_sketch(40, 40)
            self.add_pad(20)
            tree = self.add_draft(face=self._side_face_id(), angle=5)
            report["p2_draft_ok"] = not any(
                f["error"] for f in tree["features"])
            tree = self.add_thickness(self._top_face_id(), 2)
            report["p2_thickness_ok"] = not any(
                f["error"] for f in tree["features"])

            mark("p4: aperçu jaune (exécuté puis annulé)")
            count = len(self.get_tree()["features"])
            faces_now = len(self.tessellate()["groups"])
            ghost = self.preview(
                "add_chamfer", {"face": self._top_face_id(), "size": 2})
            report["p4_preview_changes_mesh"] = (
                len(ghost["groups"]) != faces_now)
            report["p4_preview_leaves_doc_intact"] = (
                len(self.get_tree()["features"]) == count
                and len(self.tessellate()["groups"]) == faces_now)

            mark("p3: arc, rainure, polygone")
            import math
            self.new_part("Pièce esquisse avancée")
            state = self.sketch_start()
            adv = state["sketch"]
            state = self.sketch_add_arc(adv, 0, 0, 20, 0, math.pi / 2)
            report["p3_arc_ok"] = state["entities"][-1]["type"] == "arc"
            before = len(state["entities"])
            state = self.sketch_add_slot(adv, 0, -30, 40, -30, 10)
            report["p3_slot_ok"] = len(state["entities"]) == before + 4
            before = len(state["entities"])
            state = self.sketch_add_polygon(adv, 80, 0, 90, 0, 6)
            report["p3_polygon_ok"] = len(state["entities"]) >= before + 6
            self.sketch_finish(adv)

            mark("p3: congé d'esquisse")
            state = self.sketch_start()
            fil = state["sketch"]
            self.sketch_add_line(fil, 0, 0, 40, 0)
            self.sketch_add_line(fil, 40, 0, 40, 30)
            state = self.sketch_fillet(fil, 0, 1, 30, 0, 40, 20, 5)
            report["p3_sketch_fillet_ok"] = any(
                e["type"] == "arc" for e in state["entities"])
            self.sketch_finish(fil)

            mark("p3: ajuster (trim)")
            state = self.sketch_start()
            trm = state["sketch"]
            self.sketch_add_line(trm, 0, 0, 40, 0)      # géo 0
            self.sketch_add_line(trm, 20, -10, 20, 10)  # géo 1, croise en (20,0)
            state = self.sketch_trim(trm, 1, 20, 8)     # coupe la branche haute
            top_ys = [max(e["p1"][1], e["p2"][1])
                      for e in state["entities"] if e["type"] == "line"]
            report["p3_trim_ok"] = all(y < 5 for y in top_ys)
            self.sketch_finish(trm)

            mark("p3: contraintes manuelles + cote à 2 entités")
            state = self.sketch_start()
            con = state["sketch"]
            self.sketch_add_line(con, 0, 0, 30, 2)
            self.sketch_add_line(con, 0, 10, 30, 14)
            self.sketch_constrain(con, "horizontal", 0)
            state = self.sketch_constrain(con, "parallel", 0, geo2=1)
            line0 = next(e for e in state["entities"] if e["id"] == 0)
            report["p3_constrain_ok"] = (
                abs(line0["p1"][1] - line0["p2"][1]) < 1e-6)
            state = self.sketch_dim(con, 0, geo2=1)  # parallèles → distance
            report["p3_dim_distance_ok"] = any(
                d["type"] == "Distance" for d in state["dims"])
            self.sketch_add_line(con, 50, 0, 80, 0)   # géo 2
            self.sketch_add_line(con, 50, 0, 80, 20)  # géo 3, snap en (50,0)
            state = self.sketch_dim(con, 2, geo2=3)   # sécantes → angle
            report["p3_dim_angle_ok"] = any(
                d["type"] == "Angle" for d in state["dims"])
            self.sketch_finish(con)

            mark("bilan")
            # Reopen the saved part so the viewport ends on real geometry,
            # not on the last sketch-only test document.
            self.open_part(path)
            report["tree_after_pad"] = self.get_tree()
            mesh = self.tessellate()
            report["mesh_faces"] = len(mesh["groups"])
            report["mesh_triangles"] = len(mesh["indices"]) // 3
            return report
        except KernelError as exc:
            raise KernelError("échec à l'étape « {} » : {}".format(
                report["steps"][-1], exc))
        except Exception as exc:  # noqa: BLE001 - name the step, always
            raise KernelError("échec à l'étape « {} » : {}".format(
                report["steps"][-1], _explain(exc)))


#: Ops recorded as one undo step each. Left out on purpose: document
#: lifecycle (new/open), read-only ops, undo/redo themselves, and
#: sketch_move — a drag streaming at ~20 Hz would shred the undo stack
#: into per-frame steps.
_TRANSACTIONAL = frozenset({
    "add_rect_sketch", "add_pad", "add_pocket", "add_fillet", "add_chamfer",
    "add_revolution", "add_groove", "add_mirror", "add_linear_pattern",
    "add_polar_pattern", "add_thickness", "add_draft",
    "set_param", "set_tip", "tip_to_end", "delete_feature",
    "sketch_start", "sketch_add_line", "sketch_add_circle", "sketch_dim",
    "sketch_set_dim", "sketch_delete_geo", "sketch_finish",
    "sketch_toggle_construction",
    "sketch_add_arc", "sketch_add_slot", "sketch_add_polygon",
    "sketch_fillet", "sketch_trim", "sketch_constrain",
})


def _abort(doc):
    if doc is None:
        return
    try:
        doc.abortTransaction()
    except Exception:
        pass


def dispatch(kernel: Kernel, op: str, params: dict):
    """Route one validated request to the kernel, normalizing errors.

    Mutating ops run inside a document transaction: one UI action = one
    Ctrl+Z, and a failed op leaves the document as it was.
    """
    from . import protocol
    doc = kernel._doc if op in _TRANSACTIONAL else None
    if doc is not None:
        doc.openTransaction("freesolid-" + op)
    try:
        result = getattr(kernel, op)(**params)
    except KernelError as exc:
        _abort(doc)
        return protocol.err(str(exc))
    except Exception as exc:  # noqa: BLE001 - the envelope is the handler
        _abort(doc)
        return protocol.err(_explain(exc),
                            hint="erreur moteur non traduite — à signaler")
    if doc is not None:
        try:
            doc.commitTransaction()
        except Exception:
            pass
    return protocol.ok(result)
