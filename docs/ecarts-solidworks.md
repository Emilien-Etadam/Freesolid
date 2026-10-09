# Écarts FreeSolid ↔ SolidWorks — relevé d'interface et de flux

Relevé du 2026-10-09, en clean-room : on a observé le comportement de
SolidWorks, sans en reprendre de code, d'icône, de nom ni de logo.

- **SolidWorks** : SOLIDWORKS Design Premium 2026 SP4.1, interface en
  anglais, gabarits en français (plans « Plan de face », etc.). Sur ce
  poste, le CommandManager est **ancré verticalement à gauche** (réglage de
  l'utilisateur ; la disposition par défaut est un ruban horizontal en haut).
  Aucun fichier n'a été enregistré : les documents d'essai (pièce,
  assemblage, mise en plan) ont été fermés avec « Don't Save ».
- **FreeSolid** : application de bureau installée (moteur FreeCAD 1.1.3),
  interface en anglais, comparée au code de `main` (v0.1.3).
- **Méthode** : le même geste a été fait dans les deux logiciels (esquisse
  sur le plan de face → rectangle → cote → bossage extrudé → congé), puis
  l'assemblage et la mise en plan ont été ouverts. Les références
  `fichier:ligne` renvoient au code FreeSolid.
- **Non observé en direct** (l'outil d'automatisation ne sait pas faire un
  glisser au bouton du milieu, et aucun fichier utilisateur n'a été ouvert) :
  la navigation au bouton du milieu dans SolidWorks et le PropertyManager
  des contraintes d'assemblage. Ces lignes sont marquées *(doc.)* : elles
  décrivent le comportement par défaut documenté de SolidWorks.

Priorités :

- **P1** : bloque ou piège un utilisateur SolidWorks dès les premières
  minutes.
- **P2** : gêne réelle, mais il existe un contournement.
- **P3** : finition.

---

## Suivi du lot « clone-sw »

Lot validé : tous les écarts P1 et P2, sauf la mise en plan interactive.
Les écarts simples sont confiés à Cursor : briefs dans
[`taches-cursor.md`](taches-cursor.md).
Ils sont traités du plus simple au plus gros, avec un commit par écart sur la
branche `clone-sw`. Le comportement de référence de SolidWorks vient de la
connaissance du logiciel et de l'aide officielle, reformulées.

| # | Écart | Prio | État |
|---|---|---|---|
| 1 | Titre de l'arbre « FeatureManager » → « Arbre de création » | P2 | fait |
| 2 | Vues standard Ctrl+2 / 3 / 6 / 8 | P2 | fait |
| 3 | Navigation souris (milieu, Ctrl+milieu, molette vers le curseur, cadre au bouton gauche) | P1 | fait : milieu = rotation, Ctrl+milieu = panoramique, Maj+milieu = zoom, molette vers le curseur (vers l'avant = zoom arrière, vérifié dans SolidWorks ; inversion dans Paramètres), Z / Maj+Z, cadre fenêtre ou capture (arêtes en 3D, entités en esquisse, Ctrl = ajouter). Clic milieu sur la pièce = centre de rotation (clic milieu dans le vide pour revenir au centre de la vue). En esquisse, le milieu fait du panoramique car la rotation y est bloquée |
| 4 | Couleurs d'état de contrainte de l'esquisse | P1 | fait : bleu = libre, clair = défini (le « noir » sur fond sombre), rouge = en trop ; état « sur-contrainte » dans la barre d'état ; textes d'état traduits |
| 5 | Préfixe d'état (-) / (+) et esquisse en cours dans l'arbre | P2 | fait |
| 6 | « Quitter » l'esquisse annule vraiment | P2 | fait : op moteur sketch_cancel (transactions défaites + instantané de la géométrie) |
| 7 | Coin de confirmation ✓/✗ dans la vue | P2 | fait : agit sur la commande ouverte, sinon sur l'esquisse (fermer / quitter sans garder) |
| 8 | Barre d'espace : boîte d'orientation | P2 | fait : 6 vues en croix, iso / dimétrique / trimétrique, Normal à, épingle ; dispositions une, deux (dessus-dessous ou côte à côte) et quatre fenêtres, chacune sa caméra, un clic ou la molette active une fenêtre |
| 9 | Origine dans l'arbre et dans l'esquisse ; volumes visibles en esquisse | P2 | fait : origine (ligne de l'arbre, trièdre, repère d'esquisse) ; la pièce reste visible en esquisse (Q1 tranchée) |
| 10 | Cotation : saisie de la valeur à la pose, lignes d'attache et flèches | P1 | fait : boîte de saisie flottante à la pose et au double-clic (Entrée applique, Échap garde la mesure, « … » pour nom/expression) ; lignes d'attache, flèches, arcs d'angle ; cercle coté au diamètre (Ø), arc au rayon (R) |
| 11 | Retour pendant le tracé (inférences, symboles de relations) | P2 | fait : lignes d'inférence (alignement sur les points existants, H/V de la chaîne), point accroché en évidence, lecture longueur / angle / dimensions près du curseur, symboles de relations sur la géométrie |
| 12 | Barre S (la spline quitte la touche S) | P2 | confié à Cursor (T12) |
| 13 | Menu et barre contextuels dans la vue | P1 | fait pour le menu : clic droit sur face, arête, esquisse, surface ou vide, et en esquisse (app/viewmenu.js, testé) ; barre d'icônes contextuelle au clic gauche sur face, arête ou esquisse |
| 14 | Barre tête haute : styles d'affichage, masquer/afficher, orientation | P2 | fait : ombré, filaire, lignes cachées, visibilité mémorisée |
| 15 | Réordonner l'arbre par glisser-déposer | P2 | fait : glisser une fonction (avec ses esquisses) ; refus clair si elle passerait avant ce dont elle dépend ; l'arbre suit l'ordre du corps |
| 16 | Arbre accessible pendant une commande | P2 | fait : volet repliable en haut à gauche de la vue, mêmes clics que l'arbre |
| 17 | Barre de menus | P2 | fait : six menus, raccourcis, survol, Échap |
| 18 | Chanfrein distance-angle | P2 | fait : distance égale, deux distances, distance et angle, inversion des côtés, réédition |
| 19 | Extrusion et enlèvement : conditions de fin, direction 2, dépouille, paroi mince | P2 | fait : borgne, jusqu'au suivant, jusqu'au dernier / à travers tout, jusqu'à la face (+ décalage), plan milieu, deuxième direction, dépouille (vers l'intérieur ou l'extérieur), paroi mince (un côté, plan milieu, deux côtés ; profil fermé ou ouvert ; épaisseurs rééditables). Reste (P3) : extrémités fermées d'une paroi mince sur profil fermé |
| 20 | Révolution : choix de l'axe | P2 | fait : axe vertical, ligne de construction, axes d'origine, plan milieu, réédition |
| 21 | Congé : aperçu corrigé, bulle de cote dans la vue | P2 | confié à Cursor (T21) |
| 22 | Répétitions : choix des fonctions et de la direction | P2 | fait : fonctions choisies dans l'arbre (plusieurs), direction par axe d'origine ou arête droite, pas ou longueur totale, inversion ; idem pour la symétrie (fonctions) |
| 23 | Ouvrir / Enregistrer : dialogue de fichiers | P2 | confié à Cursor (T23) |
| 24 | Accueil et Nouveau (Ctrl+N) | P2 | confié à Cursor (T24) |
| 25 | Assemblage : contraintes standard | P1 | fait : coïncidente, concentrique, parallèle, perpendiculaire, tangente, distance, angle, verrouillage, option « opposé » ; traduites en liaisons natives (distance nulle, cylindrique…) |
| 26 | Assemblage : insertion guidée, fixe/flottant, déplacement à la souris | P2 | fait : insertion enchaînée après « Nouvel assemblage » (premier composant fixé), Fixer / Libérer au clic droit, glisser d'un composant libre dans le plan de l'écran. Le choix du fichier passera par le dialogue de T23 |
| 27 | Interface anglaise sans texte français (demande du 2026-10-09) | P1 | fait : textes interpolés passés par t(), libellés de panneaux, noms moteur (pièce, corps, plans, combiner) |

### Questions de conception en attente

- **Q1 — Volumes pendant l'esquisse.** SolidWorks laisse la pièce visible
  pendant l'édition d'une esquisse ; FreeSolid la masque, par un choix
  explicite antérieur (ticket P023, vérifié par le test smoke `4e`).
  Faut-il revenir sur P023 et afficher la pièce (éventuellement estompée) ?
  **Réponse (2026-10-09) : oui.** La pièce reste visible, le smoke `4e` le
  vérifie désormais.
- **Q2 — Vocabulaire de commandes.** `engine/vocab.py` reprend des noms de
  commandes propres à SolidWorks (« Extruded Boss/Base », « Hole Wizard »…).
  Faut-il les neutraliser pour rester clean-room ?
  **Réponse (2026-10-09) : oui.** Termes génériques partout (moteur, ruban,
  panneaux, menus, traductions) : Extrusion / Extrude, Enlèvement extrudé /
  Extrude Cut, Révolution / Revolve, Balayage / Sweep, Lissage / Loft,
  Perçage / Hole, Réseau linéaire / circulaire, Cotation, Décaler,
  Projeter les arêtes, Contrainte / Constraint, Coudre / Sew. Les documents
  déjà enregistrés gardent leurs libellés (ce sont les données de
  l'utilisateur).

---

## 1. Accueil / nouveau document

| Élément | SolidWorks | FreeSolid | Écart | Prio |
|---|---|---|---|---|
| Écran d'accueil | Fenêtre « Welcome » (Ctrl+F2), onglets Home / Recent / Learn / Alerts. Boutons New Part, Assembly, Drawing, Advanced…, Open. Vignettes des documents récents, dossiers récents, ressources, astuce du jour. | Aucun. La vue 3D est vide et l'arbre affiche « — no document — ». | Pas d'accueil, pas de fichiers récents. | P2 |
| Nouveau (Ctrl+N) | Dialogue Pièce / Assemblage / Mise en plan, avec un mode Avancé qui donne accès aux gabarits. | Le bouton « Nouvelle pièce » crée une pièce directement (`main.js:4652`). L'assemblage se crée depuis l'onglet Assembly. Pas de Ctrl+N. | Pas de choix du type ni de gabarit, pas de raccourci. | P2 |
| Ouvrir / Enregistrer | Dialogues de fichiers Windows avec filtres de type. | `window.prompt` dans lequel on tape un chemin (`main.js:4957`, `4991`, `5002`). | Il faut connaître le chemin par cœur. | P2 |
| Démarrage implicite | Il faut un document pour esquisser. | Le bouton Esquisse crée une pièce s'il n'y en a pas (`main.js:4792`). | Plus permissif. Ce n'est pas un défaut. | — |

## 2. Interface générale

### CommandManager (ruban)

| Élément | SolidWorks | FreeSolid | Écart | Prio |
|---|---|---|---|---|
| Onglets | Features, Sketch, Surfaces, Sheet Metal, Mold, Direct Editing, Evaluate, MBD, Add-ins… L'onglet affiché s'adapte au contexte : il passe sur Sketch quand on entre en esquisse. | Features, Sketch, Surfaces, Assembly (`ribbon.json`). La bascule vers Sketch en esquisse fonctionne. | Pas d'onglet Évaluer : Mesurer et Équations sont dans la topbar. | P3 |
| Barre de menus | File, Edit, View, Insert, Tools, Window, plus un menu épinglable. Chaque commande y est accessible : Insert › Features › Fillet/Round…, etc. | Aucune barre de menus, seulement une topbar d'icônes (`index.html:646`). | Le chemin « par les menus » qu'utilise un habitué de SolidWorks n'existe pas. | P2 |
| Recherche de commandes | Champ « Search Commands », aussi intégré à la barre S. | Absent. | — | P3 |
| Bouton « Self-test » | — | Visible dans la topbar de l'application installée. | Outil de développement exposé à l'utilisateur. | P3 |

### FeatureManager (arbre)

| Élément | SolidWorks | FreeSolid | Écart | Prio |
|---|---|---|---|---|
| Contenu d'une pièce neuve | Part1 (configuration), History, Sensors, Annotations, Material, les trois plans, Origine. Puis Solid Bodies(n) dès qu'il y a un corps. | Solid Bodies, Surface Bodies, Equations, puis les trois plans. **Pas d'Origine** (`main.js:2108`), pas de Material, Annotations ni History. | L'origine ne peut être ni sélectionnée ni référencée depuis l'arbre. | P2 |
| État de l'esquisse dans l'arbre | « (-) Sketch1 » quand elle est sous-contrainte, « (+) » quand elle est sur-contrainte. L'esquisse apparaît dès qu'on l'ouvre. | Pas de préfixe d'état. L'esquisse en cours n'apparaît pas dans l'arbre pendant l'édition. | — | P2 |
| Barre de reprise | Oui, glissable. | Oui, glissable, avec menu « Amener la barre ici » (`main.js:1932`). | Équivalent. | — |
| Renommer | Clic lent ou F2, édition en place. | Menu contextuel puis `prompt()` (`main.js:2410`). | — | P3 |
| Réordonner | Glisser-déposer d'une fonction. | Absent. | — | P2 |
| Arbre déroulant en surimpression | Pendant un PropertyManager, l'arbre reste accessible en surimpression dans la vue (fil d'Ariane en haut à gauche). | Le panneau remplace l'arbre, qui n'est plus accessible. | On ne peut pas choisir une fonction ou un plan dans l'arbre pendant une commande. | P2 |

### PropertyManager

| Élément | SolidWorks | FreeSolid | Écart | Prio |
|---|---|---|---|---|
| Structure | Titre, ✓, ✗, œil (aperçu détaillé), aide « ? ». Groupes repliables, zones de sélection en bleu clair, message d'aide sur fond jaune quand il manque une sélection (« Select: a plane… or an existing sketch »). | Titre, ✓, ✗, groupes repliables, zones de sélection (`panel.js:169`). | Pas de message d'aide jaune, pas de bouton d'aide, pas de bascule d'aperçu. | P3 |
| Clavier | Échap annule la commande (observé : Échap a annulé l'extrusion). Entrée dans un champ numérique applique la valeur sans fermer. | Échap annule. **Entrée dans un champ valide la fonction** (`panel.js:85`). | Un utilisateur SolidWorks qui tape 20 puis Entrée pour voir l'aperçu valide la fonction sans le vouloir. | P3 |
| Langue | — | Interface en anglais, mais certains titres de groupes et libellés sont en français : « Paramètres du congé », sélection « Arête 9 ». | Couverture i18n incomplète. | P3 |

### Coin de confirmation, barre tête haute, barre d'état

| Élément | SolidWorks | FreeSolid | Écart | Prio |
|---|---|---|---|---|
| Coin de confirmation ✓/✗ | En haut à droite de la vue, pendant toute commande et en esquisse (sortir de l'esquisse / annuler). | **Absent.** Le ✓/✗ est seulement dans le panneau. | Le geste « valider en haut à droite » ne fait rien. | P2 |
| Barre d'affichage tête haute | Zoom ajusté, zoom fenêtre, vue précédente, vue en coupe, orientation (menu déroulant), style d'affichage (ombré avec arêtes, filaire…), masquer/afficher, apparence, scène, paramètres de vue. | Iso, Face, Dessus, Droite, Zoom au mieux, Coupe, Graphe (`index.html:729`). | Pas de styles d'affichage (filaire, arêtes cachées), pas de menu d'orientation, pas de masquer/afficher. | P2 |
| Barre S | La touche S ouvre, sous le curseur, une boîte d'outils contextuelle et un champ de recherche de commandes. | Hors esquisse : rien. En esquisse : S lance la **spline** (`sketch.js:1097`). | Conflit de réflexe : S trace une spline au lieu d'ouvrir la boîte. | P2 |
| Barre d'état | Coordonnées du curseur (x, y, z), longueur de l'entité sélectionnée, état « Under Defined / Fully Defined », « Editing Sketch1 / Editing Part », unités MMGS. | Message, élément survolé, MMGS en dur. L'état de l'esquisse s'affiche en français (« Esquisse : sous-contrainte (4 DDL) ») alors que l'interface est en anglais. | Pas de coordonnées, pas de longueur, pas d'indication du mode d'édition. | P3 |
| Menu contextuel dans la vue | Clic droit sur une face : barre contextuelle d'icônes (modifier la fonction, modifier l'esquisse, esquisse, normal à, masquer, apparence…), puis sections Face / Fonction / Corps. Le simple clic gauche affiche aussi une barre contextuelle. | **Aucun.** Le clic droit sélectionne la face, sans menu. Le seul menu contextuel est celui de l'arbre (`main.js:2392`). | Tout le flux « clic sur la géométrie → action » manque. | **P1** |

## 3. Esquisse

| Élément | SolidWorks | FreeSolid | Écart | Prio |
|---|---|---|---|---|
| Entrée en esquisse | Clic sur un plan, barre contextuelle, Esquisse. La vue tourne normal au plan, le plan et l'origine (en rouge) s'affichent. | Esquisse, puis clic sur le plan dans l'arbre ou dans la vue. Vue normale au plan, rotation bloquée (`sketch.js:1526`). | Pas d'origine dessinée. **Les volumes sont masqués pendant l'esquisse** (`main.js:2485`). | P2 |
| Défaut d'affichage | — | À l'invite « choisir un plan », les étiquettes « Plan de dessus » et « Plan de droite » se superposent et deviennent illisibles. | — | P3 |
| Outils | Chaque outil ouvre un PropertyManager avec ses variantes (rectangle par coins, par centre, 3 points, parallélogramme ; coordonnées éditables ; lignes de construction). | Outils en bouton direct, sans panneau ni paramètres (`index.html:666`). | Pas de saisie numérique pendant le tracé. | P3 |
| Retour pendant le tracé | Coordonnées affichées au curseur, lignes d'inférence pointillées, symboles de relations ajoutées automatiquement (H, V, coïncidence), contour fermé ombré. | Accrochage aux extrémités et H/V (`sketch.js:163`), **mais rien n'est dessiné** : ni ligne d'aide, ni symbole, ni coordonnées, ni ombrage. | L'utilisateur ne voit pas les relations qu'il crée. | P2 |
| **Couleurs d'état de contrainte** | Bleu : sous-contraint. Noir : totalement contraint. Rouge ou jaune : sur-contraint ou en conflit. | Une seule couleur pour tout (`sketch.js:50`). Le texte d'état est dans la barre d'état, et il n'y a pas de cas « sur-contrainte ». | Le repère visuel principal de SolidWorks manque. | **P1** |
| **Cotation intelligente** | On clique l'entité, on place la cote, et **la boîte « Modify » s'ouvre sous le curseur** : on tape la valeur et la géométrie se met à jour. La cote a lignes d'attache et flèches. Un double-clic sur la cote la rouvre. Diamètre sur un cercle. | La cote est posée **à la valeur actuelle, sans boîte de saisie** (observé : « 43.74 »). Pour la changer, double-clic, puis panneau latéral (`dims.js:37`). La cote s'affiche comme une étiquette, sans lignes ni flèches. Rayon seulement sur un cercle (`kernel.py:4925`). | Le geste « coter = saisir la valeur » est cassé. | **P1** |
| Relations | Ajout par sélection puis PropertyManager « Add Relations », qui ne propose que les relations valides pour la sélection. Affichage et suppression des relations. | 12 relations dans le ruban, toujours affichées (`index.html:692`). Panneau Relations pour l'entité sélectionnée. | Pas de filtrage selon la sélection. | P3 |
| Sortie d'esquisse | Coin de confirmation (sortir / annuler), ou icône de sortie dans la barre S ou le CommandManager. | Boutons Terminer / Quitter dans le ruban. « Quitter » ne restaure pas l'état côté moteur (`sketch.js:1588`). | Annuler une esquisse ne l'annule pas vraiment. | P2 |

## 4. Fonctions volumiques

| Élément | SolidWorks | FreeSolid | Écart | Prio |
|---|---|---|---|---|
| Lancement | Sélection préalable (esquisse ou arête) acceptée. Sinon, message d'aide et sélection pendant la commande. | Pré-sélection acceptée (congé sur arête pré-sélectionnée observé). | Équivalent. | — |
| Bossage extrudé | « From » (plan d'esquisse, surface, sommet, décalage). Direction 1 : Blind, Up To Vertex, Up To Surface, Offset From Surface, Up To Body, Mid Plane (relevé). Dépouille, Direction 2, Thin Feature, Selected Contours. La vue passe en trimétrique, flèche de glissement, aperçu jaune. | Blind, Mid Plane, Reverse direction (`features.js:190`). Aperçu jaune. La vue ne bouge pas, il n'y a pas de poignée. | Manquent : jusqu'à la surface ou au sommet, direction 2, dépouille, paroi mince, contours sélectionnés, poignée de glissement. | P2 |
| Enlèvement extrudé | Mêmes conditions, plus Through All. | Through All, Blind, Reverse (`features.js:219`). | Mêmes manques. | P2 |
| Révolution | Axe choisi (ligne d'esquisse, arête, axe), deux directions, paroi mince. | Un angle, autour de l'axe vertical de l'esquisse (`features.js:119`). | Axe non choisissable. | P2 |
| Congé | Onglets Manual / FilletXpert. Types : constant, variable, de face, arrondi complet. Propagation tangente, aperçu complet / partiel / aucun. Symétrique ou asymétrique, multi-rayons, profil circulaire ou conique. Bulle de cote éditable dans la vue (« Radius: … »). | Rayon constant, arêtes ou face (`features.js:430`). Aperçu : **la face arrondie n'est pas rendue** (bande sombre, observé) ; le résultat final est correct. | Pas de bulle de cote dans la vue, pas de propagation tangente explicite, défaut d'aperçu. | P2 |
| Chanfrein | Distance-distance, distance-angle, sommet. | Une distance (`features.js:447`). | — | P2 |
| Coque | Plusieurs faces, épaisseurs multiples, vers l'extérieur. | Une face, une épaisseur (`features.js:464`). | — | P3 |
| Répétitions | On choisit les fonctions, faces ou corps à répéter. Direction donnée par une arête ou une cote ; instances à sauter. | **Seulement sur la dernière fonction.** Axe X/Y/Z pour le linéaire, axe Z pour le circulaire (`features.js:499`). | On ne peut pas choisir ce qu'on répète. | P2 |
| Édition | Double-clic sur une face : affiche les cotes de la fonction, qu'on modifie en place. « Edit Feature » dans le menu contextuel. | Double-clic sur une face : cotes affichées. Double-clic sur une cote : édition (`main.js:1127`). | Proche. | — |

## 5. Navigation 3D

| Élément | SolidWorks | FreeSolid | Écart | Prio |
|---|---|---|---|---|
| **Souris** | *(doc.)* Molette appuyée : rotation. Ctrl + molette appuyée : panoramique. Molette : zoom **vers le curseur**. Maj + molette appuyée : zoom. Glisser gauche dans le vide : **sélection par cadre**. | Glisser gauche : **rotation** (observé). Glisser droit : panoramique. Molette : zoom vers le centre. `OrbitControls` sans réglage (`main.js:205`). Pas de sélection par cadre. | Tous les réflexes de la souris sont inversés, et la sélection par cadre est impossible. | **P1** |
| Barre d'espace | Boîte « Orientation » sous le curseur : croix des 6 vues, iso / dimétrique / trimétrique, normal à, dispositions de fenêtres (1, 2, 4), épingle (relevé). | Rien (observé). | — | P2 |
| Vues standard au clavier | Ctrl+1 à Ctrl+8 (Ctrl+7 = iso, relevé dans l'info-bulle). | Ctrl+1, 4, 5, 7 seulement (`main.js:1349`). | Manquent Ctrl+2 (arrière), 3 (gauche), 6 (dessous), 8 (normal à). | P2 |
| Zoom ajusté | F. | F, mais **inactif en esquisse** (`main.js:1351`). | — | P3 |
| Flèches du clavier | Flèches : rotation. Ctrl+flèches : panoramique. Alt+flèches : rotation dans le plan (astuce de l'écran d'accueil). | Absent. | — | P3 |
| Projection | Perspective ou orthographique, au choix. | Orthographique seule (`main.js:197`). | — | P3 |
| Spécification existante | — | `docs/navigation-spec.md` décrit la correspondance avec SolidWorks pour FreeCAD en amont, **mais elle n'est pas appliquée à l'application**. | La spécification existe, elle n'est pas branchée. | — |

## 6. Assemblage

| Élément | SolidWorks | FreeSolid | Écart | Prio |
|---|---|---|---|---|
| Création | Nouveau, Assemblage : le PropertyManager « Begin Assembly » s'ouvre tout seul, avec ouverture automatique du dialogue de fichiers. Liste des documents ouverts, aperçu, option « fixe ou flottant à l'insertion ». | Bouton « New assembly » dans l'onglet Assembly. | Pas de flux guidé d'insertion. | P2 |
| Insertion | Dialogue de fichiers ou documents ouverts. Placement du composant au clic. Le premier composant est fixé à l'origine. | Chemin `.FCStd` tapé dans un `prompt` (`main.js:4403`). Le premier composant est fixé. | Il faut saisir le chemin. | P2 |
| **Contraintes** | *(doc.)* Standard : coïncidente, parallèle, perpendiculaire, tangente, concentrique, verrouillage, distance, angle. Avancées : largeur, symétrique, trajectoire, limites. Mécaniques : came, rainure, charnière, engrenage, crémaillère, vis, joint universel. Menu « Mate » grisé tant qu'il n'y a pas de composant (relevé). | Liaisons cinématiques FreeCAD : Fixe, Pivot, Cylindrique, Glissière, Rotule, Distance, Engrenages, Crémaillère-pignon, Vis, Courroie (`main.js:4425`). Une face par composant. | **Pas de coïncidente, concentrique, parallèle ni d'angle** au sens de SolidWorks. Le vocabulaire et le modèle mental ne correspondent pas. | **P1** |
| Arbre | Composants avec préfixe (f) fixe ou (-) sous-contraint, puis le dossier « Mates » (« Contraintes » dans ce gabarit). | « Assemblage », les composants (« (fixé) »), puis les contraintes (`main.js:4319`). | Pas de bascule fixe / flottant. | P2 |
| Déplacer un composant | Glisser à la souris (translation), clic droit pour la rotation. Triade de déplacement. | Panneau numérique X/Y/Z et lacet / tangage / roulis (`main.js:4360`). | Pas de glisser direct. | P2 |

## 7. Mise en plan

| Élément | SolidWorks | FreeSolid | Écart | Prio |
|---|---|---|---|---|
| Création | Nouveau, Mise en plan : choix du format (A0 à A4, relevé), feuille avec cartouche (ici en français : auteur, matière, échelle, n° de plan…). Le PropertyManager « Model View » s'ouvre tout seul. Onglets de feuilles en bas. | Panneau d'export : chemin, échelle, cotes d'encombrement, coupe X/Y/Z facultative. Le résultat est **un fichier DXF** à 3 vues (`main.js:4152`, `kernel.py:1448`). | Pas de feuille interactive, de cartouche, de vues déplaçables, de cotes éditables, d'annotations ni de PDF. | **P1** pour qui produit des plans (chantier lourd) |

---

## Points clean-room relevés en passant

- Le titre de l'arbre est « FeatureManager » (`index.html:723`). C'est un
  nom de Dassault, comme « PropertyManager » et « CommandManager » employés
  dans les docs internes. À remplacer dans l'interface par un nom générique
  (« Arbre de création », par exemple). Dans la documentation interne, on
  peut les garder comme termes de comparaison. **P2**.
- « MMGS » (barre d'état) est l'abréviation SolidWorks du système d'unités.
  « mm · g · s » serait neutre. **P3**.

## Défauts propres à FreeSolid vus pendant le relevé

- Superposition des étiquettes « Plan de dessus » et « Plan de droite » à
  l'invite de choix du plan. P3.
- Aperçu du congé sans la face arrondie (bande sombre). Le résultat final est
  correct. P2.
- Textes français dans une interface réglée en anglais : état d'esquisse dans
  la barre d'état, « Paramètres du congé », « Arête 9 », « Ctrl+clic :
  ajouter ». Dans l'arbre, « Extruded Boss » voisine avec « Congé ». P3.

## Synthèse des P1

1. **Navigation souris** : milieu = rotation, Ctrl+milieu = panoramique,
   molette = zoom vers le curseur, gauche = sélection et cadre. (§5)
2. **Cotation intelligente avec saisie de la valeur à la pose** (boîte
   « Modifier »), puis lignes d'attache et flèches. (§3)
3. **Couleurs d'état de contrainte** de l'esquisse (sous-contraint,
   contraint, sur-contraint), et préfixe d'état dans l'arbre. (§3)
4. **Menu et barre contextuels** au clic sur la géométrie. (§2)
5. **Contraintes d'assemblage standard** : coïncidente, concentrique,
   parallèle, distance, angle. (§6)
6. **Mise en plan interactive**. (§7, chantier à part)
