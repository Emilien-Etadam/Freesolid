"""Surfaces et courbes : extrusion, révolution, lissage, balayage, plane,
remplissage, décalage, prolongement, ajustement, couture, spline 3D.

Mixin de ``Kernel``. Pas d'import FreeCAD au niveau du module :
les méthodes importent le noyau à l'appel, pour éviter un cycle.

Paquet de sous-mixins, un par famille ; ``SurfaceMixin`` les assemble :

- ``commun.py`` : arbre, ajout, tampons de réédition, formes figées ;
- ``simples.py`` : extrusion, révolution, lissage, plane, balayage, décalage ;
- ``contours.py`` : remplissage, frontière, réglée ;
- ``retouches.py`` : supprimer des faces, découper, détourer, congé ;
- ``courbes.py`` : intersection, projection, hélice, composite ; radiale ;
- ``prolonger.py`` : prolonger, ajuster ;
- ``solide.py`` : couper par une surface, ôter ou remplacer une face, médiane ;
- ``formelibre.py`` : mise à plat, forme libre ;
- ``couture.py`` : coudre, épaissir ;
- ``courbe3d.py`` : courbe 3D par points, règles, ancrages.
"""

from engine.surfacefeat.commun import SurfaceCommonMixin
from engine.surfacefeat.simples import SurfaceSketchMixin
from engine.surfacefeat.contours import SurfaceBoundaryMixin
from engine.surfacefeat.retouches import SurfaceRetouchMixin
from engine.surfacefeat.courbes import CurveMixin
from engine.surfacefeat.prolonger import SurfaceExtendMixin
from engine.surfacefeat.solide import SurfaceSolidMixin
from engine.surfacefeat.formelibre import SurfaceFreeformMixin
from engine.surfacefeat.couture import SurfaceSewMixin
from engine.surfacefeat.courbe3d import Curve3dMixin


class SurfaceMixin(
        SurfaceCommonMixin,
        SurfaceSketchMixin,
        SurfaceBoundaryMixin,
        SurfaceRetouchMixin,
        CurveMixin,
        SurfaceExtendMixin,
        SurfaceSolidMixin,
        SurfaceFreeformMixin,
        SurfaceSewMixin,
        Curve3dMixin,
):
    """Surfaces et courbes : l'assemblage des sous-mixins du paquet."""
