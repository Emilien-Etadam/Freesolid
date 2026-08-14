# P009 — Finitions de l'audit : lot de petites corrections

Le top 10 est soldé. Ce prompt regroupe les constats restants de
`docs/audit/2026-08-audit.md` qui sont petits (S), sans risque et
indépendants. Périmètre : `app/*.js`, `app/index.html`,
`app/vendor/planegcs/README.md` (une ligne), `README.md`,
`engine/kernel.py` (un point précis). Chaque item est autonome — si
l'un se révèle plus gros que prévu, le sauter et le dire dans la PR.

## Client

1. **1.4 — `addRectangle` non awaité** (`app/sketch.js`) : le handler
   du 2ᵉ clic doit attendre la construction des 4 lignes (ou poser un
   garde) pour qu'un changement d'outil pendant la construction ne
   désynchronise pas. Même vérification pour les autres constructions
   multi-appels s'il y en a (slot, polygone — vérifier).
2. **1.9 — `call()` aveugle au statut HTTP** (`app/main.js`) : si
   `!response.ok`, lever une erreur avec le statut et le début du corps
   (ex. `HTTP 502 — <extrait>`) au lieu de laisser `response.json()`
   échouer opaquement. Les réponses JSON `{ok:false}` gardent leur
   chemin actuel.
3. **1.10 — échec du `sketch_move` final sans resynchro** 
   (`app/sketch.js`) : dans le catch de la file sérielle, si la requête
   échouée était la dernière (`req.gen === moveGen`), recharger l'état
   (`sketch_state`) pour que la géométrie optimiste ne reste pas à
   l'écran.
4. **1.14 — parsing numérique incohérent** : helper unique `num(value)`
   (virgule française acceptée, `NaN` → `null`, jamais `|| 0` qui
   avale) dans un petit module partagé ; remplacer les
   `parseFloat(...) || 0` et les `replace(",", ".")` épars de
   `main.js`/`sketch.js`/`panel.js`. Ne changer AUCUN comportement
   voulu : les défauts existants restent des défauts explicites.
5. **7.4 — raccourcis esquisse sensibles à la casse**
   (`app/sketch.js`) : `event.key.toLowerCase()` pour les outils
   (L, R, C, S, E, A, T, G, D…).
6. **5.4 — contrat de `panel.js`** : compléter le commentaire de spec
   en tête de fichier avec les types de rows réellement utilisés
   (`list`, `text`, `note`… — vérifier la liste exacte) et
   `invalidateSelections`.
7. **5.5 — `arcAngles` dupliqué** (`sketch.js` / `solver.js`) :
   extraire dans `app/geom2d.js` importé des deux côtés.

## UI / textes

8. **7.1 — « Selftest »** (`app/index.html` + message dans
   `app/main.js`) : renommer le bouton « Autotest » (l'op moteur
   `selftest` ne change pas).
9. **8.4 — README racine vs icônes web** (`README.md`) : corriger la
   phrase « all icons are original » pour distinguer les icônes de
   l'addon Qt (originales) des SVG FreeCAD réutilisés par l'UI web
   (LGPL, documentés dans `app/icons/README.md`).

## Moteur / licences

10. **8.2 — typo licence planegcs**
    (`app/vendor/planegcs/README.md`) : LGPL-2.0-or-later →
    **LGPL-2.1-or-later** (aligné sur le fichier LICENSE vendu).
    C'est LA seule modification autorisée sous `app/vendor/`.
11. **2.6bis — `make_drawing` : l'erreur de nettoyage masque
    l'originale** (`engine/kernel.py`) : le `raise` du `finally`
    remplace l'exception du `try`. Ne lever l'erreur de nettoyage que
    si le `try` n'a pas déjà levé (flag), sinon laisser l'originale se
    propager (le nettoyage raté est alors couvert par l'abort de
    transaction) — la logguer dans le message de l'originale si
    faisable simplement.

## Validation avant push

1. `node --check` sur chaque JS modifié (y compris le nouveau
   `geom2d.js`).
2. `python3 -m pytest tests/ -q` — 153 verts.
3. Si FreeCAD dispo : selftest — 48 étapes / 87 indicateurs verts.
4. Description de PR : un tableau item → fait/sauté (avec raison si
   sauté).
5. Commit : `[P009] finitions audit — awaits, statut HTTP, resynchro drag, num(), raccourcis, Autotest, licences, make_drawing`.
