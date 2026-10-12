"""Calques d'esquisse : des groupes nommés d'entités, avec une couleur et
une visibilité. Un calque masqué cache ses entités à l'écran (elles
restent dans l'esquisse et dans le profil, comme dans les modeleurs
usuels).

Rangés sur l'esquisse (propriété ``FreeSolidLayers``, JSON) : la liste
des calques et, pour chaque entité, le nom de son calque — repérée par
son identifiant stable FreeCAD (il survit aux suppressions qui décalent
les numéros). Les imports FreeCAD restent dans les méthodes ;
``normalize_layers`` est testée en CI.
"""

import json
import re

_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


class LayerError(ValueError):
    """Liste de calques refusée."""


def normalize_layers(layers):
    """Calques valides : noms uniques non vides, couleur « #rrggbb » ou
    vide, visibilité booléenne. ``rename`` (ancien nom) est gardé pour
    reporter les entités. Lève LayerError sinon."""
    out, seen = [], set()
    for item in layers or ():
        if not isinstance(item, dict):
            raise LayerError("calque invalide")
        name = str(item.get("name", "")).strip()
        if not name:
            raise LayerError("un calque a besoin d'un nom")
        if name in seen:
            raise LayerError("deux calques portent le même nom : {}".format(
                name))
        seen.add(name)
        color = str(item.get("color", "") or "")
        if color and not _COLOR.match(color):
            raise LayerError("couleur invalide : {}".format(color))
        layer = {"name": name, "color": color,
                 "visible": bool(item.get("visible", True))}
        if item.get("rename"):
            layer["rename"] = str(item["rename"])
        out.append(layer)
    return out


def remap_assignments(assign, layers):
    """Affectations après une nouvelle liste de calques : un calque
    renommé emporte ses entités, un calque disparu les rend au calque
    par défaut."""
    renames = {layer["rename"]: layer["name"] for layer in layers
               if layer.get("rename")}
    names = {layer["name"] for layer in layers}
    out = {}
    for key, name in (assign or {}).items():
        name = renames.get(name, name)
        if name in names:
            out[key] = name
    return out


class SketchLayersMixin:
    """Ops des calques d'esquisse (voir le docstring du module)."""

    @staticmethod
    def _layer_data(sk):
        raw = getattr(sk, "FreeSolidLayers", "") or ""
        try:
            data = json.loads(raw) if raw else {}
        except ValueError:
            data = {}
        return {"layers": list(data.get("layers") or []),
                "assign": dict(data.get("assign") or {})}

    @staticmethod
    def _store_layers(sk, data):
        if "FreeSolidLayers" not in sk.PropertiesList:
            sk.addProperty("App::PropertyString", "FreeSolidLayers",
                           "FreeSolid")
            sk.setEditorMode("FreeSolidLayers", 2)
        sk.FreeSolidLayers = json.dumps(data)

    @staticmethod
    def _geo_key(sk, gid):
        """Clé stable d'une entité (identifiant FreeCAD, sinon l'index)."""
        try:
            return str(sk.getGeometryId(int(gid)))
        except Exception:  # noqa: BLE001
            return "i%d" % int(gid)

    def _layer_of(self, sk, data, gid):
        return data["assign"].get(self._geo_key(sk, gid), "")

    def sketch_layers(self, sketch, layers=None):
        """Les calques de l'esquisse ; avec ``layers`` (liste de
        {name, color, visible, rename?}), les remplace."""
        from engine.kernel import KernelError
        sk = self._get_sketch(sketch)
        data = self._layer_data(sk)
        if layers is not None:
            try:
                clean = normalize_layers(layers)
            except LayerError as exc:
                raise KernelError(str(exc))
            data["assign"] = remap_assignments(data["assign"], clean)
            data["layers"] = [{k: v for k, v in layer.items()
                               if k != "rename"} for layer in clean]
            self._store_layers(sk, data)
        return self.sketch_state(sketch)

    def sketch_set_layer(self, sketch, geos, layer=""):
        """Range des entités sur un calque (``""`` : calque par défaut)."""
        from engine.kernel import KernelError
        sk = self._get_sketch(sketch)
        data = self._layer_data(sk)
        layer = str(layer or "")
        if layer and layer not in {l["name"] for l in data["layers"]}:
            raise KernelError("calque inconnu : {}".format(layer))
        ids = [int(g) for g in (geos or ())]
        if not ids or any(not 0 <= g < len(sk.Geometry) for g in ids):
            raise KernelError("sélectionnez les entités à ranger")
        for gid in ids:
            key = self._geo_key(sk, gid)
            if layer:
                data["assign"][key] = layer
            else:
                data["assign"].pop(key, None)
        self._store_layers(sk, data)
        return self.sketch_state(sketch)
