"""Exécution du nœud Python — le seul endroit qui appelle ``exec``.

L'évaluateur (``engine.nodegraph``) reste pur : il émet une instruction
inerte ``{"shape": "script", ...}``. C'est ici, appelé par le kernel,
que le code tourne.

Pas de bac à sable. Le script a les mêmes droits que le processus du
kernel. La protection est le consentement explicite, par document et
pour la session : jamais persisté dans le ``.FCStd``.
"""

from __future__ import annotations

import re
import textwrap

from engine.nodegraph import (
    GraphError,
    accept_value,
    evaluate as evaluate_graph,
    migrate_graph,
    _label,
)

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TRUST_MESSAGE = (
    "nœud « {} » : ce document n'est pas autorisé à exécuter du Python. "
    "Le code n'a pas tourné ; la pièce est intacte. L'autorisation vaut "
    "pour ce document et cette session, jamais enregistrée dans le fichier."
)


def script_nodes(graph):
    """Nœuds ``script`` du graphe, après migration des alias."""
    if not isinstance(graph, dict):
        return []
    migrated = migrate_graph(graph)
    nodes = migrated.get("nodes")
    if not isinstance(nodes, list):
        return []
    found = []
    for raw in nodes:
        if isinstance(raw, dict) and raw.get("type") == "script":
            found.append(raw)
    return found


def refuse_untrusted(node):
    """Refus sans exécuter — le message nomme le nœud."""
    raise GraphError(_TRUST_MESSAGE.format(_label(node)))


def execute(instruction, node, trusted):
    """Exécute l'instruction ``script``, ou refuse.

    ``trusted`` faux : lève ``GraphError`` **avant** tout ``exec``.
    C'est la seule fonction du dépôt qui exécute du Python utilisateur.
    """
    if not trusted:
        refuse_untrusted(node)
    code = instruction.get("code", "") if isinstance(instruction, dict) else ""
    if not isinstance(code, str) or not code.strip():
        raise GraphError(
            "nœud « {} » : code Python manquant".format(_label(node)))
    raw_inputs = instruction.get("inputs") if isinstance(instruction, dict) else {}
    if raw_inputs is None:
        raw_inputs = {}
    if not isinstance(raw_inputs, dict):
        raise GraphError(
            "nœud « {} » : entrées invalides".format(_label(node)))
    inputs = {}
    for name, value in raw_inputs.items():
        if not isinstance(name, str) or not _IDENT.match(name):
            raise GraphError(
                "nœud « {} » : nom d'entrée invalide « {} »".format(
                    _label(node), name))
        if name.startswith("__"):
            raise GraphError(
                "nœud « {} » : nom d'entrée réservé « {} »".format(
                    _label(node), name))
        inputs[name] = value
    params = ", ".join(inputs)
    body = textwrap.indent(code.rstrip() + "\n", "    ")
    wrapped = "def __freesolid_user({params}):\n{body}".format(
        params=params, body=body)
    filename = "<nœud {}>".format(_label(node))
    try:
        compiled = compile(wrapped, filename, "exec")
    except SyntaxError as exc:
        raise GraphError(
            "nœud « {} » : syntaxe Python — {}".format(
                _label(node), exc)) from exc
    # Pas de bac à sable : builtins réels, processus du kernel.
    namespace = {"__builtins__": __builtins__}
    try:
        exec(compiled, namespace, namespace)  # noqa: S102 — volontaire, cf. module
        result = namespace["__freesolid_user"](**inputs)
    except GraphError:
        raise
    except Exception as exc:  # noqa: BLE001 — tout devient GraphError nommé
        raise GraphError(
            "nœud « {} » : {}".format(_label(node), exc)) from exc
    return accept_value(result, node)


def evaluate(graph, variables, trusted=False):
    """Évalue un graphe, en exécutant les scripts seulement si autorisé.

    Un graphe qui porte un ``script`` et n'est pas autorisé est refusé
    **avant** tout ``exec``, en nommant le nœud. L'instruction que
    l'évaluateur émet reste inerte : c'est ``execute`` qui la résout.
    """
    scripts = script_nodes(graph)
    if scripts and not trusted:
        refuse_untrusted(scripts[0])

    def run_script(instruction, node):
        return execute(instruction, node, trusted=True)

    return evaluate_graph(
        graph, variables, run_script=run_script if scripts else None)
