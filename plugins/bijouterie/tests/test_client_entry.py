"""Le JS client est annoncé dès que le fichier existe."""

from engine.plugins import client_plugins, default_registry


def test_bijouterie_announces_js_entry():
    listed = client_plugins(default_registry())
    entry = next(
        (item for item in listed["plugins"] if item["nom"] == "bijouterie"),
        None)
    assert entry is not None
    assert entry["entree"] == "/plugins/bijouterie/plugin.js"
