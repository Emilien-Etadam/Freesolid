# P002 — Sécurité serveur : jail chemins, anti-CSRF, traversal, cap requête

Couvre les constats **3.1** (bloquant), **3.2** (bloquant), **3.3**
(majeur) et **3.8** (suggestion) de `docs/audit/2026-08-audit.md`.
Périmètre strict : `engine/protocol.py`, `engine/kernel.py`,
`engine/server.py`, `tests/`. Rien d'autre.

## 1. Jail des chemins fichiers (3.1)

Nouvelle fonction **pure** dans `engine/protocol.py` (donc testable sans
FreeCAD) :

```python
def resolve_user_path(path, extensions, must_exist=False):
    """Résout un chemin fourni par le client, ou lève ProtocolError."""
```

Règles :

- `expanduser` puis `os.path.realpath` (les symlinks sont résolus AVANT
  les vérifications).
- Le chemin résolu doit être sous l'une des racines autorisées :
  le home de l'utilisateur, `tempfile.gettempdir()`, et
  `FREESOLID_DATA_DIR` si cette variable d'environnement est définie.
  Comparaison par `os.path.commonpath`, jamais par `startswith`.
- Aucun composant du chemin **relatif à la racine autorisée** ne
  commence par `.` (protège `~/.bashrc`, `~/.ssh/...` tout en
  autorisant un home du type `/home/user`).
- L'extension (insensible à la casse) doit être dans `extensions`.
- `must_exist=True` → le fichier doit exister (lectures) ;
  sinon le **dossier parent** doit exister (écritures).
- Messages d'erreur en français, explicites (« chemin hors du dossier
  autorisé », « extension non autorisée : … »).

Brancher dans `engine/kernel.py` sur TOUS les sites qui font
actuellement `os.path.expanduser(str(path))` (audit : lignes ~166, 709,
1004, 1624, 1689, plus la police de `add_text` ~769) :

| Op | extensions | must_exist |
|---|---|---|
| `open_part` | `.FCStd .step .stp .iges .igs` | oui |
| `save_part` | `.FCStd` | non |
| `export_part` | `.stl .step .3mf` | non |
| `make_drawing` | `.dxf` | non |
| `insert_component` | `.FCStd` | oui |
| `add_text` (police) | `.ttf .otf` | oui |

Attention : `save_part` ajoute `.FCStd` si absent — faire cet ajout
**avant** l'appel à `resolve_user_path`. Les polices auto-détectées côté
serveur (liste interne de `add_text`) ne passent pas par le jail, seules
les polices fournies par le client y passent.

## 2. Anti-CSRF sur POST /api (3.2)

Dans `engine/server.py`, `do_POST` refuse en **403** (avec un JSON
`{ok: false, error: …}` en français) quand :

- l'en-tête `Origin` est présent et n'est pas dans
  `{"http://127.0.0.1:8787", "http://localhost:8787"}` (port réel du
  serveur, pas 8787 en dur — il y a une constante) ; **ou**
- le `Content-Type` ne commence pas par `application/json`.

`Origin` absent = autorisé (curl, scripts locaux). Le client
(`app/main.js`) envoie déjà du JSON — vérifier qu'il pose bien
`Content-Type: application/json` sur son `fetch`, et l'ajouter si ce
n'est pas le cas (seule modification client permise dans ce prompt).

## 3. Traversal statique (3.3)

Remplacer le check `normpath` + `startswith(_APP_DIR)` de `do_GET` par :
`realpath` du candidat puis
`os.path.commonpath([realpath(_APP_DIR), candidat]) == realpath(_APP_DIR)`.
Toujours 404 en cas de refus (ne pas révéler la raison).

## 4. Cap Content-Length (3.8)

`do_POST` : refuser en 413 toute requête dont `Content-Length` dépasse
4 Mo, ou est absent/invalide.

## Tests (obligatoires, dans `tests/`)

Nouveau `tests/test_security.py`, pur (aucun import FreeCAD) :

- `resolve_user_path` : chemin home OK ; tempdir OK ; `/etc/passwd`
  refusé ; `~/../ailleurs` refusé ; `~/.ssh/x.FCStd` refusé ;
  mauvaise extension refusée ; casse d'extension acceptée (`.fcstd`) ;
  `must_exist` sur fichier absent refusé ; symlink pointant hors jail
  refusé (créer le lien dans `tmp_path`).
- Handlers HTTP : tester la logique Origin/Content-Type/Content-Length
  en l'extrayant dans des fonctions pures de `server.py`
  (ex. `_origin_ok(origin)`, `_payload_ok(headers)`) plutôt qu'en
  lançant un vrai serveur.

## Validation avant push

1. `python3 -m pytest tests/ -q` — tout vert (107 existants + nouveaux).
2. `node --check app/main.js` si touché.
3. Si FreeCAD est disponible : `scripts/run-selftest.py` doit rester
   vert — le selftest écrit dans `tempfile.gettempdir()`, qui est une
   racine autorisée ; si un chemin du selftest sort du jail, adapter le
   **selftest** (pas le jail).
4. Commit : `[P002] sécurité serveur — jail chemins, anti-CSRF, traversal, cap requête`.
