# Gestes des fonctions

Cette grille sert à repérer où les fonctions ne se comportent pas pareil. Pour chacune, elle dit si l'on peut rééditer après coup ce qu'on a choisi à la création, et si les gestes (aperçu, double-clic, menu « Modifier », barre de retour) sont les mêmes d'une fonction à l'autre.

État décrit : 2026-11-02, après #151 (« Modifier » au menu suit le double-clic), #153 (« Désactiver » suit le moteur) et la réédition des options de création (Extrusion, Enlèvement, Coque, Perçage, surfaces décalée et radiée). La grille vient de la lecture du code et des selftests, contrôlée par un relevé : ce que l'arbre dit de chaque ligne fabriquée par le selftest (`has_params`, 51 genres), et quelques gestes rejoués dans le navigateur. Ce qui n'a pas été tranché est marqué « à vérifier ».

Tenir la grille à jour : une fonction ajoutée ou corrigée met sa ligne à jour dans le même changement (et, si un écart disparaît ou apparaît, la section « Écarts, par thème »). Les références vont au fichier et à la fonction, jamais à une ligne. « Écart n° N » renvoie au tableau de `docs/ecarts-solidworks.md`.

## Légende des colonnes

- **Aperçu à la création** : le fantôme jaune pendant que le panneau est ouvert. « oui + flèche » : la flèche de profondeur dans la vue en plus.
- **Réédition : ce qui revient** : ce que le double-clic (ou « Modifier ») permet de changer.
- **Ne revient pas** : ce qui a été choisi à la création et qu'on ne peut plus changer sans supprimer et refaire.
- **Aperçu à la réédition** : le fantôme jaune pendant la réédition. « — » : rien à rééditer.
- **Barre de retour** : la fonction se pose sur la barre et recule avec elle. « oui (drapeau) » : surface ou esquisse libre, qui se masque par drapeau au lieu de passer par le Tip du corps.
- **Selftest de réédition** : un test de bout en bout de `engine/selftest/` réédite la fonction. « non » : aucun trouvé.

« Modifier » au menu n'est pas une colonne : depuis #151, il est proposé exactement quand le double-clic rouvre quelque chose (`app/editkind.js`), donc quand la colonne « Réédition » dit autre chose que « rien ». « Désactiver » et « Masquer » non plus : leurs écarts sont dans la section des écarts, car ils tiennent à des règles du menu et non à la fonction.

## Volumes

| Fonction | Aperçu à la création | Réédition : ce qui revient | Ne revient pas | Aperçu à la réédition | Barre de retour | Selftest de réédition |
|---|---|---|---|---|---|---|
| Extrusion | oui + flèche | le panneau de la création : condition de fin (sauf passer à « jusqu'à la face » ; borgne seulement pour le premier volume d'un corps), décalage, inverser, dépouille, direction 2 (condition, profondeur, dépouille), épaisseurs et côté de la paroi mince, contours, corps fondus (une case par corps) | face d'arrivée, activer la paroi mince ou en changer le genre, esquisse, « Fusionner » et le corps de la fonction | oui + flèche (la flèche s'efface quand le sens ou la condition change) | oui | oui (conditions, direction 2, paroi mince, extrémités fermées, corps fondus) |
| Enlèvement extrudé | oui + flèche | comme l'Extrusion, sans les corps fondus | comme l'Extrusion, et les corps creusés | oui + flèche | oui | oui (à travers tout, borgne, refus de « jusqu'à la face », corps creusés qui suivent la cote) |
| Révolution | oui | angle, axe, inverser, plan médian, contours, corps fondus | esquisse, « Fusionner » et le corps de la fonction | oui | oui | oui (axe, plan médian, corps fondus) |
| Enlèvement de révolution | oui | comme la Révolution, sans les corps fondus | comme la Révolution, et les corps creusés | oui | oui | non (seule la Révolution est testée) |
| Perçage | oui | le panneau de la création sans les positions : type (simple, lamage, fraisage), cotes du type, angle du fraisage, à travers ou borgne, profondeur | positions, face et corps creusés | oui | oui | oui (type, condition de fin) |
| Lissage | oui | rien | tout : profils et ordre, soustractif, lissage droit, boucle fermée, « Fusionner », les corps fondus ou creusés | — | oui | non |
| Balayage | oui | rien | tout : profil, trajectoire, soustractif, « Fusionner », les corps fondus ou creusés | — | oui | non |
| Hélice | oui | pas, hauteur, angle | esquisse profil | oui | oui | non |
| Texte | oui | texte, taille, profondeur, position | face d'appui, relief ou gravure, police | non | oui | oui |

## Habillage, Combiner et références

| Fonction | Aperçu à la création | Réédition : ce qui revient | Ne revient pas | Aperçu à la réédition | Barre de retour | Selftest de réédition |
|---|---|---|---|---|---|---|
| Congé | oui + bulle de rayon | rayon | arêtes ou face | oui, sans la bulle | oui | oui (rayon) |
| Chanfrein | oui | type, taille, taille 2, angle, sens | arêtes ou face | oui | oui | oui |
| Chanfrein de sommet | oui | distances | le sommet | non | à vérifier (booléen, jusqu'à deux lignes) | oui |
| Coque | oui | épaisseur, « vers l'extérieur » | faces à ouvrir | oui | oui | oui (sens, refus d'une coque trop épaisse) |
| Dépouille | oui | angle | face, plan neutre | oui | oui | non |
| Combiner | non, voulu | rien | opération, corps outil | — | oui | non |
| Supprimer des corps | non | complète : corps ou solides cochés, ôter ou garder | rien | non | oui (drapeau) | oui |
| Plan de référence | oui + fantôme | rien | appui, décalage, angle | — | non (d'après le code, à vérifier) | non |
| Axe de référence | non | rien | tout | — | non (d'après le code, à vérifier) | non |
| Point de référence | non | rien | tout | — | non (d'après le code, à vérifier) | non |
| Repère | non | rien | tout | — | non (d'après le code, à vérifier) | non |

## Répétitions et graphe

| Fonction | Aperçu à la création | Réédition : ce qui revient | Ne revient pas | Aperçu à la réédition | Barre de retour | Selftest de réédition |
|---|---|---|---|---|---|---|
| Répétition linéaire, des fonctions | oui | distance, nombre, nombre en direction 2 (si déjà > 1) | fonctions répétées, direction, inverser, pas ou longueur totale, activer la direction 2, distance en direction 2, corps concernés | oui, sans la flèche | oui | oui (nombre) |
| Répétition linéaire, des corps | oui | distance, nombre, direction 2 (distance et nombre, si déjà créée) | corps répétés, direction, inverser, pas ou longueur totale, ajouter la direction 2, copies sautées | oui | oui | oui (nombre, distance) |
| Répétition circulaire, des fonctions | oui | angle total, nombre | fonctions répétées, axe, inverser, corps concernés | oui | oui | non |
| Répétition circulaire, des corps | oui | angle total, nombre | corps répétés, axe, inverser | oui | oui | non |
| Symétrie, des fonctions | oui | rien | tout : plan, fonctions, corps concernés | — | oui | non |
| Symétrie, des corps | oui | rien | tout : plan, corps | — | oui | non |
| Fonction graphe, solide (ajout, enlèvement) | non | le graphe, dans l'éditeur de graphe | ajout ou enlèvement, nature solide ou courbe | non | oui | oui |
| Fonction graphe, courbe ou surface | non | le graphe, dans l'éditeur de graphe | nature courbe ou surface | non | oui (drapeau) | oui |
| Répétition variable | non | nombre d'instances et graphe, dans l'éditeur de graphe | fonctions répétées, ajout ou enlèvement | non | oui | oui |

## Surfaces

| Fonction | Aperçu à la création | Réédition : ce qui revient | Ne revient pas | Aperçu à la réédition | Barre de retour | Selftest de réédition |
|---|---|---|---|---|---|---|
| Surface extrudée | non | longueur | esquisse, sens | à vérifier | oui (drapeau) | oui |
| Surface de révolution | non | angle | esquisse, axe, sens | à vérifier | oui (drapeau) | non |
| Surface lissée | non | rien | tout : profils et ordre | — | oui (drapeau) | non |
| Surface cousue | non | rien (forme figée) | tout : liste des surfaces | — | oui (drapeau) | non |
| Épaissir | non | épaisseur (signée) | surface source | à vérifier | oui (drapeau) | non |
| Couper avec une surface | oui | inverser le côté, épaisseur (si bande) | surface outil, passage entre un côté et une bande | non | oui | oui |
| Surface plane | non | rien | esquisse du contour | — | oui (drapeau) | non |
| Surface balayée | non | rien | profil, trajectoire | — | oui (drapeau) | non |
| Surface décalée | non | distance et « inverser le côté », comme à la création | surface source | non | oui (drapeau) | non |
| Surface de remplissage | non | rien | contour, case « tangent » | — | oui (drapeau) | non |
| Surface frontière | non | rien | 2 à 4 courbes | — | oui (drapeau) | non |
| Surface radiée | non | distance et « vers l'intérieur », comme à la création (pilotée par une équation : la distance signée, dans le panneau des cotes) | contour | non | oui (drapeau) | non |
| Surface médiane | non, voulu | rien (forme figée) | tout : les deux faces ou toutes les parois, épaisseur | — | oui (drapeau) | non |
| Surface réglée | non | rien | les deux courbes | — | oui (drapeau) | non |

## Opérations sur surfaces et courbes

| Fonction | Aperçu à la création | Réédition : ce qui revient | Ne revient pas | Aperçu à la réédition | Barre de retour | Selftest de réédition |
|---|---|---|---|---|---|---|
| Diviser | non | rien | surface, courbe outil | — | oui (drapeau) | non |
| Remplacer la face (solide) | oui | rien | face, surface de remplacement | — | oui (Tip du corps) | non |
| Supprimer la face (solide) | oui | rien | liste de faces | — | oui (Tip du corps) | non |
| Supprimer la face (surface) | oui | rien | surface, faces | — | oui (drapeau) | non |
| Annuler l'ajustement | non | rien | surface, face | — | oui (drapeau) | non |
| Congé de surfaces | non | rayon | arêtes, surface de base, un rayon par arête | non | oui (drapeau) | oui |
| Aplatir | non | un panneau d'information, sans réglage | face, surface | — | oui (drapeau) | non |
| Forme libre | non | points poussés, hauteurs, rayon, bords fixes | surface source, face | non | oui (drapeau) | oui |
| Pôles | surcouche dans la vue | déplacements, pas de grille | surface source, face | non | oui (drapeau) | oui |
| Prolonger | non | distance, « tous les bords » | surface source, bord choisi | non | oui (drapeau) | oui |
| Ajuster | non | « garder l'autre partie » | outil, surface, point cliqué, ajustement mutuel | non | oui (drapeau) | oui |
| Courbe d'intersection | non | rien | les deux surfaces, option « avec le solide » | — | oui (drapeau) | non |
| Projeter une courbe | non | rien | esquisse, face cible, direction | — | oui (drapeau) | non |
| Hélice 3D | non | pas, hauteur, rayon, angle | axe, sens | non | oui (drapeau) | oui (pas) |
| Courbe composite | non | rien | liste des courbes ou arêtes | — | oui (drapeau) | non |
| Spline 3D | surcouche dans la vue | complète : points, type, fermée, liens, tangentes | rien | non | oui (drapeau) | oui |
| Esquisse 3D | à vérifier | complète | rien | non | oui (drapeau) | oui |

## Écarts, par thème

Du plus visible pour un utilisateur au moins visible.

### 1. Le menu « Modifier » et le double-clic se contredisaient

Corrigé par #151. Le menu proposait « Modifier » sur une vingtaine de fonctions sans réédition (Lissage, Balayage, Combiner, Symétrie, références, surfaces lissée, plane, balayée…), où le geste ne menait qu'au message « aucun paramètre numérique éditable ». Il le cachait sur des surfaces que le double-clic réédite (Forme libre, Pôles, Spline 3D, Esquisse 3D, Aplatir). Le menu de la vue 3D le proposait pour toute surface, figée ou non.

Maintenant le moteur dit dans l'arbre si une fonction a des cotes (`has_params`), et `app/editkind.js` répond, pour une ligne, quel éditeur le double-clic rouvre, ou aucun. Le double-clic, le menu de l'arbre et celui de la vue lisent cette même réponse.

Le relevé a trouvé en chemin trois fausses cotes : la `Length` du plan et de l'axe de référence (une taille d'affichage) et la `Height` de la projection (sans effet en mode « Edges »). Le double-clic ouvrait pour elles un panneau sans effet. Elles ne sont plus des cotes (`engine/equations.py`, `_NO_DIMENSIONS`).

Et une ligne qu'une répétition à corps concernés creuse dans un autre corps rouvre cette répétition : creusée par une symétrie, elle proposait « Modifier » pour rien. L'arbre dit maintenant si la répétition rouverte a des cotes (`edits_has_params`).

Reste : le menu de la vue 3D n'a ni Masquer ni Supprimer, que le menu de l'arbre a.

Où ça se décide : `app/editkind.js` ; `engine/equations.py` (`_has_params`, `_editable_props`) ; `app/contextmenu.js` (`canModifyMenuTarget`) ; `app/viewmenu.js`.

### 2. Désactiver et Masquer : les règles ne suivaient pas les fonctions

- **Désactiver proposé, refusé par le moteur** : Axe, Point et Repère de référence, Courbe composite et Supprimer la face d'une surface. Le menu n'excluait que le Plan, alors que le moteur ne désactive que les objets qui portent la propriété `Suppressed` (message « seule une fonction de volume se désactive »), et qu'aucun de ces genres (`PartDesign::Line`, `Point`, `CoordinateSystem`, `SubShapeBinder`) ne la porte dans FreeCAD 1.1.3. Corrigé par #153 : l'arbre dit si une ligne se désactive (`suppressible`), le menu le suit. Une ligne qu'une répétition creuse dans un autre corps ne se désactive pas seule : on désactive la répétition.
- **Objets cachés d'une fonction** : ils se désactivent avec elle. La cavité d'une paroi mince fermée restait active et creusait le corps (une paroi tournée vers la matière y laissait son vide) ; le combiner caché d'un volume qui fond plusieurs corps les rend quand on le désactive. Corrigé par la fusion de plusieurs corps (`set_suppressed`).
- **Ce qui ne se désactive pas** : tout ce qui n'est pas une fonction de corps PartDesign. Les surfaces (y compris Épaissir, dont le résultat est un solide), les références, le réseau de corps, la Suppression de corps. Les modeleurs courants désactivent tout : il faudrait un mécanisme à FreeSolid, comme le drapeau qui fait reculer les surfaces avec la barre de retour.
- **Fonctions graphe, Répétition variable, Texte** : le menu propose « Désactiver » quand le moteur l'accepte ; l'effet sur la pièce reste à vérifier (le corps outil caché du Texte, par exemple).
- **Masquer** : il manquait à la Courbe composite et à Supprimer la face d'une surface, dont le genre (`binder`) n'était pas dans la liste des surfaces. Corrigé par #151 : toute ligne du dossier des surfaces se masque. Les fonctions de corps ne se masquent pas (seuls les corps et les surfaces du premier niveau).

Où ça se décide :

- `engine/tree.py` (`entry`) et `engine/surfacefeat/commun.py` (`_surface_tree_entry`) : le champ `suppressible` ;
- `engine/docprops.py`, `_is_suppressible` (la règle), `set_suppressed` et `set_hidden` ;
- `app/contextmenu.js`, `isSuppressibleTarget`, `isHideableTarget` et `openMenu` ;
- `app/typekeys.js` : la liste des genres, pour une ligne de plugin sans l'avis du moteur.

### 3. Fonctions sans aucune réédition

Un choix de création est définitif : il faut supprimer et refaire.

- **Volumes** : Lissage, Balayage.
- **Habillage et références** : Combiner, Axe, Point, Repère, Plan de référence.
- **Répétitions** : Symétrie des fonctions et des corps.
- **Surfaces** : lissée, plane, balayée, frontière, réglée, remplissage sans tangence.
- **Surfaces figées sans réédition** : cousue, médiane, remplissage tangent. Le moteur les recalcule déjà avec leurs sources (il garde ce qu'il faut sur chaque forme) : un panneau de réédition est possible, comme pour la Forme libre.
- **Opérations** : Diviser, Annuler l'ajustement, Courbe d'intersection, Projeter, Courbe composite, Supprimer la face (surface), Remplacer et Supprimer la face du solide.

Une même fonction change de comportement selon un choix : le Remplissage est paramétrique sans tangence, figé avec. Le choix « tangent » change la rééditabilité sans le dire.

Où ça se décide : `app/tree.js`, `editSurface` (aiguille par genre de surface) et `editFeature` (branches dédiées : Révolution et son enlèvement, Chanfrein, Chanfrein de sommet, Texte, Couper avec une surface, Supprimer des corps ; le reste tombe sur `get_params`) ; `engine/equations.py` (`_EDITABLE_PROPS`, liste blanche des cotes) ; `engine/vocab.py` (`PARAM_KEYS`) ; `engine/surfacefeat/commun.py` (ce qui est « figé »).

Contre-exemple à suivre : Supprimer des corps vient d'être rendu rééditable (panneau de la création rouvert, corps cochés selon ce qu'elle vise, réécrit sur place sans changer de rang).

### 4. Les sélections qui ne reviennent pas

Arêtes, faces, profils, corps, directions, outils : aucun ne se re-choisit.

- **Arêtes et faces** : Congé, Chanfrein, Coque (faces à ouvrir), Dépouille (face et plan neutre), Chanfrein de sommet (le sommet est repéré par son numéro), Perçage (positions et face), Texte (face d'appui).
- **Profils et esquisses** : Extrusion, Enlèvement, Révolution, Hélice, Surface extrudée, de révolution et plane. L'esquisse ne change plus après coup ; seuls les contours bougent. Pour les deux surfaces extrudée et de révolution, l'esquisse n'est même pas un choix à la création : le moteur prend la dernière esquisse libre, alors que la Surface plane et la Surface balayée préremplissent avec la sélection de l'arbre.
- **Corps et fonctions répétés** : fonctions répétées, corps répétés, corps concernés (écart n° 22, « Restent… »).
- **Direction** : axe, arête, inversion, pour les trois répétitions. Pas ou longueur totale, activation de la direction 2 : la deuxième direction n'apparaît à la réédition que si elle existe déjà.
- **Outils** : le corps outil de Combiner, la surface outil de Couper avec une surface, les deux surfaces de la Courbe d'intersection, l'esquisse source de Projeter.
- **Surfaces d'origine** : Surface décalée, Épaissir, Surface radiée, Forme libre, Pôles, Prolonger (bord), Ajuster (outil, point cliqué), Congé de surfaces (arêtes, un seul rayon pour toutes).
- **Indices de face ou d'arête** : si la source change de topologie, la fonction peut pointer sur autre chose. Aucun test de décalage d'indice trouvé (comportement à vérifier).

Où ça se décide : le panneau de réédition ne contient que les cotes (`app/tree.js`, `editFeature` ; `engine/equations.py`, `get_params` et `set_params`). Les sélections sont saisies par les panneaux de création (`app/features/habillage.js`, `repetitions.js`, `surfaces.js`, `combiner.js`, `volumes.js`) et le moteur ne sait pas les remplacer (`engine/ops/`). Piste : rouvrir le panneau de création rempli, comme `editRemoveBodies`.

### 5. Les options de création qui ne reviennent pas

Des réglages simples, parfois un seul booléen, présents à la création et absents à la réédition.

Corrigé pour quatre fonctions : leur double-clic rouvre le panneau de la création, rempli de ce que la fonction est.

- **Extrusion et Enlèvement** : condition de fin, décalage, inverser, dépouille, direction 2 et paroi mince (épaisseurs, côté). Le moteur envoie les conditions dans l'arbre (`extrude`, dans les mots de la création) et `set_params` les pose ensemble, sous les clés du formulaire. La cavité d'une paroi à extrémités fermées suit le plan milieu et refuse, comme à la création, une condition non borgne ou une dépouille.
- **Coque** : la case « vers l'extérieur » (clé `outward`). La garde de la création vaut aussi à la réédition : une coque vers l'intérieur qui n'évide rien est refusée.
- **Perçage** : type, condition de fin, angle du fraisage. Les cotes suivent le type : la profondeur seulement en borgne, le Ø de tête sans « Perçage » simple, la profondeur du lamage pour le lamage, l'angle pour le fraisage. FreeCAD remet les cotes de tête à ses valeurs quand le type change : le panneau les renvoie alors toutes.
- **Surface décalée et Surface radiée** : la case de sens de la création, au lieu du signe de la distance (voir thème 7).

Reste :

- **Extrusion et Enlèvement** : passer à « jusqu'à la face » ou changer de face (une sélection, thème 4), activer la paroi mince ou changer son genre (un, plan milieu, deux côtés), ce qui ajoute ou retire des profils cachés. Pour l'Extrusion, comme pour la Révolution, le Lissage et le Balayage, « Fusionner » et le corps où la fonction se range : les changer déplacerait la fonction d'un corps à l'autre, avec ce qui la suit. Les corps qu'elle fond se rééditent pour l'Extrusion et la Révolution : une case par corps, car un corps fondu ne se clique plus à part dans la vue.
- **Dépouille** : le plan neutre.
- **Texte** : relief ou gravure, police. Le relief est dans la forme des lettres et dans le genre du booléen : il faut reconstruire.
- **Couper avec une surface** : passer de « tout un côté » à « bande épaisse » change le genre de l'outil.
- **Fonctions graphe et Répétition variable** : ajout ou enlèvement, fonctions répétées, nature de la fonction.
- **Réédition partielle qui laisse croire à une réédition complète** : Congé de surfaces (rayon seul), Prolonger, Ajuster, Hélice 3D (ni axe ni sens), Forme libre.

Où ça se décide : `engine/equations.py` (`set_params`, `_editable_props`) ; `engine/solids.py` (`_extrude_state`, `_set_extrude_options`, `_hole_state`) ; `engine/extrude.py` (`extrude_state`, `extrude_options`) ; `engine/vocab.py` (`PARAM_KEYS`) ; `app/features/volumes.js` et `habillage.js` (panneaux partagés entre création et réédition) ; `app/tree.js` (`editFeature`) ; `app/editkind.js`.

### 6. L'aperçu absent ou inégal

- **À la création** : absent pour toutes les surfaces (sauf Couper avec une surface) et toutes les opérations sur surfaces et courbes (sauf Remplacer et Supprimer la face du solide, et Supprimer la face d'une surface), pour l'Axe, le Point et le Repère, pour les fonctions graphe et la Répétition variable. Les surfaces dont le résultat est le plus incertain (Ajuster, Diviser) sont celles sans aperçu. Deux absences sont voulues : Combiner (booléen lent) et la Surface médiane.
- **À la réédition** : absent pour le Texte, le Chanfrein de sommet, Couper avec une surface (le commentaire du code annonce l'aperçu, le panneau n'en branche pas), tous les panneaux d'édition des opérations sur surfaces (Prolonger, Ajuster, Congé de surfaces, Forme libre), Supprimer des corps, les fonctions graphe. La Répétition de corps passe par le même aperçu que les fonctions, sans le fantôme des seuls corps nouveaux de la création (à vérifier).
- **Surfaces** : la réédition par la voie générique redessine l'aperçu du corps seul. Pour une surface sans solide, il est probablement vide ou trompeur (à vérifier).
- **Bulle de rayon du Congé** : présente à la création, absente à la réédition.
- **Flèche de profondeur** : seulement pour l'Extrusion et l'Enlèvement. Ni Révolution, ni Perçage, ni Hélice, ni Surface extrudée.
- **Entrées du menu de la vue** : entrées dédiées pour l'Extrusion, l'Enlèvement et la Révolution seulement (écart d'accès, pas de réédition).

Où ça se décide : `app/main/featurepanel.js` (branche l'aperçu sauf `preview:false`, et la flèche) ; `app/features/*.js` (le drapeau `preview:false` de chaque entrée) ; `engine/ops/*.py` (`preview=True` de chaque opération) ; `app/tree.js` (un `onChange` par panneau de réédition) ; `app/main.js` (`showGhost`, qui ne dessine que le maillage du corps) ; `engine/directedit.py` (`_depth_editable`).

### 7. Le sens dit de plusieurs façons

- **Surface décalée, Surface radiée, Épaissir** : la décalée et la radiée ont maintenant la même case à la création et à la réédition (« Inverser le côté », « Vers l'intérieur »), et la radiée est libellée « Distance ». Épaissir n'a pas de case : le signe de l'épaisseur, aux deux moments. Une radiée dont la distance est pilotée par une équation garde le panneau des cotes, où le sens reste le signe.
- **Texte** : « Hauteur », « Décalage X/Y » à la création, « Taille », « X », « Y » à la réédition.
- **Hélice** : l'angle n'existe qu'à la réédition.
- **Dépouille** : libellé « Faces à dépouiller » au pluriel pour une seule face, alors que la Coque en accepte plusieurs.

Où ça se décide : `app/features/surfaces.js`, `habillage.js`, `volumes.js` (panneaux de création) ; `app/tree.js` (libellés de réédition, `PARAM_LABELS_BY_KIND` et le panneau Gravure) ; `engine/vocab.py` (`PARAM_KEYS`).

### 8. Barre de retour : des lignes qui n'y entrent pas comme les autres

- **Références** (Plan, Axe, Point, Repère) : ce ne sont pas des fonctions de l'historique. D'après le code, la barre ne les pose pas et « poser la barre ici » est refusé (« n'est pas une ligne d'historique »). À vérifier à l'exécution.
- **Chanfrein de sommet** : rangé comme un booléen (jusqu'à deux lignes, ajout puis intersection). Effet sur la barre : à vérifier.
- **Épaissir** : classée avec les surfaces (barre par drapeau) alors que son résultat est un solide ; Couper avec une surface est une fonction de corps (barre par le Tip). Pas d'écart de comportement constaté.
- **Cousue et Médiane** : si la barre recule au-dessus de leur base, le moteur saute la mise à jour sans le dire.
- **Remplacer et Supprimer la face du solide** : seules opérations de leur famille dans la chaîne du corps ; elles ne se masquent pas.
- **Ajustement mutuel** : deux lignes indépendantes, rééditer l'une ne touche pas l'autre.

Où ça se décide : `engine/tree.py` (`_history_role`, `set_tip`) ; `engine/kernel.py` (`_ROLLBACK_ROLES`) ; `engine/surfacefeat/commun.py` (`_refresh_frozen_shapes`) ; `engine/surfacefeat/solide.py` ; `engine/surfacefeat/prolonger.py`.

### 9. Le rejeu et la documentation

- **Rejeu** : `no_replay` est périmé pour l'Hélice. La raison dit « Pitch/Height hors whitelist », or ces deux cotes sont dans la liste de `get_params`. `engine/replay.py` la classe encore comme rejouable sous condition. Lissage, Balayage, Texte, Combiner, les trois répétitions de fonctions et de corps, les fonctions graphe, le Chanfrein de sommet, les références et la Spline 3D sont non rejouables, pour des raisons de fond. Ce que fait le rejeu d'une opération de surface (sans `replay` ni `no_replay`) : à vérifier.
- **Documentation** : `docs/ecarts-solidworks.md` décrit encore Extrusion, Enlèvement et Révolution comme sans conditions de fin ni axe, alors que d'autres lignes du même tableau disent « fait » ; il ne consigne aucun écart propre aux surfaces ni à l'habillage.

Où ça se décide : `engine/ops/volumes.py`, `habillage.py`, `references.py`, `surfaces.py`, `noeuds.py`, `repetitions.py` ; `engine/replay.py` ; `tests/` (le test de cohérence ne couvre que les opérations `add_*`).

### 10. La couverture du selftest

Aucune étape de réédition dans `engine/selftest/` pour : Enlèvement extrudé, Enlèvement de révolution, Lissage, Balayage, Hélice (volume), Dépouille, Combiner, Plan, Axe, Point, Repère, Répétition circulaire (fonctions et corps), Symétrie, Surface de révolution, décalée, radiée, Épaissir, et les opérations Diviser, Annuler l'ajustement, Courbe d'intersection, Projeter, Courbe composite, Remplacer et Supprimer la face. Les clés de quatre surfaces ne sont vérifiées que par un test unitaire (`tests/test_param_keys.py`). Ce qui n'a pas de réédition n'a pas de test de bout en bout ; que l'arbre et `get_params` disent la même chose est vérifié par l'étape p87, et le choix de l'éditeur par `tests/js/editkind.test.mjs`.

Aucun selftest ne vise la barre de retour ni Masquer sur les surfaces et courbes (la barre n'est testée que sur une surface générique, Masquer que sur des corps). Désactiver n'est pas testé fonction par fonction.

Où ça se décide : `engine/selftest/fonctions.py`, `document.py`, `surfaces.py`, `noeuds.py`, `esquisse.py` ; `tests/test_param_keys.py` ; `tests/js/` pour le côté interface.
