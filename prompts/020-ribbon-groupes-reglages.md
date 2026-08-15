# P020 — Ribbon : sous-catégories nommées + icônes avec/sans texte (réglages)

Deux demandes utilisateur sur le ruban (CommandManager).

## 1. Grouper les boutons en sous-catégories

Aujourd'hui chaque onglet est une rangée plate de boutons séparés par des
`div.sep`. Passer à des groupes nommés façon SolidWorks : chaque groupe est
un bloc vertical — la rangée de boutons en haut, le nom du groupe en
petit libellé centré dessous, un filet vertical entre les groupes.

Découpage (onglet Fonctions) :

- **Esquisse** : Esquisse, Plan de référence ;
- **Corps** : Corps, Combiner ;
- **Fonctions** : Bossage extrudé, Révolution, Enlèvement de matière,
  Enlèv. révolution, Assistant de perçage, Lissage, Balayage, Hélice,
  Texte ;
- **Habillage** : Congé, Chanfrein, Coque, Dépouille ;
- **Répétitions** : Rép. linéaire, Rép. circulaire, Symétrie.

Onglet Esquisse : regrouper de la même façon (par exemple **Contours** /
**Outils** / **Contraintes** — suivre l'organisation actuelle des boutons,
ne pas déplacer de fonctionnalité). Onglets Surfaces et Assemblage : un
groupe par famille existante. Le contenu des groupes est du HTML statique
dans `app/index.html` + CSS dans la feuille existante — pas de JS de
génération.

Aucun id de bouton ne change (les tests navigateur et les bindings
`features.js`/`main.js` reposent dessus). Aucun bouton ajouté ni retiré.

## 2. Icônes avec ou sans texte — menu réglages

- Nouveau bouton « Réglages » (icône engrenage, `title` en français) à
  droite de la barre d'onglets, qui ouvre un petit menu (même style que
  le menu contextuel existant) avec pour l'instant une seule entrée :
  **Libellés du ruban** : « Icônes et texte » / « Icônes seules ».
- « Icônes seules » masque le texte des boutons du ruban en CSS (classe
  sur `body`, par exemple `body.ribbon-icons-only`), les `title`
  existants servent d'info-bulle. Les boutons texte-seuls actuels
  (Autotest, Mesurer…) gardent leur texte — ne masquer que le texte des
  boutons qui ont une icône.
- Persistance : `localStorage` clé `freesolid.ribbonLabels`, relue au
  chargement. Valeur par défaut : icônes et texte (comportement actuel).
- Le menu réglages est le point d'accueil des futurs réglages : structure
  simple, extensible, pas de framework.

## Validation

- `node --check` sur chaque JS modifié ; `python3 -m pytest tests/ -q`
  (rien côté moteur, la suite doit rester verte).
- Scénario navigateur : vérifier avec le harnais existant
  (`scripts/smoke/`) que les 22 panneaux s'ouvrent toujours (les ids
  n'ont pas bougé) et qu'aucune erreur console n'apparaît en basculant
  « Icônes seules » puis retour.
- Commit(s) préfixés `[P020]`. Ne pas toucher `app/vendor/`. Français,
  vocabulaire SolidWorks 2025.
