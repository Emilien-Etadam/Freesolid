# [P037] Quarante-trois secondes qui ne ressemblent pas à un plantage

Combiner un semis de 200 pierres coûte **43 s** (mesuré à la livraison de
P035). Aujourd'hui l'écran ne dit rien pendant ce temps-là. Un utilisateur
qui ne voit rien bouger pendant trois quarts de minute conclut au plantage et
tue l'onglet — emportant son travail avec lui.

## La contrainte qui commande la conception

`engine/server.py` est un `ThreadingHTTPServer`, donc il **accepte** une
seconde requête pendant qu'une opération tourne. Mais `_KERNEL_LOCK`
(`engine/server.py:36`) sérialise tout accès au noyau, délibérément :
« FreeCAD n'est pas thread-safe et `ThreadingHTTPServer` si ».

Conséquence directe, et elle n'est pas négociable :

> **L'op d'avancement ne doit toucher au noyau sous aucun prétexte.** Si elle
> prend le verrou, elle attend la fin du booléen et ne répond jamais.

Elle lit un **état de module** — un simple dict, écrit par le fil qui
travaille, protégé par son propre petit verrou — et rend la main
immédiatement. Aucun appel FreeCAD, aucune lecture de document.

## Le livrable

### 1. Un état d'avancement, hors du noyau

Dans `engine/server.py`, à côté de `_KERNEL_LOCK` et jamais dedans :

```
_PROGRESS = {"op": None, "phase": "", "fait": 0, "total": 0, "depuis": 0.0}
```

Le noyau le nourrit par un **callback** qu'on lui passe, pas par un import
du serveur : `engine/kernel.py` ne doit pas connaître le transport. Une op
`progress` le rend tel quel, sans passer par `_KERNEL_LOCK`.

Un test doit **prouver la non-régression la plus importante du prompt** :
`progress` répond pendant qu'une op longue tient le verrou. Sans ce test,
quelqu'un réintroduira le verrou un jour sans s'en apercevoir.

### 2. Ne pas inventer un pourcentage

Un `PartDesign::Boolean` est **un appel OCCT opaque**. Il n'en sort ni
pourcentage ni battement, et c'est là que passe l'essentiel des 43 s.

Ce qui est réellement observable, et donc tout ce qu'on a le droit
d'afficher :

| Phase | Ce qu'on peut dire |
|---|---|
| Construction du compound | **une pierre à la fois** : « 47 / 200 » — la boucle sur `PlacementList` est comptable |
| La soustraction elle-même | rien de comptable. Indicateur **indéterminé** + secondes écoulées |
| Reconstruction de l'arbre | phase nommée |
| Tessellation | phase nommée |

**Une barre qui monte à 90 % puis s'arrête ment**, et ment précisément au
moment où l'utilisateur a le plus besoin d'être rassuré. Une phase nommée
plus un compteur de secondes ne ment pas.

### 3. Prévenir vaut mieux qu'occuper

Le meilleur retour visuel reste celui qui **évite l'attente**.

Le nombre de pierres est connu avant de commencer, et le coût unitaire se
mesure. Avant de lancer, annoncer : *« 200 pierres — environ 40 secondes.
Continuer ? »*

L'utilisateur peut alors décider de **reculer la barre de reprise** et de
continuer à placer, plutôt que d'attendre pour rien. C'est ce qui respecte
le plus son temps, et ça ne coûte qu'une estimation.

Seuil : ne rien demander en dessous de quelques secondes. Une boîte de
dialogue pour trois pierres serait pire que le silence.

### 4. L'attente n'interdit pas de regarder

`app/main.js:554` pose une règle du dépôt : *« Jamais de booléen “busy” qui
bloque l'utilisateur »*. La respecter.

Pendant l'opération :

- **le ruban se grise** — pas de seconde op, le verrou la ferait attendre
  de toute façon ;
- **la vue 3D reste tournable** — c'est du client pur, ça ne coûte rien, et
  c'est ce qui distingue le plus nettement « ça travaille » de « c'est
  mort » ;
- la barre d'état (`statusEl`, `app/main.js:50`) porte la phase et les
  secondes.

Le client interroge `progress` toutes les ~300 ms, et **s'arrête dès que la
réponse de l'op revient** — pas de sondage orphelin qui continue après coup.

### 5. Ce qui se passe si ça casse

Après 43 secondes d'attente, une erreur qui disparaît en silence est le pire
des cas. Le message doit rester à l'écran jusqu'à ce que l'utilisateur en
prenne acte.

### 6. Pas de bouton Annuler qui ment

Un booléen OCCT en cours **ne s'interrompt pas**. Ne pas poser de bouton
Annuler qui laisserait croire le contraire : mieux vaut une attente honnête
qu'un bouton qui ne fait rien. Si l'estimation de l'étape 3 a fait son
travail, personne n'aura eu à le chercher.

## Ce qu'il ne faut pas faire

- Ne pas prendre `_KERNEL_LOCK` dans `progress`.
- Ne pas faire connaître le transport au noyau : un callback, pas un import.
- Ne pas afficher de pourcentage pour la soustraction.
- Ne pas bloquer la vue 3D.
- Ne pas poser de bouton Annuler.
- Ne pas toucher `app/vendor/`.

## Validation avant de pousser

```bash
python3 -m compileall -q engine
python3 -m pytest -q
node --check app/main.js
node --test tests/js/*.test.mjs
PYTHONIOENCODING=utf-8 freecadcmd scripts/run-selftest.py
```

Le test qui compte est unitaire et n'a pas besoin de FreeCAD : une op longue
simulée tient `_KERNEL_LOCK`, et `progress` répond quand même, avec la phase
en cours.

Smoke : poser une dizaine de pierres, combiner, vérifier que la barre d'état
nomme les phases, que le compteur de pierres avance pendant le compound, que
la vue se tourne encore, et que le ruban revient à la fin.

Plateforme de référence : **FreeCAD 1.1.3** (`AGENTS.md`).

## Commit

Un commit, message en français, préfixé `[P037]`, **donnant l'estimation
affichée et le temps réel mesuré** sur un semis de 200 pierres — l'écart
entre les deux dira si l'annonce de l'étape 3 est honnête. Tout texte visible
par l'utilisateur est en français, vocabulaire SolidWorks 2025.
