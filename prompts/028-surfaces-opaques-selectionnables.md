# P028 — Surfaces : rendu opaque sélectionnable, et au-dessus de la barre de reprise

Deux demandes utilisateur (capture à l'appui).

## 1. La surface se voit et se clique comme une face classique

Aujourd'hui : rendu translucide turquoise, `raycast` neutralisé — pas
sélectionnable au viewport. Attendu SolidWorks : **gris opaque comme les
faces du solide**, cliquable.

### Moteur — `engine/kernel.py`, `tessellate`

Le champ `surfaces` du maillage devient une liste **par surface** (même
principe que `sketches` de P024) :

```
"surfaces": [{"name", "label", "positions": […], "indices": […]}]
```

(Actuellement : un seul buffer combiné. Consommateur unique = notre
client, pas de compat à garder ; adapter le selftest qui lirait ce
champ.) Les courbes 3D (`curves`) ne changent pas.

### Client — `app/main.js`

- **Rendu** : un mesh par surface, matériau opaque gris — même teinte de
  base que le solide (`baseMaterial`), `DoubleSide` (une surface est
  ouverte, ses deux côtés se voient), éclairage normal. Dans
  `volumesGroup` (masqué en mode esquisse). Conventions mémoire du
  fichier (`ownedMaterial`/dispose).
- **Survol** : teinte hover (même logique visuelle que les faces du
  solide — un matériau hover par surface suffit, pas besoin de groupes),
  curseur pointer, label de la surface affiché dans `#pick` comme
  « Face N » l'est aujourd'hui.
- **Clic** : sélectionne la surface — strictement le même chemin que le
  clic d'arbre actuel (`notifyPick("surface")` absorbé par
  Coudre/Épaissir/Balayage, sinon sélection visible : teinte accent +
  ligne `.sel` dans l'arbre + statut avec le label). Re-clic = toggle.
  Double-clic dans le viewport = `editSurface` (comme l'arbre).
- **Priorité de visée** : au plus proche du regard — une surface devant
  une face du solide gagne, une face devant une surface gagne (comparer
  les distances des hits, comme faces vs arêtes aujourd'hui). Les
  esquisses libres (P024) gardent leur priorité de proximité en pixels.
- La désélection existante (clic dans le vide, après fonction) couvre ce
  nouveau chemin — même état que la sélection d'arbre, rien à dupliquer.

## 2. Dans l'arbre : la surface au-dessus de la barre de reprise

Constaté : « Surface extrudée » s'affiche SOUS la barre alors que la
barre est en bout de chaîne — elle paraît hors historique/grisée. Les
surfaces ne sont pas dans la chaîne PartDesign : elles ne sont jamais
« reculées ».

Règle de rendu (`renderActiveBodyContents`) : les lignes surfaciques de
l'historique se placent **toujours au-dessus de la barre**. Concrètement,
en construisant la liste chronologique : les lignes de chaîne (fonctions
PartDesign + esquisses) s'ordonnent par `order` avec la barre après le
Tip comme aujourd'hui ; toute ligne surfacique dont l'`order` la
placerait après la barre est **hissée juste avant la barre** (l'ordre
relatif entre surfaces est conservé). Barre en bout de chaîne = barre
tout en bas, surfaces comprises.

## Validation

- `python3 -m pytest tests/ -q`, `node --check` sur chaque JS modifié.
- Selftest : adapter les indicateurs existants qui lisent
  `mesh["surfaces"]` (p12) au nouveau format — l'entrée porte le bon
  `name` et des positions non vides.
- `scripts/smoke/smoke.js` : dans le pas surfacique existant, après la
  création : (a) cliquer la surface dans le viewport → statut/`#pick`
  montre son label et l'arbre porte une `.sel` sur sa ligne ;
  (b) vérifier que la ligne « Surface extrudée » de l'historique est
  au-dessus de la barre (`li.rollback` est après elle dans le DOM) et
  n'a pas la classe `rolled-back`.
- Smoke complet : tous les pas existants restent verts.
- Commit(s) préfixés `[P028]`. Ne pas toucher `app/vendor/`. Français,
  vocabulaire SolidWorks 2025.
