# Veille — qui construit quoi autour d'une UI moderne pour FreeCAD

*Relevé du 2026-08-02, avant d'engager la piste « nouvelle UI sur moteur
headless ». Conclusion en bas.*

## Les projets existants, un par un

| Projet | Ce que c'est | Verdict pour nous |
|---|---|---|
| [magik6k/freecad-web](https://github.com/magik6k/freecad-web) | Port WebAssembly de **tout** FreeCAD, **interface Qt comprise**, via Qt-for-WASM + JSPI (Chromium 137+ seulement) | Pas un concurrent : c'est l'interface actuelle dans un onglet. Mais une **preuve majeure** que le moteur tournera un jour côté client |
| [APEbbers/FreeCAD-Ribbon](https://github.com/APEbbers/FreeCAD-Ribbon) ‡ | **Ruban pour FreeCAD lui-même** : remplace les barres d'outils par un ruban configurable en JSON, dialogue de personnalisation, réversible. GPL-3.0, ~130 ★, 3 303 commits, **dans l'Addon Manager officiel**. Descend de `geolta/FreeCAD-Ribbon` et `HakanSeven12/Modern-UI` | **La réponse concurrente à notre prémisse**, et elle nous bat sur le ruban seul : couverture fonctionnelle totale et immédiate. Sa dette est le couplage aux internes Qt ; la nôtre est de tout ré-exposer. Détail au relevé du 2026-08-21 (suite) |
| [Salusoft89/planegcs](https://github.com/Salusoft89/planegcs) | Le **solveur d'esquisse de FreeCAD compilé en WASM**, utilisable en JS | Pas un concurrent : un **atout**. Le solveur peut tourner dans le navigateur pour le drag à 60 fps, le serveur restant la vérité |
| [solvespace/solvespace](https://github.com/solvespace/solvespace) ‡ | CAO paramétrique 2D **et 3D** avec son propre solveur, disponible en bibliothèque (`libslvs`, bindings Python). GPL-3.0-or-later, ~4,1 k ★, actif — c'est le solveur que réutilise Dune3D | La brique qui manque pour de vraies **esquisses 3D contraintes** (🔴 dans `grandes-lignes.md`)… et qu'on ne peut pas prendre : GPL-3 bloque l'emprunt comme la remontée. Référence conceptuelle, et réponse à « pourquoi pas SolveSpace ? » : la licence, pas la qualité |
| [Ondsel-Server / Lens](https://github.com/FreeCAD/Ondsel-Server) ‡ | Plateforme web de partage/visualisation de FCStd. **La société a fermé le 2024-10-30** ; Lens éteint le 2024-11-22 | Visionneuse, pas un éditeur — et désormais un **point de vigilance** : l'atelier Assembly et son solveur 3D, dont dépend notre phase C, ont été légués à la communauté (~150 PR mergées, don de 40 k€ à la FPA). Détail au relevé du 2026-08-21 |
| [SindriCAD](https://github.com/MakerViking/sindricad) | CAO paramétrique web (Tauri + Three.js) sur **build123d**, pas FreeCAD | Valide la stack UI ; moteur documentaire réinventé, reconstruction totale à chaque édition |
| [dune3d/dune3d](https://github.com/dune3d/dune3d) ‡ | CAO paramétrique bureau : **solveur SolveSpace + noyau OCCT + coquille GTK4 neuve**, par l'auteur de Horizon EDA. GPL-3.0, ~2,1 k ★, v1.4 « Einstein » (janvier 2026), FOSDEM 2026 | **Notre doctrine sur un autre couple de donneurs** — ne réécrire ni solveur ni noyau. Il réécrit quand même le modèle documentaire, et reste sur le bureau. La preuve de faisabilité du milieu : 2 ans et demi, une personne |
| [Chili3D](https://github.com/xiangechen/chili3d) † | CAO 3D 100 % navigateur, TypeScript + OCCT 8.0 en WASM + Three.js, AGPL-3.0 | Le plus proche de nous, et toujours à côté : modelage **direct**, pas d'historique paramétrique. Détail au relevé du 2026-08-15 |
| [xibyte/jsketcher](https://github.com/xibyte/jsketcher) ‡ | CAO paramétrique 2D/3D **100 % navigateur**, ~1,7 k ★ : OCCT en WASM, **solveur de contraintes 2D écrit maison en JS/TS**, historique de fonctions rééditable avec propagation d'ID d'arêtes/faces. Bêta | Le prédécesseur qu'on avait manqué — presque toute notre thèse, sans FreeCAD. ⚠️ **Licence piégeuse** : « MIT » modifié par Autodrop3d LLC avec cession de copyright obligatoire. Ni empruntable ni forkable |
| [BOMWiki/partmode](https://github.com/BOMWiki/partmode) ‡ | CAO paramétrique **local-first** dans le navigateur : OCCT-wasm via `replicad` + three.js, modèle documentaire maison, **historique de fonctions rééditable**, esquisses contraintes, expressions, multicorps, configurations, motifs ; agents MCP éditant *le même* document que l'humain. AGPL-3.0, ~635 ★ | **Le plus proche de nous à ce jour** — il ferme le trou qu'on reprochait à Chili3D (l'historique paramétrique), et son interface est un vrai ruban de 89 kloc malgré son slogan « CLI-native ». Reste le modèle documentaire réinventé, et l'AGPL. Détail au relevé du 2026-08-21 |
| freecad-mcp (plusieurs), freecad-ai ‡ | Pilotage de FreeCAD par API/LLM | De la tuyauterie voisine, pas une UI interactive — mais [`sandraschi/freecad-mcp`](https://github.com/sandraschi/freecad-mcp) est **architecturalement notre jumeau** (FreeCAD headless derrière une API REST qui sert aussi un tableau de bord web) et il est **MIT**. Relevé du 2026-08-21 |
| render-fcstd, freecad-web-visualization | Visionneuses Three.js de fichiers exportés | Affichage seul |
| Fil devtalk [« FreeCAD web frontend »](https://devtalk.freecad.org/t/freecad-web-frontend/55903) (2021) | Discussion récurrente depuis 2017 | Aucun projet n'en est sorti |
| [waffle-iron](https://github.com/sequoia-hope/waffle-iron) (SequoiaHope) | **Noyau** CAD from scratch, Rust/WASM, MIT, ~6 mois de travail assisté par IA, par un expert Onshape/SolidWorks | Le pari inverse du nôtre : noyau réécrit, UI « needs a lot of work ». Complémentaire, pas concurrent |
| [Fornjot](https://github.com/hannobraun/fornjot) ‡ | Noyau B-rep en Rust, ~20 000 commits, plusieurs années, un auteur à plein temps | **Archivé le 2026-06-19** : « *This project has been shut down. Its goals were never reached.* » Le point de donnée qui remplace l'intuition « pas vibe-codable » par une preuve |
| [Oblikovati](https://github.com/Oblikovati/Oblikovati) ‡ | CAO paramétrique « classe Inventor » **réécrite de zéro en Go** : noyau B-rep maison, nommage topologique persistant, rendu Vulkan 1.3, GUI + CLI headless. **644 kloc**, 4 800 fichiers, 2 418 fichiers de test, actif. GPL-2.0 (app) / Apache-2.0 (contrat d'API) | Le cinquième noyau réécrit, et le plus gros. Ratio parlant : 121 kloc d'opérations, mais **1 625 lignes de congés** — « early/foundational » assumé. Rien à prendre (GPL-2), mais deux idées : valider son noyau contre OCCT, et séparer la licence du **contrat** de celle de l'implémentation |
| [ecto/vcad](https://github.com/ecto/vcad) ‡ | CAO paramétrique complète — **noyau BRep Rust réécrit** (~445 kloc, 92 crates), app React/Three.js, Tauri, CLI, serveur MCP, banc d'essai IA. Apache-2.0, actif | Le même pari inverse que waffle-iron, **soixante-dix fois plus grand** et fini. Rien à prendre au noyau ; quatre idées à prendre au-dessus. Relevé complet : [`vcad.md`](vcad.md) |
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

*† La ligne Chili3D du tableau ci-dessus a été ajoutée à cette date. Les lignes marquées ‡ — vcad, PartMode, FreeCAD-Ribbon, Dune3D, jsketcher, Fornjot, Oblikovati, SolveSpace, verb — ont été ajoutées aux trois relevés du 2026-08-21, en bas de page, qui ont aussi mis à jour les lignes Ondsel, freecad-mcp et Nodi3D devenues inexactes.*

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

Une contrainte à ne pas perdre de vue — et qui a changé de cible.
Le moteur écoute sur `127.0.0.1:8787` avec une allowlist d'`Origin`,
mais celle-ci laisse passer les requêtes sans en-tête `Origin` (curl,
scripts locaux). L'utilisateur qui lance FreeSolid a déjà un shell :
un nœud Python dans le graphe ne lui donne rien de neuf. **Le vrai
risque est le fichier.** Le graphe est persisté dans le `.FCStd`
(N004) ; une pièce reçue d'un tiers deviendrait un fichier exécutable
si le code tournait tout seul.

C'est pourquoi le nœud Python (N008) est autorisé, et pourquoi la
contrainte « données, jamais du code » est **levée pour ce nœud**,
remplacée par : **jamais sans consentement explicite, jamais persisté.**
À la première exécution d'un script du document, le code est montré ;
l'autorisation vaut pour ce document et cette session ; elle n'est
jamais écrite dans le `.FCStd` — un attaquant y inscrirait « ce
document est de confiance ». Sans autorisation : refus en français,
nœud désigné, pièce intacte. Pas de bac à sable : le script tourne
dans le processus du kernel, et l'interface le dit.

L'enregistreur de macros (liste d'opérations du protocole) n'est plus
l'étage visé — voir [`nodes-macros.md`](nodes-macros.md) §4.

## 3. Nœuds façon Grasshopper — un deuxième plan de travail, pas un deuxième moteur

### L'existant

| Projet | Ce que c'est | Ce qu'on en retient |
|---|---|---|
| **[j8sr0230/Nodes](https://github.com/j8sr0230/Nodes)** | L'atelier **Nodes** de FreeCAD (ex-`FreeCAD-nodes`) : éditeur d'algorithme graphique, ~674 commits, actif, dans l'Addon Manager depuis FreeCAD 0.21, [doc](https://freecad-nodes.readthedocs.io/). Dépend de `pyqt-node-editor` (l'éditeur), `qtpy` et **`awkward`** (les données). **LGPL-2.1** | **La référence à étudier** — voir ci-dessous. Même licence que nous : le code est *empruntable*, pas seulement regardable |
| [Nodi3D](https://github.com/Nodi3d/nodi) | Grasshopper dans le navigateur, Apache-2.0, partage de graphes par lien, export OBJ/STL/DXF. **Dernier commit le 2024-11-08** (relevé du 2026-08-21) | La preuve qu'un éditeur de nœuds tient dans un onglet ; mais géométrie maillée, pas de B-Rep exact — et le projet est à l'arrêt |
| [kovacsv/VisualScriptCAD](https://github.com/kovacsv/VisualScriptCAD) | Modeleur 3D par script visuel sur `VisualScriptEngine`, C++, GPL-3.0, ~131 ★. **« No Maintenance » depuis 2019** | Troisième preuve de faisabilité d'un éditeur de nœuds — mais géométrie maillée, projet arrêté, licence bloquante. Sans objet depuis que le graphe est une *vue* (`nodes-macros.md`) |
| [pboyer/verb](https://github.com/pboyer/verb) ‡ | Bibliothèque **NURBS** en **MIT** : évaluation de courbes et surfaces, dérivées, tessellation adaptative, intersections. Livrée déjà construite en JS (`verb.es.js`). Pas de solides, pas de booléens. ~811 ★, dernier commit 2025-04 | **Le seul apport directement branchable de la veille.** Le pendant de planegcs pour les courbes : B-splines calculées **côté client**, sans aller-retour serveur — pour les courbes 3D par points (phase D) et les aperçus de glisser. MIT : empruntable **et** remontable |
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

2. **🟧 Le graphe de macros — piste abandonnée (N008).** Un éditeur de nœuds dont
   **chaque nœud est une opération du protocole** était la piste du 2026-08-15,
   après un enregistreur de macros. **Ce n'est plus ce qu'on construit.** Le
   nœud Python dans la fonction graphe a pris cette place : voir §2 ci-dessus
   et [`nodes-macros.md`](nodes-macros.md) §4.

Les *data trees* (semer 500 perçages sur une surface gauche) ne sont plus
un mur : la fonction graphe les porte déjà, et `awkward` reste l'optimisation
de `j8sr0230/Nodes` sous notre licence — à ouvrir seulement si le volume le
justifie, comme les esquisses 3D et les configurations dans
[`grandes-lignes.md`](grandes-lignes.md).

## Conclusion du complément

Rien dans ce relevé ne remet en cause la doctrine du 2026-08-02 — les trois
sujets la confirment plutôt. **Aucun des trois ne demande d'écrire de la
géométrie**, ce qui est le bon signe.

- **Chili3D** se prend en inspiration d'**interface** et jamais en code :
  AGPL-3.0 contre notre LGPL-2.1.
- **`j8sr0230/Nodes`** est l'inverse exact : LGPL-2.1 comme nous, donc son
  **code** est empruntable — et c'est justement sa moitié invisible
  (le modèle de données `awkward`) qui vaut le détour, pas son éditeur Qt.
- **Le nœud Python** (N008) remplace le chantier macros. Ce n'est pas un
  enregistreur d'opérations : c'est du code dans le graphe, exécuté par
  le kernel après consentement explicite, jamais persisté comme « de
  confiance » dans le `.FCStd`. La contrainte « données, jamais du
  code » est levée pour ce nœud, et pour lui seul.
- **Les nœuds** restent branchés sur le document. Ordre : la vue graphe
  de l'arbre, la fonction graphe, le catalogue, le nœud Python. L'étape
  « macros » de la feuille de route est abandonnée.

Suite donnée le jour même dans [`nodes-macros.md`](nodes-macros.md), et elle
resserre encore la doctrine : **le graphe n'est pas un objet, c'est une
vue**. Rien à séparer du document, donc pas de format de graphe, pas
d'évaluateur, pas de synchronisation — les arêtes existent déjà dans
`OutList` et dans les expressions, il suffit que `get_tree` cesse de les
jeter.

---

# Relevé du 2026-08-21 — vcad, la frontière, la reconnaissance amont

*‡ La ligne vcad du tableau du 2026-08-02 a été ajoutée à cette date.*

[ecto/vcad](https://github.com/ecto/vcad) est trop gros pour une ligne de
tableau : le relevé complet est dans [`vcad.md`](vcad.md). Ce qu'il faut
en retenir ici, et ce qu'il a produit d'inattendu.

## Ce que c'est

Le pari inverse du nôtre, mené jusqu'au bout et à une échelle qu'on n'avait
pas encore vue : ~445 000 lignes de Rust en 92 crates (noyau BRep complet,
booléens, congés, tessellation, STEP, nommage topologique), 80 000 lignes de
TypeScript pour l'app React/Three.js, une app Tauri, un CLI, un serveur MCP,
un banc d'essai IA de 242 Mo. Apache-2.0, actif, avec une société derrière.

C'est la case `waffle-iron` du tableau du 2026-08-02 — « noyau réécrit,
UI à faire » — mais soixante-dix fois plus grande, et avec l'UI finie.
**La doctrine n'en sort pas ébranlée : elle en sort documentée.** Le coût
du pari est là, lisible dans l'arborescence — 26 000 lignes rien que pour
les booléens, exactement le poste que FreeSolid hérite déjà éprouvé.

## Ce qu'on lui prend — quatre idées, et pas une ligne

Le tri s'est fait par une seule question : *de quel côté de la frontière
tombe la chose ?* La quasi-totalité des 445 kloc tombe côté FreeCAD, donc
hors sujet. Ce qui reste tombe **entièrement de notre côté**, là où nous
n'avons pas de grand frère parce que FreeCAD résout ces problèmes-là dans
son interface Qt, que nous avons jetée :

| Idée | Où ça atterrit chez nous |
|---|---|
| Discipline de verdict sur une référence — résolu / ambigu / perdu, **jamais de re-liaison silencieuse** ~~+ signature géométrique (`EdgeHint`)~~ | `engine/replay.py` — **par-dessus la carte d'éléments de FreeCAD.** Le mécanisme géométrique de vcad est abandonné : la reconnaissance amont du même jour a montré que le moteur expose déjà la provenance (voir plus bas) |
| Reçu de vérification : chaque mesure porte son oracle, sa version, ses unités, et « n'a pas pu tourner » ≠ « passé » | `scripts/run-selftest.py` |
| Garde de confiance pure et synchrone **avant** le dispatch, qui refuse sans jamais réécrire un argument | `engine/protocol.py` — remède commun aux constats 3.1–3.6 de l'audit |
| Schéma d'outils **dérivé** du vocabulaire au lieu d'être écrit à côté | `engine/vocab.py` |

Aucune ne demande d'écrire de la géométrie — le même bon signe qu'au
2026-08-15.

## Ce qu'on ne lui prend pas — le code, et pour une raison neuve

Le raisonnement ne se termine pas comme celui de Chili3D. L'AGPL de Chili3D
**interdit** l'emprunt : reprendre un fichier ferait basculer FreeSolid
entier. L'Apache-2.0 de vcad, elle, *passerait* — notre « or-later » permet
de distribuer l'ensemble en LGPL-3.0.

Ce qui tranche est ailleurs, et c'est le vrai apport de ce relevé : une
contribution à FreeCAD doit être remontable en **LGPL-2.1-or-later**. Le
jour où une ligne de FreeSolid descend d'Apache-2.0, cette ligne et toute sa
descendance **ne peuvent plus jamais partir en amont**. Le prix d'un
copier-coller n'est pas juridique, il est stratégique : c'est la porte
amont qu'il ferme.

D'où la règle, qui vaut au-delà de vcad : **des dépôts sous licence non
remontable, on prend des idées et jamais des lignes.**

## Ce que le relevé a produit d'inattendu — une doctrine

Trier les emprunts a obligé à écrire la frontière noir sur blanc, et à
constater qu'elle a un second sens, jamais formulé jusqu'ici : quand le
travail sur FreeSolid fait apparaître un manque **côté FreeCAD**, le
contournement reste chez nous mais le constat, lui, doit partir en amont.

Ce n'est pas une intention généreuse, c'est une position : FreeSolid est un
client headless instrumenté, versionné sur une version de référence unique,
avec un selftest. C'est un point de vue sur FreeCAD que FreeCAD n'a pas sur
lui-même. Six contournements déjà présents dans `engine/` en sont la preuve
— deux SIGSEGV TechDraw reproductibles, une API undo absente, une API de
joints instable, et surtout `engine/guard.py`, écrit pour nos utilisateurs
et utile bien au-delà d'eux.

La règle, la procédure de tri et le registre des neuf constats sont dans
[`amont-freecad.md`](amont-freecad.md).

## Complément du même jour — la reconnaissance amont

Le registre de [`amont-freecad.md`](amont-freecad.md) contenait neuf
constats prêts à partir vers FreeCAD. Avant d'en formuler un seul, ils ont
été confrontés à la source : dépôt `FreeCAD/FreeCAD` lu au tag **1.1.3**
(notre référence) *et* sur `main`, plus la recherche d'issues existantes.
**Six constats sur neuf ont changé d'état.** Le détail est dans
[`amont-freecad.md`](amont-freecad.md) §4 et §8 ; ce qu'il faut retenir
pour la veille :

- **Le plus gros : FreeCAD expose déjà la carte d'éléments en Python.**
  `getElementMappedName`, `getElementIndexedName`, `getElementName`, les
  attributs `ElementMap` / `ElementReverseMap` / `ElementMapSize` /
  `ElementMapVersion` / `Tag`, et `getElementHistory(name, recursive=…)`
  — présents dans les bindings de **1.1.3**. Le « fix toponaming » que
  [`architecture-app.md`](architecture-app.md) cite comme raison de garder
  ce moteur est **adressable depuis notre code**, et nous ne nous en
  servions pas. L'emprunt à vcad se réduit d'autant : on garde la
  discipline de verdict, on jette le mécanisme.
- **Un candidat a trouvé sa porte.** L'issue
  [#19255](https://github.com/FreeCAD/FreeCAD/issues/19255) — *« "BRep_API:
  command not done" is not a clear or actionable error message »* — est
  **ouverte** et étiquetée **Help wanted**. C'est exactement ce que fait
  `engine/guard.py`.
- **Deux crashs qu'on s'apprêtait à signaler sont probablement déjà
  corrigés.** En 1.1.3, `DrawViewSection::getSectionCS()` enveloppe déjà
  la construction du repère dans un `try/catch` ; et la famille « TechDraw
  SIGSEGV depuis la CLI » a son issue amont
  ([#20024](https://github.com/FreeCAD/FreeCAD/issues/20024)), fermée.

La leçon de veille, au-delà des constats : **le dépôt amont est une source
consultable en quelques minutes** — un clone partiel de 26 Mo suffit à lire
les `.pyi`, qui sont la seule description honnête de la surface Python. Il
faut s'en méfier des forums et du wiki, qui décrivent souvent le fork
*LinkStage3* de realthunder plutôt que l'amont.

## Complément du même jour — trois lignes du tableau corrigées

- **Ondsel est mort, et ça nous concerne.** La société a fermé le
  **2024-10-30**, Lens s'est éteint le **2024-11-22**. Elle a légué son
  travail : ~150 PR mergées en amont, un don de 40 k€ à la FreeCAD Project
  Association pour rendre le code exploitable par la communauté. **L'atelier
  Assembly et le solveur 3D dont dépend notre phase C n'ont donc plus leurs
  auteurs d'origine** — ils sont maintenus par la communauté. Ce n'est pas
  une raison de changer de plan, c'en est une de documenter l'API des
  joints headless pendant que le sujet est encore frais (entrée **A3** du
  registre).
- **[`BOMWiki/partmode`](https://github.com/BOMWiki/partmode) — le plus
  proche de nous à ce jour, et il faut le dire.** CAO paramétrique
  local-first dans le navigateur : OCCT-wasm via `replicad`, three.js,
  modèle documentaire maison en « schema-5 », **historique de fonctions
  rééditable**, esquisses contraintes, expressions, multicorps,
  configurations, motifs — plus des agents MCP qui éditent *le même*
  document que l'humain, à travers la même frontière noyau/UI. ~635 ★,
  AGPL-3.0.

  Il ferme précisément le trou qu'on reprochait à Chili3D au relevé du
  2026-08-15 (« modelage direct, pas d'historique paramétrique »). La
  conclusion « la voie est libre » du 2026-08-02 doit donc être **nuancée,
  pas annulée** : ce qui reste à nous seuls, c'est le couple *modèle
  documentaire de FreeCAD conservé* + *`.FCStd` réouvrable dans FreeCAD*.
  PartMode réinvente le document, comme SindriCAD et Chili3D avant lui —
  c'est la ligne de partage, et elle n'a pas bougé. Posture identique à
  Chili3D pour le reste : **AGPL, donc regarder, jamais copier**, et rien
  qui puisse partir en amont.

### PartMode — l'interface, contre l'impression que donne son slogan

Le site s'annonce « **CLI-native agentic browser CAD** », ce qui laisse
attendre un outil pour agents avec une interface en second. **La source dit
l'inverse**, et il vaut mieux le savoir avant de se rassurer :

| | PartMode | FreeSolid |
|---|---|---|
| Chrome | **ruban** (`<section class="ws-ribbon">`), 7 espaces : `home`, `sketch`, `solid`, `assembly`, `view`, `output`, `manage` — idiome Fusion 360 | ruban à 4 onglets : esquisse, fonctions, assemblage, surfaces — idiome SolidWorks |
| Barre d'application | annuler/rétablir, modèles, configurations, ouvrir/enregistrer, exports STEP/STL/AMF/3MF/DXF/PDF/mise en plan, aide, plein écran | — |
| Modules d'interface | assistant de perçage, édition directe, `TransformControls`, `OrbitControls`, drag d'assemblage, annotations et normes de mise en plan, diagnostics de fonction | viewport Three.js, arbre SW, panneaux |
| JS d'interface | **~89 000 lignes** (`studio*.js`) | **~8 900 lignes** (`app/*.js`) |

**Ce qu'ils ont et que nous n'avons pas : un contrat de navigation.**
`src/ux-navigation-contract.ts` déclare huit parcours figés, chacun avec un
contexte (`first-visit` ou `existing-editor`), un objectif en clair et la
suite exacte de clics **avec les sélecteurs** — « Start a blank sketch » →
clic sur `#bw-welcome-start`. C'est de la découvrabilité **testable** au
lieu d'affirmée. Portée honnête : les huit parcours couvrent l'*accès*
(ouvrir un modèle, la bibliothèque, une configuration, exporter une mise en
plan), aucun ne décrit le geste de modélisation lui-même.

**Une lecture à corriger, la nôtre.** On peut être tenté de compter le
`right-drag` en rosace à quatre directions (isoler / éditer / supprimer /
masquer, zone morte de 28 px) comme un geste d'expert peu découvrable.
C'est l'inverse pour notre public : **c'est une convention SolidWorks**,
et [`navigation-spec.md`](navigation-spec.md) la liste noir sur blanc
(« Glisser clic droit : rosace de gestes »). Pour un utilisateur SW, ce
geste rend PartMode *plus* familier, pas moins — et leur implémentation
sert désormais de référence lisible dans notre propre spécification.

**Ce qu'on en conclut pour FreeSolid.** Ne pas se battre sur la surface
d'interface : à dix contre un, c'est perdu d'avance et ce n'est pas notre
thèse — nos différenciateurs sont le document FreeCAD conservé, le `.FCStd`
réouvrable, PartDesign et planegcs. En revanche, **le contrat de navigation
est la bonne chose à leur prendre**, et ce n'est pas un widget : écrire les
parcours d'un débutant comme des données testées coûte presque rien, rend
la découvrabilité mesurable, et complète exactement ce que fait déjà
`engine/protocol.py` pour les opérations — les gestes d'interface, eux, ne
sont déclarés nulle part chez nous. AGPL : l'idée, jamais le fichier.

**Limite assumée de ce constat.** Tout ceci est lu *dans la source*, pas
vu à l'écran : `partmode.com` est bloqué depuis notre environnement
d'analyse. Présence de code n'est pas qualité d'usage, et 89 000 lignes
d'interface, c'est aussi plus de surface où se perdre. L'intuitivité se
tranche en l'utilisant — et le test qui vaut est le nôtre : esquisse
rectangle cotée → bossage extrudé, sans lire l'aide.

- **[`sandraschi/freecad-mcp`](https://github.com/sandraschi/freecad-mcp) —
  notre jumeau architectural, sous MIT.** FreeCAD 1.1.1+ headless derrière
  une API REST (`:10944`) qui sert *aussi* un tableau de bord React
  (`:10945`) depuis le même processus — c'est-à-dire exactement la coupe de
  [`architecture-app.md`](architecture-app.md). 46 outils schématisés pour
  agents via FastMCP. Petit projet (~20 ★), et de périmètre inverse du
  nôtre : automatisation large (CFD, FEM, BIM, découpe) plutôt qu'éditeur
  interactif.

  Son intérêt est ailleurs, et il est nouveau : **c'est le premier dépôt de
  cette veille qui soit à la fois empruntable et remontable.** MIT est
  compatible LGPL-2.1 dans les deux sens (cf.
  [`amont-freecad.md`](amont-freecad.md) §3). Si la piste « schéma d'outils
  dérivé du vocabulaire » ([`vcad.md`](vcad.md) §5.4) se concrétise, c'est
  là qu'il faut regarder d'abord — et c'est le seul endroit où on aura le
  droit de copier.

## Conclusion

Rien à changer à la doctrine du 2026-08-02, une fois de plus — mais cette
fois elle gagne un versant, et une preuve.

Le versant : on ne réécrit pas le noyau *et* on ne garde pas pour soi ce
que le noyau nous montre.

La preuve : la première application sérieuse de ce second versant a
supprimé du travail au lieu d'en créer. Six constats instruits, un module
`EdgeHint` annulé, deux rapports de bug évités, une issue ouverte trouvée.
**Regarder en amont avant d'écrire est moins cher qu'écrire.** C'est la
règle mise en tête du §5 de [`amont-freecad.md`](amont-freecad.md).

Et une surprise, qui ne venait pas de dehors : le candidat amont le plus
mûr du projet **était déjà écrit chez nous**.
[`navigation-spec.md`](navigation-spec.md) répond mot pour mot à ce qu'un
mainteneur FreeCAD a demandé publiquement en décembre 2024 — et personne
n'y a répondu depuis. Il est entré au registre sous l'entrée **A10**. Le
premier tour l'avait manqué parce qu'il cherchait des contournements dans
`engine/` ; celui-là ne contourne rien, c'est un document. La leçon vaut
d'être retenue : **un constat amont ne prend pas toujours la forme d'une
rustine.**

Et une nuance à porter au crédit de la veille elle-même : avec PartMode,
« la voie est libre » devient « la voie est étroite ». Ce qui reste à nous
seuls tient en une phrase — le modèle documentaire de FreeCAD conservé, et
le `.FCStd` qui se rouvre dans FreeCAD. Tout le reste a maintenant des
concurrents sérieux, **y compris sur l'interface**, qui était censée être
notre terrain : PartMode y met dix fois notre volume de code, et un
contrat de navigation testable que nous n'avons pas.

Ce qui n'est pas une raison de courir après le volume. C'en est une de
prendre chez eux la seule chose qui se prend sans écrire de fonction : le
contrat. Nos opérations sont déjà déclarées dans `engine/protocol.py` ;
nos gestes d'interface ne le sont nulle part.

---

# Relevé du 2026-08-21 (suite) — quatre angles morts du tableau

*Le tableau du 2026-08-02 a été bâti sur une question : « qui construit une
UI moderne **pour FreeCAD** ? » Il a donc bien vu les projets qui se posaient
la même question, et manqué ceux qui en posaient une autre. Quatre angles
morts, du plus gênant au plus rassurant.*

## 1. L'angle mort gênant — moderniser l'UI de FreeCAD **sans** la remplacer

C'est la réponse concurrente à notre prémisse, elle existe, elle est
distribuée officiellement, et le tableau ne la mentionnait pas.

[**APEbbers/FreeCAD-Ribbon**](https://github.com/APEbbers/FreeCAD-Ribbon)
remplace les barres d'outils de FreeCAD par un **ruban** bâti sur les
barres existantes : conception stockée en JSON, dialogue de personnalisation
(tailles de boutons, fusion de panneaux, réordonnancement, panneaux
transverses, feuilles de style), désinstallation réversible. **GPL-3.0,
~130 ★, 3 303 commits, présent dans l'Addon Manager officiel.** Il descend
de [`geolta/FreeCAD-Ribbon`](https://github.com/geolta/FreeCAD-Ribbon) et
de [`HakanSeven12/Modern-UI`](https://github.com/HakanSeven12/Modern-UI),
via la bibliothèque PyQtRibbon.

**Il faut le dire honnêtement : sur le ruban seul, il nous bat.** Il hérite
gratuitement de *toutes* les fonctions de FreeCAD, y compris celles que nous
n'avons pas et n'aurons pas avant longtemps ; nous, nous devons ré-exposer
chaque fonction une par une. Sa dette est ailleurs :

| | FreeCAD-Ribbon | FreeSolid |
|---|---|---|
| Ce qui est modernisé | la **disposition** des commandes existantes | la disposition **et** l'interaction, le viewport, la sélection |
| Ce qui reste | Qt, les dialogues, les modales, la navigation de FreeCAD | rien de Qt |
| Surface de couplage | les **internes Qt** de FreeCAD | un protocole JSON de 98 opérations |
| Couverture fonctionnelle | **totale, immédiate** | ce que nous avons ré-exposé |
| Installation | un addon | FreeCAD ≥ 1.0 + notre serveur |

Le couplage n'est pas théorique : l'issue amont
[#30248](https://github.com/FreeCAD/FreeCAD/issues/30248) — *RibbonUI ne se
charge plus suite au commit `0d58641`* — a été confirmée et classée
**régression**. Mais il faut être juste : **l'amont l'a traitée comme une
régression et l'a corrigée** (PR #30261). L'écosystème absorbe la casse ;
ce n'est pas de la négligence. La différence avec nous n'est pas la qualité
du soin, c'est la **taille de la surface** : un protocole JSON par-dessus
une frontière de processus se casse moins souvent que les internes d'un
toolkit graphique, et quand il se casse, le selftest le dit.

**Ce qu'on en fait.** Rien à prendre — GPL-3.0, donc ni empruntable chez
nous (LGPL-2.1-or-later) ni remontable dans FreeCAD (LGPL-2.1-or-later
aussi) : un addon sous GPL-3 ne peut pas fusionner dans le cœur. Mais c'est
la **référence d'organisation du ruban la plus pertinente qui existe**,
puisqu'elle range les vraies commandes de FreeCAD. À regarder quand on
arbitrera nos propres panneaux. Et à citer : quand on nous demandera
« pourquoi ne pas juste améliorer l'UI de FreeCAD ? », la réponse est
« quelqu'un le fait déjà, très bien, et voici pourquoi nous coupons
ailleurs ».

## 2. L'angle mort flatteur — Dune3D fait notre pari, sur un autre couple

[**dune3d/dune3d**](https://github.com/dune3d/dune3d), par Lukas K. (auteur
de Horizon EDA) : **le solveur de SolveSpace + le noyau OCCT + une coquille
neuve en GTK4**. GPL-3.0, ~2,1 k ★, v1.4.0 « Einstein » en janvier 2026,
présenté au FOSDEM 2026 après deux ans et demi de travail.

C'est **notre doctrine, appliquée à un autre couple de donneurs** : ne
réécrire ni le solveur ni le noyau, ne refaire que ce qui se voit. Sa
motivation d'origine, dite dans son README, est d'ailleurs une critique de
FreeCAD que nous partageons à moitié — l'esquisseur modal et purement 2D —
doublée d'une critique de SolveSpace (pas de STEP, pas de vrais congés).

| | Dune3D | FreeSolid |
|---|---|---|
| Noyau | OCCT direct | OCCT **via FreeCAD** |
| Solveur | SolveSpace | planegcs (celui de FreeCAD) |
| Modèle documentaire | **réécrit** | celui de FreeCAD, intact |
| Coquille | GTK4, bureau | web |
| Fichiers | format propre + STEP | `.FCStd` réouvrable dans FreeCAD |

La ligne de partage est exactement la même qu'avec Chili3D, SindriCAD et
PartMode : **tout le monde réécrit le modèle documentaire, personne ne le
garde.** C'est, à ce jour, notre seul différenciateur réellement unique —
et le relevé de ce jour l'a maintenant vérifié sur cinq projets
indépendants.

Ce que Dune3D apporte de neuf au dossier, c'est une **preuve de
faisabilité du milieu** : on peut faire une CAO paramétrique moderne et
utilisable en réutilisant les morceaux durs, sans être ni FreeCAD ni un
noyau réécrit. Deux ans et demi, une personne. C'est l'ordre de grandeur
auquel se comparer — pas les 445 kloc de vcad.

## 3. L'angle mort ancien — jsketcher, le prédécesseur navigateur

[**xibyte/jsketcher**](https://github.com/xibyte/jsketcher), ~1,7 k ★,
1 784 commits : « *parametric 2D and 3D CAD modeler written in pure
javascript* ». OCCT compilé en WASM pour le solide, **solveur de
contraintes 2D écrit maison en JS/TS**, métaphore fonction/historique avec
navigation dans l'historique et réédition des paramètres — et, détail qui
compte pour nous, **propagation d'identifiants d'arêtes et de faces**,
c'est-à-dire une attaque du toponaming. Statut : bêta.

Il aurait dû être au tableau du 2026-08-02 : c'est le plus ancien
« FreeSolid sans FreeCAD » et il coche presque toutes les cases de la thèse.

**Et il porte le piège de licence le plus vicieux de toute la veille.** Son
`LICENSE` ressemble à du MIT et n'en est pas : c'est un MIT **modifié par
Autodrop3d LLC**, qui impose que toute modification soit soumise en *pull
request* avec **cession de copyright**, sauf à acheter une licence
commerciale. Autrement dit : ni empruntable, ni forkable en pratique — et
les listes qui le rangent sous « MIT » se trompent.

**Leçon pour la grille de licences** de [`amont-freecad.md`](amont-freecad.md)
§3 : le nom d'une licence dans un README, une liste curatée ou une page
GitHub **n'est pas une licence**. On lit le fichier `LICENSE` avant de
classer un dépôt comme empruntable. Ça vient de nous coûter cinq minutes ;
ça aurait pu coûter un contentieux.

## 4. L'angle mort rassurant — le verdict 2026 sur les noyaux réécrits

Le tableau du 2026-08-02 concluait sur un avertissement d'expert : les
noyaux géométriques ne sont « pas vibe-codables ». Ce n'était qu'une
citation de forum. **Elle a maintenant des données.**

| Projet | État au 2026-08-21 |
|---|---|
| [**Fornjot**](https://github.com/hannobraun/fornjot) — noyau B-rep en Rust, Hanno Braun | **Archivé le 2026-06-19.** Le README dit : « *This project has been shut down. Its goals were never reached.* » Près de **20 000 commits**, plusieurs années, un auteur dédié à plein temps, ~48 versions. La ligne principale n'avait plus avancé depuis plus d'un an |
| [**Truck**](https://github.com/ricosjp/truck) — noyau CAD en Rust, Ricos | Actif — mais la feuille de route annonce toujours « *re-implement the B-rep with NURBS* ». Après des années, le B-rep NURBS est encore **devant** eux |
| [**vcad**](vcad.md) | 445 kloc, 92 crates, actif — et un booléen de 26 kloc pour un noyau qui ne compile pas sans deux dépôts frères |
| **waffle-iron** | ~6 mois de travail assisté par IA, UI « needs a lot of work » |

Fornjot est le point de donnée le plus net qu'on pouvait espérer : ce
n'est pas un projet abandonné faute d'intérêt, c'est un projet **soigné,
financé par son auteur, documenté publiquement pendant des années**, qui
s'arrête en écrivant que ses objectifs n'ont jamais été atteints. Aucun
des quatre n'a produit un noyau qu'on voudrait mettre sous une pièce de
production.

**Doctrine confirmée, et cette fois avec des preuves plutôt qu'une
intuition.** Le noyau n'est pas le morceau qu'on réécrit — c'est le morceau
qu'on hérite.

## 5. Et le joueur commercial — Zoo (KittyCAD)

[**KittyCAD/modeling-app**](https://github.com/KittyCAD/modeling-app) — Zoo
Design Studio. CAO « AI-native » articulée autour de **KCL**, leur langage
de CAO paramétrique, qui est la source de vérité du modèle. L'application
est open source ; **le moteur géométrique ne l'est pas**.

Statut pour nous : hors périmètre — c'est un produit financé, fermé là où
ça compte, et sur le créneau du *code-CAD* plus que de l'esquisse à la
souris. Mais c'est le seul acteur de cette veille avec des moyens
industriels, et son pari (le langage comme source de vérité) est le
troisième modèle documentaire possible, à côté de l'historique linéaire et
du graphe. À surveiller sans plus.

## Ce que cette suite change

Rien à la doctrine — et c'est la troisième fois de la journée que ce relevé
l'écrit, ce qui commence à être un résultat en soi. Mais trois choses
changent dans notre façon de la défendre :

1. **On ne peut plus dire « personne n'a fait ça ».** Il faut dire ce qui
   est vrai et vérifié sur cinq projets indépendants — Chili3D, SindriCAD,
   PartMode, Dune3D, jsketcher réécrivent tous le modèle documentaire.
   **Personne ne garde celui de FreeCAD.** C'est plus étroit qu'avant, et
   c'est solide.
2. **On a une réponse à « pourquoi ne pas juste améliorer FreeCAD ? »**,
   et elle ne consiste pas à dénigrer FreeCAD-Ribbon, qui fait très bien
   ce qu'il fait. Elle consiste à montrer les deux surfaces de couplage.
3. **On a des preuves à la place d'une intuition** sur le noyau. Fornjot
   archivé vaut mieux que n'importe quelle citation de forum.

Une correction de méthode, enfin. Ces quatre angles morts existaient parce
que le tableau interrogeait « une UI moderne **pour FreeCAD** ». La veille
doit poser au moins trois questions, pas une : *qui refait l'UI de FreeCAD*,
*qui refait une CAO paramétrique sans FreeCAD*, et *qui a essayé d'écrire
un noyau et où il en est*. La troisième est celle qui protège la doctrine ;
c'est celle qu'on avait le moins instruite.

---

# Relevé du 2026-08-21 (fin) — cinq dépôts signalés

*Cinq liens transmis. Un était déjà au tableau, un est une vraie trouvaille,
un est directement utilisable, deux ne servent qu'à documenter. Verdict pour
chacun.*

## 1. Oblikovati — la trouvaille, et le cinquième noyau réécrit

[**Oblikovati/Oblikovati**](https://github.com/Oblikovati/Oblikovati) :
« *a parametric, feature-based, history-driven mechanical-CAD (MCAD)
application — an Inventor-class 3D solid modeler — rebuilt from the ground
up in **Go** with a **Vulkan 1.3** renderer* ». Noyau B-rep maison,
**nommage topologique persistant**, Dear ImGui, deux binaires livrés :
`oblikovati-head` (GUI) et `oblikovati-cli` (**headless**).

Mesuré à la source le 2026-08-21 :

| | |
|---|---|
| Volume | **644 257 lignes de Go**, 4 800 fichiers — plus gros que vcad |
| Tests | **2 418 fichiers `_test.go`** — la moitié des fichiers du dépôt |
| Noyau | `kernel/ops` 121 714 l. · `kernel/geom` 28 312 l. · `kernel/brep` 27 039 l. · `kernel/topo` 4 274 l. · **`kernel/blend` (congés) 1 625 l.** |
| Activité | dernier commit **le jour même du relevé** ; ~106 ★, 3 833 commits |
| Licence | **GPL-2.0** pour l'application · **Apache-2.0** pour le contrat `Oblikovati.API`, séparé exprès pour autoriser des extensions fermées |
| Statut assumé | « early/foundational » : le modelage de pièce marche, assemblages, mises en plan et tôlerie sont à la feuille de route |

**Lecture honnête du ratio.** 121 kloc d'opérations et 27 kloc de B-rep,
mais **1 625 lignes de congés**. Les congés sont, après les booléens, le
morceau le plus dur d'un noyau — c'est là qu'on mesure la maturité, pas au
total. Le projet le dit lui-même (« early/foundational ») ; c'est la
prétention affichée (« Inventor-class ») qui va plus vite que le code. Le
dépôt porte un `CLAUDE.md` : développement assisté par IA, comme
`waffle-iron`.

**Deux choses valent quand même le détour, et aucune n'est du code.**

1. **Sa priorité d'ingénierie est notre entrée A9.** Son `CLAUDE.md` place
   « *tessellation correctness* » **au-dessus de toute fonctionnalité », et
   la contrôle par des tests de non-régression comparant volume et aire à
   un **noyau externe (`gmsh` / OpenCASCADE `getMass`)**. C'est la
   troisième occurrence indépendante de l'idée de banc d'essai noyau, après
   `mecheval` de vcad et notre selftest — et la plus concrète : *valider
   son propre noyau contre OCCT*. Nous, nous avons OCCT comme noyau ; nous
   pouvons faire l'inverse, et valider **FreeCAD contre lui-même** d'une
   version à l'autre. Voir [`amont-freecad.md`](amont-freecad.md) A9.
2. **Son montage de licences est une idée d'architecture.** Application en
   GPL-2, **contrat d'API en Apache-2.0** : le protocole est libre de
   contrainte pour que n'importe qui écrive un client, l'implémentation
   reste protégée. Nous avons exactement cette dualité sans l'avoir
   nommée — `engine/protocol.py` est un contrat, le reste est une
   implémentation. La question mérite d'être posée un jour : notre
   protocole gagnerait-il à être documenté comme un contrat séparé ?

**À prendre : rien.** GPL-2.0 sur l'application, donc ni empruntable chez
nous ni remontable à FreeCAD.

## 2. SolveSpace — il aurait dû être au tableau depuis le début

[**solvespace/solvespace**](https://github.com/solvespace/solvespace) :
« *a parametric 2d/3d CAD tool* », **GPL-3.0-or-later**, ~4,1 k ★,
activement maintenu. C'est le solveur que [Dune3D](https://github.com/dune3d/dune3d) réutilise, et il est
disponible en bibliothèque (`libslvs`, bindings Python).

Ce qui le rend intéressant pour nous tient en un mot : **3D**. Son solveur
gère des contraintes **dans l'espace**, pas seulement dans un plan. Or
[`grandes-lignes.md`](grandes-lignes.md) classe les esquisses 3D en 🔴 —
« FreeCAD ne les a pas », et notre repli est des courbes 3D par points sans
contraintes. SolveSpace montre que la brique existe.

**Et pourtant, rien à en tirer directement :** GPL-3.0-or-later couvre tout
le projet, `libslvs` compris. Ni empruntable dans FreeSolid
(LGPL-2.1-or-later), ni remontable dans FreeCAD. Notre solveur reste
planegcs, qui est celui de FreeCAD, en LGPL et déjà vendoré.

Statut : **référence conceptuelle** pour le jour où la question des
contraintes 3D reviendra — et argument à connaître, puisque c'est la
réponse qu'on nous opposera (« pourquoi pas SolveSpace ? »). La réponse est
la licence, pas la qualité.

## 3. verb — le seul des cinq qu'on peut vraiment utiliser

[**pboyer/verb**](https://github.com/pboyer/verb) : bibliothèque NURBS
**MIT**, ~811 ★, écrite en Haxe et compilée vers JS, C#, C++, Python, PHP.
Le dépôt livre `verb.js`, `verb.min.js` et `verb.es.js` **déjà construits** —
un `import` suffit. Modules : `Eval`, `Divide`, `Modify`, `Make`,
`Intersect`, `Tess`, `Analyze`, `Check`.

Ce qu'elle fait : évaluation de courbes et surfaces NURBS, dérivées,
**tessellation adaptative**, **intersections**. Ce qu'elle ne fait pas :
pas de solides B-rep, pas de booléens. C'est de la géométrie, pas un noyau —
et c'est précisément pour ça qu'elle est utilisable.

**Pourquoi elle compte pour FreeSolid.** C'est le pendant de planegcs, pour
les courbes : de quoi calculer et afficher une B-spline **côté client**,
sans aller-retour serveur. Deux usages immédiats :

- les **courbes 3D par points** de la phase D (le repli esquisse 3D) —
  aujourd'hui chaque édition passe par le moteur ;
- tout aperçu de courbe pendant un glisser, sur le modèle de ce que M3 a
  fait pour l'esquisse 2D.

**Et sa licence est la bonne** : MIT, donc **à la fois empruntable dans
FreeSolid et remontable à FreeCAD** — le troisième dépôt de toute cette
veille dans ce cas, après `sandraschi/freecad-mcp`. À noter au passage :
`app/vendor/` a déjà sa discipline pour ce genre d'apport.

Activité faible (dernier commit **2025-04-02**), ce qui est normal pour une
bibliothèque de mathématiques stabilisée — à distinguer d'un projet mort.

## 4. VisualScriptCAD — un point d'histoire, rien de plus

[**kovacsv/VisualScriptCAD**](https://github.com/kovacsv/VisualScriptCAD) :
modeleur 3D par script visuel bâti sur `VisualScriptEngine`, du même auteur
que l'excellent `Online3DViewer`. C++, GPL-3.0, ~131 ★, 323 commits —
et **marqué « No Maintenance » depuis 2019**. L'auteur lui-même le présente
comme « *a simple experimental 3D modeling application* ».

Il complète la ligne « nœuds » du relevé du 2026-08-15 : c'est une
troisième preuve qu'un éditeur de nœuds sur de la géométrie est faisable —
après Nodi3D et `j8sr0230/Nodes`. Mais géométrie maillée, projet arrêté,
licence bloquante. **Rien à prendre**, et la décision de
[`nodes-macros.md`](nodes-macros.md) — le graphe est une *vue*, pas un
second moteur — le rend de toute façon sans objet.

## 5. Nodi3D — déjà au tableau, et il faut le dater

[**Nodi3d/nodi**](https://github.com/Nodi3d/nodi) figure au tableau depuis
le relevé du 2026-08-15 (« Grasshopper dans le navigateur, Apache-2.0 »).
Rien à changer au verdict — géométrie maillée, pas de B-Rep exact — mais
une précision à ajouter : **dernier commit le 2024-11-08**, soit près de
deux ans d'arrêt. Sa ligne du tableau est mise à jour en conséquence.

## Ce que ce lot change

**Sur les noyaux réécrits, le tableau est maintenant complet — et il
raconte une histoire cohérente.** Cinq tentatives sérieuses, aucune
utilisable en production :

| Projet | Langage | État au 2026-08-21 |
|---|---|---|
| **Fornjot** | Rust | **archivé** le 2026-06-19 — « *goals were never reached* », ~20 000 commits |
| **Truck** | Rust | actif — B-rep NURBS toujours **devant** eux |
| **waffle-iron** | Rust | ~6 mois assistés par IA, UI « needs a lot of work » |
| **vcad** | Rust | 445 kloc, 92 crates, actif — booléen de 26 kloc, ne compile pas seul |
| **Oblikovati** | **Go** | 644 kloc, actif — **1 625 lignes de congés**, « early/foundational » assumé |

Deux langages, cinq équipes, des centaines de milliers de lignes, et pas un
noyau qu'on mettrait sous une pièce de production. **La doctrine ne se
discute plus : on hérite le noyau, on ne l'écrit pas.**

**Et un gain concret, un seul, mais net : `verb`.** C'est le premier apport
de cette journée de veille qui soit directement branchable, sous une licence
qui n'interdit rien, et qui répond à un manque déjà inscrit à la feuille de
route. Tout le reste de la journée aura servi à *ne pas* écrire du code ;
celui-ci sert à en écrire moins.
