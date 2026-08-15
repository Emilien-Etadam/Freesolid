# Macros et graphe de nœuds — parti pris

Décisions du 2026-08-15, à la suite du relevé Chili3D / Nodes de
[`landscape.md`](landscape.md). Ce document fixe **ce qu'on construit et
dans quel ordre** ; il ne décrit pas encore d'UI.

Le parti pris tient en une phrase : **le graphe n'est pas un objet, c'est une
vue**. Il n'y a rien à séparer du document, donc rien à resynchroniser.

Trois choix en découlent :

1. Le graphe **est** le document — pas un fichier à côté, pas un JSON rangé
   dedans, pas un modèle parallèle.
2. Ses nœuds sont de **vraies fonctions PartDesign rééditables** — ce sont
   celles de l'arbre, pas des copies.
3. La vue en graphe du FeatureManager n'est donc pas une étape préparatoire :
   c'est **la chose elle-même**, d'abord en lecture, plus tard en édition.

## 1. Ce que « ne rien séparer » fait disparaître

La première rédaction de ce document posait le graphe comme un artefact
distinct, et butait aussitôt sur une question sans bonne réponse :

> L'utilisateur change la cote d'un bossage dans l'arbre, puis relance le
> graphe. Qui gagne ?

Il fallait alors choisir entre la **cuisson** (le graphe génère puis lâche
prise — mais il ne pilote plus rien) et le **lien vivant** (le graphe reste
propriétaire — mais il faut verrouiller les fonctions par une propriété
custom que FreeCAD ignore, donc une édition faite dans FreeCAD périme le
graphe en silence). Les deux étaient des consolations.

**La question ne se pose que parce qu'il y a deux modèles.** Si le graphe
*est* le document, il n'y a plus qu'un point de vérité : double-cliquer une
cote dans l'arbre et tirer un fil dans le graphe sont deux gestes sur les
mêmes objets, passés par les mêmes opérations du protocole. Rien à cuire,
rien à verrouiller, rien à périmer.

Ce qui tombe avec la séparation, et qu'on n'écrira donc pas : le format de
graphe et son évaluateur, la persistance en `App::TextDocument`, le marquage
des fonctions générées, la détection de désynchronisation, et la notion
d'identité stable nœud → fonction. C'est-à-dire l'essentiel du travail.

Le `.FCStd` reste **strictement un document FreeCAD** : aucune métadonnée
FreeSolid, aucune annexe. C'est la promesse du projet, tenue ici sans effort
plutôt que défendue de justesse.

## 2. Les fils existent déjà — il y en a deux sortes

Un graphe, c'est des nœuds et des arêtes. Les nœuds sont les objets du
document. Les arêtes aussi sont déjà là, sous deux formes que FreeCAD
distingue et que l'arbre plat mélange ou cache :

| Arête | D'où elle vient | Ce qu'elle dit |
|---|---|---|
| **Géométrique** | `obj.OutList` — `Profile`, `AttachmentSupport`, `BaseFeature`, corps outils des booléens | *ce bossage consomme cette esquisse, qui s'attache à ce plan, qui dépend de cette face* |
| **Paramétrique** | le moteur d'expressions — `ExpressionEngine`, déjà lu par `_expression_map` (`kernel.py:2166`) | *cette cote vaut `2*largeur + 5`, donc elle est pilotée par la variable `largeur`* |

Le deuxième point mérite d'être vu pour ce qu'il est : **les expressions sont
déjà le flux de données**. `D1@Bossage1 = 2*largeur + 5` est littéralement
une arête entre le `App::VarSet` et une propriété de fonction. La phase A a
construit la couche dataflow du projet sans l'appeler ainsi ; le graphe ne
fait que la rendre visible.

C'est aussi ce qui répond aux « curseurs » de Grasshopper sans rien
inventer : un paramètre d'entrée du graphe est une **variable globale**, elle
existe, elle est persistée, elle est déjà éditable dans le panneau Équations.

## 3. Ce que ce modèle ne fera pas

Le prix de « ne rien séparer » est net, et il vaut mieux l'écrire maintenant
que le découvrir : **le graphe ne peut exprimer que ce que le document sait
exprimer.**

Tombent donc, tant qu'on s'y tient :

- les **nœuds intermédiaires sans objet de document** (un nœud « addition »
  flottant) — sauf s'ils se ramènent à une expression, ce qui couvre le
  plus gros des cas ;
- les **boucles et les listes** — semer 500 perçages sur une surface gauche.
  Ce sont les *data trees* de Grasshopper, et ils exigent un évaluateur qui
  n'est pas celui de FreeCAD ;
- la **géométrie générative** non paramétrique (Voronoï, remplissages
  algorithmiques), qui est le terrain naturel de `j8sr0230/Nodes`.

Ce n'est pas un manque à combler en douce : ce serait un second modèle, donc
exactement ce que la phrase fondatrice du projet refuse. Si le besoin devient
réel, il se traitera comme un chantier assumé et déclaré, avec le modèle
`awkward` de `j8sr0230/Nodes` (LGPL-2.1, empruntable) comme point de départ —
et pas avant. En attendant, c'est un écart à annoncer honnêtement, comme les
esquisses 3D et les configurations le sont déjà dans
[`grandes-lignes.md`](grandes-lignes.md).

## 4. Les macros ne sont plus l'étage du dessous

La rédaction précédente faisait du graphe « l'interface graphique des
macros ». **C'est faux dès lors que le graphe est le document** : un graphe
montre l'état d'une pièce, une macro rejoue une suite de gestes. Deux sujets
distincts, qui ne se commandent plus l'un l'autre.

Les macros gardent leur intérêt propre et leur analyse (`landscape.md` §2) :
les 88 opérations de `engine/protocol.py` sont déjà le langage,
l'enregistrement se réduit à journaliser les requêtes reçues par
`server.py`, la relecture à les re-poster. Le morceau dur reste la
**résolution de références** — les ops désignent les fonctions par nom
(`Bossage1`), donc rejouer sur un autre document ne marche pas tout seul.

Et la contrainte de format tient toujours, indépendamment du graphe : une
macro est une **liste d'opérations validées, jamais du Python exécuté**.
L'allowlist d'`Origin` de `server.py` laisse passer les requêtes sans en-tête
`Origin` (curl, scripts locaux) ; tant que le contenu est de la donnée
revalidée par `protocol.py`, la surface d'attaque est celle d'aujourd'hui.

## 5. Le travail réel

Tout se ramène à une chose : **`get_tree` doit émettre les arêtes.**

Aujourd'hui il ne le fait pas (`kernel.py:2234`). Il lit `Profile` dans le
seul but d'imbriquer une esquisse consommée sous sa fonction, puis jette le
reste — `AttachmentSupport`, `BaseFeature`, corps outils. Ce qu'il renvoie
est une liste plate à un niveau d'imbrication, pas un graphe.

| Étape | Où | Coût |
|---|---|---|
| Arêtes géométriques | `get_tree` : champ `deps` par entrée, depuis `obj.OutList` filtré au corps | 🟢 la donnée est dans FreeCAD, il suffit de ne plus la jeter |
| Arêtes paramétriques | même endroit, depuis `_expression_map` | 🟢 le lecteur existe déjà |
| Contrat | `protocol.py` + tests | 🟢 faible, mais c'est un **changement de protocole** : à faire proprement |
| Rendu du graphe | client | 🟧 le vrai morceau — disposition et lisibilité sur une pièce à 60 fonctions |
| Édition dans le graphe | client → ops existantes | 🟧 ensuite, geste par geste, sans opération nouvelle côté moteur |

Ce que la seule lecture rapporte déjà, avant toute édition : la réponse à
« d'où vient cette face ». Une répétition qui référence une esquisse
attachée à un plan qui dépend d'une autre fonction est illisible en liste et
évidente en graphe. Et une cote pilotée par une variable, aujourd'hui
signalée par un simple préfixe Σ, montre enfin **d'où** elle est pilotée.

## L'ordre

1. **Arêtes dans `get_tree`** — géométriques et paramétriques, contrat et
   tests. C'est la seule vraie dépendance de tout le reste.
2. **Vue graphe en lecture seule** — utile immédiatement, et c'est déjà le
   composant final.
3. **Édition dans le graphe** — chaque geste retombe sur une opération
   existante ; rien de neuf côté moteur.
4. **Macros** — sujet indépendant, à mener quand il aura sa propre valeur.

Aucune étape ne demande d'écrire de la géométrie, et aucune n'ajoute quoi que
ce soit dans le `.FCStd`.
