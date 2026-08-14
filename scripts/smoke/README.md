# Smoke test navigateur

Le parcours utilisateur canonique joué par un vrai Chromium contre un
vrai serveur FreeCAD : esquisse sur plan → rectangle → drag de coin
(solveur planegcs WASM) → bossage avec aperçu jaune → OK → Ctrl+Z →
Ctrl+Y. **Toute erreur console ou page fait échouer le test.**

## Lancer en local

```bash
# 1. dépendances (une fois) — three est épinglé sur la version de
#    l'importmap d'app/index.html et servi à la place d'unpkg
cd scripts/smoke && npm install

# 2. le serveur, avec le Python de FreeCAD
freecadcmd scripts/smoke/serve.py &

# 3. le test (CHROMIUM_PATH si Chromium n'est pas géré par Playwright)
node scripts/smoke/smoke.js
```

Variables : `SMOKE_URL` (défaut `http://127.0.0.1:8787`),
`CHROMIUM_PATH` (chemin d'un Chromium système ; sinon Playwright
résout le sien).

Les captures d'écran de chaque étape sont écrites dans
`scripts/smoke/shots/` (ignoré par git).

Note : le serveur garde son document entre deux runs — le test est
tolérant (il repart de l'état courant), mais un serveur frais donne le
parcours de référence.
