"""HTTP server binding the protocol to the kernel — stdlib only.

Run with the Python that has FreeCAD, typically the AppImage's freecadcmd:

    ~/freesolid-test/squashfs-root/usr/bin/freecadcmd \
        ~/freesolid-test/Mod/freesolid/engine/server.py

Then open http://localhost:8787 — the server also serves the static UI from
``app/``, so one process gives one working tab. Localhost only: this is a
local tool, not a service.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from engine import kernel as kernel_mod          # noqa: E402
from engine import protocol                      # noqa: E402

PORT = 8787
_APP_DIR = os.path.join(_REPO_ROOT, "app")

#: One document per server process — M0 scope.
_KERNEL = kernel_mod.Kernel()

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
}


class Handler(BaseHTTPRequestHandler):

    # -- api -------------------------------------------------------------

    def do_POST(self):  # noqa: N802 - stdlib API name
        if self.path != "/api":
            self._send(404, {"ok": False, "error": "POST /api uniquement"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            op, params = protocol.validate_request(payload)
        except (protocol.ProtocolError, ValueError) as exc:
            self._send(400, protocol.err(str(exc)))
            return
        response = kernel_mod.dispatch(_KERNEL, op, params)
        self._send(200, response)

    # -- static UI -------------------------------------------------------

    def do_GET(self):  # noqa: N802 - stdlib API name
        path = "/index.html" if self.path in ("", "/") else self.path
        # No traversal: only plain files inside app/.
        candidate = os.path.normpath(os.path.join(_APP_DIR, path.lstrip("/")))
        if not candidate.startswith(_APP_DIR) or not os.path.isfile(candidate):
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
