# Surfacique — périmètre et état

Ce document fixe **ce que « tout le surfacique » veut dire** pour FreeSolid :
la liste fermée des commandes de surfaces et de courbes qu'un modeleur
paramétrique de pièces de la classe de SolidWorks propose, et l'état de
chacune. Les noms sont les nôtres (vocabulaire générique de la CAO) ; rien
n'est repris de l'aide, des icônes ni des textes de l'éditeur.

## Critère « fait »

Une commande est **faite** quand les six points tiennent :

1. **Moteur** — une op JSON déclarée dans `engine/ops/surfaces.py`,
   annulable (`undo=True`), qui refuse proprement une entrée impossible (message
   traduit dans `engine/lang/en.json`).
2. **Interface** — un bouton du ruban (onglet Surfaces) avec icône
   originale, un panneau qui se remplit au clic dans la vue.
3. **Réédition** — double-clic dans l'arbre : les paramètres reviennent et
   la forme se reconstruit ; les formes figées sont recalculées à chaque
   reconstruction quand leur source change.
4. **Selftest** — au moins un indicateur dans `engine/selftest.py`
   (FreeCAD réel, CI).
5. **Smoke** — le bouton ouvre son panneau sans erreur console
   (`scripts/smoke/smoke.js`, CI).
6. **Clic** — le geste complet vérifié à la souris dans le navigateur.

## Surfaces

| Commande | État | Op moteur | Selftest |
|---|---|---|---|
| Surface extrudée (profil ouvert ou fermé) | ✅ | `surface_extrude` | `p12_surface_ok` |
| Surface de révolution | ✅ | `surface_revolve` | `p12_surface_revolve_ok` |
| Surface balayée (esquisse ou spline 3D) | ✅ | `surface_sweep` | `p46_balayage_suit_spline` |
| Surface lissée (plusieurs profils) | ✅ | `surface_loft` | `p12_surface_loft_ok` |
| Surface frontière (2 à 4 courbes) | ✅ | `surface_boundary` | `p48_surface_frontiere` |
| Surface de remplissage (contour quelconque, tangence G1, arête fermée) | ✅ | `surface_fill` | `p46_remplissage_*`, `p48_remplissage_tangent`, `p48_remplir_arete_fermee` |
| Surface plane | ✅ | `surface_planar` | `p46_surface_plane` |
| Surface décalée | ✅ | `surface_offset` | `p46_surface_decalee` |
| Surface radiée | ✅ | `surface_radiate` | `p50_surface_radiee` |
| Surface réglée | ✅ | `surface_ruled` | `p48_surface_reglee` |
| Surface médiane (deux faces, ou toute la pièce) | ✅ | `surface_mid` | `p50_surface_mediane` |
| Forme libre — points poussés (bosses, creux, bords fixes) | ✅ | `surface_freeform` (`pushes`) | `p50_forme_libre` |
| Forme libre — points de contrôle déplacés un à un, sur une ou plusieurs faces | ✅ | `surface_freeform` (`moves`), `surface_control_points` | `p50_forme_libre` |
| Aplatir (patron à plat, déformation mesurée) | ✅ | `surface_flatten` | `p50_aplatir` |

## Opérations sur les surfaces

| Commande | État | Op moteur | Selftest |
|---|---|---|---|
| Prolonger (un bord ou tous) | ✅ | `surface_extend` | `p46_prolonger_*` |
| Ajuster (standard et mutuel, partie gardée au clic) | ✅ | `surface_trim` | `p46_ajuster_*`, `p46_ajustement_mutuel` |
| Désajuster (bords naturels, trous bouchés) | ✅ | `surface_untrim` | `p48_desajuster` |
| Coudre (et solidifier une peau fermée ; suit ses sources) | ✅ | `surface_sew` | `p12_sew_ok` |
| Épaissir en solide | ✅ | `surface_thicken` | `p12_thicken_solid_ok` |
| Épaissir en enlevant (bande épaisse ôtée au solide) | ✅ | `add_surface_cut` (`thickness`) | `p50_epaissir_enlever` |
| Couper le solide avec une surface | ✅ | `add_surface_cut` | `p47_coupe_*` |
| Congé de surface | ✅ | `surface_fillet` | `p48_conge_surface` |
| Supprimer des faces (surface ou solide, trou refermé) | ✅ | `surface_delete_faces`, `add_delete_face` | `p48_supprimer_faces`, `p49_supprimer_face_solide` |
| Remplacer une face du solide | ✅ | `add_replace_face` | `p49_remplacer_*` |
| Ligne de séparation (scinder des faces) | ✅ | `surface_split` | `p48_ligne_separation` |

## Courbes

| Commande | État | Op moteur | Selftest |
|---|---|---|---|
| Esquisse 3D, mode d'édition : lignes en chaîne, splines, points ; points partagés, ou liés à la pièce (ils la suivent) ; Tab change le plan de clic ; près d'un axe, la ligne s'y cale (trait de couleur) et garde la relation « le long de X/Y/Z » ; cotes de longueur, de distance et d'angle affichées dans la vue (double-clic pour changer la valeur) ; splines à poignées de tangente (toutes visibles dès que la spline est choisie, Alt : un seul côté, longueurs en %) ; tout tenu par un solveur 3D (même calcul moteur et client), conflits refusés ; Ctrl+Z / Ctrl+Y dans l'esquisse ; réédition par double-clic dans l'arbre ; sert de trajectoire de balayage | ✅ | `add_sketch3d`, `edit_sketch3d` ; calcul `sketch3dmath` | `p70_esquisse3d`, `p70_suit_et_balaie`, `test_sketch3dmath`, `sketch3dmath.test` |
| Spline 3D (spline ou polyligne, règles axe / angle / longueur, solveur global, points liés) | ✅ | `add_curve3d`, `edit_curve3d` | `p46_spline_points`, `p46_esquisse3d_*` |
| Éditer la spline 3D dans la vue : tirer ses points (plan de clic), poignées de tangente sur tous les points (Alt : un seul côté ; longueurs en %), Ctrl+clic pour un point de plus (forme gardée), Suppr, polygone de contrôle (pôles à tirer), peigne de courbure, simplifier, lisser, libérer les poignées | ✅ | `edit_curve3d` (`tangents`), `curve_poles`, `curve_move_pole` | `p69_poignees`, `p69_poles` |
| Courbe par coordonnées XYZ | ✅ | `add_curve3d` — coordonnées tapées dans le panneau | `p46_spline_points` |
| Courbe par points de la pièce | ✅ | `add_curve3d` — points liés (⛓) à des sommets ou centres | `p46_esquisse3d_angle_lien` |
| Hélice et spirale | ✅ | `curve_helix` | `p50_helice` |
| Courbe composite | ✅ | `curve_composite` | `p48_courbe_composite` |
| Courbe projetée sur une surface | ✅ | `curve_project` | `p48_courbe_projetee` |
| Courbe d'intersection | ✅ | `curve_intersection` | `p48_courbe_intersection` |

## Hors périmètre (assumé)

Ces commandes relèvent d'autres domaines ; elles ne comptent pas dans
« tout le surfacique ».

- Analyses de qualité de surface (zébrures, courbure, déviation) — onglet
  Évaluer, chantier séparé.
- Maillage et numérisation (surfaces depuis un nuage de points ou un STL).
- Tôlerie, moules (plan de joint, surfaces d'arrêt) : fonctions
  spécialisées à traiter après le cœur pièce (voir le cap « mini-SolidWorks
  propre »).

## Comportements à connaître

- Forme libre : une même fonction déforme autant de faces qu'on veut —
  chaque point poussé agit sur la face où il est posé, les grilles de pôles
  de toutes les faces s'affichent ensemble ; les faces non touchées restent
  telles quelles, le tout recousu. La taille de grille se change aussi en
  réédition : chaque pôle réglé garde sa place relative sur sa face.
- Aplatir : le patron donne sa déformation mesurée (écart d'aire et de
  longueur du contour, en %, double-clic dans l'arbre). Elle est nulle
  sur une face développable (plan, cylindre, cône) ; sur une face à double
  courbure, le patron s'étire forcément pour se mettre à plat et le
  chiffre dit de combien — le déroulé (moindres carrés conformes) répartit
  cet étirement au mieux.
- Coudre : pas d'objet paramétrique natif dans FreeCAD 1.1 — la peau
  cousue est recalculée depuis ses sources à chaque reconstruction.
