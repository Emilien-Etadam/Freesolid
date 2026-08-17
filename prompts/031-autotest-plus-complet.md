# P031 — Autotest plus complet (couverture + rapport lisible)

Demande utilisateur : « mets à jour l'autotest pour qu'il soit plus
complet ». L'Autotest = le bouton du ruban → op `selftest` du moteur.

## Diagnostic vérifié (ne pas re-diagnostiquer)

- Les 88 ops du protocole apparaissent déjà toutes dans le selftest —
  la couverture *nominale* est complète. Les trous réels sont ailleurs :
- **Chemins d'erreur** : 173 `raise KernelError` dans le moteur,
  ~125 messages de garde distincts — seulement **6** chemins de refus
  exercés par le selftest.
- **Profondeur des assertions** : 131 indicateurs mais à peine
  5 assertions de volume réel (beaucoup d'indicateurs = « pas
  d'erreur », pas « la géométrie est juste »).
- **Rapport invisible** : le bouton n'affiche que « Autotest OK —
  N faces, M triangles, reparam OK » ; tout le rapport part en
  `console.log`. L'étape `bilan` ne calcule aucun récapitulatif
  OK/échecs. (C'est ce qui avait déjà semé la confusion lors d'un test
  utilisateur : des erreurs console sans rapport lisible.)

## Mission moteur — `engine/kernel.py`

1. **Nouvelle étape `p31: gardes — les refus parlent français`** :
   exercer ~12 gardes utilisateur majeures, chacune via un indicateur
   booléen `p31_refus_*` qui vérifie que `KernelError` est levée **et**
   que le message français attendu y est. Choisir des gardes réelles
   existantes, par exemple (vérifiées) : suppression du dernier corps
   (« impossible de supprimer le dernier corps »), fonction sans
   esquisse disponible (« aucune esquisse disponible »),
   `set_tip` hors historique (« ligne d'historique »),
   `delete_feature`/`set_param`/`rename` sur nom inconnu (« fonction
   inconnue »), op d'esquisse sur nom inconnu (« esquisse inconnue »),
   `open_part` sur chemin inexistant, Combiner sans second corps,
   plan d'esquisse invalide. Ne PAS inventer de gardes : ne tester que
   des refus déjà présents dans le code.
2. **Nouvelle étape `p31: vérités géométriques`** : sur une pièce
   neuve, vérifier des valeurs exactes (tolérance 1e-6 relative) :
   bossage 40×30×10 → volume 12000 mm³ et 6 faces ; enlèvement
   traversant 10×10 → volume 11000 ; symétrie/répétition → volume
   multiplié comme attendu ; Combiner-soustraire → volume attendu.
3. **Nouvelle étape `p31: aller-retour complet`** : modèle riche
   (variable + expression sur une fonction, fonction renommée, couleur
   de corps, surface, esquisse libre, barre de retour posée au milieu
   via `set_tip`) → `save_part` → `open_part` → vérifier : variables,
   label renommé, couleur, flags `rolled_back`, position du tip, et
   volume identique avant/après (indicateurs `p31_reopen_*`).
4. **Aller-retour STEP** : exporter en STEP une pièce de volume connu,
   la réimporter, comparer les volumes à 0,1 % (`p31_step_roundtrip`).
5. **Annuler en chaîne** : 3 fonctions, 3 × `undo`, 3 × `redo`,
   volume et arbre identiques à l'état initial (`p31_undo_chain`).
6. **`bilan` récapitule** : fonction pure module-niveau
   `selftest_summary(report)` (sans FreeCAD) qui compte les
   indicateurs booléens top-niveau et liste les échecs ; l'étape
   `bilan` pose `report["bilan"] = {"verifications": N, "ok": M,
   "echecs": [noms]}`. Les étapes existantes ne changent pas.

## Mission client — `app/main.js`

Le clic Autotest devient lisible sans ouvrir la console :

- Statut : `Autotest : {steps} étapes, {ok}/{verifications}
  vérifications — OK` (ou ` — ÉCHEC` en rouge si `echecs` non vide),
  à partir de `report.bilan` (fallback : comportement actuel si le
  champ manque).
- Si `echecs` non vide : ouvrir un panneau d'information (comme le
  panneau d'infos d'esquisse : `noApply`) listant les indicateurs en
  échec, un par ligne. Pas de panneau quand tout est vert.
- Conserver le `console.log` du rapport complet et l'affichage
  d'échec d'étape existant (« échec à l'étape « X » »).

## Validation

- `python3 -m pytest tests/ -q` — nouveaux cas pour
  `selftest_summary` (rapport vide, tout vert, échecs listés, les
  non-booléens ignorés).
- Selftest complet sous freecadcmd : toutes les vérifications vertes,
  total attendu ≥ 115 + ~20 nouvelles.
- `node --check app/main.js`.
- `scripts/smoke/smoke.js` — nouveau pas final : cliquer
  `#btn-selftest`, attendre (jusqu'à 240 s) que le statut commence par
  « Autotest », vérifier qu'il contient « vérifications — OK » et
  qu'aucune erreur console n'apparaît.
- Commit(s) préfixés `[P031]`. Ne pas toucher `app/vendor/`.
