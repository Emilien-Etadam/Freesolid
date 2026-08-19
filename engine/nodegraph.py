"""Évaluateur de fonction graphe — pur, sans FreeCAD.

Une fonction graphe est une ligne de l'arbre : un flux de nœuds à
l'intérieur, boucles et listes comprises, et **une forme en sortie**.
Ce module ne fabrique aucune géométrie. Il rend une liste plate
d'instructions ``{"shape": "box"|"cylinder", ...}`` ; c'est le kernel
qui les traduit en ``Part``.

Un graphe est un dict ``{"nodes": [...], "edges": [...], "output": <id>}``.

Chaque nœud : ``{"id": <str|int>, "type": <str>, ...}``.

Le catalogue complet — types, ports, catégories, icônes, état
implémenté — vit dans ``engine.vocab.GRAPH_NODES``. Ici, seulement
l'évaluation des catégories pures (nombre, vecteur, liste) et des deux
générateurs déjà là (cylindre, boîte).

Alias N004, migrés à l'évaluation : ``calcul`` + ``op`` → addition /
soustraction / multiplication / division ; ``point`` (composition) →
``vecteur``.

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
from engine.vocab import GRAPH_NODE_BY_TYPE, GRAPH_NODES


COUNT_MAX = _COUNT_MAX
_MAX_DEPTH = 32

_NODE_INPUTS = {
    spec.type: tuple(port.key for port in spec.inputs)
    for spec in GRAPH_NODES
}
_NODE_FIELDS = {
    spec.type: tuple((field.key, field.kind) for field in spec.fields)
    for spec in GRAPH_NODES
    if spec.fields
}
_POINT_INPUTS = frozenset(
    port.key
    for spec in GRAPH_NODES
    for port in spec.inputs
    if port.kind == "point"
)
_NODE_SHAPES = frozenset(spec.type for spec in GRAPH_NODES if spec.shape)
_IMPLEMENTED = frozenset(spec.type for spec in GRAPH_NODES if spec.implemented)

_LEGACY_CALC = {
    "+": "addition",
    "-": "soustraction",
    "*": "multiplication",
    "/": "division",
}
_LIST_OPS = frozenset({"flatten", "simplify", "graft", "unwrap", "wrap"})


def vocabulary():
    """Types de nœuds, libellés français et ports — lecture seule.

    Les ports et l'état viennent de ``engine.vocab.GRAPH_NODES``.
    C'est le contrat de l'opération ``graph_vocabulary``.
    """
    from engine.vocab import (
        GRAPH_NODE_LABELS,
        graph_category_label,
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
    for spec in GRAPH_NODES:
        inputs = []
        for port in spec.inputs:
            item = {"key": port.key, "label": graph_input_label(port.key)}
            if port.kind != "number":
                item["kind"] = port.kind
            inputs.append(item)
        entry = {
            "type": spec.type,
            "label": graph_node_label(spec.type),
            "category": spec.category,
            "category_label": graph_category_label(spec.category),
            "icon": spec.icon,
            "inputs": inputs,
            "shape": spec.shape,
            "implemented": spec.implemented,
        }
        if not spec.implemented:
            entry["reason"] = spec.reason
        fields = _NODE_FIELDS.get(spec.type, ())
        if fields:
            entry["fields"] = [
                {"key": key, "label": graph_field_label(key),
                 "kind": kind_name}
                for key, kind_name in fields
            ]
        entries.append(entry)
    return entries


def migrate_graph(graph):
    """Réécrit les types N004 vers le catalogue N006.

    ``calcul`` + ``op`` devient addition/soustraction/multiplication/
    division. ``point`` (composition x,y,z) devient ``vecteur`` — le
    type ``point`` du catalogue est le générateur de sommet, pas encore
    implémenté.
    """
    if not isinstance(graph, dict):
        return graph
    raw_nodes = graph.get("nodes")
    if not isinstance(raw_nodes, list):
        return graph
    nodes = []
    for raw in raw_nodes:
        if not isinstance(raw, dict):
            nodes.append(raw)
            continue
        node = dict(raw)
        kind = node.get("type")
        if kind == "point":
            node["type"] = "vecteur"
        elif kind == "calcul":
            node["type"] = _LEGACY_CALC.get(node.get("op"), "addition")
            node.pop("op", None)
        nodes.append(node)
    migrated = dict(graph)
    migrated["nodes"] = nodes
    return migrated

_BINARY_OPS = {
    "addition": lambda a, b: a + b,
    "soustraction": lambda a, b: a - b,
    "multiplication": lambda a, b: a * b,
    "division": lambda a, b: a / b,
    "puissance": lambda a, b: a ** b,
}

_UNARY_OPS = {
    "sinus": math.sin,
    "cosinus": math.cos,
    "tangente": math.tan,
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
    return _Evaluator(migrate_graph(graph), variables).run()


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


def _flatten_list(value, node):
    """Aplatit toutes les listes imbriquées, sans toucher points ni formes."""
    if not isinstance(value, list):
        return [value]
    out = []
    for item in value:
        if isinstance(item, list):
            out.extend(_flatten_list(item, node))
        else:
            out.append(item)
        if len(out) > COUNT_MAX:
            raise GraphError(
                "nœud « {} » : plafond de {} éléments dépassé ({}) — "
                "aucune troncature".format(_label(node), COUNT_MAX, len(out)))
    return out


def _simplify_list(value):
    """Effondre les listes d'un seul élément, récursivement."""
    if not isinstance(value, list):
        return value
    simplified = [_simplify_list(item) for item in value]
    if len(simplified) == 1:
        return simplified[0]
    return simplified


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
        if kind in _BINARY_OPS:
            return _apply(
                self._binary_fn(kind, node), self._inputs(node), node, 0)
        if kind in _UNARY_OPS:
            return _apply(
                self._unary_fn(kind, node), self._inputs(node), node, 0)
        if kind == "plage":
            return _apply(self._plage_fn(node), self._inputs(node), node, 0)
        if kind == "vecteur":
            return _apply(self._point_fn(node), self._inputs(node), node, 0)
        if kind == "addition_vecteur":
            return _apply(self._vec_add_fn(node), self._inputs(node), node, 0)
        if kind == "soustraction_vecteur":
            return _apply(self._vec_sub_fn(node), self._inputs(node), node, 0)
        if kind == "echelle_vecteur":
            return _apply(self._vec_scale_fn(node), self._inputs(node), node, 0)
        if kind == "longueur_vecteur":
            return _apply(self._vec_length_fn(node), self._inputs(node), node, 0)
        if kind == "produit_vectoriel":
            return _apply(self._vec_cross_fn(node), self._inputs(node), node, 0)
        if kind == "vecteur_x":
            return (1.0, 0.0, 0.0)
        if kind == "vecteur_y":
            return (0.0, 1.0, 0.0)
        if kind == "vecteur_z":
            return (0.0, 0.0, 1.0)
        if kind == "longueur_liste":
            return self._list_length(self._inputs(node)[0], node)
        if kind == "decalage":
            values = self._inputs(node)
            return self._list_shift(values[0], values[1], node)
        if kind == "option_liste":
            return self._list_option(node, self._inputs(node)[0])
        if kind == "cylindre":
            return _apply(self._cylinder_fn(node), self._inputs(node), node, 0)
        if kind == "boite":
            return _apply(self._box_fn(node), self._inputs(node), node, 0)
        spec = GRAPH_NODE_BY_TYPE.get(kind)
        if spec is not None and not spec.implemented:
            raise GraphError(
                "nœud « {} » : {}".format(_label(node), spec.reason))
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
        if isinstance(value, list):
            _check_ceiling(value, node)
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

    def _binary_fn(self, kind, node):
        fn = _BINARY_OPS[kind]

        def _run(left, right):
            a = _as_number(left, node)
            b = _as_number(right, node)
            if kind == "division" and b == 0:
                raise GraphError(
                    "nœud « {} » : division par zéro".format(_label(node)))
            try:
                result = fn(a, b)
            except (ValueError, OverflowError) as exc:
                raise GraphError(
                    "nœud « {} » : {}".format(_label(node), exc)) from exc
            return _as_number(result, node)

        return _run

    def _unary_fn(self, kind, node):
        fn = _UNARY_OPS[kind]

        def _run(value):
            number = _as_number(value, node)
            return _as_number(fn(number), node)

        return _run

    def _plage_fn(self, node):
        def _run(depart, fin, pas):
            start = _as_number(depart, node)
            stop = _as_number(fin, node)
            step = _as_number(pas, node)
            if step == 0:
                raise GraphError(
                    "nœud « {} » : pas nul".format(_label(node)))
            values = []
            current = start
            if step > 0:
                while current < stop:
                    values.append(current)
                    current += step
                    if len(values) > COUNT_MAX:
                        break
            else:
                while current > stop:
                    values.append(current)
                    current += step
                    if len(values) > COUNT_MAX:
                        break
            if not values:
                raise GraphError(
                    "nœud « {} » : plage vide".format(_label(node)))
            if len(values) > COUNT_MAX:
                raise GraphError(
                    "nœud « {} » : plafond de {} éléments dépassé ({}) — "
                    "aucune troncature".format(
                        _label(node), COUNT_MAX, len(values)))
            return values
        return _run

    def _vec_add_fn(self, node):
        def _run(left, right):
            a = _as_point(left, node)
            b = _as_point(right, node)
            return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
        return _run

    def _vec_sub_fn(self, node):
        def _run(left, right):
            a = _as_point(left, node)
            b = _as_point(right, node)
            return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
        return _run

    def _vec_scale_fn(self, node):
        def _run(vector, factor):
            point = _as_point(vector, node)
            scale = _as_number(factor, node)
            return (point[0] * scale, point[1] * scale, point[2] * scale)
        return _run

    def _vec_length_fn(self, node):
        def _run(vector):
            x, y, z = _as_point(vector, node)
            return math.hypot(x, y, z)
        return _run

    def _vec_cross_fn(self, node):
        def _run(left, right):
            a = _as_point(left, node)
            b = _as_point(right, node)
            return (
                a[1] * b[2] - a[2] * b[1],
                a[2] * b[0] - a[0] * b[2],
                a[0] * b[1] - a[1] * b[0],
            )
        return _run

    def _list_length(self, value, node):
        if isinstance(value, list):
            length = len(value)
            _check_ceiling(value, node)
            return float(length)
        return 1.0

    def _list_shift(self, value, offset, node):
        items = list(value) if isinstance(value, list) else [value]
        if not items:
            return []
        count = len(items)
        shift = int(round(_as_number(offset, node))) % count
        return items[shift:] + items[:shift]

    def _list_option(self, node, value):
        op = node.get("op", "flatten")
        if op not in _LIST_OPS:
            raise GraphError(
                "nœud « {} » : opération de liste inconnue « {} »".format(
                    _label(node), op))
        if op == "flatten":
            return _flatten_list(value, node)
        if op == "wrap":
            return [value]
        if op == "unwrap":
            if isinstance(value, list) and len(value) == 1:
                return value[0]
            return value
        if op == "graft":
            items = value if isinstance(value, list) else [value]
            return [[item] for item in items]
        return _simplify_list(value)

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
