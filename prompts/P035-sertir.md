# [P035] Sertir — on pose, puis on combine

Suite directe de P034, qui a livré des pierres aimantées et déplaçables mais
**posées sur** la surface, jamais dedans. Ce prompt creuse les sièges.

La séparation n'est pas un découpage de commodité, c'est la décision
d'architecture du §7.4 bis de [`docs/bijouterie.md`](../docs/bijouterie.md),
et elle repose sur deux mesures :

| | Coût mesuré |
|---|---|
| Poser ou déplacer 200 pierres | **0,001 s** (sonde H5) |
| Creuser 200 sièges, compound et une seule coupe | **3,4 s** (sonde Q6) |
| Les mêmes, une coupe par pierre | **11,1 s** — et l'écart se creuse avec le nombre |

Si le siège se creusait à la pose, chaque déplacement relancerait le
booléen. D'où : **on pose, puis on combine**, en une opération explicite.

## Le livrable

### 1. Une fonction de l'arbre, jamais une cuisson

`combine_gems` crée **une ligne d'historique**, rééditable et supprimable —
pas un booléen appliqué une fois pour toutes.

C'est le point qui décide de tout le reste. Une cuisson trahirait la
promesse du projet au dernier geste : les pierres redeviendraient
impossibles à bouger, et l'ancrage `(u, v)` que P034 a construit ne servirait
plus à rien passé le sertissage.

La fonction **relit `(u, v)` à chaque recompute**, comme le semis lui-même :
bouger une pierre puis reconstruire doit redéplacer son siège. Le même
`_refresh_gem_placements` (`engine/kernel.py:285`) est déjà branché au bon
endroit ; le compound d'outils se rebâtit derrière.

### 2. Le siège est un gabarit, comme la gemme

`assets/sieges/conique.FCStd` — même mécanisme, même chemin, même
`copyObject`. Pas une forme calculée dans le code.

**Le siège n'est pas la pierre.** Un siège creusé au profil exact de la gemme
ne la laisserait pas entrer, et n'ouvrirait pas la culasse à la lumière.
Il lui faut donc ses propres cotes, pilotées par expressions :

| Variable | Rôle |
|---|---|
| `diametre` | celui de la pierre, repris tel quel |
| `jeu` | le desserrage, 0,02 à 0,05 mm — sans lui la pierre ne descend pas |
| `profondeur` | jusqu'où la culasse s'enfonce |
| `ouverture` | le trou traversant sous la culasse, qui laisse passer la lumière |

Construit par script, comme `cylindre-plat` (P034 §0) : la bibliothèque se
fabrique, elle ne se dépose pas à la main.

### 3. Un compound, une seule coupe

Non négociable, et chiffré : 3,4 s contre 11,1 s à 200 pierres, avec un écart
qui **grandit** (la coupe une par une est superlinéaire, le compound est
linéaire à ≈ 17 ms par pierre).

Donc : bâtir les N outils, `Part.makeCompound`, **une** soustraction.

Budget à annoncer à l'utilisateur, pas à masquer : sur une pierre facettée le
booléen coûte 2 à 4 fois plus qu'un cône (73 ms contre 19, sondes G4 et H7).
Un sertissage de 200 pierres peut donc demander une dizaine de secondes. **La
main doit passer au client** avant de creuser — un sertissage qui gèle
l'onglet sans rien dire sera pris pour un plantage.

### 4. La barre de reprise résout le coût, et elle existe déjà

Une fois le sertissage dans l'arbre, déplacer une pierre relancerait le
booléen à chaque geste. Le dépôt a **déjà** l'outil qui répond, et c'est
exactement le geste SolidWorks :

> `set_tip` avant la fonction de sertissage → on déplace les pierres à
> 60 fps, sans booléen ; `tip_to_end` → le sertissage se recalcule une fois.

**Ne rien inventer pour ça.** Vérifier que la barre de reprise traverse
correctement la nouvelle fonction, et que le semis reste manipulable
au-dessus d'elle — c'est tout ce que ce prompt demande de plus.

### 5. La garde qui refuse

Deux pierres trop proches donnent deux sièges qui se rejoignent, et le jonc
peut **se scinder en deux solides**. Le geste doit alors **refuser**, avec le
message qui dit lesquelles :

- après la coupe, si `len(shape.Solids) > 1` → refuser, annuler la
  transaction, nommer les pierres en cause ;
- si le volume enlevé dépasse une part déraisonnable du corps → même
  traitement.

Une pièce coupée en deux qui s'affiche sans rien dire est pire qu'une erreur.
C'est la ligne de conduite de N010 (« une garde qui refuse »), reprise ici.

### 6. Ce que le selftest doit prouver

À ajouter à `Kernel.selftest`, comme `p034_ancrage` :

1. poser trois pierres sur un jonc, sertir → **un seul solide**, volume
   strictement inférieur au jonc nu ;
2. **déplacer une pierre puis reconstruire** → son siège a suivi. C'est le
   test qui distingue une fonction d'une cuisson, et il doit tomber si
   quelqu'un fige le compound un jour ;
3. deux pierres délibérément superposées → la garde **refuse**, et le
   document reste utilisable.

## Ce qu'il ne faut pas faire

- Ne pas creuser à la pose : `place_gem` et `move_gem` restent sans booléen.
- Ne pas cuire — le sertissage est une ligne d'arbre, rééditable.
- Ne pas creuser avec la forme de la pierre : le siège a ses propres cotes.
- Ne pas boucler N soustractions : un compound, une coupe.
- Ne pas figer les placements du compound : ils se relisent depuis `(u, v)`.
- Ne pas ajouter de dépendance ; ne pas toucher `app/vendor/`.

## Validation avant de pousser

```bash
python3 -m compileall -q engine
python3 -m pytest -q
node --check app/main.js
node --test tests/js/*.test.mjs
PYTHONIOENCODING=utf-8 freecadcmd scripts/run-selftest.py
```

Smoke : poser trois pierres sur un jonc, sertir, vérifier le solide unique ;
reculer la barre de reprise, déplacer une pierre, avancer la barre, vérifier
que le siège a suivi. Étendre le smoke sans casser ses étapes.

Plateforme de référence : **FreeCAD 1.1.3** (`AGENTS.md`).

## Commit

Un commit (ou une petite série cohérente), message en français, préfixé
`[P035]`, **donnant le temps mesuré d'un sertissage de 200 pierres** sur la
machine de développement. Tout texte visible par l'utilisateur est en
français, vocabulaire SolidWorks 2025.
