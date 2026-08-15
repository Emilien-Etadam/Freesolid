"""HTTP server binding the protocol to the kernel — stdlib only.

Run with the Python that has FreeCAD, typically freecadcmd:

    freecadcmd engine/server.py

Then open http://localhost:8787 — the server also serves the static UI from
``app/``, so one process gives one working tab. Localhost only: this is a
local tool, not a service.
"""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from engine import kernel as kernel_mod          # noqa: E402
from engine import protocol                      # noqa: E402

PORT = 8787
_APP_DIR = os.path.join(_REPO_ROOT, "app")
_MAX_BODY_BYTES = 4 * 1024 * 1024

#: One document per server process — M0 scope.
_KERNEL = kernel_mod.Kernel()

#: FreeCAD n'est pas thread-safe et ThreadingHTTPServer si : un drag à
#: 20 Hz plus un aperçu débouncé pouvaient entrer en collision dans le
#: même document. Une op à la fois, par construction.
_KERNEL_LOCK = threading.Lock()

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".wasm": "application/wasm",
}


def _origin_ok(origin, port=PORT):
    """``Origin`` absent = autorisé (curl, scripts) ; sinon allowlist locale."""
    if origin is None or origin == "":
        return True
    allowed = {
        "http://127.0.0.1:{}".format(port),
        "http://localhost:{}".format(port),
    }
    return origin in allowed


def _payload_ok(headers, max_bytes=_MAX_BODY_BYTES):
    """Vérifie Content-Type et Content-Length d'un POST /api.

    Returns:
        ``(None, length)`` si OK, sinon ``(status, message_fr)``.
    """
    content_type = headers.get("Content-Type", "")
    if not content_type.lower().startswith("application/json"):
        return 403, "Content-Type application/json requis"

    raw_length = headers.get("Content-Length")
    if raw_length is None or raw_length == "":
        return 413, "Content-Length manquant ou invalide"
    try:
        length = int(raw_length)
    except (TypeError, ValueError):
        return 413, "Content-Length manquant ou invalide"
    if length < 0 or length > max_bytes:
        return 413, "requête trop volumineuse (maximum 4 Mo)"
    return None, length


def _safe_static_path(url_path, app_dir=_APP_DIR):
    """Résout un chemin UI sous ``app_dir``, ou ``None`` si hors jail / absent."""
    path = "/index.html" if url_path in ("", "/") else url_path
    # Ignore query/fragment — serving is path-only.
    path = path.split("?", 1)[0].split("#", 1)[0]
    candidate = os.path.join(app_dir, path.lstrip("/"))
    real_app = os.path.realpath(app_dir)
    real_candidate = os.path.realpath(candidate)
    try:
        if os.path.commonpath([real_app, real_candidate]) != real_app:
            return None
    except ValueError:
        return None
    if not os.path.isfile(real_candidate):
        return None
    return real_candidate


class Handler(BaseHTTPRequestHandler):

    # -- api -------------------------------------------------------------

    def do_POST(self):  # noqa: N802 - stdlib API name
        if self.path != "/api":
            self._send(404, {"ok": False, "error": "POST /api uniquement"})
            return
        if not _origin_ok(self.headers.get("Origin")):
            self._send(403, protocol.err(
                "origine non autorisée — FreeSolid n'accepte que "
                "localhost"))
            return
        check = _payload_ok(self.headers)
        if check[0] is not None:
            status, message = check
            self._send(status, protocol.err(message))
            return
        length = check[1]
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            op, params = protocol.validate_request(payload)
        except (protocol.ProtocolError, ValueError) as exc:
            self._send(400, protocol.err(str(exc)))
            return
        with _KERNEL_LOCK:
            response = kernel_mod.dispatch(_KERNEL, op, params)
        self._send(200, response)

    # -- static UI -------------------------------------------------------

    def do_GET(self):  # noqa: N802 - stdlib API name
        candidate = _safe_static_path(self.path)
        if candidate is None:
            self._send(404, {"ok": False, "error": "introuvable"})
            return
        ext = os.path.splitext(candidate)[1]
        with open(candidate, "rb") as handle:
            body = handle.read()
        self.send_response(200)
        self.send_header("Content-Type",
                         _CONTENT_TYPES.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- plumbing --------------------------------------------------------

    def _send(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Quiet by default; the terminal is the user's, not a log sink.
        pass


def main():
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError as exc:
        print("FreeSolid engine : impossible d'ouvrir le port {} ({})".format(
            PORT, exc))
        print("Un autre serveur tourne peut-être déjà — fermez-le ou "
              "réessayez.")
        return
    print("FreeSolid engine prêt : http://localhost:{}".format(PORT))
    print("(Ctrl+C pour arrêter)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


# No `if __name__ == "__main__"` guard: freecadcmd executes scripts without
# setting __name__ to "__main__", so the guard made the server import cleanly
# and exit without serving (seen on 1.1.3). The env var is the escape hatch
# for anything that needs to import this module without binding the port.
if os.environ.get("FREESOLID_NO_SERVE") != "1":
    main()
