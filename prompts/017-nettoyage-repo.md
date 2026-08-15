# P017 — Nettoyage du dépôt : ne garder que l'app, README propre

Le dépôt porte encore la **piste 1** historique (l'addon Qt FreeCAD :
`Init.py`, `InitGui.py`, `package.xml`, `resources/`, `FreeSolid/`,
le paquet `freesolid/` et ses tests). Décision : le produit, c'est
**l'app** (`app/` + `engine/`). On retire l'addon et on réécrit le
README autour de l'app seule.

Suppression par `git rm` ordinaire — **pas de réécriture d'historique**
(pas de filter-branch/rebase : l'historique garde la trace de l'addon).

## 1. Rapatrier ce dont le moteur dépend (À FAIRE EN PREMIER)

`engine/kernel.py` importe deux modules du paquet addon :

- `freesolid.guard.friendly_error` (traduction des erreurs OCCT),
- `freesolid.vocab` (`label_for_type`, `label_for_origin` — les
  libellés SolidWorks français de l'arbre).

Les déplacer dans `engine/` : `engine/guard.py`, `engine/vocab.py` —
fichiers repris tels quels, imports mis à jour dans `kernel.py`
(3 sites, grep `freesolid.`) et dans leurs tests. Si `vocab.py` ou
`guard.py` importent d'autres modules du paquet addon, rapatrier le
minimum nécessaire — et le signaler dans la PR.

## 2. Supprimer (git rm)

- `Init.py`, `InitGui.py`, `package.xml`, `pyproject.toml` (il ne
  décrit que l'addon ; si des réglages utiles à l'app y vivent, les
  migrer d'abord),
- `resources/`, `FreeSolid/`,
- `freesolid/` (après l'étape 1),
- les tests qui ne testent QUE l'addon (`test_commands.py`,
  `test_context.py`, `test_diagnostics.py`, `test_prefs.py`, et tout
  autre du même genre — vérifier un par un ce qu'ils importent).
  `test_guard.py` et les tests de vocab restent (modules rapatriés),
  imports adaptés.
- `AGENTS.md` reste (outil de travail Cursor). `.editorconfig`,
  `.gitignore`, `LICENSE`, `.github/` restent.

Vérifier après coup : `grep -rn "freesolid" engine/ app/ tests/
scripts/ .github/` ne doit plus renvoyer que des occurrences du NOM du
produit (chaînes, commentaires), aucune d'import Python.

## 3. README.md — réécriture complète, en français

Structure attendue (court, précis, sans marketing creux) :

1. **Titre + une phrase** : FreeSolid — une interface de CAO mécanique
   moderne (vocabulaire SolidWorks, look Plasticity) sur un moteur
   FreeCAD headless intact ; fichiers 100 % .FCStd standard.
2. **Capture d'écran** : réutiliser une capture du smoke
   (`scripts/smoke/shots/` en local — en committer UNE dans
   `docs/img/`, taille raisonnable).
3. **Démarrage** : les trois commandes (freecadcmd + serve + ouvrir
   http://localhost:8787), prérequis FreeCAD ≥ 1.0.
4. **Ce qui marche aujourd'hui** : liste courte par domaine (esquisse
   contrainte + solveur WASM 60 fps, fonctions PartDesign, multi-corps
   et couleurs, assemblage + joints + solveur, surfacique, équations et
   expressions, import/export STEP/STL/3MF, mise en plan DXF cotée,
   image d'esquisse). Une ligne chacun, pas de tableau géant.
5. **Architecture** : trois couches en cinq lignes (app/ navigateur —
   engine/ HTTP JSON localhost — FreeCAD headless), lien vers
   `docs/architecture-app.md`.
6. **Développement** : lancer les tests (pytest, node --test, selftest,
   smoke), lien `prompts/README.md` pour le mode de travail.
7. **Licences** : LGPL-2.1-or-later, mention planegcs et icônes
   FreeCAD vendorées avec liens vers leurs README de provenance.

Mettre à jour les liens/mentions « addon » dans `docs/` si un doc y
réfère encore comme au produit courant (ne pas réécrire les docs
historiques — juste ce qui induirait en erreur aujourd'hui).

## 4. CI

`.github/workflows/ci.yml` : le job pytest tourne tel quel (moins de
tests, c'est attendu). Vérifier qu'aucun job ne référence un chemin
supprimé. Donner le nouveau compte pytest dans la PR.

## Validation avant push

1. `python3 -m pytest tests/ -q` — vert (compte réduit, le donner).
2. `node --test tests/js/*.test.mjs` — 50 verts ; `node --check` si JS
   touché (aucun attendu).
3. Selftest FreeCAD : 48 étapes — le compte d'indicateurs de la
   branche courante (99 si P016 est passé avant, 95 sinon) doit être
   conservé À L'IDENTIQUE : le rapatriement guard/vocab ne doit rien
   changer au moteur.
4. Smoke local vert.
5. `grep -rn "from freesolid\|import freesolid"` → zéro résultat.
6. Commit : `[P017] nettoyage — l'app seule (addon retiré, guard/vocab rapatriés, README réécrit)`.
