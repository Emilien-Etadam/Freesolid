# P032 — Expression refusée sans corrompre la pièce + gravure rééditable

Deux problèmes remontés par l'utilisateur sur la pièce vitrine, tous
deux reproduits sur FreeCAD 1.0.2.

## Diagnostic vérifié (ne pas re-diagnostiquer)

**A. Une saisie non numérique dans le panneau corrompt la pièce.**
Dans `set_params`, une chaîne non numérique part en
`obj.setExpression(prop, …)` ; si l'identifiant n'existe pas (ex. « _ »
saisi dans « Nombre d'occurrences » de la répétition circulaire),
l'expression est **stockée d'abord**, le recompute échoue **ensuite**
(« Property '_' not found in '_' »), et le refus laisse la liaison
cassée dans le document : l'objet reste `Invalid` et **tout recompute
ultérieur échoue** — la barre de retour semble bloquée, et la Gravure
cascade en « Tool shape is null ». Vérifié : retaper un nombre répare
(le chemin numérique efface l'expression), mais l'utilisateur ne peut
pas le deviner.
Vérifié aussi : « 6,5 » (virgule décimale française) passe par le
chemin expression et stocke silencieusement `('Occurrences', '6.5')`
au lieu d'être lu comme un nombre.

**B. La gravure de texte n'est pas rééditable.** `add_text` construit
une forme figée (`Part::Feature` « Forme du texte »), un corps outil et
une combinaison booléenne — aucun ne mémorise texte/taille/profondeur.
Double-clic « Forme du texte » → « Surface figée — non éditable » ;
double-clic « Gravure » → « aucun paramètre numérique éditable ». De
plus « Forme du texte » apparaît dans le dossier « Corps surfaciques »
et dans l'historique : c'est un artefact interne, pas une surface créée
par l'utilisateur.

## Mission moteur — `engine/kernel.py`

1. **`set_params` (et `set_param`) atomiques** : avant de poser une
   expression, mémoriser la liaison existante (`ExpressionEngine`) et
   la valeur ; après `setExpression`, recompute dans un try ; en cas
   d'échec, **restaurer** l'ancienne liaison (ou `None`) et la valeur,
   recompute, puis relever l'erreur en français (« expression refusée :
   … — la pièce n'a pas été modifiée »). Le document ne reste jamais
   `Invalid` après un refus.
2. **Virgule décimale** : dans le chemin valeur-chaîne, essayer
   `float(text.replace(",", "."))` AVANT le chemin expression — « 6,5 »
   est un nombre, pas une équation. (Une virgule dans une vraie
   expression reste refusée par l'allowlist : inchangé.)
3. **Gravure paramétrique rééditable** :
   - `add_text` pose sur l'objet booléen (la ligne « Gravure ») des
     propriétés custom persistées (précédent `FreeSolidColor`) :
     `FreeSolidTextString`, `FreeSolidTextSize`, `FreeSolidTextDepth`,
     `FreeSolidTextX`, `FreeSolidTextY`, `FreeSolidTextEmboss`,
     `FreeSolidTextFace` — et marque la forme (`Part::Feature`) et le
     corps outil comme internes (`FreeSolidTextTool = True`).
   - Nouvelle op `edit_text(feature, text=None, size=None, depth=None,
     x=None, y=None)` (protocol + kernel) : régénère la forme du texte
     en place (même logique de construction que `add_text`, mêmes
     placement/normal), met à jour les propriétés, recompute. Erreurs
     en français ; refus atomique (la pièce reste intacte si la police
     ne produit rien, etc.).
   - Les objets marqués `FreeSolidTextTool` disparaissent du dossier
     « Corps surfaciques », de l'historique, du `tessellate` des
     surfaces et des corps (`other_bodies`) — ils restent des artefacts
     internes du .FCStd. Les fichiers antérieurs (non marqués) gardent
     l'affichage actuel : pas de détection heuristique.
4. Selftest — nouveaux indicateurs : `p32_expr_refus_atomique`
   (expression inconnue → `KernelError` ET `ExpressionEngine` intact ET
   barre encore mobile), `p32_virgule_nombre` (« 6,5 » → nombre, pas
   d'expression), `p32_gravure_editable` (`edit_text` change le texte →
   le mesh change), `p32_forme_texte_cachee` (pas de « Forme du
   texte » dans surfaces/historique de la pièce vitrine). Adapter les
   indicateurs existants si la vitrine perd sa ligne « Forme du
   texte » (le compte de lignes d'historique du smoke passe de ≥ 7 à
   ≥ 6 si besoin — vérifier).

## Mission client — `app/main.js` (+ `app/features.js` si utile)

- Double-clic (ou clic droit → Modifier) sur la ligne « Gravure » :
  panneau dédié — champ texte (type text), Taille (mm), Profondeur
  (mm), X, Y — pré-rempli depuis les propriétés `FreeSolidText*`
  (exposées par `get_tree` ou `get_params` étendu, au choix le plus
  simple), Appliquer → `edit_text`. Aperçu non requis.
- Les gravures antérieures (sans propriétés) gardent le message actuel.
- Statut d'erreur d'expression : afficher le message moteur (déjà le
  cas via l'erreur normale).

## Validation

- pytest (garde FreeCAD comme `tests/test_rollback.py`) : atomicité
  (liaison intacte après refus, `set_tip` fonctionne ensuite), virgule,
  `edit_text` (texte changé, volume change ; erreurs propres),
  objets internes absents de l'arbre.
- Selftest complet sous freecadcmd : tout vert (≥ 142 + 4).
- `node --check` sur chaque JS modifié.
- `scripts/smoke/smoke.js` : après l'Autotest, double-cliquer la ligne
  « Gravure », changer le texte en « OK », Appliquer, vérifier statut
  sans erreur et mesh modifié (`mesh_triangles` ou capture) ; vérifier
  qu'aucune ligne « Forme du texte » n'apparaît dans l'arbre.
- Commit(s) préfixés `[P032]`. Ne pas toucher `app/vendor/`.
