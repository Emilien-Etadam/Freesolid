# FreeSolid App — architecture cible

*Nouvelle interface, moteur conservé.* L'interface est du web (esthétique
Plasticity, FeatureManager SolidWorks) ; la géométrie, les documents, le
solveur et l'historique restent ceux de FreeCAD, exécuté **sans interface**.

```
┌───────────────────────────────────────────────┐
│  app/ — navigateur ou Tauri                   │
│  Three.js (viewport) · arbre SW · panneaux    │
└───────────────┬───────────────────────────────┘
                │ HTTP JSON (M0) → WebSocket (M2)
┌───────────────┴───────────────────────────────┐
│  engine/ — FreeCAD headless (freecadcmd)      │
│  documents .FCStd · PartDesign · Sketcher     │
│  solveur planegcs · toponaming fix · STEP     │
└───────────────────────────────────────────────┘
```

## Pourquoi cette coupe

- **Tout ce que l'utilisateur voit** est à nous : CSS, pas Qt. Le look
  Plasticity est une feuille de style, l'arbre SolidWorks est un `<ul>`.
- **Tout ce qui fait qu'une CAO est une CAO** est hérité : recompute
  incrémental (l'avantage décisif sur SindriCAD), gros arbres, fichiers
  `.FCStd` ouvrables dans FreeCAD standard — la porte de sortie de
  l'utilisateur reste toujours ouverte.

La coupe se lit dans les deux sens. Comment trancher un cas mixte — le
besoin est à nous, la capacité manquante est à FreeCAD — et ce qu'on fait
des manques ainsi découverts : [`amont-freecad.md`](amont-freecad.md).

## Le protocole (M0)

Transport : HTTP JSON en localhost, zéro dépendance des deux côtés
(`http.server` côté Python, `fetch` côté JS). WebSocket seulement quand le
streaming le justifiera (M2 : aperçus pendant le drag).

Opérations M0 : `ping`, `selftest`, `new_part`, `add_rect_sketch`,
`add_pad`, `set_param`, `get_tree`, `tessellate`. Schémas dans
`engine/protocol.py`, seule source de vérité, testée sans FreeCAD.

## Les deux risques identifiés — et leur traitement

1. **Le picking** (cliquer une face à l'écran → retrouver la face OCCT).
   Traité *par construction* : la tessellation part face par face, chaque
   face devient un groupe indexé du maillage (`groups[] = {faceId, start,
   count}`). Le raycast Three.js renvoie l'index du triangle → le groupe →
   le `faceId` moteur. Pas d'heuristique, pas de tolérance.
2. **La boucle d'esquisse** (drag d'un point → solveur → retour < 50 ms).
   M0 l'esquive (rectangle piloté par cotes), M2 l'attaque côté serveur,
   M3 la déporte dans le navigateur via planegcs-wasm (déjà porté par
   Salusoft89) — le serveur restant la vérité au lâcher de souris.

## Jalons

| | Contenu | Critère de sortie |
|---|---|---|
| **M0** | pièce démo : esquisse rectangle cotée → Pad → affichage, arbre, édition de la profondeur, picking de faces | le paramétrique se voit : changer 10 → 25 mm reconstruit la pièce |
| M1 | Pocket, Congé/Chanfrein sur face piquée, sauvegarde .FCStd, ouverture de fichiers existants | une vraie petite pièce de bout en bout |
| M2 | éditeur d'esquisse v1 (lignes, cercles, contraintes de base, cotation), WebSocket | le rectangle n'est plus une primitive magique |
| M3 | solveur client (planegcs-wasm), sélection avancée, répétitions | le drag d'esquisse est fluide |
| M4 | assemblage (solveur Ondsel via le moteur), mise en plan différée | à re-scoper arrivé là |

## Exécution chez l'utilisateur (M0)

Le moteur tourne avec le Python de l'AppImage déjà installée — aucun
environnement à monter :

```bash
freecadcmd engine/server.py
# puis ouvrir http://localhost:8787
```

Le serveur sert aussi l'UI statique (`app/`) : un seul processus, un onglet.

## Ce que cette architecture ne promet pas

Les limites structurelles du moteur restent : un Body = un solide contigu
(pas de multicorps), et la qualité du recompute est celle de FreeCAD. On
change la peau et la main ; pas les os.
