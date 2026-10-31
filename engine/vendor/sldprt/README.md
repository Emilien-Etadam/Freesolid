# sldprt (OpenSW) — repris tel quel

Source : [Emilien-Etadam/OpenSW](https://github.com/Emilien-Etadam/OpenSW),
dossier `src/sldprt/`, commit `3f3db0041a4110bca89b9b60128d233e99b4efa8`
(« Initial public release »). Même auteur que FreeSolid, même licence :
**AGPL-3.0-only** (voir `LICENSE` à la racine). Les travaux tiers dont le
lecteur s'est inspiré sont crédités dans `NOTICE`, recopié avec lui.

Ce qu'il fait ici : `engine/foreign.py` lui confie les `.sldprt`, `.x_t` et
`.x_b`. Il décode la partition Parasolid en pur Python et écrit un STEP, que
FreeCAD relit. Seule la géométrie morte entre ; l'arbre de fonctions du
fichier n'est jamais rejoué. Aucun fichier de schéma Parasolid n'est livré :
les faits intégrés (`builtin.py`, `schema_facts.py`) suffisent.

Seule dépendance facultative : `olefile`, pour les anciens `.SLDPRT` au
format OLE. Sans elle, ces fichiers-là sont refusés avec un message qui le
dit ; les autres s'ouvrent.

**Aucune modification locale.** Une correction se fait dans OpenSW, puis on
recopie le dossier entier et on met à jour le commit ci-dessus :

```bash
rm -r engine/vendor/sldprt/{*.py,xt}
cp -r <OpenSW>/src/sldprt/. engine/vendor/sldprt/
cp <OpenSW>/NOTICE engine/vendor/sldprt/NOTICE
find engine/vendor/sldprt -name __pycache__ -prune -exec rm -rf {} +
```

Les modules `xt/edit.py` et `xt/write.py` (écriture Parasolid) ne servent
pas à FreeSolid : ils restent pour que la copie reste identique au dépôt
source.
