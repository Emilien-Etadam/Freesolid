# prompts/ — le canal Claude → Cursor

Fonctionnement :

1. Claude écrit un prompt numéroté ici (`LNNN-sujet.md`) et le pousse.
2. Cursor ouvre le prompt, exécute la mission **telle qu'écrite**, produit
   le livrable demandé, commit et pousse.
3. Claude vérifie (relecture, selftest, pytest) et écrit le prompt suivant.

Règles pour Cursor :

- Le livrable et ses contraintes sont définis dans le prompt — ne pas
  élargir le périmètre, ne pas « améliorer » au passage.
- Ne jamais toucher `app/vendor/` (code tiers vendu tel quel).
- Tout texte visible par l'utilisateur est en français, vocabulaire
  SolidWorks 2025.
- Valider avant de pousser : `python3 -m pytest tests/ -q` et
  `node --check` sur chaque JS modifié. Le selftest complet
  (`scripts/run-selftest.py`) nécessite FreeCAD — le lancer si disponible,
  sinon le signaler dans le commit.
- Un prompt = un commit (ou une petite série cohérente), message en
  français, préfixé du numéro du prompt : `[P001] …`, `[N001] …`.

## Les séries

La lettre dit à quel chantier le prompt appartient ; la numérotation
repart de 1 pour chaque série.

| Série | Chantier | Référence |
|---|---|---|
| `P` | l'app — fonctions de CAO, UI, moteur | — |
| `N` | nœuds — arêtes de dépendance, vue graphe, fonction graphe, nœud Python | [`docs/nodes-macros.md`](../docs/nodes-macros.md) |
