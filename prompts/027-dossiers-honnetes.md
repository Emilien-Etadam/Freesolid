# P027 — FeatureManager : dossiers honnêtes (compteurs réels, dépli auto)

## Contexte — retour utilisateur (vérifié sur capture)

Après une extrusion surfacique sur une pièce neuve :

1. La fonction créée est invisible : elle est dans « Corps
   surfaciques (1) », dossier replié par défaut (règle P021). Une
   fonction qu'on vient de créer doit apparaître immédiatement.
2. « Corps volumiques (1) » est faux : il compte le conteneur
   PartDesign::Body créé avec la pièce, même vide. SolidWorks compte
   les corps **solides** — ici ce devrait être (0).

## Mission

### 1. Moteur — `engine/kernel.py`, `get_tree`

Chaque entrée de `bodies` gagne `has_solid: true|false` — vrai si le
corps porte un solide réel : `Shape` non nul, non vide, avec au moins
un `Solids`. (Un corps dont le Tip est reculé tout en haut → false ;
après tip_to_end → true : le drapeau suit l'état affiché.)

### 2. Client — `app/main.js`, compteurs

- « Corps volumiques (N) » : N = nombre de corps avec `has_solid`.
- Les corps sans solide restent listés dans le dossier (il faut pouvoir
  activer/renommer un corps vide) mais leur ligne est grisée avec le
  suffixe « — vide » à la place du compteur d'éléments.
- « Corps surfaciques (N) » et « Équations (N) » : déjà exacts, ne pas
  toucher.

### 3. Client — dépli automatique à la création

À chaque `renderTree`, comparer les compteurs au rendu précédent
(mémoriser les précédents dans l'état de session, à côté de
`folderState`) : si le compteur d'un dossier **augmente**, forcer son
dépli (`folderState[clé] = true`). Ainsi :

- première surface créée → « Corps surfaciques » s'ouvre et montre la
  nouvelle fonction ;
- premier solide (bossage) → « Corps volumiques » passe (0)→(1) et
  s'ouvre ;
- première variable → « Équations » s'ouvre.

Un repli manuel de l'utilisateur reste respecté tant que le compteur
n'augmente pas à nouveau. Une baisse de compteur (suppression) ne
change rien au pli.

### 4. Tests

- Selftest : dans l'étape p12 (surfacique), indicateur
  `p12_body_not_solid` — sur la pièce surfacique sans bossage, l'entrée
  bodies a `has_solid` faux ; et dans m0, `m0_body_solid` — après le
  pad, `has_solid` vrai.
- `scripts/smoke/smoke.js` : au chargement d'une pièce neuve (juste
  après la première esquisse, avant le bossage), le dossier affiche
  « Corps volumiques (0) » ; après le bossage, « (1) » et le dossier
  est déplié (la ligne du corps est visible). Adapter les pas existants
  qui lisent les libellés de dossiers si besoin.
- `python3 -m pytest tests/ -q`, `node --check` sur chaque JS modifié.

## Contraintes

Commit(s) préfixés `[P027]`. Ne pas toucher `app/vendor/`. Français,
vocabulaire SolidWorks 2025.
