# [N009b] Rendre la divergence de version impossible à manquer

Le N009 est **rouge en CI** : `selftest` et `smoke` échouent, `pytest` passe.
Autrement dit, les deux seuls jobs qui utilisent FreeCAD.

Le rapport de spike porte sa propre explication : il annonce ses mesures sous
**« FreeCAD 1.0.0 »**, alors que `AGENTS.md` fixe **1.1.3** comme plateforme
de référence depuis le P033 et que la CI épingle `freecad=1.1.3`
(`ci.yml:41,85`).

C'est la **deuxième fois**, en sens inverse :

| | Bac à sable (1.0.0) | CI (1.1.3) |
|---|---|---|
| N006 | smoke ❌ | smoke ✅ |
| N009 | selftest ✅ | selftest ❌ |

Deux tours de discussion perdus à débattre de résultats qui ne parlaient pas
de la même géométrie.

**Périmètre : l'environnement, le rapport de selftest, puis le spike rejoué.**

## 1. La divergence doit s'annoncer d'elle-même

C'est le cœur du prompt. « Penser à utiliser la bonne version » ne tient pas
— on l'a déjà écrit dans `AGENTS.md`, et ça n'a pas suffi.

- Le rapport de selftest porte la **version de FreeCAD** qui l'a produit.
  `Kernel` sait déjà la lire (`kernel.py:251`) : `App.Version()`.
- Si elle **diffère de la version de référence**, le selftest le dit en tête
  de rapport, de façon voyante — et **échoue**, plutôt que de rendre des
  chiffres qui ne veulent rien dire.
- La version de référence se lit à un seul endroit. La choisir — `AGENTS.md`
  est prescriptif mais c'est de la prose ; un fichier ou une constante que
  `ci.yml` et le selftest lisent tous les deux vaut mieux. **Une seule
  source**, comme pour tout le reste dans ce dépôt.

Un repli explicite reste possible (variable d'environnement pour travailler
sciemment sur une autre version), mais il doit **marquer le rapport** : les
mesures ne sont alors pas comparables.

## 2. L'échec doit être lisible en CI

`run-selftest.py` imprime bien les indicateurs faux **en dernier**
(`scripts/run-selftest.py:42`). Mais FreeCAD vide ses barres de progression
en sortie de processus, par un canal que Python ne contrôle pas — et le
diagnostic disparaît dessous. En CI, on lit des `(98 %)` au lieu du nom de
l'indicateur.

Un diagnostic qu'on ne peut pas lire ne sert à rien — c'est la leçon du
`REFUS:` au N004d, et elle se répète.

La sortie n'étant pas fiable pour ça, **écrire les indicateurs faux dans un
fichier**, et faire afficher ce fichier par le job en cas d'échec. Immunisé
contre l'entrelacement, parce qu'il ne dépend d'aucun ordre d'écriture.

Toute autre solution qui garantit la lisibilité convient — mais la vérifier
sur un échec réel, pas la supposer.

## 3. Puis rejouer le spike sur 1.1.3

Une fois 1 et 2 en place, reprendre le spike du N009 **sur la plateforme de
référence** et corriger ce que la version invalide.

Ce qui reste vrai quelle que soit la version, et n'est pas à refaire :

- la liste de ce qui se reconstitue depuis `get_params` et de ce qui ne se
  reconstitue pas ;
- la distinction entre **rupture d'indice** (la topologie change, 12 arêtes
  deviennent 24, `Edge3` désigne autre chose) et **échec géométrique** (le
  rayon du congé ne rentre plus) — cette distinction est le meilleur apport
  du spike ;
- le fait que 200 instances ne prennent pas plusieurs minutes.

Ce qui est à **remesurer**, parce que ce sont des chiffres :

- le volume attendu du cas minimal (20 160 mm³ sur 1.0.0) ;
- le seuil de rupture du congé (entre 4 et 3 mm sur 1.0.0) ;
- les temps pour 10, 50, 200 instances.

Et une question que le premier spike n'a pas posée, plus importante que les
seuils : **quand la topologie change, l'indice périmé produit-il une erreur
ou une géométrie silencieusement fausse ?** Un congé qui s'applique à la
mauvaise arête sans rien dire est bien pire qu'un refus. Si c'est silencieux,
la répétition variable aura besoin d'une garde de topologie — et ça change la
suite.

## Ce qu'il ne faut pas faire

- Ne pas ajuster les valeurs attendues pour que la CI passe : ce sont des
  mesures, elles se refont sur la bonne version.
- Ne pas désactiver ni assouplir un indicateur qui échoue.
- Ne pas exposer d'opération, ne pas construire la fonction d'arbre : le
  N009 reste un spike.
- Ne pas toucher `app/`, ni `app/vendor/`.

## Validation avant de pousser

```bash
python3 -m compileall -q engine
python3 -m pytest -q
PYTHONIOENCODING=utf-8 freecadcmd scripts/run-selftest.py
```

**La CI doit être verte** — c'est elle qui tranche, pas le bac à sable. Si
elle reste rouge, ne pas re-livrer : dire quel indicateur tombe et pourquoi.

**pytest** : la comparaison de version est de la logique pure — version
identique, version différente, repli explicite. Testable sans FreeCAD.

**selftest** : le rapport porte la version, et un échec provoqué est lisible
dans le job.

## Commit

Un commit par point, messages en français, préfixés `[N009b]`. Celui du
point 3 **porte les mesures refaites sur 1.1.3**, et répond à la question du
silence sur l'indice périmé.
