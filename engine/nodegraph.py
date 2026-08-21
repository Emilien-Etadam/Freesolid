"""Évaluateur de fonction graphe — pur, sans FreeCAD.

Une fonction graphe est une ligne de l'arbre : un flux de nœuds à
l'intérieur, boucles et listes comprises, et **une forme en sortie**.
Ce module ne fabrique aucune géométrie. Il rend une liste plate
d'instructions ``{"shape": <type du nœud>|"script", ...}`` ; c'est le
kernel qui les traduit en ``Part``, et qui exécute les ``script``.
Les types d'instruction se dérivent de ``GRAPH_NODES`` — une seule
source, pas trois listes parallèles.
Un nœud Python n'est **jamais** évalué ici : l'instruction émise est
inerte. Un callback ``run_script`` (fourni par le kernel) peut la
résoudre ; sans lui, elle circule telle quelle.

Une répétition variable n'est pas une forme : ``evaluate_instances``
rend la liste d'instances que ``parse_repeat_instances`` accepte déjà.
``evaluate`` ne change pas.

Un graphe est un dict ``{"nodes": [...], "edges": [...], "output": <id>}``.

Chaque nœud : ``{"id": <str|int>, "type": <str>, ...}``.

Le catalogue complet — types, ports, catégories, icônes, état
implémenté — vit dans ``engine.vocab.GRAPH_NODES``. Ici, seulement
l'évaluation : catégories pures, générateurs, courbes et surfaces qui
ne consomment pas de forme, et l'émission inerte du nœud ``script``.

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
from engine.vocab import (
    GRAPH_NODE_BY_TYPE, GRAPH_NODES, graph_node_label,
)


COUNT_MAX = _COUNT_MAX
_MAX_DEPTH = 32
_SCRIPT_KIND = "script"

_NODE_INPUTS = {
    spec.type: tuple(port.key for port in spec.inputs)
    for spec in GRAPH_NODES
}
_NODE_OPTIONAL = {
    spec.type: frozenset(port.key for port in spec.inputs if port.optional)
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
#: Types d'instruction géométrique = nœuds ``shape`` du catalogue.
#: Plus ``script``, qui n'est pas une forme mais circule comme instruction.
_INSTRUCTION_KINDS = _NODE_SHAPES | {_SCRIPT_KIND}
#: Solides (générateurs) vs courbes / surfaces — une ligne d'arbre
#: a une seule nature. Dérivé du catalogue, pas recopié à la main.
_SOLID_SHAPES = frozenset(
    spec.type for spec in GRAPH_NODES
    if spec.shape and spec.category == "generators"
)
_WIRE_SHAPES = frozenset(
    spec.type for spec in GRAPH_NODES
    if spec.shape and spec.category == "curves"
)
_FACE_SHAPES = frozenset(
    spec.type for spec in GRAPH_NODES
    if spec.shape and spec.category == "surfaces"
)
_SURFACE_SHAPES = _WIRE_SHAPES | _FACE_SHAPES

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


def evaluate(graph, variables, run_script=None):
    """Instructions géométriques d'un graphe, ou lève GraphError.

    ``graph``      : ``{"nodes": [...], "edges": [...], "output": <id>}``
    ``variables``  : ``{nom: valeur}`` — les variables globales, valeurs
                     courantes.
    ``run_script`` : callable ``(instruction, node) -> valeur``, ou
                     ``None``. **Ce module n'exécute jamais le Python** :
                     sans callback, un nœud ``script`` rend une
                     instruction inerte ``{"shape": "script", ...}``.
    Retour         : ``[{"shape": <type du nœud>|"script", ...}]`` —
                     des instructions, pas des formes.
    """
    return _Evaluator(migrate_graph(graph), variables, run_script).run()


def evaluate_instances(graph, variables):
    """Instances d'une répétition variable — pas des formes.

    Rend exactement ce que ``parse_repeat_instances`` accepte :
    ``[{"offset": [x, y, z], "params": {"Pad": {"Length": 10}}}, …]``.
    Les contrôles de N010 (nombres, plafond, noms de fonction, garde)
    traversent ; ils ne sont pas réécrits ici.
    """
    return _Evaluator(migrate_graph(graph), variables).run_instances()


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
    return isinstance(value, dict) and value.get("shape") in _INSTRUCTION_KINDS


def _is_instance(value):
    if not isinstance(value, dict) or _is_instruction(value):
        return False
    offset = value.get("offset")
    params = value.get("params")
    if not isinstance(params, dict):
        return False
    return isinstance(offset, (list, tuple)) and len(offset) == 3


def _is_cote_params(value):
    if not isinstance(value, dict):
        return False
    if _is_instruction(value) or _is_instance(value) or _is_point(value):
        return False
    if not value:
        return True
    return all(
        isinstance(name, str) and isinstance(props, dict)
        for name, props in value.items()
    )


def _is_shape_instruction(value):
    return isinstance(value, dict) and value.get("shape") in _NODE_SHAPES


def _is_point_list(value):
    return (
        isinstance(value, list)
        and bool(value)
        and all(_is_point(item) for item in value)
    )


def _is_point_grid(value):
    return (
        isinstance(value, list)
        and bool(value)
        and all(_is_point_list(item) for item in value)
    )


def classify_shape_instructions(instructions):
    """Répartit les instructions en solides et courbes/surfaces.

    ``script`` n'apparaît pas ici : le kernel l'a déjà résolu. Un type
    inconnu est ignoré — c'est ``_shape_from_instruction`` qui refuse.
    """
    solids = []
    surfaces = []
    for inst in instructions:
        if not isinstance(inst, dict):
            continue
        kind = inst.get("shape")
        if kind in _SOLID_SHAPES:
            solids.append(kind)
        elif kind in _SURFACE_SHAPES:
            surfaces.append(kind)
    return solids, surfaces


def mixed_output_message(solids, surfaces):
    """Refus d'une sortie mixte — nomme les natures, en français."""
    def _names(kinds):
        seen = []
        for kind in kinds:
            label = graph_node_label(kind)
            if label not in seen:
                seen.append(label)
        return ", ".join(seen)

    solid_txt = _names(solids)
    other_txt = _names(surfaces)
    other_role = "courbe"
    if surfaces and all(kind in _FACE_SHAPES for kind in surfaces):
        other_role = "surface"
    elif surfaces and any(kind in _FACE_SHAPES for kind in surfaces):
        other_role = "courbe ou surface"
    solid_role = "solide"
    return (
        "le graphe mélange un {} ({}) et une {} ({}) — "
        "une ligne d'arbre a une seule nature".format(
            solid_role, solid_txt, other_role, other_txt)
    )


def output_nature(instructions):
    """``solid`` ou ``surface``, ou ``None`` si mixte / sans forme."""
    solids, surfaces = classify_shape_instructions(instructions)
    if solids and surfaces:
        return None
    if solids:
        return "solid"
    if surfaces:
        return "surface"
    return None


def graph_surface_kind(instructions):
    """« Courbe » ou « Surface » — lecture des instructions, pas un calcul.

    Les deux sont de nature ``surface`` pour la garde. Le libellé d'arbre
    dit laquelle. Toutes faces → Surface ; sinon Courbe.
    """
    _, kinds = classify_shape_instructions(instructions)
    if kinds and all(kind in _FACE_SHAPES for kind in kinds):
        return "Surface"
    return "Courbe"


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
        kind = value.get("shape")
        if kind == _SCRIPT_KIND:
            return "script"
        return "forme {}".format(kind)
    if _is_instance(value):
        return "instance"
    if _is_cote_params(value):
        return "cotes"
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


def _apply_with_leaves(fn, args, node, depth, is_leaf):
    """Comme ``_apply``, mais ``is_leaf`` empêche d'éclater une liste.

    Une polyligne (liste de points) ou une grille B-spline (liste de
    rangées) est une feuille : l'appariement s'applique autour, pas
    dedans.
    """
    if depth > _MAX_DEPTH:
        raise GraphError(
            "nœud « {} » : imbrication trop profonde".format(_label(node)))
    lists = [
        arg for arg in args
        if isinstance(arg, list) and not is_leaf(arg)
    ]
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
            arg[index] if (isinstance(arg, list) and not is_leaf(arg)) else arg
            for arg in args
        ]
        result.append(_apply_with_leaves(
            fn, item_args, node, depth + 1, is_leaf))
    _check_ceiling(result, node)
    return result


def accept_value(value, node):
    """Valeur qu'un script a le droit de rendre — types de l'évaluateur.

    Nombre, liste, vecteur, ou instruction de forme (un type ``shape``
    du catalogue). Tout le reste est refusé, en français, en nommant
    le nœud.
    """
    if _is_number(value):
        return _as_number(value, node)
    if _is_point(value):
        return _as_point(value, node)
    if _is_shape_instruction(value):
        return value
    if isinstance(value, list):
        _check_ceiling(value, node)
        return [accept_value(item, node) for item in value]
    raise GraphError(
        "nœud « {} » : type de retour inconnu ({})".format(
            _label(node), _preview(value)))


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


def _as_cote_params(value, node):
    if not _is_cote_params(value):
        raise GraphError(
            "nœud « {} » : cotes attendues, reçu {}".format(
                _label(node), _preview(value)))
    out = {}
    for feat, props in value.items():
        if not isinstance(feat, str) or not feat:
            raise GraphError(
                "nœud « {} » : nom de fonction invalide".format(_label(node)))
        cleaned = {}
        for prop, number in props.items():
            if not isinstance(prop, str) or not prop:
                raise GraphError(
                    "nœud « {} » : nom de cote invalide".format(_label(node)))
            cleaned[prop] = _as_number(number, node)
        out[feat] = cleaned
    return out


def _as_instance(value, node):
    if not _is_instance(value):
        raise GraphError(
            "nœud « {} » : instance attendue, reçu {}".format(
                _label(node), _preview(value)))
    offset = _as_point(tuple(value["offset"]), node)
    params = _as_cote_params(value.get("params") or {}, node)
    return {
        "offset": [offset[0], offset[1], offset[2]],
        "params": params,
    }


def _flatten_instances(value, node):
    if _is_instance(value):
        return [_as_instance(value, node)]
    if isinstance(value, list):
        out = []
        for item in value:
            out.extend(_flatten_instances(item, node))
        if len(out) > COUNT_MAX:
            raise GraphError(
                "nœud « {} » : plafond de {} éléments dépassé ({}) — "
                "aucune troncature".format(_label(node), COUNT_MAX, len(out)))
        return out
    raise GraphError(
        "nœud « {} » : la sortie du graphe n'est pas une instance".format(
            _label(node)))


class _Evaluator:
    def __init__(self, graph, variables, run_script=None):
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
        self.run_script = run_script
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

    def run_instances(self):
        result = self._eval(self.output_id)
        node = self.nodes[self.output_id]
        instances = _flatten_instances(result, node)
        if not instances:
            raise GraphError(
                "nœud « {} » : le graphe ne produit aucune instance".format(
                    _label(node)))
        return instances

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
        if kind == "ligne":
            return _apply(self._line_fn(node), self._inputs(node), node, 0)
        if kind == "arc":
            return _apply(self._arc_fn(node), self._inputs(node), node, 0)
        if kind == "arc_3pts":
            return _apply(self._arc3_fn(node), self._inputs(node), node, 0)
        if kind == "cercle":
            return _apply(self._circle_fn(node), self._inputs(node), node, 0)
        if kind == "helice":
            return _apply(self._helix_fn(node), self._inputs(node), node, 0)
        if kind == "plan":
            return _apply(self._plane_fn(node), self._inputs(node), node, 0)
        if kind == "polyligne":
            return _apply_with_leaves(
                self._polyline_fn(node), self._inputs(node), node, 0,
                _is_point_list)
        if kind == "bspline":
            return _apply_with_leaves(
                self._bspline_fn(node), self._inputs(node), node, 0,
                _is_point_list)
        if kind == "bspline_surface":
            return _apply_with_leaves(
                self._bspline_surface_fn(node), self._inputs(node), node, 0,
                _is_point_grid)
        if kind == _SCRIPT_KIND:
            return self._script(node)
        if kind == "cote":
            return _apply(self._cote_fn(node), self._inputs(node), node, 0)
        if kind == "instance":
            return _apply(self._instance_fn(node), self._inputs(node), node, 0)
        spec = GRAPH_NODE_BY_TYPE.get(kind)
        if spec is not None and not spec.implemented:
            raise GraphError(
                "nœud « {} » : {}".format(_label(node), spec.reason))
        raise GraphError(
            "nœud « {} » : type inconnu « {} »".format(_label(node), kind))

    def _inputs(self, node):
        ident = str(node["id"])
        values = []
        optional = _NODE_OPTIONAL.get(node["type"], frozenset())
        for port in _NODE_INPUTS[node["type"]]:
            if port in self.incoming[ident]:
                values.append(self._eval(self.incoming[ident][port]))
                continue
            if port in node:
                values.append(self._literal(node[port], node, port))
                continue
            if port in optional:
                values.append(None)
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
            return {"shape": "cylindre", "radius": r, "height": h,
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
            return {"shape": "boite", "length": dx, "width": dy, "height": dz,
                    "x": x, "y": y, "z": z}
        return _run

    def _xyz(self, value, node):
        point = _as_point(value, node)
        return [point[0], point[1], point[2]]

    def _as_flag(self, value, node):
        return 1.0 if _as_number(value, node) != 0 else 0.0

    def _as_direction(self, value, node):
        vec = self._xyz(value, node)
        if vec[0] == 0 and vec[1] == 0 and vec[2] == 0:
            raise GraphError(
                "nœud « {} » : direction nulle".format(_label(node)))
        return vec

    def _as_point_list(self, value, node, minimum=2):
        items = value if isinstance(value, list) else [value]
        points = [self._xyz(item, node) for item in items]
        if len(points) < minimum:
            raise GraphError(
                "nœud « {} » : au moins {} points, reçu {}".format(
                    _label(node), minimum, len(points)))
        return points

    def _as_point_grid(self, value, node):
        if _is_point_list(value) or not isinstance(value, list) or not value:
            raise GraphError(
                "nœud « {} » : grille de points attendue "
                "(liste de rangées)".format(_label(node)))
        rows = []
        width = None
        for row in value:
            points = self._as_point_list(row, node, minimum=2)
            if width is None:
                width = len(points)
            elif len(points) != width:
                raise GraphError(
                    "nœud « {} » : rangées de longueurs {} et {}".format(
                        _label(node), width, len(points)))
            rows.append(points)
        if len(rows) < 2:
            raise GraphError(
                "nœud « {} » : une surface B-spline demande au moins "
                "deux rangées".format(_label(node)))
        return rows

    def _positive(self, value, node, label):
        number = _as_number(value, node)
        if number <= 0:
            raise GraphError(
                "nœud « {} » : {} doit être positif".format(
                    _label(node), label))
        return number

    def _line_fn(self, node):
        def _run(point1, point2):
            a = self._xyz(point1, node)
            b = self._xyz(point2, node)
            if a == b:
                raise GraphError(
                    "nœud « {} » : les deux points sont confondus".format(
                        _label(node)))
            return {"shape": "ligne", "point1": a, "point2": b}
        return _run

    def _arc_fn(self, node):
        def _run(radius, point, direction, angle1, angle2):
            r = self._positive(radius, node, "le rayon")
            a1 = _as_number(angle1, node)
            a2 = _as_number(angle2, node)
            if a1 == a2:
                raise GraphError(
                    "nœud « {} » : l'arc a une ouverture nulle".format(
                        _label(node)))
            return {
                "shape": "arc",
                "rayon": r,
                "point": self._xyz(point, node),
                "direction": self._as_direction(direction, node),
                "angle1": a1,
                "angle2": a2,
            }
        return _run

    def _arc3_fn(self, node):
        def _run(point1, point2, point3):
            a = self._xyz(point1, node)
            b = self._xyz(point2, node)
            c = self._xyz(point3, node)
            if a == b or b == c or a == c:
                raise GraphError(
                    "nœud « {} » : les trois points ne sont pas distincts"
                    .format(_label(node)))
            return {"shape": "arc_3pts", "point1": a, "point2": b, "point3": c}
        return _run

    def _circle_fn(self, node):
        def _run(radius, point, direction):
            return {
                "shape": "cercle",
                "rayon": self._positive(radius, node, "le rayon"),
                "point": self._xyz(point, node),
                "direction": self._as_direction(direction, node),
            }
        return _run

    def _helix_fn(self, node):
        def _run(pas_helice, hauteur, rayon, angle, gauche):
            return {
                "shape": "helice",
                "pas_helice": self._positive(pas_helice, node, "le pas"),
                "hauteur": self._positive(hauteur, node, "la hauteur"),
                "rayon": self._positive(rayon, node, "le rayon"),
                "angle": _as_number(angle, node),
                "gauche": self._as_flag(gauche, node),
            }
        return _run

    def _plane_fn(self, node):
        def _run(longueur, largeur, point, direction):
            return {
                "shape": "plan",
                "longueur": self._positive(longueur, node, "la longueur"),
                "largeur": self._positive(largeur, node, "la largeur"),
                "point": self._xyz(point, node),
                "direction": self._as_direction(direction, node),
            }
        return _run

    def _polyline_fn(self, node):
        def _run(point, ferme):
            return {
                "shape": "polyligne",
                "points": self._as_point_list(point, node, minimum=2),
                "ferme": self._as_flag(ferme, node),
            }
        return _run

    def _bspline_fn(self, node):
        def _run(centres, ferme):
            closed = self._as_flag(ferme, node)
            minimum = 3 if closed else 2
            return {
                "shape": "bspline",
                "points": self._as_point_list(centres, node, minimum=minimum),
                "ferme": closed,
            }
        return _run

    def _bspline_surface_fn(self, node):
        def _run(centres):
            return {
                "shape": "bspline_surface",
                "centres": self._as_point_grid(centres, node),
            }
        return _run

    def _script(self, node):
        """Émet l'instruction inerte — n'exécute jamais le code."""
        code = node.get("code", "")
        if not isinstance(code, str):
            raise GraphError(
                "nœud « {} » : code Python manquant".format(_label(node)))
        ident = str(node["id"])
        inputs = {}
        declared = _NODE_INPUTS[node["type"]]
        for port in declared:
            if port in self.incoming[ident]:
                inputs[port] = self._eval(self.incoming[ident][port])
            elif port in node:
                inputs[port] = self._literal(node[port], node, port)
        instruction = {
            "shape": _SCRIPT_KIND,
            "code": code,
            "inputs": inputs,
            "id": ident,
        }
        if self.run_script is None:
            return instruction
        return self.run_script(instruction, node)

    def _cote_field(self, node, key, missing):
        value = node.get(key)
        if not isinstance(value, str) or not value.strip():
            raise GraphError(
                "nœud « {} » : {}".format(_label(node), missing))
        return value.strip()

    def _cote_fn(self, node):
        feature = self._cote_field(
            node, "feature", "nom de fonction manquant")
        prop = self._cote_field(node, "prop", "nom de cote manquant")

        def _run(valeur, suite=None):
            number = _as_number(valeur, node)
            if suite is None:
                return {feature: {prop: number}}
            merged = {
                name: dict(props)
                for name, props in _as_cote_params(suite, node).items()
            }
            if feature in merged and prop in merged[feature]:
                raise GraphError(
                    "nœud « {} » : {}.{} définie deux fois".format(
                        _label(node), feature, prop))
            merged.setdefault(feature, {})[prop] = number
            return merged

        return _run

    def _instance_fn(self, node):
        def _run(decalage, cotes=None):
            offset = _as_point(decalage, node)
            params = {} if cotes is None else _as_cote_params(cotes, node)
            return {
                "offset": [offset[0], offset[1], offset[2]],
                "params": params,
            }

        return _run
