# planegcs (WASM) — vendored

Source : [@salusoft89/planegcs](https://www.npmjs.com/package/@salusoft89/planegcs) v1.2.0
— le solveur de contraintes planegcs de FreeCAD (Sketcher), compilé en
WebAssembly. Licence **LGPL-2.0-or-later** (fichier LICENSE ci-contre),
comme le reste des composants FreeCAD réutilisés par FreeSolid.

Contenu : la distribution `dist/` du paquet npm telle quelle (fichiers
`.js` ES modules + `planegcs_dist/planegcs.wasm`), sans les `.d.ts` ni
les source maps. Aucune modification locale — pour mettre à jour,
réinstaller le paquet npm et recopier `dist/`.

Utilisé par `app/solver.js` (M3) : résolution locale des esquisses
pendant le drag, à 60 fps sans aller-retour serveur.
