# P025 — Propriétés d'entité d'esquisse dans la barre latérale

## Contexte

En mode esquisse, la sélection d'entités existe déjà (outil
Sélectionner, jusqu'à 8 entités, surbrillance accent via
`selectedMaterial`) et le bouton « Relations » (`sk-relations`) liste
les contraintes d'UNE entité sélectionnée, à la demande. La demande
utilisateur, geste SolidWorks : sélectionner une entité doit ouvrir
**automatiquement** ses propriétés dans la barre latérale
(PropertyManager), sans passer par un bouton.

## Mission — `app/sketch.js` (et `app/panel.js` si besoin)

### 1. Panneau automatique à la sélection d'UNE entité

Quand `mode.selection` passe à exactement une entité (clic outil
Sélectionner), ouvrir dans le PropertyManager un panneau de propriétés
(pattern existant du panneau infos d'esquisse P019 : `noApply: true` +
`actions`) :

- **Titre** : type en français — Ligne, Cercle, Arc, Spline, Ellipse,
  Polyligne (mêmes libellés que le reste de l'app).
- **Propriétés** (lecture seule, valeurs en mm arrondies au 1/100) :
  - ligne : longueur, départ (x, y), arrivée (x, y) ;
  - cercle : centre (x, y), rayon, diamètre ;
  - arc : centre (x, y), rayon, angle balayé ;
  - spline / polyligne : nombre de points ;
  - ellipse : centre, grand rayon, petit rayon.
  - note fixe : « Pour piloter une valeur : Cotation intelligente (D). »
    (l'édition numérique directe passe par les cotes — ne pas
    implémenter d'édition de coordonnées ici).
- **Relations** : la liste des contraintes de l'entité avec suppression
  par ligne — réutiliser la logique du bouton `sk-relations` (même
  appel `sketch_constraints`, même geste de suppression). Le bouton
  du ruban reste en place (autre porte d'entrée, même contenu).
- **Actions** :
  - « Construction » : bascule `sketch_toggle_construction` (l'état
    actuel affiché) ;
  - « Supprimer » : `sketch_delete_geo` (même confirmation que le
    chemin existant s'il y en a une, sinon direct comme la touche
    Suppr).

### 2. Cycle de vie

- Sélection de 2+ entités : le panneau se ferme (le compteur de la
  barre de statut existant suffit — les gestes multi-entités sont les
  relations du ruban).
- Désélection (clic dans le vide, Échap, changement d'outil), fin du
  drag qui désélectionne, suppression de l'entité, sortie du mode
  esquisse : le panneau se ferme. Utiliser le remplacement/fermeture
  silencieux de panel.js (P019) pour ne pas déclencher d'onCancel
  parasites.
- Pendant un drag de point/arête de l'entité sélectionnée : ne pas
  rouvrir/rafraîchir le panneau à chaque frame — le rafraîchir une
  fois au pointerup (les valeurs affichées doivent alors être à jour).
- Le panneau ne doit pas voler le focus clavier (les raccourcis
  d'esquisse L/R/C/D… continuent de marcher) — même discipline que les
  panneaux existants.

### 3. Validation

- `node --check` sur chaque JS modifié ; `python3 -m pytest tests/ -q`
  (rien côté moteur attendu — si un champ manque dans `sketch_state`
  pour une propriété, l'ajouter est acceptable, avec le selftest qui
  suit).
- `scripts/smoke/smoke.js` : un pas dans l'esquisse existante — clic
  sur une ligne du rectangle, vérifier que le panneau affiche
  « Ligne » et une longueur non vide ; vérifier qu'une 2e entité
  sélectionnée ferme le panneau ; Échap, la suite inchangée.
- Commit(s) préfixés `[P025]`. Ne pas toucher `app/vendor/`. Français,
  vocabulaire SolidWorks 2025.
