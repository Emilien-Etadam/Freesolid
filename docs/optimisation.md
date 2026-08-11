# Analyse d'optimisation du code

État au 2026-08-11, après les phases A-E. Classement par gravité réelle,
pas par élégance. Ce qui est corrigé est marqué ✔.

## Corrigé dans la foulée de cette analyse

- ✔ **Concurrence moteur** (`engine/server.py`) : FreeCAD n'est pas
  thread-safe, `ThreadingHTTPServer` si. Un drag d'esquisse à ~20 Hz plus
  un aperçu jaune débouncé pouvaient exécuter deux ops en même temps dans
  le même document — corruption silencieuse possible. Un
  `threading.Lock` sérialise `dispatch()` : une op à la fois, par
  construction. Coût : nul (le moteur était déjà le goulot).

## À faire quand ça mordra (ordonné par rapport gain/effort)

1. **Re-tessellation intégrale après chaque op** (`updateViewport` :
   `tessellate` + `tessellate_edges`, chacun balayant corps actif +
   autres corps + surfaces). Sur les pièces de test c'est invisible ;
   sur une pièce à 200 fonctions ce sera le poste dominant. Remède :
   cache par empreinte de forme (`Shape.hashCode()` par corps), ne
   re-tesseller que ce qui a changé. Effort moyen, gain majeur sur
   grosses pièces.
2. **Latence du drag d'esquisse** : chaque mouvement = un aller-retour
   HTTP + solveur (throttle 45 ms → ~20 Hz). Le vrai remède est le
   chantier M3 (planegcs compilé en WASM, solveur dans le navigateur,
   60 fps, le serveur ne valide qu'au lâcher). C'est LE saut de fluidité
   restant.
3. **Poids du JSON de maillage** : les positions voyagent en doubles
   pleine précision (~2× trop gros). Remèdes par ordre de simplicité :
   arrondir à 10⁻⁴ mm ; puis passer les buffers en base64/Float32 si un
   jour le serveur n'est plus sur localhost. Non urgent tant que tout
   est local.
4. **Aperçu jaune = 2 recomputes par frappe** (exécution + annulation,
   débouncé à 250 ms). Correct sur pièces moyennes. Si ça rame :
   n'aperçevoir que la fonction en cours sur une copie de forme figée
   (Part API) au lieu de rejouer l'historique.
5. **redraw() d'esquisse reconstruit tout le groupe Three.js** à chaque
   état, y compris les sprites de cotes (un canvas réalloué par cote).
   Cache des sprites par texte + mise à jour incrémentale des lignes si
   les esquisses dépassent ~200 entités.
6. **Pile d'annulation non bornée** : chaque op UI est une transaction.
   FreeCAD borne par défaut, mais vérifier `UndoLimit` sur les longues
   sessions.
7. **`selftest` s'allonge** (~30 étapes, plusieurs documents créés/
   fermés). C'est un outil de diagnostic, pas un test de perf — le
   découper en `selftest?depuis=p8` si l'attente devient gênante.

## Non-problèmes examinés et écartés

- Rendu : `renderTree` reconstruit le DOM entier — trivial à cette
  échelle. Les ~55 SVG d'icônes sont servis en local et cachés par le
  navigateur. Les imports FreeCAD dans les méthodes du kernel sont des
  no-ops après le premier appel.
- Architecture : le protocole « ops nommées + params JSON » n'a aucune
  couche à retirer ; le picking par construction (groupes d'indices) est
  O(nb faces) au survol via `findIndex` — remplaçable par une table si
  une pièce dépasse ~10 000 faces.

## Risque de robustesse (hors perf) à garder en tête

- **Segfaults OCCT** (vu : chanfrein sur bord de coque dépouillée) :
  ininterceptable en Python, le serveur meurt. La parade architecturale
  est un processus travailleur relancé par un superviseur ; à construire
  le jour où ça mord en usage réel, pas avant.
