# P033 — Migration de la plateforme de référence vers FreeCAD 1.1.3

Décision utilisateur : basculer de 1.0.2 (fin de vie) vers 1.1.3
(dernière 1.1.x). Évaluation faite : le selftest complet donne
**144/146 sur 1.1.3** — seuls `p10_joint_solved` et
`p16_interference_found` tombent, tous deux à cause du solveur
d'assemblage. La compatibilité 1.0.2 est conservée par replis (pas de
double matrice de tests : la référence devient 1.1.3, la 1.0.2 est
vérifiée en revue).

## Diagnostic vérifié (ne pas re-diagnostiquer)

Tout est reproduit sur les AppImages 1.0.2 et 1.1.3 headless :

1. Sur 1.1.3, un joint dont les références sont **ancrées à
   l'assemblage** — `(asm, ["Component.Face1"])`, la forme posée en
   premier par `add_joint` — est accepté **silencieusement** mais
   jamais résolu : « MbD: Convergence = 0 », le joint reste `Touched`,
   les positions ne bougent pas. Aucune exception : c'est pour ça que
   le repli actuel ne se déclenche jamais.
2. Le banc d'essai natif du workbench (`TestCore.test_solve_assembly`)
   prouve que le solve **headless fonctionne** sur 1.1.3 — avec des
   références **directes à l'objet** et **deux sous-éléments** :
   `[obj, ["Face6", "Vertex7"]]`.
3. Vérifié sur nos composants réels (`App::Link` vers corps externe) :
   `joint.Proxy.setJointConnectors(joint, [(link1, ["Face1",
   "Face1"]), (link2, ["Face1", "Face1"])])` → **résolu** sur 1.1.3
   (joint `Up-to-date`, position exacte). Doubler le sous-élément
   `[s, s]` est légitime (banc natif : Face2+Face2 → centre de face ;
   `"Box."` doublé → identité) — un sub vide se double aussi.
4. Sur **1.0.2**, cette forme directe via `setJointConnectors` lève
   `AttributeError: 'NoneType' object has no attribute 'Placement'` —
   le mécanisme actuel (propriétés brutes, forme ancrée) doit rester
   en repli.
5. `_ground`/`GroundedJoint` fonctionne tel quel sur 1.1.3.
6. « The graph must be a DAG » à l'insertion d'un lien : bénin (le
   solve aboutit malgré lui) ; l'insertion canonique 1.1.3 est
   `asm.newObject("App::Link", …)` qui l'évite.
7. 1.1.3 a remplacé la propriété `Activated` des joints par
   `Suppressed` — le kernel n'utilise ni l'une ni l'autre : rien à
   faire.

## Mission moteur — `engine/kernel.py`

1. **`add_joint`** : construire les références en **forme directe
   doublée** `(link, [sub, sub])` (sub vide → `["", ""]`) et les poser
   via `joint.Proxy.setJointConnectors(joint, refs)` dans un try ;
   toute exception → repli sur le mécanisme actuel d'affectation des
   propriétés `Reference1`/`Reference2` (formes ancrée puis directe),
   inchangé. Le commentaire actuel sur « Expect input sequence of
   size 2 » reste vrai pour le repli. Après `setJointConnectors`, le
   solve est déjà déclenché par le module natif — garder quand même
   l'appel `_solve_assembly()` existant (idempotent, et c'est lui qui
   nettoie le joint si sur-contraint).
2. **`insert_component`** : créer le lien via
   `self._assembly_object().newObject("App::Link", "Component")` quand
   l'objet assemblage existe ; repli sur le chemin actuel
   (`doc.addObject` + `addObject`) pour les assemblages anciens
   format. Le label et le reste ne changent pas.
3. Mettre à jour la docstring de `new_assembly` (« spike validé sur
   1.1.3 » date d'avant — écrire : plateforme de référence 1.1.3,
   repli 1.0.2).

## Périphérie

- `README.md` : l'URL d'installation passe à
  `https://github.com/FreeCAD/FreeCAD/releases/download/1.1.3/FreeCAD_1.1.3-Linux-x86_64-py311.AppImage`
  (attention : plus de « -conda » dans le nom depuis 1.1).
- `.github/workflows/ci.yml` : tenter `freecad=1.1` sur conda-forge ;
  si indisponible, garder la version actuelle et le dire en
  commentaire — la CI ne doit pas casser.
- Ne rien changer au selftest : `p10_*` et `p16_*` doivent passer
  tels quels sur les deux versions après le correctif.

## Validation

- `python3 -m pytest tests/ -q` et `node --check` habituels.
- La validation FreeCAD double-version (selftest 146 indicateurs sur
  1.1.3 **et** 1.0.2, smoke sur 1.1.3) sera faite en revue avec les
  deux AppImages — signaler dans le commit si non lancée localement.
- Commit(s) préfixés `[P033]`. Ne pas toucher `app/vendor/`.
