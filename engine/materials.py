"""Matières et couleurs de face.

Une matière se pose sur un corps : son nom, sa masse volumique (g/cm³),
sa teinte. Les propriétés de masse la prennent par défaut. La teinte
devient la couleur du corps, sauf si l'utilisateur en a choisi une.
Une face peut aussi recevoir sa propre couleur, pour l'affichage.

Rangées sur le corps (``FreeSolidMaterial``, ``FreeSolidDensity``,
``FreeSolidFaceColors`` en JSON). Valeurs usuelles, arrondies, de
catalogues génériques. Les imports FreeCAD restent dans les méthodes ;
``LIBRARY``, ``material_by_id`` et ``clean_face_colors`` sont testées en
CI.
"""

import json
import re

#: (identifiant, nom, masse volumique en g/cm³, teinte d'affichage).
LIBRARY = [
    ("steel", "Acier", 7.85, "#8c939b"),
    ("stainless", "Acier inoxydable", 8.0, "#b4bac1"),
    ("cast_iron", "Fonte", 7.2, "#5d6268"),
    ("aluminium", "Aluminium", 2.70, "#c7ccd2"),
    ("brass", "Laiton", 8.5, "#c9a64a"),
    ("copper", "Cuivre", 8.96, "#c27a4b"),
    ("titanium", "Titane", 4.43, "#9da3a6"),
    ("pla", "PLA", 1.24, "#e8e3d4"),
    ("petg", "PETG", 1.27, "#9fc3d8"),
    ("abs", "ABS", 1.04, "#d9d6cf"),
    ("nylon", "Polyamide (nylon)", 1.14, "#ece8dc"),
    ("polycarbonate", "Polycarbonate", 1.20, "#c5d8e6"),
    ("oak", "Bois (chêne)", 0.75, "#a87b4f"),
    ("glass", "Verre", 2.5, "#bcd9de"),
]

_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def material_by_id(material_id):
    """Entrée de la bibliothèque, ou None."""
    return next((m for m in LIBRARY if m[0] == material_id), None)


def clean_face_colors(colors):
    """{numéro de face (texte): "#rrggbb"} valide ; le reste est écarté."""
    out = {}
    for key, value in (colors or {}).items():
        try:
            face = int(key)
        except (TypeError, ValueError):
            continue
        if face >= 0 and isinstance(value, str) and _COLOR.match(value):
            out[str(face)] = value.lower()
    return out


class MaterialsMixin:
    """Ops : bibliothèque, matière d'un corps, couleur de face."""

    def material_library(self):
        """Les matières proposées, nommées dans la langue de la requête."""
        return {"materials": [
            {"id": mid, "name": self._t(name), "density": density,
             "color": color}
            for mid, name, density, color in LIBRARY]}

    def _material_of(self, body):
        """{id, name, density} de la matière du corps, ou None."""
        mid = getattr(body, "FreeSolidMaterial", "") or ""
        if not mid:
            return None
        known = material_by_id(mid)
        density = float(getattr(body, "FreeSolidDensity", 0) or 0)
        name = self._t(known[1]) if known else self._t("Matière personnalisée")
        return {"id": mid, "name": name,
                "density": density or (known[2] if known else 1.0)}

    def set_body_material(self, body, material="", density=None):
        """Pose une matière de la bibliothèque (``material``), une matière
        personnalisée (``custom`` et ``density``), ou retire la matière
        (``""``)."""
        from engine.kernel import KernelError
        doc = self._require_doc()
        obj = doc.getObject(str(body))
        if obj is None or obj.TypeId != "PartDesign::Body":
            raise KernelError("corps inconnu : {}".format(body))
        material = str(material or "")
        known = material_by_id(material)
        if material == "custom":
            try:
                value = float(density)
            except (TypeError, ValueError):
                value = 0.0
            if value <= 0:
                raise KernelError("masse volumique invalide")
        elif material and known is None:
            raise KernelError("matière inconnue : {}".format(material))
        for prop, kind in (("FreeSolidMaterial", "App::PropertyString"),
                           ("FreeSolidDensity", "App::PropertyFloat"),
                           ("FreeSolidTinted", "App::PropertyBool")):
            if prop not in obj.PropertiesList:
                obj.addProperty(kind, prop, "FreeSolid")
                obj.setEditorMode(prop, 2)
        obj.FreeSolidMaterial = material
        obj.FreeSolidDensity = (value if material == "custom"
                                else known[2] if known else 0.0)
        # La teinte suit la matière tant que l'utilisateur n'a pas choisi
        # lui-même la couleur du corps.
        own = getattr(obj, "FreeSolidColor", "") and not obj.FreeSolidTinted
        if not own:
            tint = known[3] if known else ""
            if "FreeSolidColor" not in obj.PropertiesList:
                obj.addProperty("App::PropertyString", "FreeSolidColor",
                                "FreeSolid", "Couleur d'affichage")
            obj.FreeSolidColor = tint
            obj.FreeSolidTinted = bool(tint)
        return self.get_tree()

    def _face_colors(self, body):
        raw = getattr(body, "FreeSolidFaceColors", "") or ""
        try:
            return clean_face_colors(json.loads(raw) if raw else {})
        except ValueError:
            return {}

    def set_face_color(self, faces, color=None):
        """Couleur d'affichage de faces du corps actif (``None`` : celle du
        corps). Les numéros sont ceux de la vue ; une fonction qui change
        la topologie peut les déplacer."""
        from engine.kernel import KernelError, parse_body_color
        body = self._require_body()
        shape = getattr(body, "Shape", None)
        count = len(shape.Faces) if shape is not None else 0
        ids = [int(f) for f in faces or ()]
        if not ids or any(not 0 <= f < count for f in ids):
            raise KernelError("cliquez les faces à colorer")
        value = parse_body_color(color)
        colors = self._face_colors(body)
        for face in ids:
            if value:
                colors[str(face)] = value
            else:
                colors.pop(str(face), None)
        if "FreeSolidFaceColors" not in body.PropertiesList:
            body.addProperty("App::PropertyString", "FreeSolidFaceColors",
                             "FreeSolid")
            body.setEditorMode("FreeSolidFaceColors", 2)
        body.FreeSolidFaceColors = json.dumps(colors)
        return self.get_tree()
