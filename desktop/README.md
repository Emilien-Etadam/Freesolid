# FreeSolid — application de bureau

> **Version de développement, non fonctionnelle** : comme le reste de
> FreeSolid, cette application est un prototype. Elle sert à essayer et à
> remonter des problèmes, pas à produire des pièces.

Une fenêtre [Tauri 2](https://tauri.app) autour du même `app/` + `engine/`
que la version navigateur. Rien n'est recalculé ailleurs que sur la machine
de l'utilisateur : l'app lance `freecadcmd engine/server.py` en processus
enfant, attend qu'il réponde sur `127.0.0.1:8787`, puis affiche l'interface
servie par ce moteur. Fermer la fenêtre arrête le moteur.

## Ce que fait l'écran de lancement

1. **Cherche FreeCAD** dans l'ordre : variable `FREESOLID_FREECADCMD`,
   chemin choisi par l'utilisateur (`config.json`), installation gérée par
   FreeSolid, `PATH`, emplacements habituels de l'OS (`/usr/bin`,
   `~/squashfs-root` du tutoriel, `C:\Program Files\FreeCAD *`,
   `/Applications/FreeCAD.app`…). Un binaire n'est retenu que s'il répond à
   `--version`.
2. **Propose l'installation** s'il n'y en a pas : téléchargement de l'archive
   officielle de la version de référence (`engine/platform.py`, `FREECAD`)
   depuis les releases GitHub de FreeCAD, vérification du `-SHA256.txt`
   publié à côté, extraction dans le dossier de données de l'app. Aucun
   droit administrateur, reprise du téléchargement si l'app est fermée
   entre-temps.
   - Linux : AppImage extraite (`--appimage-extract`, sans FUSE), x86_64 et aarch64
   - Windows : archive 7z portable, extraite par un décompresseur Rust
     (`tar.exe` de Windows en secours)
   - macOS : DMG monté, `FreeCAD.app` copié, DMG démonté
3. **Vérifie les mises à jour de FreeSolid** (voir plus bas) et les propose
   en un clic.
4. **Lance le moteur** et ouvre l'interface dans une fenêtre neuve.

Dans l'interface, le bouton engrenage ouvre **Paramètres** : version de
FreeSolid et de FreeCAD, chemin de `freecadcmd`, journal du moteur, liens
vers le dépôt, recherche et installation des mises à jour, réglages
d'affichage. La page est servie par le moteur (`127.0.0.1:8787`) ; elle
accède à l'API Tauri grâce à l'entrée `remote` de
`src-tauri/capabilities/default.json`.

L'écran de lancement est en français, ou en anglais si la langue du
système commence par « en » ; l'interface elle-même suit le choix fait dans
Paramètres → Langue. Une version de FreeCAD différente de la référence est
acceptée avec un avertissement. « Changer de FreeCAD… » et le choix manuel d'un fichier ou
d'un dossier restent disponibles à chaque étape.

Emplacements (par OS, via Tauri) :

| Quoi | Linux | Windows | macOS |
|---|---|---|---|
| Données (`config.json`, `freecad/<version>/`) | `~/.local/share/com.etadam.freesolid` | `%APPDATA%\com.etadam.freesolid` | `~/Library/Application Support/com.etadam.freesolid` |
| Journal du moteur (`engine.log`) | `~/.local/share/com.etadam.freesolid/logs` | `%LOCALAPPDATA%\com.etadam.freesolid\logs` | `~/Library/Logs/com.etadam.freesolid` |

## Développer

Prérequis : Rust stable, Node 22, et les
[dépendances système de Tauri](https://tauri.app/start/prerequisites/)
(sur Ubuntu : `libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev
patchelf`).

```bash
cd desktop
npm ci
npm run dev        # fenêtre en mode dev, recompilation Rust à la volée
npm run build      # installeurs dans src-tauri/target/release/bundle/
```

Tests du crate qui localise, installe et lance FreeCAD (pur Rust, sans
Tauri ni webkit, donc exécutable partout) :

```bash
cd desktop/src-tauri
cargo test -p freesolid-freecad
```

Structure :

```
desktop/
  ui/index.html            écran de lancement (JS sans bundler, API globale Tauri)
  src-tauri/
    src/lib.rs             commandes Tauri : status, install_freecad, choose_freecadcmd, start_engine
    freecad/               crate freesolid-freecad : locate, assets, install, engine, version, config
    tauri.conf.json        fenêtre, ressources embarquées (engine/, app/, plugins/), updater
    capabilities/          permissions accordées à l'écran de lancement
    icons/                 générées par `npm run icons` depuis ../icon.png
```

Pour forcer un binaire pendant le développement :
`FREESOLID_FREECADCMD=/chemin/vers/freecadcmd npm run dev`.

## Publier une version

Les installeurs sont construits par `.github/workflows/release.yml` sur un
tag `v*`, pour Linux (AppImage + deb), Windows (NSIS) et macOS (arm64 et
x86_64, `.app` + DMG). La release GitHub reçoit aussi `latest.json` et les
signatures que l'updater vérifie.

1. Mettre la même version dans `VERSION` (racine du dépôt, lue par le
   moteur et affichée dans Paramètres) et `desktop/src-tauri/tauri.conf.json`
   (`version`) ; le workflow refuse un tag qui ne correspond pas, et
   `tests/test_platform.py` vérifie que les deux fichiers s'accordent.
2. `git tag v0.1.0 && git push origin v0.1.0`.

### Clé de signature (une fois)

L'updater n'accepte qu'une mise à jour signée par la clé privée qui
correspond à `plugins.updater.pubkey` dans `tauri.conf.json`. Deux secrets
GitHub à créer dans le dépôt (Settings → Secrets and variables → Actions) :

- `TAURI_SIGNING_PRIVATE_KEY` : le contenu du fichier de clé privée
- `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` : son mot de passe. Si la clé n'en a
  pas, **ne créez pas ce secret** (GitHub refuse une valeur vide) : le
  workflow reçoit alors une chaîne vide, ce qui convient.

Pour générer une nouvelle paire (et remplacer `pubkey` dans
`tauri.conf.json`) :

```bash
cd desktop
npx tauri signer generate -w ~/.tauri/freesolid.key
```

Perdre la clé privée = les apps déjà installées ne pourront plus se mettre
à jour automatiquement (il faudra réinstaller).

## Mises à jour de FreeSolid

Au démarrage, l'écran de lancement interroge
`https://github.com/Emilien-Etadam/Freesolid/releases/latest/download/latest.json`
(plugin `tauri-plugin-updater`). Si une version plus récente existe, un
bandeau propose de l'installer : téléchargement, vérification de la
signature, remplacement de l'app, relance. Hors ligne ou sans release, rien
ne s'affiche.

Limites connues :

- Sur Linux, seule l'**AppImage** se met à jour toute seule ; le `.deb`
  passe par le gestionnaire de paquets.
- Sur macOS, les builds ne sont pas signés par Apple : au premier lancement,
  clic droit → Ouvrir. Une signature/notarisation Apple (secrets
  `APPLE_*` dans le workflow) lèvera cet avertissement.
- Les noms d'archives FreeCAD (`FreeCAD_<v>-<OS>-<arch>-py311.<ext>`) sont
  ceux de la série 1.1.x ; si FreeCAD change son nommage, adapter
  `freecad/src/assets.rs` (un test par plateforme).
