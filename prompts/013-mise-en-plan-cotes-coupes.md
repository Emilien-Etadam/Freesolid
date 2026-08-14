# P013 — Mise en plan : cotes et vue en coupe

Produit (`docs/fonctions-manquantes.md` : « Cotes de mise en plan » et
« Coupes, sections, détails »). Aujourd'hui `make_drawing` sort trois
vues DXF muettes — utilisable pour un atelier, pas comme plan. Objectif :
des **cotes automatiques** et une **vue en coupe** optionnelle.

Périmètre : `engine/kernel.py` (make_drawing + selftest),
`engine/protocol.py` (params optionnels — pas de nouvelle op),
`app/main.js` (panneau mise en plan enrichi), `tests/`.

## 1. Cotes automatiques (TechDraw::DrawViewDimension)

`make_drawing` accepte un nouveau paramètre optionnel `dims=True` :

- Sur la vue de face, poser automatiquement les cotes d'**encombrement**
  (largeur + hauteur de la boîte englobante de la vue) via
  `DrawViewDimension` (Type "DistanceX"/"DistanceY", References2D sur
  les arêtes extrêmes de la vue). C'est le niveau « plan d'atelier » ;
  les cotes fonctionnelles complètes restent hors périmètre.
- Si l'API refuse (références 2D introuvables sur cette forme),
  continuer **sans** cote plutôt qu'échouer — le DXF muet reste
  meilleur que pas de DXF ; remonter `dims_ok: false` dans le retour.
- Le retour de l'op gagne : `{path, size, dims_ok?: bool}`.

Spike conseillé avant d'écrire : sur la boîte du selftest, sortir dans
un script jetable la liste des arêtes 2D de la vue (`getEdgeByIndex` /
`getVisibleEdges` selon la version) pour choisir les références — noter
dans la PR ce qui marche sur 1.0.x.

## 2. Vue en coupe (TechDraw::DrawViewSection)

Paramètre optionnel `section="X"|"Y"|"Z"` (défaut : pas de coupe) :

- Ajouter une `DrawViewSection` basée sur la vue de face, plan de coupe
  passant par l'origine, normale selon l'axe demandé
  (`SectionNormal`/`SectionOrigin` + `BaseView`), hachures par défaut.
- La vue s'ajoute à la page exportée en DXF comme les autres ; même
  politique d'échec : si la section échoue (géométrie non coupable),
  continuer sans elle et remonter `section_ok: false`.

## 3. Protocole

`make_drawing` garde sa déclaration typée actuelle (path). `dims` et
`section` sont **optionnels** : documentés en commentaire, non typés
(cohérent avec la règle P008). Pas de mise à jour de snapshot (aucune
nouvelle op).

## 4. UI

Le bouton Mise en plan (`btn-drawing`) ouvre déjà un flux — l'enrichir :
panneau PropertyManager (s'il n'existe pas déjà, le créer dans le
registry `features.js` si le flux s'y prête, sinon rester bespoke) :

- chemin du fichier (texte, comme aujourd'hui),
- échelle (existant),
- check « Cotes d'encombrement » (défaut coché),
- select « Coupe » : Aucune / X / Y / Z (défaut Aucune).

Après succès : message existant + « (sans cotes) » si `dims_ok` est
faux, « (sans coupe) » si `section_ok` est faux.

## 5. Selftest

Étendre l'étape mise en plan (p13) :

- `make_drawing(..., dims=True, section="Y")` sur la pièce existante →
  `p13_dims_ok` (le retour dit `dims_ok` vrai) et `p13_section_ok`.
  Si le spike révèle qu'une des deux APIs est indisponible en 1.0.x,
  l'indicateur reflète la réalité (`dims_ok` faux accepté) MAIS le
  DXF doit toujours sortir — et le constat précis (API, version,
  erreur) va dans la description de PR pour décision.
- Le nettoyage TechDraw existant doit rester vert
  (`p13_drawing_clean_ok`) — les nouvelles vues/cotes sont aussi des
  objets à purger.

## Validation avant push

1. `python3 -m pytest tests/ -q` — 153 verts.
2. `node --check` sur les JS modifiés ; `node --test` — 50 verts.
3. Selftest FreeCAD : 48 étapes, 92 indicateurs verts attendus (90+2 —
   ou constat documenté si une API manque en 1.0.x).
4. Smoke local vert.
5. Commit : `[P013] mise en plan — cotes d'encombrement + vue en coupe (TechDraw)`.
