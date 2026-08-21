# Spécification — style de navigation « SolidWorks » pour FreeCAD

**Statut : brouillon à valider par un utilisateur SolidWorks expert.**

## Pourquoi ce document

FreeCAD n'a pas de style de navigation SolidWorks. La demande a été posée en
amont ([discussion #18635](https://github.com/FreeCAD/FreeCAD/discussions/18635))
et un mainteneur a répondu : *documentez précisément les mouvements souris et
les combinaisons clavier, le code est dans `NavigationStyle.cpp`*. Personne
n'a fourni cette spécification ; la discussion a été fermée en décembre 2024
avec « rouvrez si vous avancez ».

Ce document est cette spécification. Une fois validée, elle se rouvre telle
quelle dans la discussion, et l'implémentation est quelques centaines de
lignes de C++ sur le modèle des styles existants (`BlenderNavigationStyle`,
`RevitNavigationStyle`…).

> **État amont revérifié le 2026-08-21 :** la discussion #18635 a bien été
> fermée le 2024-12-23 par luzpaz sur « *If you make progress feel free to
> re-open discussion* », après qu'il a pointé `src/Gui/NavigationStyle.cpp`
> et les styles existants comme modèles. **Personne n'a fourni la
> spécification demandée depuis.** La porte est donc toujours ouverte, et
> ce document est entré au registre amont sous l'entrée **A10** —
> [`amont-freecad.md`](amont-freecad.md) §4, où il est aujourd'hui le
> candidat le plus mûr. Il ne lui manque que l'étape 1 ci-dessous.

## Table de correspondance proposée

Chaque ligne est à confirmer ou corriger — les cases ☐ sont là pour ça.
Référence : SolidWorks, réglages souris par défaut.

| Action | Geste SolidWorks | Notes | Validé |
|---|---|---|---|
| Sélection | Clic gauche | | ☐ |
| Rotation | **Glisser bouton du milieu** | Le cœur du style | ☐ |
| Panoramique | **Ctrl + glisser milieu** | *La* différence avec le style Blender (Maj+milieu) | ☐ |
| Zoom | Molette | ⚠️ SolidWorks zoome **en arrière** en molette avant — sens inversé par rapport à FreeCAD. Prévoir l'option « inverser le sens » | ☐ |
| Zoom (glisser) | Maj + glisser milieu, vertical | | ☐ |
| Rotation dans le plan écran (roll) | Alt + glisser milieu | | ☐ |
| Centre de rotation | **Clic milieu sur une arête/face/sommet** : l'orbite s'ancre dessus | Comportement signature de SW, absent de tous les styles FreeCAD | ☐ |
| Zoom fenêtre | (SW : Maj+Z / commande dédiée) | À trancher : geste ou raccourci | ☐ |
| Zoom ajusté | F | | ☐ |
| Menu contextuel | Clic droit (relâché sans glisser) | | ☐ |
| Gestes souris | **Glisser clic droit** : rosace de gestes | Hors périmètre navigation stricte — à mentionner comme non-objectif dans la PR. **Implémentation de référence lisible** : [PartMode](https://github.com/BOMWiki/partmode) le fait en ~20 lignes (`studio-input-customization.js`) — quatre directions par comparaison de `|dx|` et `|dy|`, zone morte de 28 px, table figée nord/est/sud/ouest → isoler/éditer/supprimer/masquer. AGPL : l'idée, jamais le fichier | ☐ |
| Rotation par flèches | Flèches = orbite, Maj+flèches = 90°, Alt+flèches = roll | | ☐ |
| Sélection rectangulaire | Glisser gauche : gauche→droite = contenu, droite→gauche = traversant | Concerne la sélection, pas la caméra — probablement hors périmètre `NavigationStyle` | ☐ |

## Cas limites à spécifier

1. **Molette : zoom vers le curseur ou vers le centre ?** SolidWorks zoome
   vers le curseur. FreeCAD a un réglage global (« zoom at cursor ») — le
   style doit-il l'imposer ou le respecter ?
2. **Clic milieu sans géométrie sous le curseur** : SW garde le dernier
   centre d'orbite ou reprend le centre de la boîte englobante ?
3. **Pendant l'édition d'esquisse** : mêmes gestes, ou le pan passe-t-il en
   priorité ? (Dans SW, la molette et le pan restent identiques en esquisse.)
4. **Interaction avec la Space Mouse** : hors périmètre, géré par un autre
   canal dans FreeCAD.

## Étapes

1. ☐ Validation ligne à ligne de la table par un utilisateur SW quotidien.
2. ☐ Réponse aux quatre cas limites.
3. ☐ Réouverture de la discussion #18635 avec ce document.
4. ☐ Implémentation `SolidWorksNavigationStyle` (C++, `src/Gui/`), ou
   recherche d'un contributeur via le forum.

En attendant l'amont, FreeSolid règle la navigation sur le style Blender —
le plus proche existant (rotation au bouton du milieu ; seul le modificateur
du panoramique diffère).
