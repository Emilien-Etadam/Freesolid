# Macros et graphe de nœuds — parti pris

Décisions du 2026-08-15, à la suite du relevé Chili3D / Nodes de
[`landscape.md`](landscape.md). Ce document fixe **ce qu'on construit et
dans quel ordre** ; il ne décrit pas encore d'UI.

Trois choix sont posés :

1. Le graphe de nœuds est **à part**, façon Grasshopper, et **optionnel**.
2. Ses nœuds produisent de **vraies fonctions PartDesign rééditables**, pas
   des formes `Part` figées.
3. Le FeatureManager gagne une **vue en graphe** de l'arbre existant.

Le reste de ce document est la conséquence de ces trois choix — dont une
difficulté que (1) et (2) créent ensemble et qu'il faut trancher avant
d'écrire une ligne.

## 1. La difficulté : deux éditeurs pour la même fonction

Grasshopper n'a pas ce problème parce que sa géométrie cuite est **muette** :
pas d'historique, rien à rééditer, on relance le graphe et ça refait un
objet neuf. En demandant des fonctions **rééditables**, on obtient l'inverse :
le bossage produit par le graphe est un `PartDesign::Pad` normal, que le
double-clic ouvre comme n'importe quel autre.

D'où la question, qui n'a que trois réponses :

> L'utilisateur change la cote d'un bossage dans l'arbre, puis relance le
> graphe. Qui gagne ?

**(C) Ne pas trancher** est la mauvaise réponse : deux éditeurs sur le même
objet, le dernier arrivé écrase, l'utilisateur perd son travail sans
comprendre pourquoi. Restent (A) et (B).

### (A) Cuisson — le graphe génère puis lâche prise ✅ retenu

Le graphe produit les fonctions et **s'en détache**. Une fois cuites, elles
appartiennent à l'utilisateur : double-clic, cotes, expressions, suppression,
tout marche comme d'habitude. Relancer le graphe ne les touche pas — ça
produit un **nouveau corps**.

- Le `.FCStd` reste un document FreeCAD **strictement normal**. Aucune
  métadonnée FreeSolid sur les fonctions, aucun verrou.
- Rien de nouveau à persister, donc rien à faire fuir.
- C'est le modèle mental que les utilisateurs de Grasshopper ont déjà :
  *bake*, et après c'est à toi.
- Prix assumé : le graphe est un **générateur**, pas un lien vivant. Changer
  un paramètre dans le graphe ne met pas à jour la pièce déjà produite.

### (B) Lien vivant — le graphe reste propriétaire ❌ écarté pour l'instant

Les fonctions issues du graphe seraient marquées et **non éditables au
double-clic** ; pour les changer on rouvre le graphe. Un seul point de
vérité, et c'est séduisant.

Ça casse pourtant la promesse centrale du projet, de façon sournoise. Le
marquage passerait par une propriété custom — le précédent existe,
`FreeSolidColor` est déjà posé comme ça (`kernel.py:1241`) — mais **FreeCAD
ignore ce marquage**. L'utilisateur ouvre son `.FCStd` dans FreeCAD, où rien
ne signale que ces fonctions sont pilotées, les modifie, revient dans
FreeSolid : le graphe est silencieusement périmé. Un désaccord de couleur est
sans conséquence ; un désaccord sur qui possède une fonction n'en est pas un.

(B) n'est pas exclu à jamais — il est exclu **tant que le fichier doit rester
ouvrable dans FreeCAD sans piège**. À rouvrir seulement si l'usage réclame
un vrai lien vivant, et avec une réponse à ce problème-là.

## 2. Où vit le graphe

Le graphe est logiquement à part, mais un fichier séparé se perd : c'est
exactement le travers `.gh` + `.3dm` de Grasshopper, où envoyer le modèle
sans le graphe est l'erreur la plus fréquente.

Piste retenue, **à valider par spike** : ranger le graphe **dans le `.FCStd`**
sous forme d'un objet [`App::TextDocument`](https://wiki.freecadweb.org/Std_TextDocument/en)
contenant son JSON. C'est un type FreeCAD standard, prévu pour du texte
arbitraire, sérialisé dans le `.FCStd` comme le reste.

On obtient les deux propriétés à la fois : le graphe voyage avec la pièce
(un seul fichier à envoyer), et le document reste **standard** — FreeCAD
l'ouvre, y voit un objet texte, ne casse rien. À l'opposé d'une propriété
custom, un `App::TextDocument` ne prétend rien sur les fonctions : c'est une
annexe, pas un verrou. Cohérent avec (A).

À vérifier au spike : qu'un `App::TextDocument` créé en headless survit à
l'aller-retour sauvegarde/ouverture, et que sa présence ne gêne aucun
recalcul. *(Un fil FreeCAD signale un cas d'incompatibilité avec des
documents FEM — hors de notre périmètre, mais à confirmer.)*

## 3. Ce que les nœuds sont réellement

**Un nœud = une opération du protocole.** Le graphe n'évalue pas de
géométrie : il produit une **liste ordonnée d'opérations** envoyée au moteur,
qui construit de vraies fonctions PartDesign. Les fils portent des paramètres
et des références de fonctions, jamais des solides.

C'est ce qui rend le choix (2) — fonctions rééditables — presque gratuit :
`add_pad` appelé par un graphe produit exactement le même `PartDesign::Pad`
que `add_pad` appelé par un clic. Aucune voie de construction nouvelle,
aucune géométrie à écrire, et les 88 opérations de `engine/protocol.py`
revalident tout à l'identique.

Corollaire à ne pas perdre : **le graphe est l'interface graphique des
macros**, pas un système parallèle. Il n'a de sens qu'une fois les macros
faites, et il hérite de leur contrainte — une macro reste une liste
d'opérations validées, jamais du Python exécuté (voir `landscape.md` §2).

Ce que ce modèle ne donne pas d'emblée : les *data trees*, donc semer 500
perçages sur une surface gauche. Étage au-dessus, à ouvrir seulement sur
besoin réel ; `j8sr0230/Nodes` — LGPL-2.1 comme nous — a déjà résolu ce
problème avec `awkward`, son code est empruntable le jour venu.

## 4. La vue en graphe du FeatureManager

Décision 3, et c'est la brique à faire **en premier** : sans géométrie, sans
macro, sans risque.

Une nuance de coût relevée dans le code, contre ce que laissait entendre le
relevé initial : ce n'est pas gratuit. `get_tree` (`kernel.py:2234`)
**n'émet pas les dépendances**. Il lit bien `Profile` pour imbriquer une
esquisse consommée sous sa fonction, mais il jette le reste — plans
d'attachement (`AttachmentSupport`), `BaseFeature`, corps outils des
booléens. Le résultat est une liste plate à un niveau d'imbrication, pas un
graphe.

Le travail est donc :

| Étape | Où | Coût |
|---|---|---|
| Émettre les arêtes du graphe | `get_tree` : un champ `deps` par entrée, alimenté par `obj.OutList` filtré au corps | 🟢 faible — la donnée est dans FreeCAD, il suffit de ne plus la jeter |
| Étendre le contrat | `protocol.py` + tests | 🟢 faible, mais c'est un changement de protocole : à faire proprement |
| Dessiner le graphe | client | 🟧 le vrai morceau — disposition, lisibilité sur une pièce à 60 fonctions |

Ce que ça rapporte tout de suite, indépendamment des nœuds : la réponse à
« d'où vient cette face », que l'arbre plat cache. Une répétition qui
référence une esquisse qui s'attache à un plan qui dépend d'une autre
fonction, c'est illisible en liste et évident en graphe.

Et surtout : **c'est le même composant de rendu que l'éditeur de nœuds**, en
lecture seule. Le construire d'abord, c'est régler la disposition et la
lisibilité sur des données qu'on a déjà, avant d'y brancher de l'édition.

## L'ordre

1. **Vue graphe du FeatureManager** — `deps` dans `get_tree`, rendu client
   en lecture seule. Utile seul, et prépare le terrain.
2. **Spike `App::TextDocument`** — aller-retour headless, une demi-journée.
   Décide où vit le graphe.
3. **Macros** — enregistrement des opérations, relecture, paramétrage par
   expressions. Le morceau dur est la résolution de références (rejouer sur
   un autre document).
4. **Éditeur de nœuds** — l'interface graphique de l'étape 3, en mode
   cuisson (A), rangé dans le document (étape 2), rendu avec le composant de
   l'étape 1.

Chaque étape est utile sans la suivante, et aucune ne demande d'écrire de la
géométrie.
