# P005 — Courses async client : refresh, aperçu, drag serveur, solveur local

Couvre les constats **1.1, 1.2, 1.3** (réponses obsolètes qui écrasent
un état plus récent) et **1.6** (solveur local sous-contraint) de
`docs/audit/2026-08-audit.md`. Périmètre : `app/main.js`,
`app/sketch.js`, `app/solver.js`, `app/panel.js` (uniquement si un
`isOpen()` doit y être exposé). Aucune modification moteur.

Principe commun aux trois premiers : **une réponse ne s'applique que si
elle est encore la plus récente.** Compteur monotone capturé au départ,
comparé au retour — jamais de booléen « busy » qui bloque l'utilisateur.

## 1. Jeton de génération sur le viewport (1.1)

Dans `app/main.js` : un compteur module `let viewGen = 0`.

- `refresh(treePromise)` et `refreshAny(...)` font `const gen = ++viewGen`
  en entrée, puis vérifient `gen === viewGen` après **chaque** `await`
  (avant `renderTree`, avant/entre les étapes d'`updateViewport`) ;
  sinon `return` silencieux.
- `updateViewport` reçoit le jeton (paramètre) plutôt que de lire une
  globale au mauvais moment.
- Scénario qui doit devenir sûr : deux Ctrl+Z rapides — la réponse du
  premier undo, plus lente, ne doit jamais réappliquer son arbre ni son
  maillage après ceux du second.

## 2. Jeton sur l'aperçu jaune (1.2)

Dans `schedulePreview` : compteur `previewGen` incrémenté à **chaque**
appel (y compris `built == null`). Le callback débouncé capture sa
génération ; au retour du `call("preview", …)` :

- génération obsolète → ne rien faire (pas de `showGhost`, pas de
  `clearGhost` — la génération courante s'en charge) ;
- panneau fermé entre-temps → ne rien faire. Si le panneau n'expose pas
  son état, ajouter un accesseur minimal (`panel.isOpen()` ou équivalent)
  dans `app/panel.js` — rien d'autre.

Scénario sûr : taper vite dans un champ puis fermer le panneau — aucun
fantôme ne doit réapparaître après la fermeture.

## 3. File sérielle pour le drag serveur (1.3)

Dans `app/sketch.js`, le chemin **fallback** (solveur local
indisponible) remplace le throttle 45 ms par une file sérielle :

- jamais plus d'un `sketch_move` en vol ;
- pendant qu'une requête est en vol, on ne garde que la **dernière**
  position `(x, y)` ; à la réponse, si une position est en attente, on
  l'envoie ;
- seule la réponse de la requête la plus récente peut faire
  `applyState` ;
- le `sketch_move` final du `onPointerUp` (chemin solveur local) passe
  par la même file — il ne doit pas doubler un move en vol.

L'update optimiste local (le point suit le curseur) reste tel quel.

## 4. Solveur local : `null` = non supporté (1.6)

Dans `app/solver.js`, `load()` : aujourd'hui seul `undefined` (type de
contrainte inconnu) désactive le solveur local ; un retour `null`
(contrainte connue mais références non résolues, ex. coïncidence vers
un point d'axe) est **ignoré** → le modèle local est sous-contraint et
le drag diverge du serveur jusqu'au lâcher. Correction :

- `translate` qui retourne `null` ou `undefined` → `load` retourne
  `false` (fallback drag serveur pour toute l'esquisse) ;
- un tableau vide (`Block`) reste valide ;
- mettre à jour le commentaire d'en-tête de `translate` (« zéro, une ou
  plusieurs ») pour reprendre la nouvelle politique.

## Validation avant push

1. `node --check` sur chaque JS modifié.
2. `python3 -m pytest tests/ -q` — inchangé (143), aucun fichier moteur
   touché.
3. Auto-relecture ciblée : lister dans la description de PR chaque
   `await` de `main.js` dont le retour applique de l'état viewport, et
   confirmer qu'il est gardé par le jeton.
4. Commit : `[P005] courses async client — jetons refresh/aperçu, file sketch_move, solveur local strict`.
