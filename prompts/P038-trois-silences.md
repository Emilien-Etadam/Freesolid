# [P038] Trois choses qui ne marchent pas, et deux qui se taisent

Trois défauts relevés à l'usage réel. Ils sont localisés — chacun a son
adresse dans le code — mais **deux d'entre eux partagent la même faute de
fond : ils échouent sans rien dire.** Ce prompt demande de corriger les
trois, et de faire parler les échecs.

## 1. Le tracé ne se voit pas — cercle, ellipse, oblong

L'aperçu existe et fonctionne. Il n'a simplement **pas de branche** pour ces
outils-là.

`app/sketch.js:948-983` : la chaîne de `else if` couvre `line`, `rect`,
`rectc` et `spline`. Rien pour `circle`, `ellipse`, `slot`, ni `arc`, ni
`polygon` — qui souffrent du même manque et qu'il faut traiter en même temps
plutôt que d'y revenir.

`previewLine` est un `THREE.Line` : un cercle s'y dessine comme une polyligne
de son contour, une ellipse pareil, un oblong comme deux demi-cercles et deux
segments. Le point d'ancrage (centre posé au premier clic) est déjà dans
`mode.pending*` pour les outils qui en ont un — sinon l'ajouter sur le même
modèle que `mode.pendingRect`.

Le tracé suit le **snap**, comme les autres : `snap(local, event)`, pas la
position brute du curseur, sinon l'aperçu ment sur ce qui sera posé.

## 2. Les cotes du viewport ne s'affichent pas — et l'échec est muet

La chaîne est complète et correcte : `dblclick` (`app/main.js:1268`) →
`meshGroups[hoveredGroup].feature` → `showFeatureDims`. Le moteur remplit ce
`feature` par groupe (`kernel.py:4663`).

**Mais seulement si `_face_producers()` a trouvé quelque chose** — et il est
bâti sur un `face.hashCode()` enfermé dans un `try / except Exception:
continue` (`engine/kernel.py:364-382`).

```python
try:
    current[face.hashCode()] = index
except Exception:
    continue
```

Si `hashCode()` ne rend plus ce qu'il rendait — OCCT 7.8, embarqué depuis
FreeCAD 1.0, a retiré `TShape::HashCode` au profit de `std::hash` —
l'index reste **vide**, aucun groupe ne reçoit de `feature`, et le
double-clic ne montre rien. Sans un mot.

### Ce qu'il faut faire, dans cet ordre

**a. Mesurer avant de corriger.** Une sonde courte, sur le modèle de
`scripts/spike-*.py` : construire un bossage, appeler `_face_producers()`,
et dire combien de faces sur combien ont trouvé leur fonction. Si c'est
`0/6`, la cause est là. Si c'est `6/6`, elle est ailleurs et il faut
chercher côté client — ne pas corriger à l'aveugle.

**b. Ne plus avaler.** Ce `except Exception: continue` est la vraie faute :
il transforme une API cassée en fonctionnalité absente. Si l'appariement
échoue, la fonction doit le **dire** — au minimum un compte dans la réponse,
pour qu'un écran vide ait une explication.

**c. Le repli, si `hashCode` est bien le coupable.** `Shape.isSame()`
compare deux faces sans passer par un hachage. Le nombre de faces d'une
pièce se compte en dizaines : une comparaison par paires coûte moins que le
bug qu'on remplace. Mesurer avant de s'inquiéter du coût.

## 3. La barre latérale n'édite rien — et elle en a l'air

Ce n'est pas une sauvegarde qui rate. **Le panneau est en lecture seule, par
construction** (`app/sketch.js:1203-1230`) :

- les propriétés sont posées en `type: "note"` — du texte, pas des champs ;
- les relations n'offrent qu'un `onDelete` ;
- le panneau porte `noApply: true` — **aucun bouton Appliquer**.

Il porte même une note qui tente de rediriger : *« Pour piloter une valeur :
Cotation intelligente (D). »* Elle ne suffit manifestement pas : on voit une
valeur dans un panneau, on la modifie, on attend qu'elle s'applique.

**Rendre les cotes de ce panneau éditables sur place.** Le champ existe
déjà — `openDimEditor` (`app/dims.js`), le même qu'en esquisse et dans le
viewport depuis P036, virgule française et expressions comprises. Une cote
listée dans « Relations » se modifie donc comme partout ailleurs.

Ce qui **n'est pas** une cote (coïncidente, tangente, horizontale) garde son
comportement actuel : on la supprime, on ne la « valorise » pas.

Et si une valeur reste non modifiable pour une bonne raison, **elle doit en
avoir l'air** — grisée, pas offerte à la saisie.

## Le fil qui relie les trois

Le 1 est un manque simple. Les 2 et 3 sont la même erreur sous deux formes :
**quelque chose paraît devoir marcher, ne marche pas, et ne le dit pas.** Un
`except` qui avale, un panneau qui affiche sans permettre.

Donc, au-delà des trois correctifs : **quand une action reste sans effet,
l'écran doit le dire.** C'est ce qui distingue un outil d'un piège.

## Ce qu'il ne faut pas faire

- Ne pas ajouter l'aperçu pour le seul cercle en laissant ellipse et oblong.
- Ne pas corriger `_face_producers` sans avoir mesuré d'abord ce qu'il rend.
- Ne pas laisser un `except Exception: continue` sur un appariement qui
  conditionne une fonctionnalité visible.
- Ne pas rendre éditable ce qui n'est pas une cote.
- Ne pas toucher `app/vendor/`.

## Validation avant de pousser

```bash
python3 -m compileall -q engine
python3 -m pytest -q
node --check app/sketch.js && node --check app/main.js
node --test tests/js/*.test.mjs
PYTHONIOENCODING=utf-8 freecadcmd scripts/run-selftest.py
```

Le selftest doit gagner un indicateur : `_face_producers` apparie **toutes**
les faces d'une pièce simple, et non zéro. C'est le test qui aurait attrapé
le défaut 2 avant qu'il n'arrive à l'écran.

Smoke : tracer un cercle, une ellipse et un oblong en voyant le tracé suivre
le curseur ; double-cliquer une face et voir ses cotes ; modifier une cote
depuis la barre latérale et voir la pièce changer.

Plateforme de référence : **FreeCAD 1.1.3** (`AGENTS.md`).

## Commit

Un commit (ou une petite série cohérente), message en français, préfixé
`[P038]`, **donnant ce que la sonde du point 2a a mesuré** — combien de faces
sur combien étaient appariées avant correction. Tout texte visible par
l'utilisateur est en français, vocabulaire SolidWorks 2025.
