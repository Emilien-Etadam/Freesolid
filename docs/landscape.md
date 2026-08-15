# Veille — qui construit quoi autour d'une UI moderne pour FreeCAD

*Relevé du 2026-08-02, avant d'engager la piste « nouvelle UI sur moteur
headless ». Conclusion en bas.*

## Les projets existants, un par un

| Projet | Ce que c'est | Verdict pour nous |
|---|---|---|
| [magik6k/freecad-web](https://github.com/magik6k/freecad-web) | Port WebAssembly de **tout** FreeCAD, **interface Qt comprise**, via Qt-for-WASM + JSPI (Chromium 137+ seulement) | Pas un concurrent : c'est l'interface actuelle dans un onglet. Mais une **preuve majeure** que le moteur tournera un jour côté client |
| [Salusoft89/planegcs](https://github.com/Salusoft89/planegcs) | Le **solveur d'esquisse de FreeCAD compilé en WASM**, utilisable en JS | Pas un concurrent : un **atout**. Le solveur peut tourner dans le navigateur pour le drag à 60 fps, le serveur restant la vérité |
| [Ondsel-Server / Lens](https://github.com/FreeCAD/Ondsel-Server) | Plateforme web de partage/visualisation de FCStd | Visionneuse, pas un éditeur |
| [SindriCAD](https://github.com/MakerViking/sindricad) | CAO paramétrique web (Tauri + Three.js) sur **build123d**, pas FreeCAD | Valide la stack UI ; moteur documentaire réinventé, reconstruction totale à chaque édition |
| [Chili3D](https://github.com/xiangechen/chili3d) † | CAO 3D 100 % navigateur, TypeScript + OCCT 8.0 en WASM + Three.js, AGPL-3.0 | Le plus proche de nous, et toujours à côté : modelage **direct**, pas d'historique paramétrique. Détail au relevé du 2026-08-15 |
| freecad-mcp (plusieurs), freecad-ai | Pilotage de FreeCAD par API/LLM | De la tuyauterie voisine, pas une UI interactive |
| render-fcstd, freecad-web-visualization | Visionneuses Three.js de fichiers exportés | Affichage seul |
| Fil devtalk [« FreeCAD web frontend »](https://devtalk.freecad.org/t/freecad-web-frontend/55903) (2021) | Discussion récurrente depuis 2017 | Aucun projet n'en est sorti |
| [waffle-iron](https://github.com/sequoia-hope/waffle-iron) (SequoiaHope) | **Noyau** CAD from scratch, Rust/WASM, MIT, ~6 mois de travail assisté par IA, par un expert Onshape/SolidWorks | Le pari inverse du nôtre : noyau réécrit, UI « needs a lot of work ». Complémentaire, pas concurrent |
| [Onshape](https://www.onshape.com) | La CAO navigateur des fondateurs de SolidWorks, noyau Parasolid, gratuite en non-commercial | Le seul vrai « SW moderne dans un navigateur » existant. Cloud obligatoire, documents publics en gratuit, fermé — c'est exactement l'espace que « local + open source » laisse ouvert |

## Conclusion

**La voie est libre.** Tout le monde a fait soit l'inverse (la vieille UI
portée telle quelle en WASM), soit à côté (nouveau moteur documentaire), soit
en dessous (visionneuses, API). Personne n'a fait : *interface neuve +
moteur documentaire FreeCAD headless conservé* — c'est-à-dire garder les
documents paramétriques, PartDesign, le solveur, le fix toponaming et STEP,
et ne réécrire que la présentation et l'interaction.

Deux atouts inattendus ressortent de la veille :

1. **planegcs-wasm** existe déjà — le composant le plus risqué de notre
   futur éditeur d'esquisse (résolution de contraintes pendant le drag) a
   déjà été porté par quelqu'un d'autre.
2. **Le port WASM de magik6k** prouve que la dépendance à un serveur Python
   local n'est pas une impasse : le jour venu, le même moteur pourra tourner
   dans l'onglet. (Contexte, via la discussion Hacker News : ce port était un
   benchmark d'agent IA réalisé en ~4 jours, assumé bugué par son auteur —
   une démo de faisabilité, pas un produit.)

Et un avertissement d'expert, relevé dans la même discussion, qui fonde le
choix d'architecture : les noyaux géométriques regorgent de cas dégénérés et
de comptabilité de tolérances absents des données d'entraînement des LLM —
« pas vibe-codable », dixit un développeur qui en est à sa troisième
réécriture. Raison exacte pour laquelle ce projet ne réécrit **jamais** le
noyau : il garde celui qui a vingt ans de cas pourris derrière lui, et ne
refait que ce qui se voit.

---

# Relevé complémentaire du 2026-08-15 — Chili3D, macros, nœuds

*† La ligne Chili3D du tableau ci-dessus a été ajoutée à cette date.*

## 1. Chili3D — le miroir inversé

[Chili3D](https://github.com/xiangechen/chili3d) (Xiang Chen, ~4,7k étoiles,
~1 170 commits, statut **alpha** assumé) est une CAO 3D qui tourne
entièrement dans l'onglet : TypeScript, OpenCascade 8.0 compilé en
WebAssembly par Emscripten, Three.js pour le rendu, IndexedDB pour la
persistance, Rspack pour le build. Interface **ruban type Office**, système
de **plugins chargés à l'exécution**, i18n (en/zh/pt-BR), import/export
STEP, IGES, BREP, STL. Licence **AGPL-3.0** (module WASM en LGPL-3.0), avec
licence commerciale sur demande — modèle open-core.

Même thèse que nous (« la CAO mécanique mérite une UI web moderne »), même
noyau géométrique au fond (FreeCAD est lui-même bâti sur OCCT). La
divergence est **le modèle documentaire**, et elle décide de tout :

| | FreeSolid | Chili3D |
|---|---|---|
| Noyau géométrique | OCCT **via FreeCAD** | OCCT brut en WASM |
| Modèle documentaire | celui de FreeCAD, intact | réécrit maison |
| Historique paramétrique rééditable | oui (double-clic → recalcul) | **non** — direct + undo/redo ; annoncé en roadmap |
| Contraintes d'esquisse | solveur planegcs à ~60 fps | outils de dessin, pas de solveur comparable |
| Fichiers | `.FCStd` natif, réouvrable dans FreeCAD | format propre + échange STEP/IGES/BREP/STL |
| Installation | FreeCAD ≥ 1.0 requis (~800 Mo) | **zéro install**, une URL |
| Licence | LGPL-2.1-or-later | AGPL-3.0 / commerciale |

**Ce qu'on lui prend — l'UI, et rien d'autre.** Le ruban, la hiérarchie
d'assemblage, le plan de travail dynamique, les outils de mesure
(angle/longueur/aire/volume), le système de plugins : c'est de
l'organisation d'interface, exactement le terrain où le projet a décidé de
tout refaire. Bon endroit où aller chercher des idées de disposition et de
nommage.

**Ce qu'on ne lui prend pas — le code.** AGPL-3.0 contre notre
LGPL-2.1-or-later : reprendre le moindre fichier ferait basculer FreeSolid
entier en AGPL. Chili3D est une **référence visuelle**, jamais une réserve
de code. Regarder, pas copier-coller.

**Ce qu'il a et que nous n'avons pas — le zéro-install.** C'est son seul
avantage réel, et il est sérieux : notre README consacre deux tutoriels
pas-à-pas à faire installer 800 Mo de FreeCAD. La réponse n'est pas de
réécrire le noyau, c'est la piste `magik6k/freecad-web` déjà repérée au
relevé du 2026-08-02 — le jour où FreeCAD headless tourne en WASM dans
l'onglet, on prend le zéro-install sans rien céder sur le paramétrique.

**Le risque, daté.** Il n'existe que si Chili3D ajoute un véritable
historique paramétrique avec contraintes. Ce chantier-là, c'est vingt ans de
FreeCAD à refaire — le même mur « pas vibe-codable » qui conclut le relevé
précédent. Rien à changer à la doctrine ; à re-regarder si sa roadmap bouge.

## 2. Macros — le protocole est déjà le langage

Chez FreeCAD, une macro est un fichier `.FCMacro` de Python pilotant l'API,
avec un **enregistreur de macros** dans la GUI et une
[bibliothèque officielle](https://github.com/FreeCAD/FreeCAD-macros)
distribuée par l'Addon Manager. Ces macros-là ne sont **pas réutilisables
telles quelles** chez nous : elles appellent `Gui.*` et supposent
l'application Qt vivante, que le moteur headless n'a pas.

En revanche FreeSolid est bien mieux placé que FreeCAD pour les macros, et
c'est un acquis gratuit de l'architecture : **chaque geste utilisateur
transite déjà par une opération JSON nommée** — 88 aujourd'hui dans
`engine/protocol.py`, de `add_pad` à `sketch_constrain`, chacune validée par
un contrat unitairement testé. Autrement dit l'enregistreur existe déjà à
moitié :

| Brique | Coût | Comment |
|---|---|---|
| **Enregistrement** | 🟢 quasi nul | journaliser les requêtes déjà reçues par `server.py` → une liste `[{op, params}]` |
| **Relecture** | 🟢 faible | re-poster la liste ; `protocol.py` re-valide tout, aucune voie d'exécution nouvelle |
| **Paramétrage** | 🟢 faible | remplacer les littéraux par des expressions — le moteur d'expressions et les variables globales existent depuis la phase A |
| **Rejouabilité sur un autre document** | 🟧 le vrai travail | les ops désignent les fonctions par nom (`Bossage1`, `Esquisse2`) ; rejouer ailleurs suppose une résolution de références, pas un simple replay |

Une contrainte à ne pas perdre de vue : le format de macro doit rester
**une liste d'opérations du protocole, pas du Python arbitraire**. Le moteur
écoute sur `127.0.0.1:8787` avec une allowlist d'`Origin`, mais celle-ci
laisse passer les requêtes sans en-tête `Origin` (curl, scripts locaux).
Une macro = données validées : la surface d'attaque reste celle
d'aujourd'hui. Une macro = code Python exécuté : on ouvre une exécution de
code arbitraire à tout processus local. Le choix se fait maintenant, pas
après.

## 3. Nœuds façon Grasshopper — un deuxième plan de travail, pas un deuxième moteur

### L'existant

| Projet | Ce que c'est | Ce qu'on en retient |
|---|---|---|
| **[j8sr0230/Nodes](https://github.com/j8sr0230/Nodes)** | L'atelier **Nodes** de FreeCAD (ex-`FreeCAD-nodes`) : éditeur d'algorithme graphique, ~674 commits, actif, dans l'Addon Manager depuis FreeCAD 0.21, [doc](https://freecad-nodes.readthedocs.io/). Dépend de `pyqt-node-editor` (l'éditeur), `qtpy` et **`awkward`** (les données). **LGPL-2.1** | **La référence à étudier** — voir ci-dessous. Même licence que nous : le code est *empruntable*, pas seulement regardable |
| [Nodi3D](https://github.com/Nodi3d/nodi) | Grasshopper dans le navigateur, Apache-2.0, partage de graphes par lien, export OBJ/STL/DXF | La preuve qu'un éditeur de nœuds tient dans un onglet ; mais géométrie maillée, pas de B-Rep exact |
| Grasshopper (Rhino), Dynamo (Revit) | Les références du genre | Le modèle mental que les utilisateurs auront en tête |

### `j8sr0230/Nodes` en détail — ce qui se prend, ce qui se jette

Le projet se sépare proprement en deux moitiés, et elles ne valent pas la
même chose pour nous :

- **L'éditeur — à jeter.** Il est bâti sur `pyqt-node-editor`, donc soudé à
  Qt. Rien n'en survit dans un navigateur ; c'est de toute façon la partie
  que le projet a décidé de refaire partout ailleurs.
- **Le modèle de données — à étudier de près.** Le choix d'`awkward`
  ([Awkward Array](https://awkward-array.org/), tableaux imbriqués de
  longueurs irrégulières) est la réponse de l'auteur au problème le plus dur
  du genre : les *data trees* de Grasshopper, c'est-à-dire propager des
  listes imbriquées à travers un graphe sans que la sémantique
  d'appariement devienne folle. C'est le morceau qu'on aurait mal réinventé,
  il est écrit, il est **sous notre licence**, et il est lisible.

Deux questions se posaient sur son fonctionnement — persistance du graphe
dans le `.FCStd`, et fonctions PartDesign rééditables *vs* formes `Part`
figées. Elles ont été **rendues sans objet pour FreeSolid** le même jour :
en décidant que le graphe *est* le document et non un artefact à côté, il
n'y a plus ni graphe à persister ni géométrie à générer — le graphe est une
vue sur les fonctions existantes. Voir [`nodes-macros.md`](nodes-macros.md).

Ce que Nodes garde d'utile après cette décision : son modèle de données
`awkward` pour les *data trees*, une fois que la **fonction graphe** de
`nodes-macros.md` §3 aura un volume qui le justifie — les boucles et les
listes, elles, sont retenues, encapsulées dans une fonction de l'arbre sur
le modèle de l'esquisse.

### Le point qui décide

Grasshopper et l'arbre de fonctions ne sont **pas la même chose déguisée** :

- Grasshopper est un **flux de données** — le graphe *est* le modèle, il n'y
  a pas d'historique ni de pièce à rééditer, et le cœur difficile ce sont
  les *data trees* (listes imbriquées propagées à travers les nœuds).
- PartDesign/SolidWorks est un **historique linéaire** — une chaîne de
  fonctions sur un corps, avec un `.FCStd` au bout.

Écrire un vrai Grasshopper, c'est écrire un second évaluateur documentaire à
côté de celui de FreeCAD. C'est exactement le piège du noyau réécrit,
transposé d'un cran plus haut : 🔴 refusé sous cette forme.

### Les deux formes acceptables, par coût croissant

1. **🟢 L'arbre vu comme un graphe (vue seule).** L'arbre de fonctions *est*
   déjà un graphe — esquisses, plans de référence, corps, booléens et
   répétitions ont des dépendances qui ne sont pas linéaires ; `get_tree` les
   connaît. Les afficher comme un graphe navigable est une **vue nouvelle
   sur des données existantes**, zéro géométrie à écrire. C'est aussi la
   meilleure réponse à « d'où vient cette face », que l'arbre plat cache.

2. **🟧 Le graphe de macros — la vraie piste.** Un éditeur de nœuds dont
   **chaque nœud est une opération du protocole** et dont l'évaluation
   produit une liste ordonnée d'opérations envoyée au moteur. Les fils
   portent des paramètres et des références de fonctions, pas de la
   géométrie. On y gagne le générateur paramétrique (visserie, gabarits,
   familles de pièces, répétitions pilotées) *sans* second moteur : le
   résultat est un `.FCStd` normal, avec un vrai historique, ouvrable dans
   FreeCAD. C'est le point 2 de la section macros, avec des fils au lieu
   d'une liste — et ça n'a de sens qu'**après** les macros, dont il est
   l'interface graphique.

Reste ce qu'un tel graphe ne donne pas d'emblée : les *data trees*, donc la
génération de nuages de géométrie (semer 500 perçages sur une surface
gauche). Ce n'est plus un mur depuis qu'on sait qu'`awkward` est la réponse
de `j8sr0230/Nodes` au même problème, sous notre licence — mais c'est un
étage au-dessus, à ouvrir seulement si le besoin se manifeste, et à assumer
explicitement d'ici là comme les esquisses 3D et les configurations le sont
déjà dans [`grandes-lignes.md`](grandes-lignes.md).

## Conclusion du complément

Rien dans ce relevé ne remet en cause la doctrine du 2026-08-02 — les trois
sujets la confirment plutôt. **Aucun des trois ne demande d'écrire de la
géométrie**, ce qui est le bon signe.

- **Chili3D** se prend en inspiration d'**interface** et jamais en code :
  AGPL-3.0 contre notre LGPL-2.1.
- **`j8sr0230/Nodes`** est l'inverse exact : LGPL-2.1 comme nous, donc son
  **code** est empruntable — et c'est justement sa moitié invisible
  (le modèle de données `awkward`) qui vaut le détour, pas son éditeur Qt.
- **Les macros** sont déjà à moitié construites par les 88 opérations du
  protocole. Elles se font sans nouveau moteur, à une condition non
  négociable : rester des **données validées**, jamais du Python exécuté.
- **Les nœuds** ne valent que branchés sur ce même protocole. Ordre :
  la vue graphe de l'arbre (gratuite), puis les macros, puis l'éditeur à
  fils qui n'est que leur interface graphique.

Suite donnée le jour même dans [`nodes-macros.md`](nodes-macros.md), et elle
resserre encore la doctrine : **le graphe n'est pas un objet, c'est une
vue**. Rien à séparer du document, donc pas de format de graphe, pas
d'évaluateur, pas de synchronisation — les arêtes existent déjà dans
`OutList` et dans les expressions, il suffit que `get_tree` cesse de les
jeter.
