"""Langue des messages du moteur — pur Python, sans FreeCAD."""

import ast
import json
import re
from pathlib import Path

import pytest

from engine import i18n, protocol

_ROOT = Path(__file__).resolve().parent.parent
_EN = json.loads((_ROOT / "engine" / "lang" / "en.json").read_text(encoding="utf-8"))


def test_normalize_lang():
    assert i18n.normalize_lang("en") == "en"
    assert i18n.normalize_lang("en-US") == "en"
    assert i18n.normalize_lang(" EN_GB ") == "en"
    assert i18n.normalize_lang("fr-CA") == "fr"
    assert i18n.normalize_lang("de") == "fr"
    assert i18n.normalize_lang(None) == "fr"
    assert i18n.normalize_lang(42) == "fr"


def test_request_lang_is_optional_and_tolerant():
    assert protocol.request_lang({"op": "ping"}) == "fr"
    assert protocol.request_lang({"op": "ping", "lang": "en"}) == "en"
    assert protocol.request_lang({"op": "ping", "lang": ["en"]}) == "fr"
    assert protocol.request_lang(None) == "fr"
    # « lang » n'est pas un paramètre : la validation ne le voit pas.
    assert protocol.validate_request({"op": "ping", "lang": "en"})[0] == "ping"


def test_translate_exact_template_and_fallback():
    assert i18n.translate("rien à annuler", "en") == "nothing to undo"
    assert i18n.translate("rien à annuler", "fr") == "rien à annuler"
    assert i18n.translate("corps inconnu : Body007", "en") == "unknown body: Body007"
    assert i18n.translate("message inconnu du catalogue", "en") == "message inconnu du catalogue"
    assert i18n.translate("", "en") == ""
    assert i18n.translate(None, "en") is None


def test_translate_nested_captures_are_translated_too():
    text = "nœud « boite » : plage vide"
    assert i18n.translate(text, "en") == 'node "boite": empty range'
    # Le gabarit générique « nœud « {} » : {} » traduit sa capture.
    text = "nœud « a » : {}".format("division par zéro")
    assert i18n.translate(text, "en") == 'node "a": division by zero'
    # Une capture sans entrée reste telle quelle.
    text = "échec à l'étape « m0 » : quelque chose d'inattendu"
    assert i18n.translate(text, "en") == 'failed at step "m0": quelque chose d\'inattendu'


def test_labels_follow_the_language():
    assert i18n.label("Extrusion", "en") == "Extrude"
    assert i18n.label("Extrusion", "fr") == "Extrusion"
    assert i18n.label("Fixé — {}", "en").format("Pied") == "Fixed — Pied"


def test_unknown_language_has_no_catalog():
    assert i18n.catalog("klingon") == []
    assert i18n.catalog("fr") == []
    assert i18n.catalog("en")


def _engine_sources() -> str:
    text = []
    # Récursif : un message qui part dans un sous-paquet (engine/ops/…)
    # reste une clé utilisée, pas une entrée orpheline.
    for path in sorted((_ROOT / "engine").rglob("*.py")):
        text.append(path.read_text(encoding="utf-8"))
    joined = "\n".join(text)
    # Littéraux coupés par « " \n  " » (concaténation implicite) : recollés.
    joined = re.sub(r'"\s*\n\s*"', "", joined)
    joined = joined.replace("{!r}", "{}").replace('\\"', '"')
    return joined


def test_catalog_keys_exist_in_engine_sources():
    sources = _engine_sources()
    orphans = [key for key in _EN if key not in sources]
    assert orphans == []


def _message_templates(node):
    """Gabarits d'un message : ``"…"``, ``"…".format(…)``, littéraux
    concaténés, chaque branche d'un ``a if c else b``, chaque valeur d'un
    ``{…}[clé]``. Un message calculé (texte d'une exception, aide) : rien."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "format"):
        return _message_templates(node.func.value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _message_templates(node.left)
        right = _message_templates(node.right)
        return [left[0] + right[0]] if len(left) == len(right) == 1 else []
    if isinstance(node, ast.IfExp):
        return _message_templates(node.body) + _message_templates(node.orelse)
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Dict):
        return [text for value in node.value.values
                for text in _message_templates(value)]
    return []


def test_every_kernel_error_message_is_translated():
    """Chaque message de ``KernelError`` écrit en toutes lettres dans le
    moteur a son entrée anglaise, exacte ou gabarit."""
    missing = []
    for path in sorted((_ROOT / "engine").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and node.args
                    and getattr(node.func, "id", None) == "KernelError"):
                continue
            for text in _message_templates(node.args[0]):
                if text.replace("{!r}", "{}") not in _EN:
                    missing.append("{}:{} {}".format(
                        path.relative_to(_ROOT).as_posix(), node.lineno, text))
    assert missing == []


def test_catalog_keeps_placeholder_counts():
    bad = [key for key, value in _EN.items()
           if key.count("{}") != value.count("{}")]
    assert bad == []


@pytest.mark.parametrize("message", [
    "opération inconnue 'x' — attendu l'une de : ping, selftest",
    "params doit être un objet JSON",
    "la requête doit être un objet JSON",
])
def test_protocol_errors_are_covered(message):
    assert i18n.translate(message, "en") != message
