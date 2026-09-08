"""Langue des messages du moteur — français source, anglais par catalogue.

Le noyau écrit ses messages en français. À la frontière HTTP, le serveur
traduit dans la langue demandée par la requête (``lang``) au moyen de
``engine/lang/<code>.json`` : un dictionnaire « gabarit français → gabarit
traduit », où ``{}`` marque une variable, comme dans les ``str.format`` du
noyau. Un message sans entrée reste en français : rien ne casse.

Pur Python, sans FreeCAD.
"""

import json
import os
import re

#: Langues livrées. Le français n'a pas de catalogue : il est la source.
LANGS = ("fr", "en")
DEFAULT_LANG = "fr"

_LANG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lang")
_CACHE: dict[str, list] = {}


def normalize_lang(value) -> str:
    """« en », « en-US », « EN_GB » → « en » ; tout le reste → « fr »."""
    if not isinstance(value, str):
        return DEFAULT_LANG
    code = value.strip().lower()[:2]
    return code if code in LANGS else DEFAULT_LANG


def _compile(catalog: dict) -> list:
    """Entrées triées, gabarit le plus long d'abord (le plus spécifique).

    Chaque entrée : ``(exact, regex, traduction)`` — ``regex`` vaut None
    quand le gabarit n'a pas de variable.
    """
    entries = []
    for source, target in catalog.items():
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        if "{}" in source:
            pattern = "(.*?)".join(re.escape(part) for part in source.split("{}"))
            regex = re.compile("^" + pattern + "$", re.S)
        else:
            regex = None
        entries.append((source, regex, target))
    entries.sort(key=lambda e: -len(e[0]))
    return entries


def catalog(lang: str) -> list:
    """Entrées compilées de la langue, ``[]`` pour le français ou l'inconnu."""
    lang = normalize_lang(lang)
    if lang == DEFAULT_LANG:
        return []
    if lang not in _CACHE:
        path = os.path.join(_LANG_DIR, lang + ".json")
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            data = {}
        _CACHE[lang] = _compile(data if isinstance(data, dict) else {})
    return _CACHE[lang]


def _fill(template: str, values) -> str:
    out = template
    for value in values:
        out = out.replace("{}", value, 1)
    return out


def translate(text, lang: str) -> str:
    """Le texte dans ``lang`` : correspondance exacte, puis par gabarit.

    Un gabarit ``nœud « {} » : {}`` reconnaît
    ``nœud « a » : plage vide`` et remplit la traduction avec ``a`` et
    ``plage vide`` — la partie capturée est elle-même traduite quand elle
    correspond à une entrée, sinon laissée telle quelle.
    """
    if not isinstance(text, str) or not text:
        return text
    entries = catalog(lang)
    if not entries:
        return text
    for source, regex, target in entries:
        if regex is None:
            if source == text:
                return target
            continue
        match = regex.match(text)
        if match:
            parts = [translate(part, lang) for part in match.groups()]
            return _fill(target, parts)
    return text


def label(text: str, lang: str) -> str:
    """Libellé posé dans le document (« Bossage extrudé » → « Extruded Boss »)."""
    return translate(text, lang)
