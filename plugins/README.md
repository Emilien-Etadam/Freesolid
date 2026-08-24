# plugins/ — les modules verticaux

FreeSolid est un outil de CAO généraliste. Ce qui relève d'un métier
particulier vit dans un **plugin** : un répertoire posé ici, chargé au
démarrage du moteur.

## Installer un plugin

Déposez son répertoire ici, et redémarrez le moteur :

```
plugins/
└── bijouterie/
    ├── plugin.json     manifeste : nom, module, opérations, dossier statique
    ├── plugin.py       enregistre crochets, opérations et contributions
    └── ui/             le JavaScript, servi sous /plugins/<nom>/…
```

Il n'y a **pas de chargement à chaud** : la liste est lue une fois, au
démarrage. Personne n'a besoin de brancher un plugin sans redémarrer un
logiciel de CAO, et le rechargement à chaud multiplierait les états
possibles.

## Ce qu'un plugin peut faire

Le registre (`engine/plugins.py`) offre, côté moteur, cinq points de
contribution — `after_recompute`, `tree_contribution`, `mesh_contribution`,
`op`, `selftest_step` — et trois crochets de reconnaissance :
`tolerates_invalid`, `boolean_tool`, `deletes_feature`. Côté client
(`app/plugins.js`) : `ribbon`, `feature`, `hud`, `key`, `treeRow`,
`viewport`, `pointer`.

La surface privée du noyau qu'un plugin a le droit d'appeler est
**épinglée par un test** — `tests/test_plugins.py::test_surface_plugin_reste_disponible`.
La renommer casserait un plugin hors dépôt sans que rien ne s'allume ici.

## Un plugin absent est un silence, pas une erreur

Le registre attrape toute exception autour du `register()` d'un plugin :
un plugin cassé ne doit pas empêcher FreeSolid de démarrer. L'erreur part
dans `registry.notes`.

Ça a un revers. Le selftest ne rend alors que les indicateurs du noyau —
tous verts — et `run-selftest.py` sort 0. **Un plugin qui ne se charge
plus rend une CI verte.** C'est exactement ce qu'une CI de plugin croit
vérifier et ne vérifiait pas.

Deux remèdes, tous deux dans `scripts/run-selftest.py` :

- les notes du registre sont **imprimées à chaque lancement** — une panne
  de chargement est lisible au lieu d'être muette ;
- `FREESOLID_SELFTEST_PLUGINS=nom1,nom2` **exige** ces plugins : chargés,
  et ayant contribué au moins un indicateur. Sinon, sortie 1.

C'est au dépôt du plugin de poser la variable dans sa CI — lui seul sait
ce qui doit être là. Le noyau, lui, ne doit rien exiger : il tourne très
bien sans aucun plugin.

## Sécurité

Un plugin est du Python arbitraire, dans le processus du moteur, avec les
mêmes droits. **Pas de bac à sable, et pas de dialogue de consentement** —
contrairement au nœud Python de `engine/scriptnode.py`.

La différence est délibérée : un script arrive dans un `.FCStd` qu'on a pu
recevoir de n'importe qui, un plugin est un répertoire que vous avez
**délibérément posé** ici. Le geste d'installation *est* le consentement,
comme pour n'importe quel paquet.

Le manifeste, lui, reste validé et jailé : ni `..`, ni chemin absolu, ni
séparateur dans `module` ou `statique`.

## Le premier plugin

**Bijouterie** — pierres aimantées sur les surfaces, réglage du diamètre au
clavier, écart entre pierres affiché, combinaison booléenne.
Sa conception est documentée dans [`docs/bijouterie.md`](../docs/bijouterie.md).
