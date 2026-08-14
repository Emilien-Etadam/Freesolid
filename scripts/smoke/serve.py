# Lance le serveur FreeSolid sous freecadcmd avec stdout UTF-8 —
# freecadcmd démarre en ASCII et le « prêt » accentué le tuait.
#
#     freecadcmd scripts/smoke/serve.py
import os
import runpy
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
runpy.run_path(os.path.join(_ROOT, "engine", "server.py"))
