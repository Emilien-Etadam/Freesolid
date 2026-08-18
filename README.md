# FreeSolid

Interface de CAO mécanique moderne sur un moteur FreeCAD headless intact — les fichiers restent des `.FCStd`
standard, ouvrables dans FreeCAD.

![FreeSolid — pièce après le smoke navigateur](docs/img/smoke.png)

## Démarrage

Si vous avez déjà FreeCAD ≥ 1.0 :

```bash
freecadcmd engine/server.py
# puis ouvrir http://localhost:8787
```

Un seul processus sert l'API JSON et l'UI statique (`app/`).

### Tutoriel pas à pas — Linux (aucun prérequis)

Copiez-collez ce bloc entier dans un terminal (Ctrl+Alt+T l'ouvre sur la
plupart des systèmes). Il télécharge FreeCAD (~800 Mo, une seule fois),
récupère FreeSolid et lance le serveur :

```bash
cd ~
curl -L -o FreeCAD.AppImage https://github.com/FreeCAD/FreeCAD/releases/download/1.1.3/FreeCAD_1.1.3-Linux-x86_64-py311.AppImage
chmod +x FreeCAD.AppImage
./FreeCAD.AppImage --appimage-extract
git clone https://github.com/Emilien-Etadam/Freesolid.git
cd Freesolid
~/squashfs-root/usr/bin/freecadcmd engine/server.py
```

Quand le terminal affiche « FreeSolid engine prêt », ouvrez
**<http://localhost:8787>** dans votre navigateur. C'est tout.

- Pour arrêter : `Ctrl+C` dans le terminal.
- Les fois suivantes, seules les deux dernières lignes sont nécessaires :

  ```bash
  cd ~/Freesolid
  ~/squashfs-root/usr/bin/freecadcmd engine/server.py
  ```

- Si `git` n'est pas installé (`git : commande introuvable`) :
  `sudo apt install git` (Ubuntu/Debian) ou téléchargez le ZIP du dépôt
  (bouton **Code → Download ZIP** sur GitHub) et décompressez-le dans
  votre dossier personnel.

### Tutoriel pas à pas — Windows

1. Installez FreeCAD 1.0 depuis
   [freecad.org/downloads](https://www.freecad.org/downloads.php)
   (installeur classique, options par défaut).
2. Sur la page GitHub du projet : bouton **Code → Download ZIP**, puis
   clic droit sur le ZIP → **Extraire tout** vers votre dossier
   `Documents`.
3. Ouvrez PowerShell (menu Démarrer → tapez « PowerShell ») et
   copiez-collez :

   ```powershell
   cd $env:USERPROFILE\Documents\Freesolid-main
   & "C:\Program Files\FreeCAD 1.0\bin\freecadcmd.exe" engine\server.py
   ```

   (Si FreeCAD est installé ailleurs, adaptez le chemin — cherchez
   `freecadcmd.exe` dans le dossier d'installation.)
4. Ouvrez **<http://localhost:8787>** dans votre navigateur.

## Ce qui marche aujourd'hui

- **Esquisse** contrainte + solveur WASM (planegcs) à ~60 fps pendant le
  drag ; décalage d'entités, symétrie, répétition, congé, ajustement
- **PartDesign** : bossage/enlèvement, révolution, congé, chanfrein, coque,
  dépouille, perçage, lissage, balayage, hélice, répétitions
- **Multi-corps** et couleurs d'affichage par corps
- **Assemblage** : composants, joints, solveur MbD, interférences
- **Surfacique** : extrusion/révolution de profils ouverts, lissage,
  épaissir — **paramétrique et rééditable** (double-clic, expressions) ;
  coudre reste figé
- **Équations** et expressions (variables globales, cotes pilotées)
- **Import/export** STEP, STL, 3MF ; sauvegarde/ouverture `.FCStd`
- **Mise en plan** DXF cotée (vues Face / Dessus / Iso), coupe X/Y/Z
  optionnelle
- **Image d'esquisse** (calque de fond)

## Architecture

Trois couches :

1. `app/` — navigateur (Three.js, FeatureManager, panneaux)
2. `engine/` — HTTP JSON sur `127.0.0.1:8787` (stdlib Python)
3. FreeCAD headless (`freecadcmd`) — géométrie, historique, STEP

Détail : [`docs/architecture-app.md`](docs/architecture-app.md).

## Développement

```bash
python3 -m pip install pytest
python3 -m compileall -q engine
python3 -m pytest -q

node --test tests/js/*.test.mjs

PYTHONIOENCODING=utf-8 freecadcmd scripts/run-selftest.py
# smoke navigateur (FreeCAD + Chromium) : scripts/smoke/
```

## Licences

LGPL-2.1-or-later, comme FreeCAD.

Composants vendorés :

- solveur d'esquisse WASM — [`app/vendor/planegcs/README.md`](app/vendor/planegcs/README.md)
- icônes FreeCAD — [`app/icons/README.md`](app/icons/README.md)
