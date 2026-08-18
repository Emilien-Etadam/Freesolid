"""Évaluateur de fonction graphe — pur, sans FreeCAD.

Une fonction graphe est une ligne de l'arbre : un flux de nœuds à
l'intérieur, boucles et listes comprises, et **une forme en sortie**.
Ce module ne fabrique aucune géométrie. Il rend une liste plate
d'instructions ``{"shape": "box"|"cylinder", ...}`` ; c'est le kernel
qui les traduit en ``Part``.

Un graphe est un dict ``{"nodes": [...], "edges": [...], "output": <id>}``.

Chaque nœud : ``{"id": <str|int>, "type": <str>, ...}``.

Types :

- ``nombre``    : littéral. Champ ``value`` (nombre). Sortie : nombre.
- ``variable``  : champ ``name``. Sortie : valeur courante dans
                  ``variables``.
- ``serie``     : entrées ``depart``, ``pas``, ``nombre``. Sortie : liste
                  de nombres ``[depart, depart+pas, ...]``.
- ``calcul``    : champ ``op`` ∈ {``+``, ``-``, ``*``, ``/``} ; entrées
                  ``a``, ``b``. Sortie : nombre ou liste.
- ``point``     : entrées ``x``, ``y``, ``z``. Sortie : point ou liste
                  de points.
- ``cylindre``  : entrées ``rayon``, ``hauteur``, ``ancrage`` (point).
- ``boite``     : entrées ``longueur``, ``largeur``, ``hauteur``,
                  ``ancrage``.

Une entrée se résout par une arête ``{"from", "to", "input"}``, ou à
défaut par un littéral du même nom sur le nœud (nombre scalaire).

Règle d'appariement
-------------------

C'est ce qui rend Grasshopper puissant et déroutant. Elle se décide
ici, une fois :

- un **scalaire face à une liste** se diffuse : ``serie(0, 10, 5) * 2``
  donne cinq valeurs ;
- **deux listes de même longueur** s'apparient terme à terme ;
- **deux listes de longueurs différentes sont refusées**, avec un
  message qui donne les deux longueurs.

La règle est récursive : une liste de listes est appariée niveau par
niveau. Un refus explicite est relâchable plus tard ; une répétition
silencieuse (Grasshopper rallonge la plus courte) ne l'est plus une
fois que des pièces en dépendent.
"""

from __future__ import annotations

import math

from engine.protocol import _COUNT_MAX


COUNT_MAX = _COUNT_MAX
_MAX_DEPTH = 32

_NODE_INPUTS = {
    "nombre": (),
    "variable": (),
    "serie": ("depart", "pas", "nombre"),
    "calcul": ("a", "b"),
    "point": ("x", "y", "z"),
    "cylindre": ("rayon", "hauteur", "ancrage"),
    "boite": ("longueur", "largeur", "hauteur", "ancrage"),
}

#: Champs propres au nœud — pas des ports. L'évaluateur les lit sur
#: le dict du nœud (``value``, ``name``, ``op``).
_NODE_FIELDS = {
    "nombre": (("value", "number"),),
    "variable": (("name", "text"),),
    "calcul": (("op", "op"),),
}

_POINT_INPUTS = frozenset({"ancrage"})
_NODE_SHAPES = frozenset({"cylindre", "boite"})


def vocabulary():
    """Types de nœuds, libellés français et ports — lecture seule.

    Les ports viennent de ``_NODE_INPUTS`` ; les mots de ``engine.vocab``.
    C'est le contrat de l'opération ``graph_vocabulary``.
    """
    from engine.vocab import (
        GRAPH_NODE_LABELS,
        graph_field_label,
        graph_input_label,
        graph_node_label,
    )

    missing = [kind for kind in _NODE_INPUTS if kind not in GRAPH_NODE_LABELS]
    if missing:
        raise RuntimeError(
            "libellé manquant pour le type de nœud « {} »".format(
                missing[0]))
    entries = []
    for kind, ports in _NODE_INPUTS.items():
        inputs = []
        for key in ports:
            item = {"key": key, "label": graph_input_label(key)}
            if key in _POINT_INPUTS:
                item["kind"] = "point"
            inputs.append(item)
        entry = {
            "type": kind,
            "label": graph_node_label(kind),
            "inputs": inputs,
            "shape": kind in _NODE_SHAPES,
        }
        fields = _NODE_FIELDS.get(kind, ())
        if fields:
            entry["fields"] = [
                {"key": key, "label": graph_field_label(key),
                 "kind": kind_name}
                for key, kind_name in fields
            ]
        entries.append(entry)
    return entries

_OPS = {
    "+": lambda a, b: a + b,
    "-": lambda a, b: a - b,
    "*": lambda a, b: a * b,
    "/": lambda a, b: a / b,
}


class GraphError(Exception):
    """Graphe invalide ; le message nomme le nœud fautif, en français."""


def evaluate(graph, variables):
    """Instructions géométriques d'un graphe, ou lève GraphError.

    ``graph``     : ``{"nodes": [...], "edges": [...], "output": <id>}``
    ``variables`` : ``{nom: valeur}`` — les variables globales, valeurs
                    courantes.
    Retour        : ``[{"shape": "box"|"cylinder", ...}]`` — des
                    instructions, pas des formes.
    """
    return _Evaluator(graph, variables).run()


def _label(node):
    ident = node.get("id", "?")
    kind = node.get("type", "?")
    return "{} ({})".format(ident, kind)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_point(value):
    if isinstance(value, tuple) and len(value) == 3:
        return all(_is_number(v) for v in value)
    if isinstance(value, dict) and not _is_instruction(value):
        return all(k in value and _is_number(value[k]) for k in ("x", "y", "z"))
    return False


def _is_instruction(value):
    return isinstance(value, dict) and value.get("shape") in ("box", "cylinder")


def _as_number(value, node):
    if not _is_number(value):
        raise GraphError(
            "nœud « {} » : nombre attendu, reçu {}".format(
                _label(node), _preview(value)))
    number = float(value)
    if not math.isfinite(number):
        raise GraphError(
            "nœud « {} » : nombre non fini".format(_label(node)))
    return number


def _as_point(value, node):
    if isinstance(value, tuple) and len(value) == 3:
        return (_as_number(value[0], node),
                _as_number(value[1], node),
                _as_number(value[2], node))
    if isinstance(value, dict) and not _is_instruction(value):
        try:
            return (_as_number(value["x"], node),
                    _as_number(value["y"], node),
                    _as_number(value["z"], node))
        except KeyError:
            pass
    raise GraphError(
        "nœud « {} » : point attendu, reçu {}".format(
            _label(node), _preview(value)))


def _as_count(value, node):
    number = _as_number(value, node)
    if abs(number - round(number)) > 1e-9:
        raise GraphError(
            "nœud « {} » : le compte doit être un entier, reçu {}".format(
                _label(node), _preview(value)))
    count = int(round(number))
    if count < 0:
        raise GraphError(
            "nœud « {} » : compte négatif ({})".format(_label(node), count))
    if count == 0:
        raise GraphError(
            "nœud « {} » : compte nul".format(_label(node)))
    if count > COUNT_MAX:
        raise GraphError(
            "nœud « {} » : plafond de {} éléments dépassé ({}) — "
            "aucune troncature".format(_label(node), COUNT_MAX, count))
    return count


def _preview(value):
    if isinstance(value, list):
        return "liste[{}]".format(len(value))
    if _is_instruction(value):
        return "forme {}".format(value.get("shape"))
    if _is_point(value):
        return "point"
    return repr(value)


def _leaf_count(value):
    if isinstance(value, list):
        return sum(_leaf_count(item) for item in value)
    return 1


def _check_ceiling(value, node):
    count = _leaf_count(value)
    if count > COUNT_MAX:
        raise GraphError(
            "nœud « {} » : plafond de {} éléments dépassé ({}) — "
            "aucune troncature".format(_label(node), COUNT_MAX, count))


def _apply(fn, args, node, depth):
    """Applique ``fn`` aux arguments avec la règle d'appariement."""
    if depth > _MAX_DEPTH:
        raise GraphError(
            "nœud « {} » : imbrication trop profonde".format(_label(node)))
    lists = [arg for arg in args if isinstance(arg, list)]
    if not lists:
        return fn(*args)
    length = len(lists[0])
    for other in lists[1:]:
        if len(other) != length:
            raise GraphError(
                "nœud « {} » : listes de longueurs {} et {}".format(
                    _label(node), length, len(other)))
    if length > COUNT_MAX:
        raise GraphError(
            "nœud « {} » : plafond de {} éléments dépassé ({}) — "
            "aucune troncature".format(_label(node), COUNT_MAX, length))
    result = []
    for index in range(length):
        item_args = [
            arg[index] if isinstance(arg, list) else arg
            for arg in args
        ]
        result.append(_apply(fn, item_args, node, depth + 1))
    _check_ceiling(result, node)
    return result


def _flatten_instructions(value, node):
    if _is_instruction(value):
        return [value]
    if isinstance(value, list):
        out = []
        for item in value:
            out.extend(_flatten_instructions(item, node))
        if len(out) > COUNT_MAX:
            raise GraphError(
                "nœud « {} » : plafond de {} éléments dépassé ({}) — "
                "aucune troncature".format(_label(node), COUNT_MAX, len(out)))
        return out
    raise GraphError(
        "nœud « {} » : la sortie du graphe n'est pas une forme".format(
            _label(node)))


class _Evaluator:
    def __init__(self, graph, variables):
        if not isinstance(graph, dict):
            raise GraphError("le graphe doit être un objet")
        nodes = graph.get("nodes")
        edges = graph.get("edges")
        if not isinstance(nodes, list):
            raise GraphError("le graphe doit avoir une liste « nodes »")
        if not isinstance(edges, list):
            raise GraphError("le graphe doit avoir une liste « edges »")
        if len(nodes) > COUNT_MAX:
            raise GraphError(
                "plafond de {} nœuds dépassé ({}) — aucune troncature"
                .format(COUNT_MAX, len(nodes)))
        if len(edges) > COUNT_MAX:
            raise GraphError(
                "plafond de {} arêtes dépassé ({}) — aucune troncature"
                .format(COUNT_MAX, len(edges)))
        if "output" not in graph:
            raise GraphError("le graphe n'a pas de nœud de sortie")
        if variables is None:
            variables = {}
        if not isinstance(variables, dict):
            raise GraphError("variables : objet {nom: valeur} attendu")
        self.variables = variables
        self.nodes = {}
        for raw in nodes:
            if not isinstance(raw, dict):
                raise GraphError("nœud invalide : {}".format(_preview(raw)))
            if "id" not in raw:
                raise GraphError("nœud sans identifiant")
            ident = str(raw["id"])
            if ident in self.nodes:
                raise GraphError("nœud en double : « {} »".format(ident))
            kind = raw.get("type")
            if kind not in _NODE_INPUTS:
                raise GraphError(
                    "nœud « {} » : type inconnu « {} »".format(
                        ident, kind))
            self.nodes[ident] = raw
        self.incoming = {ident: {} for ident in self.nodes}
        for raw in edges:
            if not isinstance(raw, dict):
                raise GraphError("arête invalide : {}".format(_preview(raw)))
            src = str(raw.get("from", ""))
            dst = str(raw.get("to", ""))
            port = raw.get("input")
            if src not in self.nodes:
                raise GraphError("arête depuis un nœud inconnu « {} »".format(src))
            if dst not in self.nodes:
                raise GraphError("arête vers un nœud inconnu « {} »".format(dst))
            allowed = _NODE_INPUTS[self.nodes[dst]["type"]]
            if port not in allowed:
                raise GraphError(
                    "nœud « {} » : entrée inconnue « {} »".format(
                        _label(self.nodes[dst]), port))
            if port in self.incoming[dst]:
                raise GraphError(
                    "nœud « {} » : entrée « {} » branchée deux fois".format(
                        _label(self.nodes[dst]), port))
            self.incoming[dst][port] = src
        self.output_id = str(graph["output"])
        if self.output_id not in self.nodes:
            raise GraphError(
                "nœud de sortie inconnu « {} »".format(self.output_id))
        self.cache = {}
        self.stack = []

    def run(self):
        result = self._eval(self.output_id)
        node = self.nodes[self.output_id]
        instructions = _flatten_instructions(result, node)
        if not instructions:
            raise GraphError(
                "nœud « {} » : le graphe ne produit aucune forme".format(
                    _label(node)))
        return instructions

    def _eval(self, ident):
        if ident in self.cache:
            return self.cache[ident]
        node = self.nodes[ident]
        if ident in self.stack:
            raise GraphError(
                "cycle détecté dans le graphe (nœud « {} »)".format(
                    _label(node)))
        self.stack.append(ident)
        try:
            value = self._compute(node)
        finally:
            self.stack.pop()
        _check_ceiling(value, node)
        self.cache[ident] = value
        return value

    def _compute(self, node):
        kind = node["type"]
        if kind == "nombre":
            if "value" not in node:
                raise GraphError(
                    "nœud « {} » : valeur littérale manquante".format(
                        _label(node)))
            return _as_number(node["value"], node)
        if kind == "variable":
            name = node.get("name")
            if not isinstance(name, str) or not name.strip():
                raise GraphError(
                    "nœud « {} » : nom de variable manquant".format(
                        _label(node)))
            if name not in self.variables:
                raise GraphError(
                    "nœud « {} » : variable inconnue « {} »".format(
                        _label(node), name))
            return _as_number(self.variables[name], node)
        if kind == "serie":
            return _apply(self._serie_fn(node), self._inputs(node), node, 0)
        if kind == "calcul":
            op = node.get("op")
            if op not in _OPS:
                raise GraphError(
                    "nœud « {} » : opération inconnue « {} » — "
                    "attendu +, -, * ou /".format(_label(node), op))
            return _apply(self._calcul_fn(op, node), self._inputs(node), node, 0)
        if kind == "point":
            return _apply(self._point_fn(node), self._inputs(node), node, 0)
        if kind == "cylindre":
            return _apply(self._cylinder_fn(node), self._inputs(node), node, 0)
        if kind == "boite":
            return _apply(self._box_fn(node), self._inputs(node), node, 0)
        raise GraphError(
            "nœud « {} » : type inconnu « {} »".format(_label(node), kind))

    def _inputs(self, node):
        ident = str(node["id"])
        values = []
        for port in _NODE_INPUTS[node["type"]]:
            if port in self.incoming[ident]:
                values.append(self._eval(self.incoming[ident][port]))
                continue
            if port in node:
                values.append(self._literal(node[port], node, port))
                continue
            raise GraphError(
                "nœud « {} » : entrée manquante « {} »".format(
                    _label(node), port))
        return values

    def _literal(self, value, node, port):
        if _is_number(value) or _is_point(value):
            return value
        raise GraphError(
            "nœud « {} » : littéral invalide pour « {} » ({})".format(
                _label(node), port, _preview(value)))

    def _serie_fn(self, node):
        def _run(depart, pas, nombre):
            start = _as_number(depart, node)
            step = _as_number(pas, node)
            if step == 0:
                raise GraphError(
                    "nœud « {} » : pas nul".format(_label(node)))
            count = _as_count(nombre, node)
            return [start + i * step for i in range(count)]
        return _run

    def _calcul_fn(self, op, node):
        fn = _OPS[op]

        def _run(left, right):
            a = _as_number(left, node)
            b = _as_number(right, node)
            if op == "/" and b == 0:
                raise GraphError(
                    "nœud « {} » : division par zéro".format(_label(node)))
            return fn(a, b)

        return _run

    def _point_fn(self, node):
        def _run(x, y, z):
            return (_as_number(x, node),
                    _as_number(y, node),
                    _as_number(z, node))
        return _run

    def _cylinder_fn(self, node):
        def _run(radius, height, anchor):
            r = _as_number(radius, node)
            h = _as_number(height, node)
            if r <= 0 or h <= 0:
                raise GraphError(
                    "nœud « {} » : rayon et hauteur doivent être positifs"
                    .format(_label(node)))
            x, y, z = _as_point(anchor, node)
            return {"shape": "cylinder", "radius": r, "height": h,
                    "x": x, "y": y, "z": z}
        return _run

    def _box_fn(self, node):
        def _run(length, width, height, anchor):
            dx = _as_number(length, node)
            dy = _as_number(width, node)
            dz = _as_number(height, node)
            if dx <= 0 or dy <= 0 or dz <= 0:
                raise GraphError(
                    "nœud « {} » : dimensions de la boîte doivent être "
                    "positives".format(_label(node)))
            x, y, z = _as_point(anchor, node)
            return {"shape": "box", "length": dx, "width": dy, "height": dz,
                    "x": x, "y": y, "z": z}
        return _run
