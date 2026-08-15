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

- Installé via micromamba dans l'environnement `freecad` (**FreeCAD 1.0.0**).
  Binaire micromamba : `~/.local/bin/micromamba` (racine par défaut
  `~/micromamba`, donc `MAMBA_ROOT_PREFIX` n'a pas besoin d'être exporté).
- Lancer une commande FreeCAD :
  `~/.local/bin/micromamba run -n freecad freecadcmd <script.py>`
- **Version — ne pas prendre 1.1.x pour le selftest.** La CI épingle
  `freecad=1.0.0`. Sur FreeCAD **1.1.0**, le solveur d'assemblage MbD se
  comporte différemment : un joint « fixe » ne repositionne pas le
  composant, donc `p10_joint_solved` et `p16_interference_found` échouent.
  C'est une différence de comportement du moteur (M4 « à re-scoper »), pas
  un bug du dépôt. Rester en `1.0.x`.
- Réinstaller l'env si le snapshot ne l'a pas conservé :
  `~/.local/bin/micromamba create -y -n freecad -c conda-forge freecad=1.0.0`

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
  (volontaire : `freecadcmd` n'exécute pas les scripts avec
  `__name__ == "__main__"`). L'échappatoire est la variable
  `FREESOLID_NO_SERVE` : si elle vaut `1` dans l'environnement, `server.py`
  se termine sans ouvrir le port. Les scripts de selftest la posent — donc
  **ne pas laisser `FREESOLID_NO_SERVE=1` exporté** dans le shell avant de
  démarrer le serveur, sinon il quitte silencieusement (bannière FreeCAD
  puis retour au prompt, port fermé).
- Le moteur ne gère **qu'un document par processus** (portée M0). Redémarrer
  le serveur pour repartir d'un document vierge.
