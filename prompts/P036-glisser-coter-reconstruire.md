# [P036] La pierre change de face, la cote s'édite, la pièce se reconstruit

Trois manques relevés au premier essai réel de P034, sur la machine de
l'auteur. Les trois se tiennent : ils portent tous sur le fait de **revenir
sur ce qu'on a posé**.

## 1. La pierre doit pouvoir glisser d'une face à l'autre

Aujourd'hui le drag reste sur la face d'ancrage. Sur un jonc — plusieurs
faces — la pierre bute à la première arête, alors que le geste attendu est de
la promener sur toute la pièce.

**Ce n'est pas qu'un raycast à élargir.** Un semis est aujourd'hui **groupé
par face** : `_find_semis` (`engine/kernel.py:1649`) cherche un `App::Link`
qui partage `(corps, face, gabarit, diamètre)`, et `FreeSolidGemFace` est
**une seule chaîne pour tout le semis**. Changer une pierre de face, c'est
donc :

1. retirer son entrée `(u, v, spin, lift)` du semis de départ ;
2. l'ajouter à celui de la face d'arrivée — en le **créant** s'il n'existe
   pas encore ;
3. **supprimer le semis de départ s'il se vide**, sinon l'arbre se remplit
   de lignes fantômes à zéro pierre.

`move_gem` accepte déjà un `face` optionnel : la migration se branche là,
sous le même appel. Côté client, le `pointermove` cesse de contraindre à la
face d'ancrage et lit le `faceId` du groupe touché — l'information est déjà
dans le maillage (`protocol.pack_mesh`).

À l'arrivée, un point à ne pas masquer : **au franchissement d'une arête, la
normale saute**. La pierre bascule d'un coup, et c'est correct — c'est ce que
dit la géométrie. Ne pas lisser, ne pas interpoler entre deux faces.

Refuser proprement si le point d'arrivée tombe hors du contour trimmé — la
garde existe déjà (`kernel.py:1643`), elle doit servir ici aussi : la pierre
revient à sa position d'avant le drag.

## 2. La cote doit s'éditer dans la zone graphique

Aujourd'hui les cotes ne sont **dessinées ni éditables hors du mode
esquisse** : `app/sketch.js:1063` sort immédiatement si `mode.state` est
faux. Pour changer le diamètre du volume de base il faut donc rouvrir
l'esquisse — alors que le geste SolidWorks est de **double-cliquer la
fonction dans la zone graphique** pour voir ses cotes, puis de
double-cliquer une cote pour la changer.

Le livrable, dans cet ordre :

1. **double-clic sur une face** → la fonction qui l'a produite s'identifie,
   et **ses cotes s'affichent en 3D**, à leur place, comme les cotes
   d'esquisse le font déjà ;
2. **double-clic sur une cote** → même champ d'édition qu'en esquisse,
   valeur ou expression ;
3. validation → `sketch_set_dim` si la cote vient de l'esquisse porteuse,
   `set_param` si c'est une propriété de la fonction ; puis reconstruction et
   rafraîchissement.

Les deux briques existent : `get_params` rend les propriétés numériques
éditables d'une fonction, et `sketch_state` rend les cotes nommées d'une
esquisse avec leur position. **Ne pas réinventer le champ d'édition** —
réutiliser celui de l'esquisse, y compris la virgule française et les
expressions.

Périmètre : les cotes de **la fonction sélectionnée**, pas toutes celles du
document. Une pièce entière couverte de cotes est illisible.

## 3. Un bouton « Reconstruire »

SolidWorks l'a, et il sert exactement quand on doute : forcer le recalcul
complet plutôt que le recalcul incrémental.

Côté moteur, FreeCAD le fait nativement — `doc.recompute(None, True, True)`
force le recalcul de **tout** l'arbre en ignorant les drapeaux « à jour ».
Une op `rebuild`, et le bouton dans le ruban.

Il doit :

- **tout retesseller et tout renvoyer** — la pièce, les arêtes, l'arbre, les
  semis ; c'est un bouton de dernier recours, il ne fait pas les choses à
  moitié ;
- **remonter les erreurs** plutôt que de les avaler : si une fonction refuse
  de se reconstruire, son message doit s'afficher — c'est précisément ce
  qu'on cherche en appuyant dessus.

## 0. Avant tout : reproduire, et dire ce qu'on a trouvé

L'auteur signale qu'après avoir édité la cote de l'esquisse du volume de
base, il **n'arrive pas à la modifier**. Les points 2 et 3 en sont la
réponse ergonomique — mais si la cote change **sans que la pièce se
reconstruise**, c'est un bug, et aucun bouton ne le rattrapera.

Donc, avant d'écrire quoi que ce soit :

> poser une pierre sur un cylindre, changer le rayon du cylindre par
> l'esquisse, et **regarder si le solide et la pierre bougent**.

Trois issues, trois traitements, et il faut dire dans le commit laquelle on
a rencontrée :

| Ce qu'on observe | Ce que ça veut dire |
|---|---|
| La cote refuse d'être rouverte | un blocage d'accès — point 2 |
| La cote change, rien ne bouge à l'écran | **un vrai bug** : le rafraîchissement client ne suit pas la reconstruction. À corriger *avant* le point 3, sinon le bouton masque la cause |
| Tout bouge, mais c'était pénible à atteindre | de l'ergonomie — points 2 et 3, et rien d'autre |

Le selftest `p034_ancrage` prouve que le moteur, lui, recale bien la pierre
après un changement de rayon. Si l'écran ne le montre pas, **le défaut est
entre le moteur et le client**, pas dans l'ancrage.

## Ce qu'il ne faut pas faire

- Ne pas lisser la normale au franchissement d'une arête.
- Ne pas laisser de semis vide dans l'arbre après une migration.
- Ne pas afficher les cotes de tout le document — celles de la sélection.
- Ne pas réécrire le champ d'édition de cote : celui de l'esquisse sert.
- Ne pas faire du bouton Reconstruire un cache-misère : si le point 0 révèle
  un bug de rafraîchissement, le corriger.
- Ne pas creuser : P036 ne touche pas au sertissage (c'est P035).
- Ne pas toucher `app/vendor/`.

## Validation avant de pousser

```bash
python3 -m compileall -q engine
python3 -m pytest -q
node --check app/main.js && node --check app/sketch.js
node --test tests/js/*.test.mjs
PYTHONIOENCODING=utf-8 freecadcmd scripts/run-selftest.py
```

Le selftest doit gagner trois indicateurs : une pierre **migrée d'une face à
l'autre** (le semis de départ a disparu, celui d'arrivée la porte), une cote
**changée hors mode esquisse** qui reconstruit la pièce, et un `rebuild` qui
rend une pièce identique à elle-même.

Smoke : poser une pierre, la faire glisser **par-dessus une arête** sur la
face voisine, changer la cote du volume de base **sans rouvrir l'esquisse**,
vérifier que la pierre suit, puis Reconstruire.

Plateforme de référence : **FreeCAD 1.1.3** (`AGENTS.md`).

## Commit

Un commit (ou une petite série cohérente), message en français, préfixé
`[P036]`, **disant laquelle des trois issues du point 0 a été rencontrée**.
Tout texte visible par l'utilisateur est en français, vocabulaire
SolidWorks 2025.
