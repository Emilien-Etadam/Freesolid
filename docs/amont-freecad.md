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
| Mise en plan TechDraw headless | **les deux** | question 3 — nos vues, leurs crashs (entrées **A4**, **A5**) |
| Suivi d'une référence de sous-élément à travers un recompute | **à trancher** | question 3 *si et seulement si* le spike montre que FreeCAD ne l'expose pas (entrée **A7**) |
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
| **MIT / BSD** | oui, avec attribution | **oui** (relicenciable en LGPL) | — |
| **Apache-2.0** | possible, mais fait passer l'ensemble distribué en LGPL-3.0 | **non** | [`vcad`](https://github.com/ecto/vcad) |
| **AGPL-3.0** | non — contaminerait FreeSolid entier | **non** | [Chili3D](https://github.com/xiangechen/chili3d) |

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

Nature : **bug** (comportement faux ou crash) · **API** (capacité absente
côté Python) · **doc** (comportement correct mais nulle part écrit) ·
**produit** (amélioration d'ergonomie ou de message) · **banc** (matière de
non-régression).

| # | Constat | Où c'est visible chez nous | Nature | État |
|---|---|---|---|---|
| **A1** | `freecadcmd` n'exécute pas un script avec `__name__ == "__main__"` — piège silencieux, non documenté | absence volontaire de garde dans `engine/server.py` ; expliqué dans `AGENTS.md` | doc | à formuler |
| **A2** | `UndoLimit` / `setMaxUndoStackSize` absents de l'API Python en 1.0.x — la pile C++ est bornée par défaut (20) sans moyen de la régler | `engine/kernel.py:311-322` (double `hasattr`), audit **2.4** | API | à revérifier sur 1.1.3 avant de formuler |
| **A3** | Joints d'assemblage headless : API instable entre 1.0.2 et 1.1.3 (`Proxy.setJointConnectors` absent en 1.0.2 → repli `Reference1`/`Reference2`), et forme d'argument piégeuse (« Expect input sequence of size 2 » selon l'emballage) | `engine/kernel.py:518-560` | doc + API | matière prête — spike de phase C déjà fait |
| **A4** | **TechDraw headless — deux crashs reproductibles.** ① `getSectionCS` : SIGSEGV quand la Direction de la vue de base est parallèle à la normale de coupe. ② `CutSurfaceDisplay=Hide` : SIGSEGV en 1.0.0 headless | `engine/kernel.py:1126-1136` (contournements en place) | **bug** | **le plus mûr du registre** — reproducteur à extraire |
| **A5** | TechDraw headless : la géométrie 2D d'une vue en coupe reste souvent vide (HLR sur le même thread) ; DXF est le seul export fiable | `engine/kernel.py:1166-1172` | doc | à formuler avec A4 |
| **A6** | Les échecs PartDesign les plus déroutants sont **corrects mais inexpliqués** — « multiple solids », « out of the allowed scope », « wire is not closed » : l'utilisateur apprend qu'il a échoué, pas pourquoi ni quoi faire | `engine/guard.py` — trois traductions écrites, testées unitairement | **produit** | **le plus abouti** : c'est notre code, LGPL-2.1-or-later, remontable tel quel — reste à en produire une version anglaise et à la proposer là où les messages sont émis |
| **A7** | Suivre une référence de sous-élément à travers un recompute avec un **verdict explicite** (résolu / ambigu / perdu) plutôt qu'une re-liaison silencieuse | `engine/replay.py`, analysé dans [`vcad.md`](vcad.md) §5.1 | API | 🟠 **spike d'abord** — la question amont n'existe que si FreeCAD 1.1 ne l'expose pas déjà |
| **A8** | Segfaults OCCT hors TechDraw | audit **2.12** | bug | seulement si un cas devient reproductible |
| **A9** | Grille de non-régression du noyau — stress booléen, aller-retour STEP, taux de succès des congés, convergence du solveur, qualité de tessellation | `scripts/run-selftest.py`, direction posée dans [`vcad.md`](vcad.md) §5.5 | banc | direction de fond : **chaque échec du banc est un rapport amont avec reproducteur** |

Deux lectures de ce tableau valent d'être notées :

- **Six entrées sur neuf existent déjà sous forme de contournement dans le
  code.** Elles n'ont rien coûté à découvrir — elles ont coûté à
  contourner, et ce coût est déjà payé. Les formuler en amont ne demande
  que d'extraire le reproducteur.
- **A6 est le cas d'école de la doctrine.** Personne n'a décidé
  d'améliorer FreeCAD : on a écrit `engine/guard.py` parce qu'un
  utilisateur de FreeSolid ne pouvait pas comprendre « multiple solids ».
  Le résultat est utile bien au-delà de nous, il est sous la bonne licence,
  et il est déjà testé. C'est exactement ce que la règle du §1 cherche à ne
  pas laisser perdre.

## 5. Comment on remonte

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
  Seule exception : A4 et A5 partent ensemble, même sous-système et même
  session de reproduction.
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
