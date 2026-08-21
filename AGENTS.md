# AGENTS.md

## Cursor Cloud specific instructions

FreeSolid est une **app web** (`app/` + `engine/`) : moteur FreeCAD
*headless* (`freecadcmd`) exposé en HTTP JSON sur `127.0.0.1:8787`, qui sert
aussi l'UI statique de `app/` (Three.js). Un seul processus = un onglet.

Les modules purs du moteur (`engine/vocab.py`, `engine/guard.py`,
`engine/protocol.py`, …) n'importent pas FreeCAD au niveau module — c'est
ce qui les rend testables en CI. Les imports FreeCAD restent dans les
corps de fonctions / méthodes.

### FreeCAD headless

- Installé via micromamba dans l'environnement `freecad`.
  **La version de référence est `engine/platform.py` (`FREECAD`)** — une
  seule source, lue par le selftest et par `.github/workflows/ci.yml`.
  Binaire micromamba : `~/.local/bin/micromamba` (racine par défaut
  `~/micromamba`, donc `MAMBA_ROOT_PREFIX` n'a pas besoin d'être exporté).
- Lancer une commande FreeCAD :
  `~/.local/bin/micromamba run -n freecad freecadcmd <script.py>`
- **Repli 1.0.x** via le kernel (`setJointConnectors` puis propriétés
  `Reference1`/`Reference2`) pour les joints. Le selftest **refuse** une
  version autre que la référence, sauf repli explicite
  `FREESOLID_ALLOW_FREECAD=<version>` — le rapport est alors marqué
  incomparable.
- Réinstaller l'env si le snapshot ne l'a pas conservé :
  `~/.local/bin/micromamba create -y -n freecad -c conda-forge freecad=$(python3 -c 'from engine.platform import FREECAD; print(FREECAD)')`

### Lancer / tester

- **Tests unitaires + byte-compile** (sans FreeCAD) : depuis la racine,
  `python3 -m compileall -q engine` puis `python3 -m pytest -q`.
- **Tests JS** : `node --test tests/js/*.test.mjs`.
- **Selftest headless** (valide tout le flux modélisation) :
  `PYTHONIOENCODING=utf-8 ~/.local/bin/micromamba run -n freecad freecadcmd scripts/run-selftest.py`
- **Serveur + UI** : `~/.local/bin/micromamba run -n freecad freecadcmd engine/server.py`
  puis ouvrir `http://localhost:8787`. Le geste hello-world : cliquer
  Esquisse → dessiner un rectangle → Bossage extrudé ; ou double-cliquer une
  fonction de l'arbre pour rééditer sa cote (reconstruction paramétrique).

### Gotcha à connaître

- `engine/server.py` n'a **pas** de garde `if __name__ == "__main__"`
  (volontaire). Le mécanisme exact, vérifié dans la source amont le
  2026-08-21 (`src/App/Application.cpp:3108-3117`) : `freecadcmd fichier.py`
  ne *lance* pas le script, il l'**importe comme module** — `addPythonPath`
  sur le dossier, puis `loadModule` sur le radical du nom. D'où trois
  conséquences : `__name__` vaut `"server"` et jamais `"__main__"`, le
  dossier du script entre dans `sys.path`, et le nom de module est le
  radical du fichier. FreeCAD ne retombe sur une vraie exécution — dans une
  **copie** du dict de `__main__` — que si l'import lève.
  L'échappatoire est la variable
  `FREESOLID_NO_SERVE` : si elle vaut `1` dans l'environnement, `server.py`
  se termine sans ouvrir le port. Les scripts de selftest la posent — donc
  **ne pas laisser `FREESOLID_NO_SERVE=1` exporté** dans le shell avant de
  démarrer le serveur, sinon il quitte silencieusement (bannière FreeCAD
  puis retour au prompt, port fermé).
- Le moteur ne gère **qu'un document par processus** (portée M0). Redémarrer
  le serveur pour repartir d'un document vierge.
