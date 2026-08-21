# Amont FreeCAD — la frontière, et ce qu'on lui rend

*Doctrine posée le 2026-08-21, à l'occasion du relevé
[`vcad.md`](vcad.md), qui a rendu la question inévitable.*

## 1. La règle, en deux phrases

> **Chaque ligne écrite se range d'un côté de la frontière.** Ce qui touche
> la géométrie, le document, le solveur ou le recompute est à FreeCAD : on
> ne le réécrit pas. Ce qui n'existe que parce que l'interface est du web et
> le moteur piloté par un protocole est à nous : on est seuls dessus.
>
> **Et quand le travail sur FreeSolid fait apparaître un manque du côté
> FreeCAD, on ne le contourne pas en silence : on le remonte.** Le
> contournement reste chez nous, mais le constat part en amont.

La première phrase n'est pas nouvelle — c'est
[`architecture-app.md`](architecture-app.md) (« on change la peau et la
main ; pas les os »). Ce document ajoute la seconde, et surtout la
**procédure** qui permet de trancher les cas mixtes, qui sont les seuls
intéressants.

Pourquoi cette seconde phrase mérite d'être écrite : FreeSolid n'est pas
seulement un consommateur de FreeCAD, c'est un **client headless
instrumenté, versionné sur une version de référence unique, avec un
selftest**. C'est une position d'observation que FreeCAD n'a pas sur
lui-même. Ce que nous voyons depuis là, personne d'autre ne le voit — et
un constat gardé pour soi est du travail jeté deux fois : une fois pour
eux, une fois pour nous à la prochaine version.

## 2. Où passe la ligne — la procédure

Trois questions, dans cet ordre. La première qui répond « oui » tranche.

1. **Est-ce que ça touche la géométrie, le modèle documentaire, le solveur
   ou le recompute ?**
   → **côté FreeCAD.** On l'utilise, on ne l'écrit pas. Si ça manque, ça
   devient une entrée du registre (§4), jamais un module chez nous.

2. **Est-ce que ça n'existe que parce que l'interface est du web, ou parce
   que le moteur est piloté par un protocole JSON ?**
   → **côté FreeSolid.** FreeCAD n'a pas le problème : chez lui
   l'utilisateur est déjà dans le processus, et la présentation est en Qt.
   Personne ne le résoudra pour nous.

3. **Cas mixte : le besoin est à nous, la capacité manquante est à eux.**
   → **les deux.** On écrit le repli chez nous, *avec un commentaire qui
   nomme l'entrée du registre*, et on instruit la question amont. On ne
   choisit pas entre les deux : le repli fait marcher le produit
   aujourd'hui, le rapport évite de le porter pour toujours.

### Le tableau des cas déjà tranchés

| Sujet | Côté | Pourquoi |
|---|---|---|
| Booléens, congés, coques, balayages, STEP | FreeCAD | question 1 — c'est la géométrie |
| Solveur d'esquisse (planegcs) | FreeCAD | question 1 — même compilé en WASM et exécuté dans le navigateur, c'est *leur* solveur, vendoré tel quel |
| Nommage topologique dans le document | FreeCAD | question 1 — le « toponaming fix » de la 1.0 est une des raisons de garder ce moteur |
| Tessellation | FreeCAD | question 1 |
| Groupement des faces dans le maillage pour le picking | FreeSolid | question 2 — le picking navigateur n'existe pas chez eux |
| Garde de rejeu d'un groupe de fonctions (`engine/replay.py`) | FreeSolid | question 2 — le rejeu N010 est notre construction, sur nos enregistrements de fonction |
| Validation du protocole JSON (`engine/protocol.py`) | FreeSolid | question 2 — il n'y a pas de protocole chez eux |
| Rapport de selftest | FreeSolid | question 2 |
| Traduction des erreurs PartDesign en termes de concepteur (`engine/guard.py`) | **les deux** | question 3 — écrit chez nous par nécessité, utile chez eux (entrée **A6**) |
| Undo borné en session longue | **les deux** | question 3 — le besoin est le nôtre, l'API Python manquante est la leur (entrée **A2**) |
| Mise en plan TechDraw headless | **les deux, sous réserve** | question 3 — nos vues, leurs crashs… si ces crashs existent encore en 1.1.3 (entrées **A4**, **A5**, suspendues à un re-test) |
| Suivi d'une référence de sous-élément à travers un recompute | **FreeCAD** — tranché le 2026-08-21 | question 1 : la carte d'éléments est à eux, **et ils l'exposent en Python** ; à nous de nous en servir, pas de la refaire (§4ter) |
| Style de navigation SolidWorks (rotation au bouton du milieu, ancrage du centre d'orbite…) | **FreeCAD** | question 1 — ça vit dans `src/Gui/NavigationStyle.cpp`, pas chez nous. En attendant, FreeSolid se règle sur le style Blender, le plus proche existant (entrée **A10**) |
| Esquisses 3D, configurations | ni l'un ni l'autre | écarts assumés de [`grandes-lignes.md`](grandes-lignes.md) — un choix de périmètre n'est pas un bug à remonter |

## 3. La grille des licences — ce qui peut partir en amont

C'est la contrainte qui **décide de la forme de nos emprunts**, et elle est
plus serrée que la simple compatibilité avec FreeSolid. Une contribution à
FreeCAD doit être remontable en **LGPL-2.1-or-later** ; toute ligne qui ne
peut pas l'être ferme la porte amont pour elle-même et pour tout ce qui en
dérive.

| Source | Intégrable dans FreeSolid | Remontable à FreeCAD | Exemple |
|---|---|---|---|
| **Nos propres lignes** | oui | **oui** | `engine/guard.py`, `engine/replay.py` |
| **LGPL-2.1(-or-later)** | oui, sans effet de bord | **oui** | [`j8sr0230/Nodes`](https://github.com/j8sr0230/Nodes) et son modèle `awkward` |
| **MIT / BSD** | oui, avec attribution | **oui** (relicenciable en LGPL) | [`pboyer/verb`](https://github.com/pboyer/verb) (NURBS), [`sandraschi/freecad-mcp`](https://github.com/sandraschi/freecad-mcp) |
| **Apache-2.0** | possible, mais fait passer l'ensemble distribué en LGPL-3.0 | **non** | [`vcad`](https://github.com/ecto/vcad) |
| **GPL-2.0** | non — contaminerait FreeSolid entier | **non** | [Oblikovati](https://github.com/Oblikovati/Oblikovati) (l'application ; son contrat d'API, lui, est en Apache-2.0) |
| **GPL-3.0** | non — contaminerait FreeSolid entier | **non** — un GPL-3 ne fusionne pas dans une bibliothèque LGPL-2.1 | [FreeCAD-Ribbon](https://github.com/APEbbers/FreeCAD-Ribbon), [Dune3D](https://github.com/dune3d/dune3d) |
| **AGPL-3.0** | non — contaminerait FreeSolid entier | **non** | [Chili3D](https://github.com/xiangechen/chili3d), [PartMode](https://github.com/BOMWiki/partmode) |
| **« Permissive » sur parole** | ⚠️ **à vérifier fichier en main** | ⚠️ | [jsketcher](https://github.com/xibyte/jsketcher) : un « MIT » modifié imposant la cession de copyright |

**Une règle de vérification, apprise le 2026-08-21 :** le nom d'une licence
dans un README, une liste curatée ou l'encart latéral de GitHub **n'est pas
une licence**. On ouvre le fichier `LICENSE` avant de classer un dépôt comme
empruntable. `jsketcher` est annoncé « MIT » un peu partout et porte en
réalité un MIT modifié par Autodrop3d LLC qui impose la soumission de toute
modification **avec cession de copyright**, sauf licence commerciale — ni
empruntable, ni forkable en pratique.

D'où la règle de lecture, qui vaut pour tout dépôt permissif :

> **Des dépôts sous licence non remontable, on prend des idées et jamais
> des lignes.** Le prix d'un copier-coller n'est pas juridique, il est
> stratégique : c'est la porte amont qu'il ferme, définitivement, pour ce
> code et sa descendance.

Conséquence directe et vérifiable : **aucune entrée du registre §4 ne peut
descendre d'un fichier vcad ou Chili3D.** Si une entrée s'avérait dériver
de l'un des deux, elle sort du registre — pas parce qu'elle serait moins
bonne, mais parce qu'elle n'est plus remontable.

## 4. Le registre amont

Constats nés du développement de FreeSolid qui appartiennent au côté
FreeCAD. Aucun n'est encore parti : ce registre est l'état des lieux, pas
un journal d'envois.

**Chaque entrée a été confrontée à la source amont le 2026-08-21** — dépôt
`FreeCAD/FreeCAD` lu au tag **1.1.3** (notre référence) *et* sur `main`,
plus la recherche d'issues existantes. Le résultat est une colonne
« vérifié » qui vaut plus que le constat lui-même : **deux entrées sont
tombées, deux ont changé de nature, une a trouvé une issue ouverte qui
l'attendait.** La méthode et ce qu'elle a coûté sont en §8.

Nature : **bug** (comportement faux ou crash) · **API** (capacité absente
côté Python) · **doc** (comportement correct mais nulle part écrit) ·
**produit** (amélioration d'ergonomie ou de message) · **feat** (fonction
manquante qu'on est en mesure d'apporter) · **banc** (matière de
non-régression).

| # | Constat | Où c'est visible chez nous | Nature | Vérifié en amont le 2026-08-21 | État |
|---|---|---|---|---|---|
| **A10** | **FreeCAD n'a pas de style de navigation SolidWorks**, et un mainteneur a dit précisément ce qu'il faudrait pour en ajouter un | [`navigation-spec.md`](navigation-spec.md) — la spécification demandée, déjà rédigée en brouillon | feat | ✅ **la porte est ouverte et personne n'y est entré** : la [discussion #18635](https://github.com/FreeCAD/FreeCAD/discussions/18635) a été fermée le 2024-12-23 par luzpaz sur « *If you make progress feel free to re-open discussion* », après avoir pointé `src/Gui/NavigationStyle.cpp` et les styles existants comme modèles. **Aucune proposition détaillée n'a été fournie depuis** (vérifié le 2026-08-21) | 🥇 **l'entrée la plus mûre du registre** — il ne manque qu'une validation ligne à ligne par un utilisateur SolidWorks quotidien |
| **A1** | `freecadcmd script.py` **importe le fichier comme module** au lieu de l'exécuter comme script — d'où `__name__` = le nom du fichier, jamais `"__main__"` | absence volontaire de garde dans `engine/server.py` ; expliqué (imprécisément) dans `AGENTS.md` | doc | ✅ **mécanisme établi** : `src/App/Application.cpp:3108-3117` appelle `addPythonPath(dirname)` puis `loadModule(stem)`, et ne retombe sur `runFile(path, local=true)` — qui exécute dans une **copie** du dict de `__main__` — que si l'import lève | à formuler ; **corriger d'abord notre propre `AGENTS.md`** |
| **A2** | Aucun moyen de borner la pile d'undo depuis Python | `engine/kernel.py:311-322` (double `hasattr`), audit **2.4** | API | ✅ **confirmé et élargi** : `src/App/Document.pyi` n'expose ni `UndoLimit` ni `setMaxUndoStackSize` / `getMaxUndoStackSize`, **ni en 1.1.3 ni sur `main` au 2026-08-21** — seulement `UndoRedoMemSize` en lecture seule. Le C++ a bien `setMaxUndoStackSize()`, il n'est pas exporté. Et le manque **ne figure pas** au [catalogue public des défauts de l'API Python](https://gist.github.com/galou/1fea17fbcf8cd25cf613b142cd9012ce) tenu par galou : notre entrée est inédite, et ce catalogue est l'endroit où la rattacher | **demande amont nette et minuscule** ; nos deux branches `hasattr` sont du code mort à annoter |
| **A3** | Joints d'assemblage headless : API non documentée, forme d'argument piégeuse | `engine/kernel.py:518-560` | doc | ✅ **requalifié** : `setJointConnectors` n'est pas absent, il est **exercé par la suite de tests amont** — `src/Mod/Assembly/AssemblyTests/TestCore.py:251` — et n'est qu'une façade posant `Reference1`/`Reference2`. Il manque donc la **documentation**, pas l'API | demande amont réduite à la doc ; voir §4bis pour ce que le test amont nous apprend sur **notre** code |
| **A4** | TechDraw headless : SIGSEGV sur `getSectionCS` (direction parallèle) et sur `CutSurfaceDisplay=Hide` | `engine/kernel.py:1126-1136` (contournements en place) | bug | ⚠️ **prémisse probablement périmée** : en 1.1.3 `DrawViewSection::getSectionCS()` enveloppe déjà la construction du repère dans un `try/catch` et journalise « failed to create section CS » au lieu de planter. Et la famille « TechDraw SIGSEGV depuis la CLI » a son issue amont, [#20024](https://github.com/FreeCAD/FreeCAD/issues/20024), **fermée par la PR #20110** | 🔴 **ne rien remonter avant d'avoir re-testé sur 1.1.3.** Nos contournements datent de 1.0.0 et pourraient être devenus inutiles. Le re-test est écrit : [`scripts/spike-techdraw-coupe.py`](../scripts/spike-techdraw-coupe.py) — **hors CI par construction**, puisqu'il peut faire un SIGSEGV et tuerait le job |
| **A5** | TechDraw headless : géométrie 2D de coupe souvent vide (HLR même thread) ; DXF seul export fiable | `engine/kernel.py:1166-1172` | doc | ⚠️ même réserve que A4 — la partie « cut async » de notre commentaire n'est pas couverte par le `try/catch`, elle reste plausible | à re-tester avec A4, même spike |
| **A6** | Les échecs PartDesign les plus déroutants sont **corrects mais inexpliqués** — « multiple solids », « out of the allowed scope », « wire is not closed » | `engine/guard.py` — trois traductions écrites, testées unitairement | produit | ✅ **une issue ouverte attend exactement ça** : [#19255](https://github.com/FreeCAD/FreeCAD/issues/19255) — *« "BRep_API: command not done" is not a clear or actionable error message »*, **ouverte**, étiquetée **Help wanted**, projet « OCCT Liaison » | **le candidat le plus mûr du registre** : notre code est déjà écrit, testé, sous la bonne licence, et il y a une porte ouverte où frapper |
| **A7** | ~~Suivre une référence de sous-élément à travers un recompute avec un verdict explicite~~ | ~~`engine/replay.py`~~ | — | ❌ **entrée close — FreeCAD l'expose déjà.** Voir §4ter | **retirée du registre** ; devient une tâche FreeSolid |
| **A8** | Segfaults OCCT hors TechDraw | audit **2.12** | bug | — non instruit | seulement si un cas devient reproductible |
| **A9** | Grille de non-régression du noyau — stress booléen, aller-retour STEP, taux de succès des congés, convergence du solveur, qualité de tessellation | `scripts/run-selftest.py`, direction posée dans [`vcad.md`](vcad.md) §5.5 | banc | — direction, pas constat | **chaque échec du banc est un rapport amont avec reproducteur**. Méthode confirmée par une troisième source indépendante : [Oblikovati](https://github.com/Oblikovati/Oblikovati) place la justesse de tessellation **au-dessus de toute fonctionnalité** et la contrôle en comparant volume et aire à un noyau externe (`gmsh` / OCCT `getMass`). Nous pouvons faire l'inverse : comparer FreeCAD **à lui-même** d'une version de référence à la suivante |

Ce que le tableau dit, maintenant qu'il est vérifié : **le registre a
rétréci par le bas et grandi par le haut.** Sur six constats instruits, un
est mort (A7), deux sont suspendus à un re-test (A4, A5), un a changé de
nature (A3), un s'est renforcé (A2) et un a trouvé sa porte (A6) — aucune
de ces six conclusions n'était devinable depuis notre code seul.

Et l'entrée qui les dépasse toutes, **A10**, n'a pas été découverte
dehors : elle dormait dans nos propres `docs/` depuis des mois.
[`navigation-spec.md`](navigation-spec.md) répond mot pour mot à ce qu'un
mainteneur a demandé publiquement, et personne n'y a répondu depuis
décembre 2024. Le premier tour du registre l'a manquée parce qu'il a été
**semé depuis les contournements de `engine/`** — or celle-ci ne contourne
rien : elle vit dans `docs/`, et c'est un document, pas une rustine.
Leçon de méthode reportée en §8.

C'est la démonstration que la doctrine du §1 ne coûte pas seulement du
travail : elle en économise, et elle révèle du travail déjà fait qu'on
avait oublié d'appeler par son nom.

### 4bis — Ce que la reconnaissance a trouvé de notre côté

Deux constats sont retombés sur **notre** code, ce qui était l'effet
recherché : lire l'amont, c'est aussi se relire.

- **Nos joints passent probablement la mauvaise paire.** Le test amont
  `AssemblyTests/TestCore.py:251` appelle `setJointConnectors` avec
  `refs = [[obj, ["Face6", "Vertex7"]], …]` — une paire **(face, sommet)**
  par référence : la face donne le plan, le sommet donne la position.
  `engine/kernel.py:525-531` double le même nom (`[sub_name, sub_name]`),
  forme trouvée par tâtonnement et documentée comme telle dans le
  commentaire (« Face2+Face2 → centre »). À confronter au banc : ce n'est
  pas un bug amont, c'est une convention amont qu'on ignorait.
- **Notre `AGENTS.md` décrit A1 de travers.** Il dit que `freecadcmd`
  « n'exécute pas les scripts avec `__name__ == "__main__"` ». Le mécanisme
  réel est plus surprenant et a d'autres effets : le fichier est **importé
  comme module**, donc son dossier entre dans `sys.path` et son nom de
  module est le radical du fichier. À corriger chez nous avant de proposer
  quoi que ce soit en amont.

### 4ter — A7 : l'entrée close, et pourquoi elle valait le détour

`engine/replay.py` garde des références de sous-éléments sous la forme
`Edge3` / `Face2` — des **noms indexés**, c'est-à-dire précisément
l'identifiant fragile. Toute la garde `shape_fingerprint` /
`topology_verdict` existe pour compenser cette fragilité, et
[`vcad.md`](vcad.md) §5.1 proposait de la renforcer par une signature
géométrique empruntée à vcad.

**C'était réinventer ce que le moteur offre déjà.** Vérifié dans les
bindings Python de FreeCAD **1.1.3** (`src/App/ComplexGeoData.pyi`,
`src/Mod/Part/App/PartFeature.pyi`, `src/Mod/Part/App/TopoShape.pyi`) :

| Ce que FreeCAD 1.1.3 expose en Python | Ce que ça donne |
|---|---|
| `ComplexGeoData.getElementMappedName(name)` | le nom **mappé** (stable) d'un élément indexé |
| `ComplexGeoData.getElementIndexedName(name)` | l'inverse : du nom stable vers `Edge3` |
| `ComplexGeoData.getElementName(name, direction=0)` | la conversion dans les deux sens |
| `ComplexGeoData.ElementMap` / `ElementReverseMap` / `ElementMapSize` / `ElementMapVersion` | la carte elle-même, lisible **et** écrivable, et sa version |
| `Part::Feature.getElementHistory(name, recursive=True, sameType=False, showName=False)` | la **remontée complète** jusqu'à l'objet d'origine |
| `TopoShape.getElementHistory(name)` | `(tag source, nom source, [intermédiaires])`, ou `None` |
| `ComplexGeoData.Tag`, `Hasher` | ce qui active et alimente le mappage |

Autrement dit : le « toponaming fix » que
[`architecture-app.md`](architecture-app.md) cite comme raison de garder ce
moteur **est adressable depuis notre code**, et nous ne nous en servons pas.

Conséquences, dans l'ordre :

1. **On n'écrit pas d'`EdgeHint`.** L'emprunt à vcad se réduit à la
   *discipline de verdict* (résolu / ambigu / perdu, jamais de re-liaison
   silencieuse) — une idée d'API, pas un mécanisme.
2. **La tâche FreeSolid change de nature** : ce n'est plus « durcir la
   garde », c'est **stocker le bon identifiant**. La forme exacte de cet
   identifiant a été tranchée par le spike — voir §4quater.
3. ~~Un spike reste nécessaire~~ — **il a tourné le 2026-08-21**
   ([`scripts/spike-element-map.py`](../scripts/spike-element-map.py), arrivé par la PR #63),
   et son résultat corrige le point 2. §4quater.

Ce renversement est la meilleure justification du §1 qu'on pouvait
espérer : la frontière ne sert pas seulement à décider **qui écrit quoi**,
elle évite d'écrire.

### 4quater — A7 mesuré : la carte se traverse **à l'envers**, pas de face

*Résultat du 2026-08-21, [`scripts/spike-element-map.py`](../scripts/spike-element-map.py) (PR #63) sur FreeCAD 1.1.3
réel (CI). Il corrige §4ter, qui reposait sur une lecture de source non
vérifiée à l'exécution.*

| Sonde | Verdict | Mesure |
|---|---|---|
| `api_exposée` | 🟢 | les sept noms répondent |
| `carte_peuplée` | 🟢 | `ElementMapSize=30`, `Tag≠0`, `ElementMapVersion='15.70200.5'` |
| `aller_retour` | 🟢 | `Face1` → `'#d:1;:G;XTR;:H4ec:7,F'` → `Face1` |
| `survie_reparam` | 🟢 | tient à 10 → 25 mm — **mais aucun indice ne bouge : sonde faible** |
| **`survie_topologie`** | 🔴 | 6 → 10 faces après un enlèvement traversant ; le nom capturé sur le `Pad` rend **`''`** sur la forme de l'enlèvement |
| **`resolution_corps`** | 🔴 | même nom, sur la forme du `Body` : **`''`** |
| **`pont_historique`** | 🟢 | une face de la **nouvelle pointe** → son nom à elle → `getElementHistory` rend `[(Pocket, …), (Pad, '#d:1;…,F'), (Sketcher, 'g1;SKT')]` — **la trace remonte jusqu'au Pad** |

**Ce que ça veut dire, et ce n'est pas ce que §4ter annonçait.** Un nom
mappé n'est pas un identifiant global : **il est porté par la forme d'une
fonction**. Le nom d'une face du `Pad` n'est pas une clé de la carte du
`Pocket`, ni de celle du `Body`. Stocker « le nom mappé » et le résoudre
plus tard **ne marche pas**.

Mais la chaîne est navigable — **dans l'autre sens**. Depuis un nom porté
par la pointe courante, `getElementHistory` remonte jusqu'à la fonction
d'origine et au nom qu'elle portait.

**D'où la forme réelle de la tâche :**

1. Enregistrer non pas un nom, mais le **couple `(fonction propriétaire,
   nom mappé sur cette fonction)`**.
2. Au rejeu, **énumérer les éléments de la pointe**, prendre le nom mappé
   de chacun, appeler `getElementHistory`, et chercher le couple stocké
   dans la trace.
3. Le verdict à trois états emprunté à vcad se pose là : **un** élément
   dont la trace contient le couple → *résolu* ; plusieurs → *ambigu* ;
   aucun → *perdu*. Jamais de re-liaison silencieuse.

C'est une recherche à l'envers, en O(éléments de la pointe) par référence.
Plus coûteux qu'un accès direct, mais c'est de la **provenance**, pas de
la ressemblance géométrique — donc strictement mieux que l'`EdgeHint` de
vcad, qui reste abandonné.

**La leçon de méthode, elle, est la vraie prise du jour.** §4ter avait été
écrit sur la seule lecture des bindings, et il concluait juste sur
« l'API existe » et faux sur « il suffit de stocker le nom ». Lire la
source dit ce qui est **exposé** ; seule l'exécution dit ce qui **marche**.
Les deux gestes sont nécessaires, et le second n'est pas optionnel.

## 5. Comment on remonte

- **D'abord vérifier l'amont, ensuite seulement écrire.** Règle mise en
  tête parce que c'est celle que la reconnaissance du 2026-08-21 a
  démontrée le plus durement : sur six constats instruits, un était déjà
  résolu dans l'API (A7), deux visaient un crash déjà corrigé (A4, A5) et
  un décrivait comme absente une API simplement non documentée (A3).
  Lire les bindings de la version de référence et chercher l'issue
  existante coûte une heure ; l'oublier coûte un module inutile.
- **Un reproducteur minimal en `freecadcmd`, sans FreeSolid dans la
  boucle.** Un mainteneur ne doit pas avoir à installer notre projet pour
  reproduire notre constat. Si le cas ne se réduit pas à un script FreeCAD
  autonome, il n'est pas mûr — il reste au registre.
- **La version nommée.** La référence est
  [`engine/platform.py`](../engine/platform.py) (`FREECAD`, aujourd'hui
  1.1.3), et le rapport nomme aussi la version où le comportement diffère
  quand on la connaît (souvent 1.0.2, notre repli documenté).
- **En anglais.** FreeCAD journalise ses erreurs sans traduction et
  discute en anglais ; nos docs restent en français, nos rapports non.
- **Un constat = un rapport.** Le registre agrège pour nous, pas pour eux.
  Seule exception : A4 et A5 partiront ensemble s'ils survivent au re-test
  — même sous-système, même session de reproduction.
- **Le contournement reste chez nous**, avec un commentaire nommant
  l'entrée du registre. On ne maintient pas de fork de FreeCAD : le jour où
  l'amont corrige, le commentaire dit quoi retirer et à partir de quelle
  version.
- **Rien ne part qui dérive d'un dépôt non remontable** (§3). Cette
  vérification se fait avant d'écrire, pas avant d'envoyer.

## 6. Ce qu'on ne remonte pas

- **Les désaccords de goût sur l'interface.** Nous avons jeté Qt ; c'est
  notre choix, pas leur problème. Aucune ligne de ce registre ne concerne
  l'apparence.
- **Ce que FreeCAD a délibérément choisi.** « Un Body = un solide d'un seul
  tenant » n'est pas un bug : c'est un modèle, expliqué à l'utilisateur par
  `engine/guard.py`. On explique, on ne conteste pas.
- **Les 🔴 assumés de [`grandes-lignes.md`](grandes-lignes.md)** — esquisses
  3D, configurations. Ce sont des écarts de périmètre, pas des défauts.
- **Nos propres bugs.** L'audit en compte une cinquantaine ; ils sont à
  nous. Le registre ne sert pas à exporter du travail.

## 7. Entretien

Ce registre se tient à jour au fil du développement, comme
[`fonctions-manquantes.md`](fonctions-manquantes.md) : quand un
contournement est écrit pour compenser un manque du moteur, il gagne une
entrée **au moment où on l'écrit** — c'est le seul instant où le contexte
est encore frais et le reproducteur encore sous la main. Une entrée fermée
garde sa ligne, avec la version qui l'a corrigée.

## 8. La reconnaissance amont — méthode et coût

Le registre du §4 a été confronté à la source le **2026-08-21**. La méthode
tient en quatre gestes, tous reproductibles, et vaut d'être notée parce
qu'elle est bon marché :

1. **Cloner FreeCAD en lecture partielle.** `git clone --depth 1
   --filter=blob:none --sparse`, puis `sparse-checkout` sur `src/App`,
   `src/Base`, `src/Mod/Part/App`, `src/Mod/TechDraw/App`,
   `src/Mod/Assembly`, `src/Main`. **26 Mo** sur disque au lieu du dépôt
   entier, en moins d'une minute.
2. **Lire les bindings, pas la documentation.** Depuis la refonte du
   générateur de liaisons, la surface Python de FreeCAD est déclarée dans
   des fichiers `.pyi` (`src/App/Document.pyi`,
   `src/App/ComplexGeoData.pyi`, `src/Mod/Part/App/PartFeature.pyi`…).
   C'est la seule source qui ne ment pas sur ce qui est exposé — la doc
   wiki et les forums, eux, décrivent souvent le fork *LinkStage3* de
   realthunder plutôt que l'amont.
3. **Comparer la version de référence et `main`.** `git fetch --depth 1
   origin tag 1.1.3` puis `git show 1.1.3:<fichier>` répond à « est-ce dans
   *notre* version ? », et le même grep sur `main` répond à « est-ce en
   train d'arriver ? ». C'est ce couple qui a établi A2 : absent des deux.
4. **Chercher l'issue avant de l'ouvrir.** A6 avait déjà sa porte
   ([#19255](https://github.com/FreeCAD/FreeCAD/issues/19255), *Help
   wanted*) ; A4 avait déjà sa correction ([#20024](https://github.com/FreeCAD/FreeCAD/issues/20024),
   fermée par #20110).

**Un cinquième geste, ajouté après coup :** relire **nos propres `docs/`**
avec la question amont en tête. Les quatre gestes ci-dessus regardent
dehors ; celui-là regarde dedans, et c'est lui qui a fait apparaître A10.
Un constat amont ne prend pas toujours la forme d'un contournement dans le
code : il peut prendre celle d'un document écrit pour soi, sans voir qu'il
répondait à une question posée dehors.

Ce qu'il faut en retenir pour la suite : **le dépôt amont est une source
de vérité consultable en quelques minutes**, et nous ne l'avions jamais
consulté. Les six constats du registre vivaient dans nos commentaires de
code depuis des mois. Refaire ce geste avant chaque montée de version de
référence — c'est le bon moment, puisque c'est là que les `.pyi` changent.

### Limite assumée de cette passe

Rien n'a été **exécuté** : ce conteneur n'a pas FreeCAD. Tout ce qui est
marqué ✅ ci-dessus est vérifié *sur la source*, ce qui suffit pour
« l'API existe / n'existe pas », et tout ce qui est marqué ⚠️ attend un
selftest sur la machine de développement. Les deux tests qui manquent
tiennent en quelques lignes chacun :

- **A7** : `ElementMapSize` et `Tag` non nuls sur un `PartDesign::Pad`
  après recompute, et aller-retour
  `getElementMappedName` → `getElementIndexedName` stable à travers un
  changement de cote.
- **A4/A5** : rejouer la vue en coupe de `make_drawing` sur 1.1.3 **sans**
  nos deux contournements, et voir ce qui tombe. Écrit depuis :
  [`scripts/spike-techdraw-coupe.py`](../scripts/spike-techdraw-coupe.py),
  à lancer à la main — `freecadcmd scripts/spike-techdraw-coupe.py`, ou une
  sonde à la fois via `FREESOLID_SPIKE_PROBE=base-parallele|cut-surface-hide`.
  Après un crash, la dernière ligne de `spike-techdraw-coupe.txt` nomme la
  sonde qui a tué le processus.

