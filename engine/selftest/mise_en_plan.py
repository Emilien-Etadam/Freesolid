"""Selftest — mise en plan : vues, cotes et coupe en DXF.

Une fonction par étape, dans l'ordre d'exécution ;
``engine/selftest/__init__.py`` fixe l'ordre global.
"""

import os
import tempfile


def p13_mise_en_plan_dxf(self, mark, report, etat):
    mark("p13: mise en plan DXF (3 vues, cotes, coupe)")
    self.new_part("Pièce plan")
    self.add_rect_sketch(30, 20)
    self.add_pad(10)
    dxf = os.path.join(tempfile.gettempdir(),
                       "freesolid-selftest.dxf")
    drawing = self.make_drawing(dxf, dims=True, section="Y")
    report["p13_drawing_ok"] = drawing["size"] > 0
    report["p13_dims_ok"] = drawing.get("dims_ok") is True
    report["p13_section_ok"] = drawing.get("section_ok") is True
    report["p13_drawing_clean_ok"] = not any(
        o.TypeId.startswith("TechDraw::")
        for o in self._require_doc().Objects)
