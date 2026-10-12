"""Sélections étendues d'arêtes : chaîne tangente et boucle.

Depuis une arête cliquée, la chaîne tangente réunit les arêtes qui la
prolongent sans angle (un contour arrondi d'un seul clic) ; la boucle
réunit le contour fermé d'une des deux faces qui la bordent. Les numéros
sont ceux des arêtes du corps actif, comme dans la vue. Lecture seule.
"""

#: Écart toléré entre deux tangentes unitaires pour les dire alignées.
TANGENT_TOLERANCE = 1e-6


def aligned(a, b, tolerance=TANGENT_TOLERANCE):
    """Deux directions unitaires (x, y, z) parallèles, de même sens ou non."""
    dot = a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
    return abs(abs(dot) - 1.0) < tolerance


class SelectChainMixin:
    """Op : edge_chain (chaîne tangente, boucle)."""

    def edge_chain(self, edge, mode="tangent", face=0):
        """Arêtes de la chaîne tangente (``mode`` ``tangent``) ou de la
        boucle (``loop`` ; ``face`` choisit l'une des faces voisines, un
        second appel passe à l'autre)."""
        from engine.kernel import KernelError
        import Part
        shape = getattr(self._require_body(), "Shape", None)
        edges = list(shape.Edges) if shape is not None else []
        start = int(edge)
        if not 0 <= start < len(edges):
            raise KernelError("arête inconnue : {}".format(start))
        seams = self._seam_edge_ids(shape)

        def index_of(item):
            return next(i for i, e in enumerate(edges) if e.isSame(item))

        if mode == "loop":
            faces = []
            for candidate in shape.ancestorsOfType(edges[start], Part.Face):
                if not any(candidate.isSame(f) for f in faces):
                    faces.append(candidate)
            if not faces:
                raise KernelError("cette arête ne borde aucune face")
            chosen = faces[int(face) % len(faces)]
            wire = next(w for w in chosen.Wires
                        if any(e.isSame(edges[start]) for e in w.Edges))
            found = {index_of(e) for e in wire.Edges} - seams
            return {"edges": sorted(found | {start}), "faces": len(faces)}
        if mode != "tangent":
            raise KernelError("sélection inconnue : {}".format(mode))

        def tangent_at(item, vertex):
            t = item.tangentAt(item.parameterAt(vertex))
            return (t.x, t.y, t.z)

        found = {start}
        todo = [start]
        while todo:
            current = edges[todo.pop()]
            for vertex in current.Vertexes:
                here = tangent_at(current, vertex)
                for other in shape.ancestorsOfType(vertex, Part.Edge):
                    j = index_of(other)
                    if j in found or j in seams:
                        continue
                    if aligned(here, tangent_at(other, vertex)):
                        found.add(j)
                        todo.append(j)
        return {"edges": sorted(found)}
