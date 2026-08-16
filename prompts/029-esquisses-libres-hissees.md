# P029 — Esquisses libres hissées au-dessus de la barre de reprise

Suite directe de P028. Les esquisses libres ne sont pas dans la chaîne
PartDesign — comme les surfaces, elles n'ont rien à faire sous la barre
de reprise ni à paraître grisées.

## Mission — `app/main.js`

Étendre le hissage de P028 (surfaces au-dessus de la barre) aux lignes
d'esquisses **libres** (les entrées top-niveau de type
`Sketcher::SketchObject` de l'historique) : toute ligne d'esquisse libre
dont l'`order` la placerait après la barre est hissée juste avant, en
conservant l'ordre chronologique relatif entre esquisses et surfaces
hissées. Une esquisse libre n'est jamais marquée `rolled-back`.

La barre en bout de chaîne = barre tout en bas, esquisses et surfaces
comprises. Rien d'autre ne change (`tipTargetBefore` les saute déjà).

## Validation

- `node --check app/main.js` ; `python3 -m pytest tests/ -q` (inchangé).
- `scripts/smoke/smoke.js` : dans le pas existant de l'esquisse libre
  (P024), ajouter l'assertion : la ligne de l'esquisse libre est
  au-dessus de `li.rollback` dans le DOM et sans classe `rolled-back`.
- Commit(s) préfixés `[P029]`. Ne pas toucher `app/vendor/`.
